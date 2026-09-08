"""Go2W 原装遥控器解析和速度命令源。

本模块只负责订阅 ``rt/lowstate`` 中的 40-byte 遥控器数据，不发送 LowCmd，
也不负责释放 Sport Mode。控制入口负责决定何时接管机器人。
"""

from dataclasses import dataclass
import struct
import threading
import time
from typing import Dict, Tuple

import numpy as np

from unitree_sdk2py.core.channel import ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_

from config.go2w_config import DDS
from teleop.command_source import CommandSample, _resolve_bounds, _scale_axis


TAKEOVER_BUTTONS = ("L2", "R2")
QUIT_BUTTON = "Select"
# 输入顺序为 [Ly, Lx, Rx]，对应 [vx, vy, vyaw]。
UNITREE_AXIS_SIGNS = np.array([1.0, -1.0, -1.0], dtype=np.float32)


@dataclass(frozen=True)
class UnitreeRemoteState:
    """解析后的原装遥控器状态。"""

    lx: float
    ly: float
    rx: float
    ry: float
    buttons: Dict[str, bool]
    raw: bytes

    @classmethod
    def parse(cls, wireless_remote) -> "UnitreeRemoteState":
        raw = bytes(wireless_remote)
        if len(raw) != 40:
            raise ValueError(f"wireless_remote must be 40 bytes, got {len(raw)}")

        byte1, byte2 = raw[2], raw[3]
        buttons = {
            "R1": bool(byte1 & (1 << 0)),
            "L1": bool(byte1 & (1 << 1)),
            "Start": bool(byte1 & (1 << 2)),
            "Select": bool(byte1 & (1 << 3)),
            "R2": bool(byte1 & (1 << 4)),
            "L2": bool(byte1 & (1 << 5)),
            "F1": bool(byte1 & (1 << 6)),
            "F3": bool(byte1 & (1 << 7)),
            "A": bool(byte2 & (1 << 0)),
            "B": bool(byte2 & (1 << 1)),
            "X": bool(byte2 & (1 << 2)),
            "Y": bool(byte2 & (1 << 3)),
            "Up": bool(byte2 & (1 << 4)),
            "Right": bool(byte2 & (1 << 5)),
            "Down": bool(byte2 & (1 << 6)),
            "Left": bool(byte2 & (1 << 7)),
        }
        lx = struct.unpack_from("<f", raw, 4)[0]
        rx = struct.unpack_from("<f", raw, 8)[0]
        ry = struct.unpack_from("<f", raw, 12)[0]
        ly = struct.unpack_from("<f", raw, 20)[0]
        return cls(lx=lx, ly=ly, rx=rx, ry=ry, buttons=buttons, raw=raw)

    @property
    def active_buttons(self) -> Tuple[str, ...]:
        return tuple(name for name, pressed in self.buttons.items() if pressed)


def remote_to_command(remote, deadzone, minimum, maximum):
    """把 Ly/Lx/Rx 映射到有界的 [vx, vy, vyaw]。"""
    minimum, maximum = _resolve_bounds(minimum, maximum)
    axes = np.array([remote.ly, remote.lx, remote.rx], dtype=np.float32)
    if not np.isfinite(axes).all():
        raise ValueError("宇树遥控器摇杆包含 NaN/Inf")
    axes[np.abs(axes) < deadzone] = 0.0
    velocity = _scale_axis(axes * UNITREE_AXIS_SIGNS, minimum, maximum)
    return np.clip(velocity, minimum, maximum).astype(np.float32)


class UnitreeRemoteCommandSource:
    """订阅原装遥控器，提供接管按键和实时速度命令。"""

    def __init__(self, deadzone, lowstate_timeout, minimum=None, maximum=None):
        if not 0.0 <= deadzone < 1.0:
            raise ValueError("deadzone 必须在 [0, 1) 内")
        if lowstate_timeout <= 0.0:
            raise ValueError("lowstate_timeout 必须为正数")
        self._deadzone = deadzone
        self._lowstate_timeout = lowstate_timeout
        self._minimum, self._maximum = _resolve_bounds(minimum, maximum)
        self._lock = threading.Lock()
        self._remote = None
        self._last_update = 0.0
        self._packet_count = 0

        # DdsDriver 已初始化 ChannelFactory；这里只增加第二个 LowState subscriber。
        self._subscriber = ChannelSubscriber(DDS.LOWSTATE_TOPIC, LowState_)
        self._subscriber.Init(self._on_lowstate, 10)

    def _on_lowstate(self, msg):
        try:
            remote = UnitreeRemoteState.parse(msg.wireless_remote)
            axes = np.array([remote.lx, remote.ly, remote.rx, remote.ry])
            if not np.isfinite(axes).all():
                return
        except (ValueError, struct.error):
            return
        with self._lock:
            self._remote = remote
            self._last_update = time.monotonic()
            self._packet_count += 1

    def snapshot(self):
        """返回最新数据；LowState 停止刷新时拒绝复用旧命令。"""
        with self._lock:
            remote = self._remote
            last_update = self._last_update
            packet_count = self._packet_count
        if remote is None:
            raise RuntimeError("尚未收到宇树遥控器数据")
        age = time.monotonic() - last_update
        if age > self._lowstate_timeout:
            raise RuntimeError(f"LowState 已停止更新 {age:.3f}s，拒绝继续使用遥控器指令")
        return remote, age, packet_count

    def wait_for_first_state(self, timeout=5.0, stop_requested=lambda: False):
        """等待第一条可解析数据；等待期间仍未发送任何 LowCmd。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if stop_requested():
                return False
            with self._lock:
                if self._remote is not None:
                    return True
            time.sleep(0.01)
        raise RuntimeError("等待宇树遥控器 LowState 超时")

    def wait_for_takeover(self, stop_requested, first_state_timeout=5.0):
        """等待先松开、再按下 L2+R2；Select 表示取消接管。"""
        if not self.wait_for_first_state(first_state_timeout, stop_requested):
            return False

        print("\n[REMOTE READY] 先松开 L2+R2，再同时按下以接管。")
        print("接管前按 Select 可直接退出；此时不会发送 LowCmd。")
        released_once = False
        while not stop_requested():
            remote, _, _ = self.snapshot()
            if remote.buttons[QUIT_BUTTON]:
                print("取消接管。")
                return False
            pressed = all(remote.buttons[name] for name in TAKEOVER_BUTTONS)
            if not pressed:
                released_once = True
            elif released_once:
                print("[REMOTE TRIGGER] 检测到 L2+R2，准备释放 Sport Mode。")
                return True
            time.sleep(0.01)
        print("取消接管。")
        return False

    def read(self):
        remote, _, _ = self.snapshot()
        velocity = remote_to_command(
            remote, self._deadzone, self._minimum, self._maximum
        )
        return CommandSample(
            velocity=velocity,
            quit_requested=remote.buttons[QUIT_BUTTON],
            enabled=True,
        )

    def close(self):
        # Unitree ChannelSubscriber 没有需要显式关闭的设备句柄。
        pass
