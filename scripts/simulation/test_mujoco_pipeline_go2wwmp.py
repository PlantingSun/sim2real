#!/usr/bin/env python3
"""在 MuJoCo 中验证 go2wwmp 的深度图 → WMP → MotorCommand 链路。"""

import argparse
import threading
import time

import mujoco
import numpy as np

from config.go2w_config import CTRL, DDS
from config.paths import GO2W_SCENE, model_path
from driver.driver_base import RobotState
from driver.mujoco_driver import MujocoDriver
from policy.controller_go2wwmp import ControllerGo2wWMP


DEFAULT_SCENE = str(GO2W_SCENE)
DEFAULT_MODEL = model_path("go2wwmp/model_1750.pt")
TRAINED_CAMERA_POS = np.array([0.34, -0.0375, 0.09], dtype=np.float64)
PRINT_FIRST_POLICY_FRAMES = 5
DEPTH_DISPLAY_INTERVAL = 5  # 50 Hz policy / 5 = approximately 10 Hz display


def initialize_standing_pose(driver: MujocoDriver) -> None:
    """在首次按空格启动前，把 MuJoCo 状态放到策略初始站姿。"""
    if driver._joint_num != CTRL.NUM_ACTIONS:
        raise RuntimeError(
            f"MuJoCo actuator 数量错误: {driver._joint_num}, expected {CTRL.NUM_ACTIONS}"
        )

    stand_qpos = driver._model.key("stand").qpos
    if not np.allclose(stand_qpos[-driver._joint_num :], CTRL.INITIAL_JOINTS_POS):
        raise RuntimeError("XML stand keyframe 与 CTRL.INITIAL_JOINTS_POS 不一致")
    driver._data.qpos[:] = stand_qpos
    driver._data.qvel[:] = 0.0
    mujoco.mj_forward(driver._model, driver._data)
    driver._viewer.sync()
    print(f"[MujocoDriver] 初始站姿已加载: base_z={driver._data.qpos[2]:.3f} m")


def render_depth(renderer, driver: MujocoDriver, camera_id: int) -> np.ndarray:
    """读取 MuJoCo 深度相机的米制深度，并转换为 WMP 的 [0, 1] 输入。"""
    renderer.update_scene(driver._data, camera=camera_id)
    depth_m = np.asarray(renderer.render(), dtype=np.float32)
    if depth_m.shape != (64, 64):
        raise RuntimeError(f"MuJoCo 深度图尺寸错误: {depth_m.shape}")
    depth_m = np.nan_to_num(depth_m, nan=2.0, posinf=2.0, neginf=0.0)
    return np.clip(depth_m, 0.0, 2.0) / 2.0


def configure_depth_camera(driver: MujocoDriver, camera_id: int) -> None:
    """把 MuJoCo 深度相机固定到已确认的 D435i 基座坐标。"""
    scene_pos = driver._model.cam_pos[camera_id].copy()
    driver._model.cam_pos[camera_id] = TRAINED_CAMERA_POS
    print(
        "[DepthCamera] 使用已确认的 D435i 位置: "
        f"{TRAINED_CAMERA_POS.tolist()}（场景原位置: {scene_pos.tolist()}）"
    )
    mujoco.mj_forward(driver._model, driver._data)


def show_depth_image(cv2_module, depth_normalized: np.ndarray, frame_index: int) -> bool:
    """以黑白灰度窗口显示归一化深度；返回 False 表示用户请求退出。"""
    depth_u8 = np.rint(np.clip(depth_normalized, 0.0, 1.0) * 255.0).astype(np.uint8)
    display = depth_u8
    cv2_module.putText(
        display,
        f"depth 10 Hz | frame {frame_index}",
        (6, 18),
        cv2_module.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 255, 255),
        1,
        cv2_module.LINE_AA,
    )
    cv2_module.imshow("go2wwmp depth", display)
    key = cv2_module.waitKey(1) & 0xFF
    return key not in (27, ord("q"))


def print_motor_command(command) -> None:
    """打印一条 DDS 顺序 MotorCommand，便于人工检查缩放和映射。"""
    print("\nMotorCommand 数据 (DDS 顺序):")
    print(f"{'i':>3s}  {'pos':>10s}  {'vel':>10s}  {'kp':>6s}  {'kd':>6s}")
    for index in range(CTRL.NUM_ACTIONS):
        print(
            f"{index:3d}  {command.positions[index]:10.4f}  "
            f"{command.velocities[index]:10.4f}  {command.kp[index]:6.1f}  "
            f"{command.kd[index]:6.1f}"
        )


def run_check_only(controller: ControllerGo2wWMP) -> None:
    """不启动 MuJoCo viewer，检查模型、观测、world model 和动作维度。"""
    state = RobotState(
        joint_positions=CTRL.INITIAL_JOINTS_POS.copy(),
        joint_velocities=np.zeros(CTRL.NUM_ACTIONS, dtype=np.float32),
        imu_quat=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        imu_gyro=np.zeros(3, dtype=np.float32),
        imu_accel=np.array([0.0, 0.0, -9.81], dtype=np.float32),
    )
    depth = np.full((64, 64), 0.5, dtype=np.float32)
    action, command = controller.step(state, np.zeros(3, dtype=np.float32), depth)
    print(
        f"[CHECK ONLY] action shape={action.shape}, range=[{action.min():.4f}, {action.max():.4f}]"
    )
    print_motor_command(command)
    print("[CHECK ONLY] WMP 模型和单步 pipeline 通过；没有启动 MuJoCo 或连接机器人。")


def main() -> None:
    parser = argparse.ArgumentParser(description="go2wwmp WMP MuJoCo pipeline test")
    parser.add_argument("scene", nargs="?", default=DEFAULT_SCENE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--vx", type=float, default=0.0)
    parser.add_argument("--vy", type=float, default=0.0)
    parser.add_argument("--vyaw", type=float, default=0.0)
    parser.add_argument("--frames", type=int, default=0, help="策略帧数；0 表示按 viewer 运行")
    parser.add_argument("--check-only", action="store_true", help="只加载网络并执行一帧，不启动 viewer")
    parser.add_argument("--no-depth-display", action="store_true", help="不打开 OpenCV 深度窗口")
    args = parser.parse_args()

    print("=== go2wwmp WMP MuJoCo 全流程 ===")
    print(f"场景: {args.scene}")
    print(f"模型: {args.model}")
    print(f"速度: vx={args.vx} vy={args.vy} vyaw={args.vyaw}")

    controller = ControllerGo2wWMP(args.model)
    if args.check_only:
        run_check_only(controller)
        return

    driver = MujocoDriver(args.scene, data_hz=DDS.RATE_HZ)
    if not driver.initialize():
        return

    renderer = None
    sync_thread = None
    cv2_module = None
    quit_requested = False
    try:
        initialize_standing_pose(driver)
        camera_id = driver._model.camera("depth_camera").id
        configure_depth_camera(driver, camera_id)
        renderer = mujoco.Renderer(driver._model, height=64, width=64)
        renderer.enable_depth_rendering()
        if not args.no_depth_display:
            try:
                import cv2 as cv2_module
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "深度画面显示需要 OpenCV，请先在当前 Python 环境安装 cv2，"
                    "或使用 --no-depth-display 只验证 MuJoCo pipeline。"
                ) from exc
            cv2_module.namedWindow("go2wwmp depth", cv2_module.WINDOW_NORMAL)
        command = np.array([args.vx, args.vy, args.vyaw], dtype=np.float32)

        sync_thread = threading.Thread(target=driver._sync_loop)
        sync_thread.start()
        steps_per_data = int(driver._dt_data / driver._model.opt.timestep)
        policy_divider = DDS.RATE_HZ // CTRL.POLICY_RATE_HZ
        step_count = 0
        policy_count = 0

        print("空格：暂停/继续；Ctrl+C：退出。")
        while driver._viewer.is_running():
            start = time.perf_counter()
            with driver._viewer.lock():
                if not driver._pause:
                    for _ in range(steps_per_data):
                        if driver._has_cmd:
                            driver._apply_command(driver._pending_cmd)
                        mujoco.mj_step(driver._model, driver._data)
                    step_count += 1
                    if step_count % policy_divider == 0:
                        state = driver.get_state()
                        depth = render_depth(renderer, driver, camera_id)
                        action, motor_command = controller.step(state, command, depth)
                        driver.send_command(motor_command)
                        policy_count += 1
                        if (
                            cv2_module is not None
                            and policy_count % DEPTH_DISPLAY_INTERVAL == 0
                            and not show_depth_image(cv2_module, depth, policy_count)
                        ):
                            quit_requested = True
                        if policy_count <= PRINT_FIRST_POLICY_FRAMES:
                            print(
                                f"\n[POLICY FRAME {policy_count}] "
                                f"action=[{action.min():.3f}, {action.max():.3f}]"
                            )
                            print_motor_command(motor_command)
                        if args.frames > 0 and policy_count >= args.frames:
                            quit_requested = True
                else:
                    mujoco.mj_forward(driver._model, driver._data)

            if quit_requested:
                break
            elapsed = time.perf_counter() - start
            if elapsed < driver._dt_data:
                time.sleep(driver._dt_data - elapsed)
    except KeyboardInterrupt:
        pass
    finally:
        driver._running = False
        if sync_thread is not None:
            sync_thread.join(timeout=1.0)
        if renderer is not None:
            renderer.close()
        if cv2_module is not None:
            cv2_module.destroyWindow("go2wwmp depth")
        driver.shutdown()


if __name__ == "__main__":
    main()
