"""Go2WWMP 的可开关航向保持命令。

本模块只根据当前 yaw 生成 ``[vx, vy, vyaw]``，不读取 DDS、不发送 LowCmd，
也不改变 WMP 的推理和深度时序。
"""

from dataclasses import dataclass
import math
from typing import Optional

import numpy as np


HEADING_ENABLE_BUTTON = "A"
HEADING_DISABLE_BUTTON = "B"
HEADING_FORWARD_SPEED = 0.6
HEADING_YAW_KP = 1.0


def wrap_to_pi(angle):
    """把角度包到 [-pi, pi]，避免跨过 ±pi 时转向符号突变。"""
    return math.atan2(math.sin(angle), math.cos(angle))


@dataclass(frozen=True)
class HeadingCommand:
    """一个控制周期的最终命令和航向模式诊断。"""

    velocity: np.ndarray
    enabled: bool
    event: Optional[str]
    target_yaw_rad: Optional[float]
    current_yaw_rad: float
    error_rad: Optional[float]


class HeadingModeController:
    """用按键沿开关航向保持，并锁定开启瞬间的 yaw。"""

    def __init__(
        self,
        minimum,
        maximum,
        forward_speed=HEADING_FORWARD_SPEED,
        yaw_kp=HEADING_YAW_KP,
    ):
        self._minimum = np.asarray(minimum, dtype=np.float32)
        self._maximum = np.asarray(maximum, dtype=np.float32)
        if self._minimum.shape != (3,) or self._maximum.shape != (3,):
            raise ValueError("heading command bounds must contain [vx, vy, vyaw]")
        if not np.isfinite(self._minimum).all() or not np.isfinite(self._maximum).all():
            raise ValueError("heading command bounds must be finite")
        if np.any(self._minimum > self._maximum):
            raise ValueError("heading command minimum cannot exceed maximum")
        if (
            not np.isfinite(forward_speed)
            or not self._minimum[0] <= forward_speed <= self._maximum[0]
        ):
            raise ValueError("heading forward speed is outside WMP command bounds")
        if not np.isfinite(yaw_kp) or yaw_kp <= 0.0:
            raise ValueError("heading yaw_kp must be positive")

        self._forward_speed = float(forward_speed)
        self._yaw_kp = float(yaw_kp)
        self._enabled = False
        self._target_yaw = None
        self._buttons_initialized = False
        self._enable_was_pressed = False
        self._disable_was_pressed = False

    def update(self, current_yaw, manual_velocity, enable_pressed, disable_pressed):
        """处理一次按键和 yaw；B 的新按下沿优先于 A。"""
        current_yaw = float(current_yaw)
        manual_velocity = np.asarray(manual_velocity, dtype=np.float32)
        if not math.isfinite(current_yaw):
            raise ValueError("heading current yaw must be finite")
        if manual_velocity.shape != (3,) or not np.isfinite(manual_velocity).all():
            raise ValueError("manual velocity must be finite [vx, vy, vyaw]")

        enable_pressed = bool(enable_pressed)
        disable_pressed = bool(disable_pressed)
        event = None

        # 第一帧只记录当前按键状态，避免接管前按住 A 导致模式误开启。
        if not self._buttons_initialized:
            self._buttons_initialized = True
        else:
            enable_edge = enable_pressed and not self._enable_was_pressed
            disable_edge = disable_pressed and not self._disable_was_pressed
            if disable_edge:
                if self._enabled:
                    event = "disabled"
                self._enabled = False
                self._target_yaw = None
            elif enable_edge and not self._enabled:
                self._enabled = True
                self._target_yaw = wrap_to_pi(current_yaw)
                event = "enabled"

        self._enable_was_pressed = enable_pressed
        self._disable_was_pressed = disable_pressed

        if not self._enabled:
            velocity = np.clip(manual_velocity, self._minimum, self._maximum)
            return HeadingCommand(
                velocity=velocity.astype(np.float32),
                enabled=False,
                event=event,
                target_yaw_rad=None,
                current_yaw_rad=current_yaw,
                error_rad=None,
            )

        assert self._target_yaw is not None
        error = wrap_to_pi(self._target_yaw - current_yaw)
        velocity = np.array(
            [self._forward_speed, 0.0, self._yaw_kp * error], dtype=np.float32
        )
        velocity = np.clip(velocity, self._minimum, self._maximum)
        return HeadingCommand(
            velocity=velocity.astype(np.float32),
            enabled=True,
            event=event,
            target_yaw_rad=float(self._target_yaw),
            current_yaw_rad=current_yaw,
            error_rad=float(error),
        )
