#!/usr/bin/env python3
# test_mujoco_pipeline.py — Step 3: 仿真全流程测试
import sys, time, threading, numpy as np, mujoco
from driver.mujoco_driver import MujocoDriver
from driver.driver_base import MotorCommand
from policy.controller_go2w import ControllerGo2w
from config.go2w_config import CTRL, DDS
from config.paths import GO2W_SCENE, model_path

DEFAULT_SCENE = str(GO2W_SCENE)
PRINT_FIRST_POLICY_FRAMES = 5


def initialize_standing_pose(driver):
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


def print_motor_command(command):
    """打印一条 DDS 顺序 MotorCommand，避免重复转换动作。"""
    print("\nMotorCommand 数据 (DDS 顺序):")
    print(f"{'i':>3s}  {'pos':>10s}  {'vel':>10s}  {'kp':>6s}  {'kd':>6s}")
    for index in range(CTRL.NUM_ACTIONS):
        print(
            f"{index:3d}  {command.positions[index]:10.4f}  "
            f"{command.velocities[index]:10.4f}  "
            f"{command.kp[index]:6.1f}  {command.kd[index]:6.1f}"
        )


def main():
    scene = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCENE
    cmd_vx = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    cmd_vy = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    cmd_wz = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    print(f"=== Step 3: 仿真全流程 ===\n场景: {scene}  vx={cmd_vx}")

    driver = MujocoDriver(scene, data_hz=DDS.RATE_HZ)
    if not driver.initialize(): return
    initialize_standing_pose(driver)

    controller = ControllerGo2w(model_path("go2w/model_700.pt"))
    controller.reset()
    cmd_vel = np.array([cmd_vx, cmd_vy, cmd_wz], dtype=np.float32)

    sync_thread = threading.Thread(target=driver._sync_loop)
    sync_thread.start()
    dt = driver._model.opt.timestep
    steps_per_data = int(driver._dt_data / dt)
    step_count = 0
    policy_count = 0

    print("空格: 暂停/继续  Ctrl+C: 退出\n")
    try:
        while driver._viewer.is_running():
            t_start = time.perf_counter()
            with driver._viewer.lock():
                if not driver._pause:
                    for _ in range(steps_per_data):
                        if driver._has_cmd:
                            driver._apply_command(driver._pending_cmd)
                        mujoco.mj_step(driver._model, driver._data)
                    step_count += 1
                    if step_count % (DDS.RATE_HZ // CTRL.POLICY_RATE_HZ) == 0:
                        state = driver.get_state()
                        obs = controller.build_obs(state, cmd_vel)
                        action = controller.compute_action(obs)
                        p, v, kp, kd = controller.action_to_motor_command(action)
                        command = MotorCommand(positions=p, velocities=v, kp=kp, kd=kd)
                        driver.send_command(command)
                        policy_count += 1
                        if policy_count <= PRINT_FIRST_POLICY_FRAMES:
                            print(f"\n[POLICY FRAME {policy_count}]")
                            print_motor_command(command)
                else:
                    mujoco.mj_forward(driver._model, driver._data)
            elapsed = time.perf_counter() - t_start
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
