#!/usr/bin/env python3
"""使用宇树原装遥控器触发接管并控制 Go2W policy。"""

import argparse
import signal
import time

import numpy as np

from config.go2w_config import CTRL, DDS
from config.paths import model_path
from driver.dds_driver import DdsDriver
from driver.driver_base import MotorCommand
from policy.controller_go2w import ControllerGo2w
from policy.controller_go2wcr import ControllerGo2wCR
from scripts.real.test_policy_real import build_initial_hold_command, print_motor_command
from teleop.unitree_remote import UnitreeRemoteCommandSource


def main(policy_override=None):
    parser = argparse.ArgumentParser(description="Go2W 宇树原装遥控器实机 policy 测试")
    parser.add_argument(
        "--policy",
        choices=("go2w", "go2wcr"),
        default=policy_override or "go2w",
        help="策略类型（CRRL 使用 go2wcr）",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--interface", default=DDS.DEFAULT_NET_IF)
    parser.add_argument("--deadzone", type=float, default=0.10)
    parser.add_argument("--lowstate-timeout", type=float, default=0.50)
    args = parser.parse_args()
    if not 0.0 <= args.deadzone < 1.0:
        parser.error("--deadzone must be in [0, 1)")
    if args.lowstate_timeout <= 0.0:
        parser.error("--lowstate-timeout must be positive")

    if args.model is None:
        args.model = (
            model_path("go2wcr/model_1499.pt")
            if args.policy == "go2wcr"
            else model_path("go2w/model_700.pt")
        )

    print(f"=== Go2W {args.policy} 宇树原装遥控器实机测试 ===")
    print("前提：机器人已由机载服务站立，并已固定到架子或吊绳。")

    # 1. 初始化 DDS；DdsDriver.initialize() 不会发送 LowCmd。
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
        command_source = UnitreeRemoteCommandSource(args.deadzone, args.lowstate_timeout)

        # 2. 提前准备固定位置环，但在 L2+R2 触发前不写入、不发送。
        initial_command = build_initial_hold_command()
        if not command_source.wait_for_takeover(lambda: not running[0]):
            return
        if not driver.release_sport_mode():
            return

        # 3. ReleaseMode 返回后同步发送固定首帧，再启动 500 Hz 线程。
        handoff_start = time.perf_counter()
        driver.send_command(initial_command)
        if not driver.start_lowcmd_thread():
            return
        lowcmd_started = True
        handoff_ms = (time.perf_counter() - handoff_start) * 1000.0
        print(f"[Handoff] ReleaseMode 返回后到首条 LowCmd Write 完成: {handoff_ms:.3f} ms")
        print_motor_command(
            "[LOWCMD ACTIVE] 固定 INITIAL_JOINTS_POS（正在发送）",
            initial_command.positions,
            initial_command.velocities,
            initial_command.kp,
            initial_command.kd,
        )

        # 4. 模型加载期间固定位置环继续发送。加载完成后先确认 LowState 仍在更新。
        controller_class = ControllerGo2wCR if args.policy == "go2wcr" else ControllerGo2w
        controller = controller_class(args.model)
        controller.reset()
        remote, age, packets = command_source.snapshot()
        print(
            "[POST-RELEASE REMOTE] "
            f"packets={packets} age={age:.3f}s "
            f"Lx={remote.lx:+.3f} Ly={remote.ly:+.3f} Rx={remote.rx:+.3f}"
        )

        period = 1.0 / CTRL.POLICY_RATE_HZ
        print_every = max(1, CTRL.POLICY_RATE_HZ // 2)
        loop_count = 0
        print(
            f"\n{CTRL.POLICY_RATE_HZ}Hz policy 实机控制："
            "摇杆始终生效，摇杆回中归零，Select 退出。"
        )

        while running[0]:
            t0 = time.perf_counter()
            if driver.emergency:
                print("[!!] 已进入紧急阻尼，结束控制循环")
                break

            command = command_source.read()
            if command.quit_requested:
                break
            state = driver.get_state()
            obs = controller.build_obs(state, command.velocity)
            action = controller.compute_action(obs)
            command_result = controller.action_to_motor_command(action)
            if isinstance(command_result, MotorCommand):
                motor_command = command_result
            else:
                p, v, kp, kd = command_result
                motor_command = MotorCommand(positions=p, velocities=v, kp=kp, kd=kd)
            driver.send_command(motor_command)

            loop_count += 1
            if loop_count % print_every == 0:
                remote, age, packets = command_source.snapshot()
                print(
                    "\n[UNITREE REMOTE] "
                    f"packets={packets} age={age:.3f}s "
                    f"Lx={remote.lx:+.3f} Ly={remote.ly:+.3f} Rx={remote.rx:+.3f}"
                )
                print(
                    "[COMMAND SOURCE] "
                    f"vx={command.velocity[0]:+.3f} "
                    f"vy={command.velocity[1]:+.3f} "
                    f"vyaw={command.velocity[2]:+.3f}"
                )
                print_motor_command(
                    "[POLICY ACTIVE] 预测 MotorCommand（正在发送）",
                    motor_command.positions,
                    motor_command.velocities,
                    motor_command.kp,
                    motor_command.kd,
                )

            dt = time.perf_counter() - t0
            if dt < period:
                time.sleep(period - dt)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        print(f"\n✗ 宇树遥控器控制中断: {exc}")
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
