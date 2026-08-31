#!/usr/bin/env python3
"""go2wcr/CRRL 实机测试入口；沿用现有 DDS 接管和输入安全流程。"""

import argparse
import signal
import time

from config.go2w_config import CTRL, DDS
from config.paths import model_path
from driver.dds_driver import DdsDriver
from policy.controller_go2wcr import ControllerGo2wCR
from scripts.real.test_policy_real import (
    build_initial_hold_command,
    create_command_source,
    print_motor_command,
    wait_for_stage_key,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Go2W go2wcr CRRL 实物策略测试")
    parser.add_argument("--control", choices=("fixed", "keyboard", "xbox"), default="fixed")
    parser.add_argument("--vx", type=float, default=0.0)
    parser.add_argument("--vy", type=float, default=0.0)
    parser.add_argument("--vyaw", type=float, default=0.0)
    parser.add_argument("--model", default=model_path("go2wcr/model_1499.pt"))
    parser.add_argument("--interface", default=DDS.DEFAULT_NET_IF)
    parser.add_argument("--joystick", default="/dev/input/js0")
    parser.add_argument("--no-release", action="store_true", help="跳过 Sport Mode 释放")
    args = parser.parse_args()

    print(f"=== Go2W go2wcr CRRL 实机测试 === control={args.control}")
    print("前提：第一次测试必须使用架子或吊绳，并先完成离线和 MuJoCo 验证。")

    driver = DdsDriver(args.interface)
    if not driver.initialize():
        print("✗ 驱动初始化失败")
        return

    command_source = None
    lowcmd_started = False
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
                "2",
                "阶段 2：确认机器人已站稳并吊好；释放 Sport Mode 后立即启动固定 LowCmd",
            ):
                return
            if not driver.release_sport_mode():
                return
        else:
            initial_command = build_initial_hold_command()

        # ReleaseMode 返回后立即发送固定站姿首帧，再启动 DDS 500 Hz 发布循环。
        handoff_start = time.perf_counter()
        driver.send_command(initial_command)
        if not driver.start_lowcmd_thread():
            return
        lowcmd_started = True
        elapsed_ms = (time.perf_counter() - handoff_start) * 1000.0
        print(f"[Handoff] 首条 LowCmd Write 调用完成: {elapsed_ms:.3f} ms")
        print_motor_command(
            "[LOWCMD ACTIVE] 固定 INITIAL_JOINTS_POS（正在发送）",
            initial_command.positions,
            initial_command.velocities,
            initial_command.kp,
            initial_command.kd,
        )

        controller = ControllerGo2wCR(args.model)
        controller.reset()
        command_source = create_command_source(args)
        period = 1.0 / CTRL.POLICY_RATE_HZ
        print_every = max(1, CTRL.POLICY_RATE_HZ // 2)
        loop_count = 0
        print(f"\n{CTRL.POLICY_RATE_HZ}Hz go2wcr policy 控制，Ctrl+C 退出。")

        while running[0]:
            start = time.perf_counter()
            if driver.emergency:
                print("[!!] 已进入紧急阻尼，结束控制循环")
                break
            command = command_source.read()
            if command.quit_requested:
                break

            state = driver.get_state()
            obs = controller.build_obs(state, command.velocity)
            action = controller.compute_action(obs)
            motor_command = controller.action_to_motor_command(action)
            driver.send_command(motor_command)

            loop_count += 1
            if loop_count % print_every == 0:
                print(
                    "\n[COMMAND SOURCE] "
                    f"enabled={command.enabled} "
                    f"vx={command.velocity[0]:+.3f} "
                    f"vy={command.velocity[1]:+.3f} "
                    f"vyaw={command.velocity[2]:+.3f}"
                )
                print_motor_command(
                    "[POLICY ACTIVE] go2wcr MotorCommand（正在发送）",
                    motor_command.positions,
                    motor_command.velocities,
                    motor_command.kp,
                    motor_command.kd,
                )

            elapsed = time.perf_counter() - start
            if elapsed < period:
                time.sleep(period - elapsed)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        print(f"\n✗ 控制输入中断: {exc}")
    finally:
        if command_source is not None:
            command_source.close()
        if lowcmd_started:
            driver.set_emergency_damping()
            time.sleep(0.1)
        driver.shutdown()
        print("退出。")


if __name__ == "__main__":
    main()
