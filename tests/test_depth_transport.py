"""Run with the project's DDS library path; integration requires local UDP sockets."""
import os
from pathlib import Path
import subprocess
import time
import unittest

import numpy as np
from depth.receiver import DepthFrame, DepthReceiver, decode


class DepthProtocolTest(unittest.TestCase):
    def frame(self):
        return DepthFrame(1, 7, 9, 12.5, 0, 100, 200, 300,
                          [1.0] * 4096, [1] * 4096)

    def test_decode_and_roundtrip(self):
        frame = self.frame()
        frame.depth_m[65] = 0.25
        result = decode(DepthFrame.deserialize(frame.serialize()), 400)
        self.assertEqual(result.depth_m.shape, (64, 64))
        self.assertEqual(result.depth_m.dtype, np.float32)
        self.assertEqual(result.depth_m[1, 1], 0.25)
        self.assertEqual(result.source.capture_monotonic_ns, 100)

    def test_reject_malformed(self):
        for bad in (float("nan"), float("inf"), -1, 3):
            frame = self.frame()
            frame.depth_m[20] = bad
            with self.assertRaises(ValueError):
                decode(frame, 0)
        frame = self.frame()
        frame.version = 2
        with self.assertRaises(ValueError):
            decode(frame, 0)
        frame = self.frame()
        frame.valid[0] = 2
        with self.assertRaises(ValueError):
            decode(frame, 0)
        frame = self.frame()
        frame.publish_monotonic_ns = 99
        with self.assertRaises(ValueError):
            decode(frame, 0)

    @unittest.skipUnless(os.environ.get("DEPTH_INTEGRATION") == "1", "Set DEPTH_INTEGRATION=1 for UDP integration")
    def test_cpp_python_new_frames_stale_and_restart(self):
        root = Path(__file__).resolve().parents[1]
        # Dedicated test domain, never a motor command topic.
        with DepthReceiver("lo", domain=89) as receiver:
            def start():
                return subprocess.Popen(["bash", str(root / "scripts/depth/run_publisher.sh"),
                                         "--interface", "lo", "--domain", "89", "--synthetic", "--duration", "7"],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            def await_sample(previous_session=None):
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    sample = receiver.get_latest()
                    if sample is not None and sample.session_id != previous_session:
                        return sample
                    time.sleep(0.01)
                self.fail("No new DDS session received within five seconds")
            publisher = start()
            try:
                sample = await_sample()
                self.assertAlmostEqual(float(sample.depth_m[1, 1]), 65 * 2 / 4095, places=6)
                self.assertAlmostEqual(float(sample.depth_m[2, 5]), (2 * 64 + 5) * 2 / 4095, places=6)
                self.assertEqual(sample.depth_m[-1, -1], 2)
                self.assertTrue(sample.valid.all())
                receiver.stats()
                time.sleep(2)
                stats = receiver.stats()
                self.assertGreaterEqual(stats["new_frame_hz"], 50, stats)
                self.assertEqual(stats["duplicates"], 0, stats)
                self.assertEqual(stats["malformed"], 0, stats)
                first_session = sample.session_id
            finally:
                publisher.terminate()
                stdout, stderr = publisher.communicate(timeout=5)
                self.assertEqual(publisher.returncode, 0, stdout + stderr)
            time.sleep(0.15)
            self.assertIsNone(receiver.get_latest())
            publisher = start()
            try:
                sample = await_sample(first_session)
                self.assertNotEqual(sample.session_id, first_session)
            finally:
                publisher.terminate()
                stdout, stderr = publisher.communicate(timeout=5)
                self.assertEqual(publisher.returncode, 0, stdout + stderr)


if __name__ == "__main__":
    unittest.main()
