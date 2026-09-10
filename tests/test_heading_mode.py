"""Go2WWMP 航向保持模式的纯离线测试。"""

import math
import unittest

import numpy as np

from config.go2w_config import CTRL
from teleop.heading_mode import HeadingModeController, wrap_to_pi


class TestHeadingMode(unittest.TestCase):
    def make_controller(self):
        return HeadingModeController(
            minimum=CTRL.WMP_COMMAND_MIN,
            maximum=CTRL.WMP_COMMAND_MAX,
            forward_speed=0.5,
            yaw_kp=1.0,
        )

    def test_wrap_to_pi_handles_boundary(self):
        self.assertAlmostEqual(wrap_to_pi(math.pi + 0.2), -math.pi + 0.2)
        self.assertAlmostEqual(wrap_to_pi(-math.pi - 0.2), math.pi - 0.2)

    def test_preheld_enable_does_not_trigger_on_first_cycle(self):
        controller = self.make_controller()
        result = controller.update(0.4, [0.1, 0.0, -0.2], True, False)
        self.assertFalse(result.enabled)
        np.testing.assert_allclose(result.velocity, [0.1, 0.0, -0.2])

    def test_enable_locks_yaw_and_generates_correction(self):
        controller = self.make_controller()
        controller.update(0.5, [0.0, 0.0, 0.0], False, False)
        enabled = controller.update(0.5, [0.0, 0.0, 0.0], True, False)
        self.assertEqual(enabled.event, "enabled")
        self.assertAlmostEqual(enabled.target_yaw_rad, 0.5)
        np.testing.assert_allclose(enabled.velocity, [0.5, 0.0, 0.0])

        corrected = controller.update(0.2, [0.0, 0.0, -0.9], False, False)
        self.assertTrue(corrected.enabled)
        self.assertAlmostEqual(corrected.error_rad, 0.3, places=6)
        np.testing.assert_allclose(corrected.velocity, [0.5, 0.0, 0.3])

    def test_correction_uses_shortest_angle_and_wmp_clip(self):
        controller = self.make_controller()
        controller.update(math.pi - 0.1, [0.0, 0.0, 0.0], False, False)
        controller.update(math.pi - 0.1, [0.0, 0.0, 0.0], True, False)
        result = controller.update(-math.pi + 0.1, [0.0, 0.0, 0.0], False, False)
        self.assertAlmostEqual(result.error_rad, -0.2, places=6)

        clipped = controller.update(0.0, [0.0, 0.0, 0.0], False, False)
        self.assertAlmostEqual(float(clipped.velocity[2]), 1.0, places=6)

    def test_disable_restores_manual_command(self):
        controller = self.make_controller()
        controller.update(0.0, [0.0, 0.0, 0.0], False, False)
        controller.update(0.0, [0.0, 0.0, 0.0], True, False)
        result = controller.update(0.1, [-0.1, 0.0, 0.4], False, True)
        self.assertFalse(result.enabled)
        self.assertEqual(result.event, "disabled")
        self.assertIsNone(result.target_yaw_rad)
        np.testing.assert_allclose(result.velocity, [-0.1, 0.0, 0.4])

    def test_disable_button_wins_when_both_edges_arrive(self):
        controller = self.make_controller()
        controller.update(0.0, [0.0, 0.0, 0.0], False, False)
        result = controller.update(0.0, [0.0, 0.0, 0.0], True, True)
        self.assertFalse(result.enabled)
        self.assertIsNone(result.event)

    def test_invalid_yaw_is_rejected(self):
        controller = self.make_controller()
        with self.assertRaisesRegex(ValueError, "finite"):
            controller.update(float("nan"), [0.0, 0.0, 0.0], False, False)


if __name__ == "__main__":
    unittest.main()
