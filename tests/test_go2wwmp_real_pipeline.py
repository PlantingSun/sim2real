"""Offline safety/transport checks for the Go2WWMP real validation entry."""

import ast
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

import numpy as np

from depth.receiver import DepthFrame, decode
from config.go2w_config import CTRL, DDS_IDX_FROM_CTRL
from depth.opencv_display import load_cv2_for_gui
from driver.driver_base import MotorCommand, RobotState
from driver.dds_driver import DdsDriver
from policy.process_worker_go2wwmp import _depth_quality, _motor_arrays, _state_from_payload
from scripts.real.run_go2wwmp_unitree import parse_args
from teleop.unitree_remote import UnitreeRemoteState, remote_to_command


class TestGo2wWMPRealPipeline(unittest.TestCase):
    def test_opencv_gui_uses_an_existing_font_directory(self):
        load_cv2_for_gui()
        self.assertTrue(Path(os.environ["QT_QPA_FONTDIR"]).is_dir())

    def test_unitree_long_run_entry_does_not_import_test_scripts(self):
        entry = Path(__file__).parents[1] / "scripts/real/run_go2wwmp_unitree.py"
        source = entry.read_text()
        tree = ast.parse(source)
        imported = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        self.assertFalse(any("test_policy" in module for module in imported))
        self.assertLess(
            source.index('parent_conn.send(("sync_session",))'),
            source.index("driver.release_sport_mode()"),
        )
        self.assertLess(
            source.index("driver.release_sport_mode()"),
            source.index("driver.start_lowcmd_thread()"),
        )
        self.assertLess(
            source.index("driver.set_emergency_damping()"),
            source.index("worker.join(timeout=2.0)"),
        )

    def test_unitree_long_run_defaults_are_the_only_runtime_mode(self):
        with patch(
            "scripts.real.run_go2wwmp_unitree.os.sched_getaffinity",
            return_value={0, 1},
        ):
            args = parse_args([])
        self.assertTrue(args.model.endswith("models/go2wwmp/model_6000.pt"))
        self.assertFalse(args.no_depth_display)
        self.assertTrue(str(args.observation_dir).endswith("_obs"))
        with patch(
            "scripts.real.run_go2wwmp_unitree.os.sched_getaffinity",
            return_value={0, 1},
        ):
            no_obs = parse_args(["--no-observation-log"])
        self.assertIsNone(no_obs.observation_dir)
        self.assertFalse(hasattr(args, "duration"))
        self.assertFalse(hasattr(args, "ground_stand"))
        self.assertFalse(hasattr(args, "enable_wmp_action"))

    def test_unitree_remote_mapping_matches_wmp_bounds(self):
        raw = bytearray(40)
        raw[2] = (1 << 5) | (1 << 4)  # L2 + R2
        struct.pack_into("<f", raw, 4, 0.7)   # Lx; WMP vy remains zero
        struct.pack_into("<f", raw, 8, 0.5)   # Rx -> negative yaw
        struct.pack_into("<f", raw, 12, 0.0)  # Ry
        struct.pack_into("<f", raw, 20, 1.0)  # Ly -> max forward
        remote = UnitreeRemoteState.parse(raw)
        self.assertTrue(remote.buttons["L2"] and remote.buttons["R2"])
        np.testing.assert_allclose(
            remote_to_command(
                remote, 0.10, CTRL.WMP_COMMAND_MIN, CTRL.WMP_COMMAND_MAX
            ),
            [1.0, 0.0, -0.5],
        )

        struct.pack_into("<f", raw, 20, -1.0)
        remote = UnitreeRemoteState.parse(raw)
        self.assertAlmostEqual(
            float(
                remote_to_command(
                    remote, 0.10, CTRL.WMP_COMMAND_MIN, CTRL.WMP_COMMAND_MAX
                )[0]
            ),
            -0.2,
            places=6,
        )

    def test_depth_quality_preserves_known_invalid_far_plane(self):
        frame = DepthFrame(
            1, 5, 7, 0.0, -1, 100, 200, 300,
            [1.0] * 4096, [1] * 4096,
        )
        frame.depth_m[0] = 2.0
        frame.valid[0] = 0
        sample = decode(frame, 400)
        quality = _depth_quality(sample, 500)
        self.assertAlmostEqual(quality["depth_valid_ratio"], 4095 / 4096)
        self.assertEqual(quality["depth_invalid_pixels"], 1)
        self.assertEqual(quality["depth_session"], 5)
        self.assertEqual(quality["depth_frame"], 7)

    def test_depth_quality_reports_low_valid_ratio_without_disabling_worker(self):
        frame = DepthFrame(
            1, 5, 7, 0.0, -1, 100, 200, 300,
            [2.0] * 4096, [0] * 4096,
        )
        sample = decode(frame, 400)
        quality = _depth_quality(sample, 500)
        self.assertEqual(quality["depth_valid_ratio"], 0.0)
        self.assertEqual(quality["depth_invalid_pixels"], 4096)
        self.assertTrue(np.all(sample.depth_m == 2.0))

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

    def test_position_limits_disabled_but_velocity_limit_remains(self):
        driver = DdsDriver.__new__(DdsDriver)
        positions = CTRL.INITIAL_JOINTS_POS[DDS_IDX_FROM_CTRL].copy()
        command = MotorCommand(
            positions=positions,
            velocities=np.zeros(16),
            kp=np.ones(16),
            kd=np.ones(16),
        )
        self.assertTrue(np.isfinite(command.velocities).all())

        bad_position = positions.copy()
        bad_position[2] = -0.5  # DDS 2 is FR calf; MJCF max is -0.83776.
        bad = MotorCommand(bad_position, np.zeros(16), np.ones(16), np.ones(16))
        self.assertTrue(np.isfinite(bad.positions).all())

        actual = RobotState(joint_positions=positions.copy())
        actual.joint_positions[2] = -0.5
        self.assertIsNone(driver._check_limits(actual))

        bad_velocity = np.zeros(16)
        bad_velocity[0] = 30.01
        bad = MotorCommand(positions, bad_velocity, np.ones(16), np.ones(16))
        self.assertTrue(np.isfinite(bad.velocities).all())

        actual.joint_velocities[0] = 30.01
        self.assertIn("J0 |dq|=30.010", driver._check_limits(actual))


if __name__ == "__main__":
    unittest.main()
