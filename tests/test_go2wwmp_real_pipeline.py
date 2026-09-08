"""Offline safety/transport checks for the Go2WWMP real validation entry."""

import unittest

import numpy as np

from depth.receiver import DepthFrame, decode
from config.go2w_config import CTRL, DDS_IDX_FROM_CTRL
from driver.driver_base import MotorCommand
from driver.dds_driver import DdsDriver
from policy.process_worker_go2wwmp import _depth_quality, _motor_arrays, _state_from_payload


class TestGo2wWMPRealPipeline(unittest.TestCase):
    def test_depth_quality_preserves_known_invalid_far_plane(self):
        frame = DepthFrame(
            1, 5, 7, 0.0, -1, 100, 200, 300,
            [1.0] * 4096, [1] * 4096,
        )
        frame.depth_m[0] = 2.0
        frame.valid[0] = 0
        sample = decode(frame, 400)
        quality = _depth_quality(sample, 500, min_valid_ratio=0.99)
        self.assertAlmostEqual(quality["depth_valid_ratio"], 4095 / 4096)
        self.assertEqual(quality["depth_invalid_pixels"], 1)
        self.assertEqual(quality["depth_session"], 5)
        self.assertEqual(quality["depth_frame"], 7)

    def test_depth_quality_rejects_low_valid_ratio(self):
        frame = DepthFrame(
            1, 5, 7, 0.0, -1, 100, 200, 300,
            [2.0] * 4096, [0] * 4096,
        )
        sample = decode(frame, 400)
        with self.assertRaisesRegex(RuntimeError, "valid_ratio"):
            _depth_quality(sample, 500, min_valid_ratio=0.90)

    def test_motor_arrays_are_finite_float32(self):
        command = MotorCommand(
            positions=np.arange(16),
            velocities=np.arange(16) * 0.1,
            kp=np.ones(16) * 50,
            kd=np.ones(16),
        )
        arrays = _motor_arrays(command)
        self.assertEqual(set(arrays), {"positions", "velocities", "kp", "kd"})
        for value in arrays.values():
            self.assertEqual(value.dtype, np.float32)
            self.assertEqual(value.shape, (16,))
            self.assertTrue(np.isfinite(value).all())

    def test_state_payload_is_strictly_validated(self):
        payload = (np.zeros(16), np.zeros(16), np.array([1, 0, 0, 0]), np.zeros(3))
        state = _state_from_payload(payload)
        self.assertEqual(state.joint_positions.shape, (16,))
        with self.assertRaisesRegex(ValueError, "shape"):
            _state_from_payload((np.zeros(15), np.zeros(16), np.zeros(4), np.zeros(3)))
        with self.assertRaisesRegex(ValueError, "NaN"):
            bad = list(payload)
            bad[0] = np.full(16, np.nan)
            _state_from_payload(tuple(bad))

    def test_command_limits_match_initial_pose_and_reject_bad_targets(self):
        driver = DdsDriver.__new__(DdsDriver)
        positions = CTRL.INITIAL_JOINTS_POS[DDS_IDX_FROM_CTRL].copy()
        command = MotorCommand(
            positions=positions,
            velocities=np.zeros(16),
            kp=np.ones(16),
            kd=np.ones(16),
        )
        self.assertIsNone(driver._check_command_limits(command))

        bad_position = positions.copy()
        bad_position[2] = -0.5  # DDS 2 is FR calf; MJCF max is -0.83776.
        bad = MotorCommand(bad_position, np.zeros(16), np.ones(16), np.ones(16))
        self.assertIn("q_cmd", driver._check_command_limits(bad))

        bad_velocity = np.zeros(16)
        bad_velocity[0] = 30.01
        bad = MotorCommand(positions, bad_velocity, np.ones(16), np.ones(16))
        self.assertIn("dq_cmd", driver._check_command_limits(bad))


if __name__ == "__main__":
    unittest.main()
