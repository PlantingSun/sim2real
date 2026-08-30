#!/usr/bin/env python3
"""在 MuJoCo 中验证 go2wcr 的 driver → policy → MotorCommand 链路。"""

import argparse
import threading
import time

import mujoco
import numpy as np

from config.go2w_config import CTRL, DDS
from driver.mujoco_driver import MujocoDriver
from policy.controller_go2wcr import ControllerGo2wCR


DEFAULT_SCENE = "/home/robot/test_com_ws/src/descriptions/go2w_description/mjcf/go2w_scene.xml"
PRINT_FIRST_POLICY_FRAMES = 5


def initialize_standing_pose(driver: MujocoDriver) -> None:
    """在首次按空格启动前，把 MuJoCo 状态放到策略初始站姿。"""
    if driver._joint_num != CTRL.NUM_ACTIONS:
        raise RuntimeError(
            f"MuJoCo actuator 数量错误: {driver._joint_num}, "
            f"expected {CTRL.NUM_ACTIONS}"
        )

    # XML 已定义 stand keyframe；恢复完整 keyframe 可同时修正 base 高度和关节角度。
    stand_qpos = driver._model.key("stand").qpos
    if not np.allclose(stand_qpos[-driver._joint_num:], CTRL.INITIAL_JOINTS_POS):
        raise RuntimeError("XML stand keyframe 与 CTRL.INITIAL_JOINTS_POS 不一致")
    driver._data.qpos[:] = stand_qpos
    driver._data.qvel[:] = 0.0
    mujoco.mj_forward(driver._model, driver._data)
    driver._viewer.sync()
    print(f"[MujocoDriver] 初始站姿已加载: base_z={driver._data.qpos[2]:.3f} m")


def print_motor_command(command) -> None:
    """打印一条 DDS 顺序 MotorCommand，避免重复转换动作。"""
    print("\nMotorCommand 数据 (DDS 顺序):")
    print(f"{'i':>3s}  {'pos':>10s}  {'vel':>10s}  {'kp':>6s}  {'kd':>6s}")
    for index in range(CTRL.NUM_ACTIONS):
        print(
            f"{index:3d}  {command.positions[index]:10.4f}  "
            f"{command.velocities[index]:10.4f}  "
            f"{command.kp[index]:6.1f}  {command.kd[index]:6.1f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="go2wcr CRRL MuJoCo pipeline test")
    parser.add_argument("scene", nargs="?", default=DEFAULT_SCENE)
    parser.add_argument("--model", default="models/go2wcr/model_1499.pt")
    parser.add_argument("--vx", type=float, default=0.0)
    parser.add_argument("--vy", type=float, default=0.0)
    parser.add_argument("--vyaw", type=float, default=0.0)
    args = parser.parse_args()

    print("=== Step CRRL-2: go2wcr MuJoCo 全流程 ===")
    print(f"场景: {args.scene}")
    print(f"速度: vx={args.vx} vy={args.vy} vyaw={args.vyaw}")

    driver = MujocoDriver(args.scene, data_hz=DDS.RATE_HZ)
    if not driver.initialize():
        return
    initialize_standing_pose(driver)

    controller = ControllerGo2wCR(args.model)
    controller.reset()
    command = np.array([args.vx, args.vy, args.vyaw], dtype=np.float32)

    sync_thread = threading.Thread(target=driver._sync_loop)
    sync_thread.start()
    steps_per_data = int(driver._dt_data / driver._model.opt.timestep)
    policy_divider = DDS.RATE_HZ // CTRL.POLICY_RATE_HZ
    step_count = 0
    policy_count = 0

    print("空格：暂停/继续；Ctrl+C：退出。")
    try:
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
                        obs = controller.build_obs(state, command)
                        action = controller.compute_action(obs)
                        motor_command = controller.action_to_motor_command(action)
                        driver.send_command(motor_command)
                        policy_count += 1
                        if policy_count <= PRINT_FIRST_POLICY_FRAMES:
                            print(f"\n[POLICY FRAME {policy_count}]")
                            print_motor_command(motor_command)
                else:
                    mujoco.mj_forward(driver._model, driver._data)

            elapsed = time.perf_counter() - start
            if elapsed < driver._dt_data:
                time.sleep(driver._dt_data - elapsed)
    except KeyboardInterrupt:
        pass
    finally:
        driver._running = False
        sync_thread.join(timeout=1.0)
        driver.shutdown()


if __name__ == "__main__":
    main()
