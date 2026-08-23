#!/usr/bin/env python3
"""不打开外部设备的配置映射和命令输入离线测试。"""

import struct

import numpy as np

from config.go2w_config import CTRL, DDS, CTRL_IDX_FROM_DDS, DDS_IDX_FROM_CTRL
from teleop.command_source import (
    FixedCommandSource,
    KeyboardCommandSource,
    XboxCommandSource,
    _VelocityState,
)


def _event(value: int, event_type: int, number: int) -> bytes:
    return struct.pack(XboxCommandSource.EVENT_FORMAT, 123, value, event_type, number)


def main():
    dds_values = np.arange(16)
    ctrl_values = dds_values[CTRL_IDX_FROM_DDS]
    np.testing.assert_array_equal(
        ctrl_values[DDS_IDX_FROM_CTRL],
        dds_values,
    )
    assert len(DDS.JOINT_LIMITS) == 12
    assert all(
        limit == {"q_min": None, "q_max": None, "dq_max": None}
        for limit in DDS.JOINT_LIMITS
    )

    fixed = FixedCommandSource([9.0, -9.0, 0.25]).read()
    np.testing.assert_allclose(fixed.velocity, [0.5, -0.5, 0.25])

    keyboard = KeyboardCommandSource.__new__(KeyboardCommandSource)
    keyboard._state = _VelocityState()
    keyboard._linear_step = 0.05
    keyboard._yaw_step = 0.10
    keyboard._enabled = False
    keyboard._quit = False
    keyboard._handle_key("w")
    np.testing.assert_array_equal(keyboard._state.velocity, np.zeros(3))
    keyboard._handle_key("p")
    keyboard._handle_key("w")
    np.testing.assert_allclose(keyboard._state.velocity, [0.05, 0.0, 0.0])
    keyboard._handle_key("p")
    np.testing.assert_array_equal(keyboard._state.velocity, np.zeros(3))

    timestamp, value, event_type, number = XboxCommandSource.decode_event(
        _event(-32767, XboxCommandSource.EVENT_AXIS | XboxCommandSource.EVENT_INIT, 1)
    )
    assert (timestamp, value, event_type, number) == (
        123, -32767, XboxCommandSource.EVENT_AXIS, 1
    )

    xbox = XboxCommandSource.__new__(XboxCommandSource)
    xbox._deadzone = 0.10
    xbox._deadman_button = 0
    xbox._quit_button = 6
    xbox._axis_indices = (1, 0, 3)
    xbox._axis_signs = (-1.0, -1.0, -1.0)
    xbox._axes = {}
    xbox._buttons = {}
    xbox._quit = False
    xbox._fd = None

    xbox._consume_event(_event(-32767, XboxCommandSource.EVENT_AXIS, 1))
    xbox._consume_event(_event(16384, XboxCommandSource.EVENT_AXIS, 0))
    xbox._consume_event(_event(0, XboxCommandSource.EVENT_AXIS, 3))

    # 未按 deadman 时必须归零。
    xbox._drain_events = lambda: None
    np.testing.assert_array_equal(xbox.read().velocity, np.zeros(3, dtype=np.float32))

    xbox._consume_event(_event(1, XboxCommandSource.EVENT_BUTTON, 0))
    sample = xbox.read()
    assert sample.enabled
    np.testing.assert_allclose(
        sample.velocity,
        [CTRL.COMMAND_LIMITS[0], -0.5 * CTRL.COMMAND_LIMITS[1], 0.0],
        atol=2e-5,
    )

    xbox._consume_event(_event(0, XboxCommandSource.EVENT_BUTTON, 0))
    np.testing.assert_array_equal(xbox.read().velocity, np.zeros(3, dtype=np.float32))

    xbox._consume_event(_event(1, XboxCommandSource.EVENT_BUTTON, 6))
    assert xbox.read().quit_requested
    print("[PASS] mapping, limit slots, fixed/keyboard/Xbox command input")


if __name__ == "__main__":
    main()
