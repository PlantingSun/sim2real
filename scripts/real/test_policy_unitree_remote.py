#!/usr/bin/env python3
"""使用宇树原装遥控器触发接管并控制 Go2W policy。"""

import argparse
import signal
import struct
import threading
import time

import numpy as np

from unitree_sdk2py.core.channel import ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_

from config.go2w_config import CTRL, DDS
from driver.dds_driver import DdsDriver
from driver.driver_base import MotorCommand
from policy.controller_go2w import ControllerGo2w
from policy.controller_go2wcr import ControllerGo2wCR
from scripts.input.debug_unitree_remote import UnitreeRemoteState
from scripts.real.test_policy_real import build_initial_hold_command, print_motor_command
from teleop.command_source import CommandSample


# 方向和按键常量集中放在这里，实机确认后只需检查这一处。
# 宇树官方实机 policy 常用映射：vx=Ly, vy=-Lx, vyaw=-Rx。
UNITREE_AXIS_SIGNS = np.array([1.0, -1.0, -1.0], dtype=np.float32)
TAKEOVER_BUTTONS = ("L2", "R2")
QUIT_BUTTON = "Select"


class UnitreeRemoteCommandSource:
    """从 rt/lowstate 读取原装遥控器，并转换为 policy 速度指令。"""

    def __init__(self, deadzone: float, lowstate_timeout: float):
        self._deadzone = deadzone
        self._lowstate_timeout = lowstate_timeout
        self._lock = threading.Lock()
        self._remote = None
        self._last_update = 0.0
        self._packet_count = 0

        # DdsDriver 已经初始化 ChannelFactory；这里只增加第二个 LowState subscriber。
        self._subscriber = ChannelSubscriber(DDS.LOWSTATE_TOPIC, LowState_)
        self._subscriber.Init(self._on_lowstate, 10)

    def _on_lowstate(self, msg: LowState_) -> None:
        try:
            remote = UnitreeRemoteState.parse(msg.wireless_remote)
        except (ValueError, struct.error):
            return

        axes = np.array([remote.lx, remote.ly, remote.rx, remote.ry])
        if not np.all(np.isfinite(axes)):
            return

        with self._lock:
            self._remote = remote
            self._last_update = time.monotonic()
            self._packet_count += 1

    def wait_for_first_state(self, timeout: float = 5.0) -> None:
        """等待第一条有效遥控器数据；此阶段不会发送 LowCmd。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self._remote is not None:
                    return
            time.sleep(0.01)
        raise RuntimeError("等待宇树遥控器 LowState 超时")

    def snapshot(self):
        """返回最新遥控器、消息年龄和 LowState 包计数。"""
        with self._lock:
            remote = self._remote
            last_update = self._last_update
            packet_count = self._packet_count

        if remote is None:
            raise RuntimeError("尚未收到宇树遥控器数据")
        age = time.monotonic() - last_update
        if age > self._lowstate_timeout:
            raise RuntimeError(
                f"LowState 已停止更新 {age:.3f}s，拒绝继续使用遥控器指令"
            )
        return remote, age, packet_count

    def wait_for_takeover(self, stop_requested) -> bool:
        """等待 L2+R2 的新按下沿；Select 表示不接管并退出。"""
        self.wait_for_first_state()
        print("\n[REMOTE READY] 先松开 L2+R2，再同时按下以释放 Sport Mode 并接管。")
        print("按 Select 可在接管前退出；此时不会发送 LowCmd。")

        armed = False
        while True:
            if stop_requested():
                print("取消接管。")
                return False
            remote, _, _ = self.snapshot()
            if remote.buttons[QUIT_BUTTON]:
                print("取消接管。")
                return False

            combo_pressed = all(remote.buttons[name] for name in TAKEOVER_BUTTONS)
            if not combo_pressed:
                armed = True
            elif armed:
                print("[REMOTE TRIGGER] 检测到 L2+R2，开始 ReleaseMode 接管。")
                return True
            time.sleep(0.01)

    def read(self) -> CommandSample:
        """摇杆始终生效；回中时由 deadzone 归零。"""
        remote, _, _ = self.snapshot()
        quit_requested = remote.buttons[QUIT_BUTTON]

        # 原始轴顺序在此显式写出，方便实机逐行核对：Ly, Lx, Rx。
        axes = np.array([remote.ly, remote.lx, remote.rx], dtype=np.float32)
        axes[np.abs(axes) < self._deadzone] = 0.0
        velocity = axes * UNITREE_AXIS_SIGNS * CTRL.COMMAND_LIMITS
        velocity = np.clip(velocity, -CTRL.COMMAND_LIMITS, CTRL.COMMAND_LIMITS)
        return CommandSample(velocity, quit_requested=quit_requested)

    def close(self) -> None:
        # Unitree ChannelSubscriber 没有需要在这里显式关闭的设备句柄。
        pass


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
            "models/go2wcr/model_1499.pt"
            if args.policy == "go2wcr"
            else "models/go2w/model_700.pt"
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
