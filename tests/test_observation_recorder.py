"""Regression tests for the chunked Go2WWMP observation archive."""

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from driver.driver_base import RobotState
from telemetry.observation_recorder import ObservationRecorder


class TestObservationRecorder(unittest.TestCase):
    def test_chunk_contains_observations_but_not_motor_commands(self):
        with tempfile.TemporaryDirectory(prefix="go2wwmp_obs_test_") as temp:
            directory = Path(temp)
            recorder = ObservationRecorder(
                directory,
                source_log=Path("run.jsonl"),
                model_path="model.pt",
                model_sha256="abc",
                chunk_frames=2,
            )
            state = RobotState(
                joint_positions=np.zeros(16, dtype=np.float32),
                joint_velocities=np.zeros(16, dtype=np.float32),
                imu_quat=np.array([1, 0, 0, 0], dtype=np.float32),
                imu_gyro=np.zeros(3, dtype=np.float32),
            )
            snapshot = {
                "prop": np.zeros(37, dtype=np.float32),
                "obs_now": np.zeros(53, dtype=np.float32),
                "obs_history": np.zeros(250, dtype=np.float32),
                "wm_feature": np.zeros(512, dtype=np.float32),
            }
            depth = np.ones((64, 64), dtype=np.float32)
            valid = np.ones((64, 64), dtype=np.uint8)
            for loop in range(1, 3):
                recorder.append(
                    timestamp_wall_ns=loop,
                    timestamp_monotonic_ns=loop,
                    loop=loop,
                    state_tick=loop,
                    state_age_ms=1.0,
                    command=np.zeros(3, dtype=np.float32),
                    state=state,
                    snapshot=snapshot,
                    depth_session=7,
                    depth_frame=loop,
                    depth_valid_ratio=1.0,
                    depth_invalid_pixels=0,
                    depth_local_age_ms=1.0,
                    depth_source_processing_ms=2.0,
                    needs_depth_update=loop == 1,
                    depth_m=depth if loop == 1 else None,
                    depth_valid=valid if loop == 1 else None,
                )
            recorder.close()

            chunk = np.load(directory / "chunk_000000.npz")
            self.assertEqual(chunk["obs_now"].shape, (2, 53))
            self.assertEqual(chunk["obs_history"].shape, (2, 250))
            self.assertEqual(chunk["depth_image_m"].shape, (1, 64, 64))
            self.assertNotIn("action", chunk.files)
            self.assertNotIn("positions", chunk.files)
            summary = json.loads((directory / "summary.json").read_text())
            self.assertEqual(summary["frames_written"], 2)


if __name__ == "__main__":
    unittest.main()

