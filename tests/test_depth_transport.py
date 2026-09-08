"""Run with the project's DDS library path; integration requires local UDP sockets."""
import os
from pathlib import Path
import subprocess
import time
import unittest

import numpy as np
from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.qos import Policy, Qos
from cyclonedds.topic import Topic
from depth.postprocess import preprocess_depth_for_wmp
from depth.receiver import DepthFrame, DepthReceiver, decode, describe_sample


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

        frame = self.frame()
        frame.valid[0] = 0
        with self.assertRaisesRegex(ValueError, "far-plane"):
            decode(frame, 0)

        frame.depth_m[0] = 2.0
        self.assertEqual(decode(frame, 0).valid[0, 0], 0)

    def test_shared_wmp_postprocess_and_summary(self):
        depth = np.ones((64, 64), dtype=np.float32)
        depth[0, :8] = [-1.0, 0.0, 0.5, 1.0, 2.0, 3.0, np.nan, np.inf]
        original = depth.copy()

        result = preprocess_depth_for_wmp(depth)

        np.testing.assert_allclose(
            result[0, :8], [-0.5, -0.5, -0.25, 0.0, 0.5, 0.5, 0.5, 0.5]
        )
        np.testing.assert_equal(depth, original)
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(result.flags.c_contiguous)

        sample = decode(self.frame(), 400)
        summary = describe_sample(sample, include_wmp=True)
        self.assertEqual(summary["shape"], [64, 64])
        self.assertEqual(summary["dtype"], "float32")
        self.assertEqual(summary["valid_ratio"], 1.0)
        self.assertEqual(summary["wmp_shape"], [64, 64])
        self.assertEqual(summary["wmp_min"], 0.0)
        self.assertEqual(summary["wmp_max"], 0.0)

    @unittest.skipUnless(os.environ.get("DEPTH_INTEGRATION") == "1", "Set DEPTH_INTEGRATION=1 for UDP integration")
    def test_python_new_frames_stale_and_new_session(self):
        depth = np.linspace(0.0, 2.0, 4096, dtype=np.float32).tolist()
        valid = [1] * 4096
        qos = Qos(Policy.Reliability.BestEffort, Policy.History.KeepLast(1),
                  Policy.Durability.Volatile)
        with DepthReceiver("lo", domain=89) as receiver:
            participant = DomainParticipant(89)
            topic = Topic(participant, "rt/depth/image64", DepthFrame)
            writer = DataWriter(participant, topic, qos=qos)
            time.sleep(0.2)  # Local discovery.

            receiver.stats()
            for frame_id in range(120):
                capture_ns = time.monotonic_ns()
                writer.write(DepthFrame(1, 101, frame_id, float(frame_id), -1,
                                        capture_ns, capture_ns + 1000, time.time_ns(),
                                        depth, valid))
                time.sleep(1 / 60)

            sample = receiver.get_latest()
            self.assertIsNotNone(sample)
            self.assertEqual(sample.session_id, 101)
            self.assertAlmostEqual(float(sample.depth_m[1, 1]), 65 * 2 / 4095, places=6)
            self.assertTrue(sample.valid.all())
            self.assertEqual(preprocess_depth_for_wmp(sample.depth_m).shape, (64, 64))
            stats = receiver.stats()
            self.assertGreaterEqual(stats["new_frame_hz"], 50, stats)
            self.assertEqual(stats["duplicates"], 0, stats)
            self.assertEqual(stats["malformed"], 0, stats)

            time.sleep(0.15)
            self.assertIsNone(receiver.get_latest())
            capture_ns = time.monotonic_ns()
            writer.write(DepthFrame(1, 202, 0, 0.0, -1, capture_ns,
                                    capture_ns + 1000, time.time_ns(), depth, valid))
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                sample = receiver.get_latest()
                if sample is not None and sample.session_id == 202:
                    break
                time.sleep(0.01)
            self.assertIsNotNone(sample)
            self.assertEqual(sample.session_id, 202)

    @unittest.skipUnless(os.environ.get("DEPTH_CPP_INTEGRATION") == "1",
                         "Set DEPTH_CPP_INTEGRATION=1 for C++ publisher integration")
    def test_cpp_python_new_frames_stale_and_restart(self):
        root = Path(__file__).resolve().parents[1]
        if not (root / "build/depth/go2w_depth").is_file():
            self.skipTest("C++ depth publisher is not built on this host")
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
