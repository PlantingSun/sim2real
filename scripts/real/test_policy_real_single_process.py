#!/usr/bin/env python3
"""Go2W 笔记本单进程实机基线。

控制顺序恢复自 Git 提交 64c32a0 的 ``test_policy_real.py``：DDS 与 policy 位于
同一 Python 进程，不使用 multiprocessing/Pipe。默认不记录日志时，主循环行为与该
已验证版本一致；``--log`` 只用于本轮 A/B 消融。
"""

import argparse
import signal
import sys
import time

import numpy as np
import torch

from config.go2w_config import CTRL, DDS
from config.paths import model_path
from driver.dds_driver import DdsDriver
from driver.driver_base import MotorCommand
from policy.controller_go2w import ControllerGo2w
from scripts.real.test_policy_real import (
    build_initial_hold_command,
    create_command_source,
    open_log,
    print_motor_command,
    wait_for_stage_key,
)


def main():
    parser = argparse.ArgumentParser(description="Go2W 笔记本单进程实机基线")
    parser.add_argument(
        "--control", choices=("fixed", "keyboard", "xbox"), default="fixed",
        help="速度命令来源",
    )
    parser.add_argument("--vx", type=float, default=0.0)
    parser.add_argument("--vy", type=float, default=0.0)
    parser.add_argument("--vyaw", type=float, default=0.0)
    parser.add_argument("--model", default=model_path("go2w/model_700.pt"))
    parser.add_argument("--interface", default=DDS.DEFAULT_NET_IF)
    parser.add_argument("--joystick", default=DDS.DEFAULT_JOYSTICK)
    parser.add_argument("--no-release", action="store_true", help="跳过 Sport Mode 释放")
    parser.add_argument("--torch-threads", type=int, default=None,
                        help="覆盖 PyTorch 线程数；默认保持原笔记本环境设置")
    parser.add_argument("--log", default="", help="可选 A/B 日志路径")
    args = parser.parse_args()
    if args.torch_threads is not None:
        if args.torch_threads < 1:
            parser.error("torch-threads 必须为正数")
        torch.set_num_threads(args.torch_threads)

    print(f"=== Go2W 单进程笔记本基线 === control={args.control}")
    print(f"[Baseline] DDS 与 policy 同进程，无 Pipe；PyTorch threads={torch.get_num_threads()}")

    driver = DdsDriver(args.interface)
    if not driver.initialize():
        print("✗ 驱动初始化失败")
        return

    command_source = None
    lowcmd_started = False
    log_handle, log_writer, observation_handle, observation_writer = open_log(args.log)
    running = [True]

    def on_sigint(sig, frame):
        running[0] = False
        print("\n停止中...")

    signal.signal(signal.SIGINT, on_sigint)

    try:
        if not args.no_release:
            if not wait_for_stage_key("1", "阶段 1：确认机器人在地面，执行 StandUp"):
                return
            if not driver.stand_up():
                return
            initial_command = build_initial_hold_command()
            if not wait_for_stage_key(
                "2", "阶段 2：确认机器人已站稳并吊好；释放 Sport Mode 后立即启动固定 LowCmd",
            ):
                return
            if not driver.release_sport_mode():
                return
        else:
            initial_command = build_initial_hold_command()

        handoff_start = time.perf_counter()
        driver.send_command(initial_command)
        if not driver.start_lowcmd_thread():
            return
        lowcmd_started = True
        print(
            "[Handoff] ReleaseMode 返回后到首条 LowCmd Write 调用完成: "
            f"{(time.perf_counter() - handoff_start) * 1000.0:.3f} ms"
        )
        print_motor_command(
            "[LOWCMD ACTIVE] 固定 INITIAL_JOINTS_POS 指令（DDS 顺序，正在发送）",
            initial_command.positions, initial_command.velocities,
            initial_command.kp, initial_command.kd,
        )

        controller = ControllerGo2w(args.model)
        controller.reset()
        command_source = create_command_source(args)
        period = 1.0 / CTRL.POLICY_RATE_HZ
        print_every = max(1, CTRL.POLICY_RATE_HZ // 2)
        loop_count = 0
        print(f"\n{CTRL.POLICY_RATE_HZ}Hz 单进程 policy 实机控制（Ctrl+C 退出）...")

        while running[0]:
            t0 = time.perf_counter()
            if driver.emergency:
                print("[!!] 紧急阻尼中")
                time.sleep(0.5)
                continue

            command = command_source.read()
            if command.quit_requested:
                break
            state = driver.get_state()
            state_age_ms = (
                (time.perf_counter_ns() - state.received_monotonic_ns) / 1.0e6
                if state.received_monotonic_ns else -1.0
            )
            inference_start = time.perf_counter()
            observation = controller.build_obs(state, command.velocity)
            action = controller.compute_action(observation)
            p, v, kp, kd = controller.action_to_motor_command(action)
            inference_ms = (time.perf_counter() - inference_start) * 1000.0
            action_state_age_ms = (
                (time.perf_counter_ns() - state.received_monotonic_ns) / 1.0e6
                if state.received_monotonic_ns else -1.0
            )
            driver.send_command(MotorCommand(positions=p, velocities=v, kp=kp, kd=kd))
            loop_count += 1

            if log_writer is not None and log_handle is not None:
                timestamp = time.time()
                log_writer.writerow(
                    [timestamp, loop_count, (time.perf_counter() - t0) * 1000.0,
                     inference_ms, 0.0, state_age_ms, action_state_age_ms, state.tick,
                     int(command.enabled), 0, *command.velocity, *state.joint_positions,
                     *state.joint_velocities, *state.joint_torques, *state.imu_quat,
                     *state.imu_gyro, *state.imu_accel, *state.imu_rpy,
                     state.battery_voltage, state.battery_current, *action, *p, *v, *kp, *kd]
                )
                log_handle.flush()
                observation_writer.writerow(
                    [timestamp, loop_count, 0, *observation.numpy(), *action]
                )
                observation_handle.flush()

            if loop_count % print_every == 0:
                print(
                    "\n[COMMAND SOURCE] "
                    f"enabled={command.enabled}  vx={command.velocity[0]:+.3f}  "
                    f"vy={command.velocity[1]:+.3f}  vyaw={command.velocity[2]:+.3f}"
                )
                print_motor_command(
                    "[POLICY ACTIVE] 预测 MotorCommand（正在发送）", p, v, kp, kd,
                )
            elapsed = time.perf_counter() - t0
            if elapsed < period:
                time.sleep(period - elapsed)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        print(f"\n✗ 控制输入中断: {exc}")
    finally:
        if command_source is not None:
            command_source.close()
        if log_handle is not None:
            log_handle.close()
        if observation_handle is not None:
            observation_handle.close()
        if lowcmd_started:
            driver.set_emergency_damping()
            time.sleep(0.1)
        driver.shutdown()
        print("退出。")


if __name__ == "__main__":
    main()
