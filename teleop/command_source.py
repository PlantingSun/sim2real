"""固定值、终端键盘和 Linux Xbox 手柄速度命令源。"""

from dataclasses import dataclass
import os
import select
import struct
import sys
import termios
import tty
from typing import Dict, Tuple

import numpy as np

from config.go2w_config import CTRL, DDS


@dataclass(frozen=True)
class CommandSample:
    velocity: np.ndarray
    quit_requested: bool = False
    enabled: bool = True


class _VelocityState:
    """与输入设备无关的速度增量和裁剪逻辑。"""

    def __init__(self, initial=(0.0, 0.0, 0.0)):
        self._velocity = self.clip(initial)

    @staticmethod
    def clip(velocity) -> np.ndarray:
        values = np.asarray(velocity, dtype=np.float32)
        if values.shape != (3,):
            raise ValueError("velocity must contain [vx, vy, vyaw]")
        return np.clip(values, -CTRL.COMMAND_LIMITS, CTRL.COMMAND_LIMITS)

    @property
    def velocity(self) -> np.ndarray:
        return self._velocity.copy()

    def set(self, velocity) -> None:
        self._velocity = self.clip(velocity)

    def nudge(self, axis: int, delta: float) -> None:
        velocity = self._velocity.copy()
        velocity[axis] += delta
        self._velocity = self.clip(velocity)

    def zero(self) -> None:
        self._velocity[:] = 0.0


class FixedCommandSource:
    """兼容原有 --vx/--vy/--vyaw 的固定命令。"""

    def __init__(self, velocity):
        self._state = _VelocityState(velocity)

    def read(self) -> CommandSample:
        return CommandSample(self._state.velocity)

    def close(self) -> None:
        pass


class KeyboardCommandSource:
    """非阻塞终端键盘控制；开始时未使能，避免启动即运动。"""

    HELP = (
        "键盘: p 使能/停用 | w/s 前后 | a/d 左右 | q/e 转向 | "
        "空格归零 | Esc 退出"
    )

    def __init__(self, stream=None, linear_step: float = 0.05, yaw_step: float = 0.10):
        self._stream = stream if stream is not None else sys.stdin
        if not self._stream.isatty():
            raise RuntimeError("keyboard control requires an interactive terminal")
        self._fd = self._stream.fileno()
        self._original_termios = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        self._state = _VelocityState()
        self._linear_step = linear_step
        self._yaw_step = yaw_step
        self._enabled = False
        self._quit = False
        print(self.HELP)

    def _handle_key(self, key: str) -> None:
        if key == "\x1b":
            self._quit = True
        elif key == "p":
            self._enabled = not self._enabled
            if not self._enabled:
                self._state.zero()
            print(f"\n[Keyboard] {'enabled' if self._enabled else 'disabled'}")
        elif key in (" ", "x"):
            self._state.zero()
        elif not self._enabled:
            return
        elif key == "w":
            self._state.nudge(0, self._linear_step)
        elif key == "s":
            self._state.nudge(0, -self._linear_step)
        elif key == "a":
            self._state.nudge(1, self._linear_step)
        elif key == "d":
            self._state.nudge(1, -self._linear_step)
        elif key == "q":
            self._state.nudge(2, self._yaw_step)
        elif key == "e":
            self._state.nudge(2, -self._yaw_step)

    def read(self) -> CommandSample:
        while select.select([self._stream], [], [], 0.0)[0]:
            self._handle_key(self._stream.read(1))
        velocity = self._state.velocity if self._enabled else np.zeros(3, dtype=np.float32)
        return CommandSample(velocity, self._quit, self._enabled)

    def close(self) -> None:
        if self._original_termios is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._original_termios)
            self._original_termios = None


class XboxCommandSource:
    """读取 Linux joystick API，不依赖 ROS Joy 或 pygame。

    默认映射对齐 simtosim：左摇杆纵轴→vx、左摇杆横轴→vy、右摇杆横轴→vyaw。
    A 键（button 0）必须持续按住才输出非零速度，Back（button 6）请求退出。
    """

    EVENT_FORMAT = "IhBB"
    EVENT_SIZE = struct.calcsize(EVENT_FORMAT)
    EVENT_BUTTON = 0x01
    EVENT_AXIS = 0x02
    EVENT_INIT = 0x80

    def __init__(
        self,
        device: str = DDS.DEFAULT_JOYSTICK,
        deadzone: float = 0.10,
        deadman_button: int = 0,
        quit_button: int = 6,
        axis_indices: Tuple[int, int, int] = (1, 0, 3),
        axis_signs: Tuple[float, float, float] = (-1.0, -1.0, -1.0),
    ):
        self._device = device
        self._fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
        self._deadzone = deadzone
        self._deadman_button = deadman_button
        self._quit_button = quit_button
        self._axis_indices = axis_indices
        self._axis_signs = axis_signs
        self._axes: Dict[int, float] = {}
        self._buttons: Dict[int, bool] = {}
        self._quit = False
        print(
            f"Xbox: {device} | hold A to move | release A to zero | "
            "Back to exit"
        )

    @classmethod
    def decode_event(cls, event: bytes):
        """解析一个 8-byte js_event，供运行时和离线测试共用。"""
        if len(event) != cls.EVENT_SIZE:
            raise ValueError(f"expected {cls.EVENT_SIZE} bytes, got {len(event)}")
        timestamp, value, event_type, number = struct.unpack(cls.EVENT_FORMAT, event)
        return timestamp, value, event_type & ~cls.EVENT_INIT, number

    def _consume_event(self, event: bytes) -> None:
        _, value, event_type, number = self.decode_event(event)
        if event_type == self.EVENT_AXIS:
            normalized = max(-1.0, min(1.0, value / 32767.0))
            self._axes[number] = 0.0 if abs(normalized) < self._deadzone else normalized
        elif event_type == self.EVENT_BUTTON:
            self._buttons[number] = bool(value)
            if number == self._quit_button and value:
                self._quit = True

    def _drain_events(self) -> None:
        while True:
            try:
                event = os.read(self._fd, self.EVENT_SIZE)
            except BlockingIOError:
                return
            except OSError as exc:
                raise RuntimeError(f"joystick read failed: {self._device}") from exc
            if not event:
                raise RuntimeError(f"joystick disconnected: {self._device}")
            if len(event) != self.EVENT_SIZE:
                raise RuntimeError(f"incomplete joystick event from {self._device}")
            self._consume_event(event)

    def read(self) -> CommandSample:
        self._drain_events()
        enabled = self._buttons.get(self._deadman_button, False)
        if not enabled:
            return CommandSample(np.zeros(3, dtype=np.float32), self._quit, False)

        raw = np.array(
            [self._axes.get(axis, 0.0) for axis in self._axis_indices],
            dtype=np.float32,
        )
        velocity = raw * np.asarray(self._axis_signs, dtype=np.float32)
        velocity *= CTRL.COMMAND_LIMITS
        return CommandSample(_VelocityState.clip(velocity), self._quit, True)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
