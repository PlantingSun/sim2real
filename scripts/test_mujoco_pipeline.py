#!/usr/bin/env python3
# test_mujoco_pipeline.py — Step 3: 仿真全流程测试
import sys, time, threading, numpy as np, mujoco
from driver.mujoco_driver import MujocoDriver
from driver.driver_base import MotorCommand
from policy.controller_go2w import ControllerGo2w
from config.go2w_config import CTRL, DDS

DEFAULT_SCENE = "/home/robot/test_com_ws/src/descriptions/go2w_description/mjcf/go2w_scene.xml"

def main():
    scene = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCENE
    cmd_vx = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    cmd_vy = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    cmd_wz = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    print(f"=== Step 3: 仿真全流程 ===\n场景: {scene}  vx={cmd_vx}")

    driver = MujocoDriver(scene, data_hz=DDS.RATE_HZ)
    if not driver.initialize(): return

    controller = ControllerGo2w("models/go2w/model_700.pt")
    controller.reset()
    cmd_vel = np.array([cmd_vx, cmd_vy, cmd_wz], dtype=np.float32)

    sync_thread = threading.Thread(target=driver._sync_loop)
    sync_thread.start()
    dt = driver._model.opt.timestep
    steps_per_data = int(driver._dt_data / dt)
    step_count = 0

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
                        driver.send_command(MotorCommand(positions=p, velocities=v, kp=kp, kd=kd))
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
