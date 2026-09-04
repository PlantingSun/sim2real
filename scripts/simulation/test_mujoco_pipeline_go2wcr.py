#!/usr/bin/env python3
"""在 MuJoCo 中验证 go2wcr 的 driver → policy → MotorCommand 链路。"""

import argparse
import threading
import time
from config.paths import GO2W_SCENE, model_path

# Jetson 上先加载 PyTorch，避免 MuJoCo 的 OpenMP 占用 static TLS。
import torch
import mujoco
import numpy as np

from config.go2w_config import CTRL, DDS
from driver.mujoco_driver import MujocoDriver
from policy.controller_go2wcr import ControllerGo2wCR


DEFAULT_SCENE = str(GO2W_SCENE)
PRINT_FIRST_POLICY_FRAMES = 5


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
    parser.add_argument("--model", default=model_path("go2wcr/model_1499.pt"))
    parser.add_argument("--vx", type=float, default=0.0)
    parser.add_argument("--vy", type=float, default=0.0)
    parser.add_argument("--vyaw", type=float, default=0.0)
    parser.add_argument("--auto-start", action="store_true")
    parser.add_argument("--frames", type=int, default=0, help="达到该 policy 帧数后退出；0 表示持续运行")
    args = parser.parse_args()

    command = np.array([args.vx, args.vy, args.vyaw], dtype=np.float32)
    if np.any(np.abs(command) > CTRL.COMMAND_LIMITS):
        parser.error(f"速度指令超过限制 {CTRL.COMMAND_LIMITS.tolist()}")
    if args.frames < 0:
        parser.error("frames 不能为负数")

    print("=== Step CRRL-2: go2wcr MuJoCo 全流程 ===")
    print(f"场景: {args.scene}")
    print(f"速度: vx={args.vx} vy={args.vy} vyaw={args.vyaw}")

    driver = MujocoDriver(args.scene, data_hz=DDS.RATE_HZ)
    if not driver.initialize():
        return
    driver.reset_to_stand()

    controller = ControllerGo2wCR(args.model)
    controller.reset()
    if args.auto_start:
        driver._pause = False

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
                        if args.frames and policy_count >= args.frames:
                            break
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
