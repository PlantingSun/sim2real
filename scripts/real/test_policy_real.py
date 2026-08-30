#!/usr/bin/env python3
# ============================================================================
# test_policy_real.py — Step 4: 固定站姿接管 + policy 实机输出
#
# Usage:
#   source setup.sh robot
#   python scripts/real/test_policy_real.py --control keyboard
#   python scripts/real/test_policy_real.py --control xbox --joystick /dev/input/js0
# ============================================================================

import argparse
import signal
import sys
import termios
import time
import tty

import numpy as np

from driver.dds_driver import DdsDriver
from driver.driver_base import MotorCommand
from policy.controller_go2w import ControllerGo2w
from config.go2w_config import CTRL, DDS, DDS_IDX_FROM_CTRL
from teleop.command_source import (
    FixedCommandSource,
    KeyboardCommandSource,
    XboxCommandSource,
)


def create_command_source(args):
    if args.control == "keyboard":
        return KeyboardCommandSource()
    if args.control == "xbox":
        return XboxCommandSource(args.joystick)
    return FixedCommandSource([args.vx, args.vy, args.vyaw])


def wait_for_stage_key(expected_key: str, message: str) -> bool:
    """等待单个阶段按键；q 或 Esc 表示退出。"""
    if not sys.stdin.isatty():
        raise RuntimeError("staged robot control requires an interactive terminal")

    print(f"\n{message}")
    print(f"按 {expected_key} 继续，按 q 退出。")
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            key = sys.stdin.read(1)
            if key == expected_key:
                print(expected_key)
                return True
            if key in ("q", "\x1b"):
                print("取消。")
                return False
            print(f"忽略按键 {key!r}，当前只接受 {expected_key} 或 q。")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def build_initial_hold_command() -> MotorCommand:
    """构造与零 action 相同的固定初始站姿指令（DDS 顺序）。"""
    positions_ctrl = CTRL.INITIAL_JOINTS_POS.copy()
    velocities_ctrl = np.zeros(16, dtype=np.float32)
    kp_ctrl = np.full(16, CTRL.LEG_KP, dtype=np.float32)
    kd_ctrl = np.full(16, CTRL.LEG_KD, dtype=np.float32)

    for index in CTRL.WHEEL_INDICES:
        kp_ctrl[index] = CTRL.WHEEL_KP
        kd_ctrl[index] = CTRL.WHEEL_KD

    return MotorCommand(
        positions=positions_ctrl[DDS_IDX_FROM_CTRL],
        velocities=velocities_ctrl[DDS_IDX_FROM_CTRL],
        kp=kp_ctrl[DDS_IDX_FROM_CTRL],
        kd=kd_ctrl[DDS_IDX_FROM_CTRL],
    )


def print_motor_command(title, positions, velocities, kp, kd) -> None:
    """以统一格式打印一条 MotorCommand。"""
    print(f"\n{title}")
    print("  position:", np.array2string(positions, precision=4, suppress_small=True))
    print("  velocity:", np.array2string(velocities, precision=4, suppress_small=True))
    print("  kp      :", np.array2string(kp, precision=2, suppress_small=True))
    print("  kd      :", np.array2string(kd, precision=2, suppress_small=True))


def main():
    parser = argparse.ArgumentParser(description="Go2W 实物策略部署")
    parser.add_argument(
        "--control",
        choices=("fixed", "keyboard", "xbox"),
        default="fixed",
        help="速度命令来源（默认保留原 fixed 行为）",
    )
    parser.add_argument("--vx", type=float, default=0.0, help="前进速度 m/s")
    parser.add_argument("--vy", type=float, default=0.0, help="侧向速度 m/s")
    parser.add_argument("--vyaw", type=float, default=0.0, help="转向速度 rad/s")
    parser.add_argument("--model", type=str, default="models/go2w/model_700.pt")
    parser.add_argument("--interface", type=str, default=DDS.DEFAULT_NET_IF)
    parser.add_argument("--joystick", type=str, default="/dev/input/js0")
    parser.add_argument("--no-release", action="store_true", help="跳过 Sport Mode 释放")
    args = parser.parse_args()

    print(f"=== Go2W 实物部署 === control={args.control}")

    # 1. 初始化 DDS 通信；此时不会发布任何 LowCmd。
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

            # 提前构造固定指令；这里只准备数据，不发送 LowCmd。
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

        # ReleaseMode 成功返回后，不再等待人工按键或 CheckMode 轮询。
        handoff_start = time.perf_counter()
        driver.send_command(initial_command)
        if not driver.start_lowcmd_thread():
            return
        lowcmd_started = True
        handoff_ms = (time.perf_counter() - handoff_start) * 1000.0
        print(f"[Handoff] ReleaseMode 返回后到首条 LowCmd Write 调用完成: {handoff_ms:.3f} ms")

        print_motor_command(
            "[LOWCMD ACTIVE] 固定 INITIAL_JOINTS_POS 指令（DDS 顺序，正在发送）",
            initial_command.positions,
            initial_command.velocities,
            initial_command.kp,
            initial_command.kd,
        )

        # LowCmd 已由固定初始站姿接管；模型加载完成后由 policy 更新指令。
        controller = ControllerGo2w(args.model)
        controller.reset()
        command_source = create_command_source(args)

        period = 1.0 / CTRL.POLICY_RATE_HZ
        print_every = max(1, CTRL.POLICY_RATE_HZ // 2)
        loop_count = 0
        print(f"\n{CTRL.POLICY_RATE_HZ}Hz policy 实机控制（预测指令正在发送，Ctrl+C 退出）...")

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
            obs = controller.build_obs(state, command.velocity)
            action = controller.compute_action(obs)
            p, v, kp, kd = controller.action_to_motor_command(action)
            driver.send_command(MotorCommand(positions=p, velocities=v, kp=kp, kd=kd))
            loop_count += 1
            if loop_count % print_every == 0:
                print(
                    "\n[COMMAND SOURCE] "
                    f"enabled={command.enabled}  "
                    f"vx={command.velocity[0]:+.3f}  "
                    f"vy={command.velocity[1]:+.3f}  "
                    f"vyaw={command.velocity[2]:+.3f}"
                )
                print_motor_command(
                    "[POLICY ACTIVE] 预测 MotorCommand（正在发送）",
                    p,
                    v,
                    kp,
                    kd,
                )
            dt = time.perf_counter() - t0
            if dt < period:
                time.sleep(period - dt)
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
