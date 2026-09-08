"""DDS depth subscriber and Python API. No torch, ROS, or Unitree dependency."""
import argparse
from dataclasses import dataclass
import json
import re
import threading
import time
from typing import Optional

import numpy as np
from cyclonedds.domain import Domain, DomainParticipant
from cyclonedds.idl import IdlStruct
from cyclonedds.idl.annotations import final
from cyclonedds.idl.types import array, float32, float64, int32, uint8, uint32, uint64
from cyclonedds.qos import Policy, Qos
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic

from depth.postprocess import preprocess_depth_for_wmp


@final
@dataclass
class DepthFrame(IdlStruct, typename="go2w_depth::DepthFrame"):
    version: uint32
    session_id: uint64
    frame_id: uint64
    device_timestamp_ms: float64
    timestamp_domain: int32
    capture_monotonic_ns: uint64
    publish_monotonic_ns: uint64
    publish_unix_ns: uint64
    depth_m: array[float32, 4096]
    valid: array[uint8, 4096]


@dataclass
class DepthSample:
    depth_m: np.ndarray
    valid: np.ndarray
    session_id: int
    frame_id: int
    received_monotonic_ns: int
    source: DepthFrame


def decode(frame, received_ns):
    """Reject invalid wire data before it can enter a controller."""
    if frame.version != 1:
        raise ValueError("Unsupported depth protocol version")
    depth = np.asarray(frame.depth_m, dtype=np.float32)
    valid = (np.frombuffer(frame.valid, dtype=np.uint8) if isinstance(frame.valid, (bytes, bytearray))
             else np.asarray(frame.valid, dtype=np.uint8))
    if depth.size != 4096 or valid.size != 4096:
        raise ValueError("Invalid image length")
    if not np.isfinite(depth).all() or (depth < 0).any() or (depth > 2).any():
        raise ValueError("Depth outside finite [0, 2] meters")
    if (valid > 1).any() or frame.publish_monotonic_ns < frame.capture_monotonic_ns:
        raise ValueError("Invalid mask or sender timestamps")
    if np.any((valid == 0) & (depth != 2.0)):
        raise ValueError("Invalid pixels must contain the 2 meter far-plane value")
    return DepthSample(depth.reshape(64, 64).copy(), valid.reshape(64, 64).copy(),
                       frame.session_id, frame.frame_id, received_ns, frame)


def describe_sample(sample, include_wmp=False):
    """Return JSON-friendly quality and optional WMP-input statistics."""
    depth = sample.depth_m
    valid = sample.valid
    result = {
        "session_id": int(sample.session_id),
        "frame_id": int(sample.frame_id),
        "shape": list(depth.shape),
        "dtype": str(depth.dtype),
        "depth_min_m": float(np.min(depth)),
        "depth_max_m": float(np.max(depth)),
        "depth_mean_m": float(np.mean(depth)),
        "valid_ratio": float(np.mean(valid != 0)),
        "invalid_pixels": int(np.count_nonzero(valid == 0)),
    }
    if include_wmp:
        depth_wmp = preprocess_depth_for_wmp(depth)
        result.update(
            wmp_shape=list(depth_wmp.shape),
            wmp_dtype=str(depth_wmp.dtype),
            wmp_min=float(np.min(depth_wmp)),
            wmp_max=float(np.max(depth_wmp)),
            wmp_mean=float(np.mean(depth_wmp)),
        )
    return result


def _labeled_panel(cv2, image, title):
    image = cv2.resize(image, (320, 320), interpolation=cv2.INTER_NEAREST)
    canvas = np.full((356, 320, 3), 245, dtype=np.uint8)
    canvas[36:] = image
    cv2.putText(canvas, title, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 1)
    return canvas


def build_preview(cv2, sample, include_wmp=False):
    """Build depth, validity and optional WMP panels for human inspection."""
    if sample is None:
        canvas = np.zeros((356, 640, 3), dtype=np.uint8)
        cv2.putText(canvas, "STALE / NO DATA", (150, 180), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (255, 255, 255), 2)
        return canvas

    valid = sample.valid.astype(bool)
    meters_u8 = np.rint(sample.depth_m * 127.5).astype(np.uint8)
    meters = cv2.cvtColor(meters_u8, cv2.COLOR_GRAY2BGR)
    meters[~valid] = (255, 0, 255)
    valid_view = cv2.cvtColor((valid.astype(np.uint8) * 255), cv2.COLOR_GRAY2BGR)
    panels = [
        _labeled_panel(cv2, meters, "meters: 0 black / 2 white"),
        _labeled_panel(cv2, valid_view, "valid mask: white = valid"),
    ]
    if include_wmp:
        depth_wmp = preprocess_depth_for_wmp(sample.depth_m)
        wmp_u8 = np.rint((depth_wmp + 0.5) * 255.0).astype(np.uint8)
        wmp_view = cv2.cvtColor(wmp_u8, cv2.COLOR_GRAY2BGR)
        panels.append(_labeled_panel(cv2, wmp_view, "WMP input: -0.5 to +0.5"))
    return np.concatenate(panels, axis=1)


class DepthReceiver:
    def __init__(self, interface, domain=42, topic="rt/depth/image64"):
        if not re.fullmatch(r"[a-zA-Z0-9_.:-]+", interface):
            raise ValueError("Invalid network interface")
        xml = ('<CycloneDDS><Domain><General><Interfaces><NetworkInterface name="' +
               interface + '"/></Interfaces><MaxMessageSize>1400B</MaxMessageSize>'
               '<FragmentSize>1280B</FragmentSize></General></Domain></CycloneDDS>')
        self._domain = Domain(domain, config=xml)
        self._participant = DomainParticipant(domain)
        self._topic = Topic(self._participant, topic, DepthFrame)
        qos = Qos(Policy.Reliability.BestEffort, Policy.History.KeepLast(1), Policy.Durability.Volatile)
        self._reader = DataReader(self._participant, self._topic, qos=qos)
        self._lock = threading.Lock()
        self._latest = None
        self._stop = threading.Event()
        self._error = None
        self._last_key = None
        self._window_count = 0
        self._intervals_ms = []
        self._processing_ms = []
        self._last_received_ns = None
        self._started_ns = time.monotonic_ns()
        self._window_start_ns = self._started_ns
        self._counters = dict(received=0, duplicates=0, out_of_order=0, missing=0,
                              malformed=0, sessions=0, source_lagged=0)
        self._thread = threading.Thread(target=self._run, name="depth-dds", daemon=True)
        self._thread.start()

    def _run(self):
        try:
            while not self._stop.is_set():
                messages = self._reader.take(1)
                if not messages:
                    self._stop.wait(0.001)
                    continue
                frame = messages[-1]
                if not isinstance(frame, DepthFrame):
                    continue  # DDS instance lifecycle notification
                now = time.monotonic_ns()
                try:
                    sample = decode(frame, now)
                except (ValueError, TypeError):
                    with self._lock:
                        self._counters["malformed"] += 1
                    continue
                with self._lock:
                    key = (sample.session_id, sample.frame_id)
                    if self._last_key and key[0] == self._last_key[0]:
                        if key[1] == self._last_key[1]:
                            self._counters["duplicates"] += 1
                            continue
                        if key[1] < self._last_key[1]:
                            self._counters["out_of_order"] += 1
                            continue
                        self._counters["missing"] += max(0, key[1] - self._last_key[1] - 1)
                    else:
                        self._counters["sessions"] += 1
                    self._last_key = key
                    # Sender-local processing delay needs no cross-host clock sync.
                    processing_ms = (frame.publish_monotonic_ns - frame.capture_monotonic_ns) / 1e6
                    if processing_ms > 100:
                        self._counters["source_lagged"] += 1
                        continue
                    if self._last_received_ns is not None:
                        self._intervals_ms.append((now - self._last_received_ns) / 1e6)
                    self._last_received_ns = now
                    self._window_count += 1
                    self._processing_ms.append(processing_ms)
                    # Bounded diagnostics even when the caller never requests stats.
                    self._intervals_ms = self._intervals_ms[-4096:]
                    self._processing_ms = self._processing_ms[-4096:]
                    self._latest = sample
                    self._counters["received"] += 1
        except Exception as exc:
            self._error = exc

    def get_latest(self, max_age_ms=100) -> Optional[DepthSample]:
        """Return a copy or None; age is receiver-local plus sender processing age.

        Network transit time is unknown without synchronized host clocks.
        """
        if max_age_ms < 0:
            raise ValueError("max_age_ms must be nonnegative")
        if self._error:
            raise RuntimeError("Depth receiver failed") from self._error
        with self._lock:
            s = self._latest
            if s is None:
                return None
            local_age = time.monotonic_ns() - s.received_monotonic_ns
            processing_age = s.source.publish_monotonic_ns - s.source.capture_monotonic_ns
            if (local_age + processing_age) / 1e6 > max_age_ms:
                return None
            return DepthSample(s.depth_m.copy(), s.valid.copy(), s.session_id,
                               s.frame_id, s.received_monotonic_ns, s.source)

    def stats(self):
        with self._lock:
            now = time.monotonic_ns()
            seconds = (now - self._window_start_ns) / 1e9
            result = dict(self._counters)
            result["window_s"] = seconds
            result["new_frame_hz"] = self._window_count / seconds if seconds else 0
            result["age_ms"] = (now - self._last_received_ns) / 1e6 if self._last_received_ns else None
            for name, values in (("interval_ms", self._intervals_ms), ("processing_ms", self._processing_ms)):
                for suffix, percentile in (("p50", 50), ("p95", 95), ("p99", 99), ("max", 100)):
                    result[name + "_" + suffix] = float(np.percentile(values, percentile)) if values else None
            self._window_count = 0
            self._intervals_ms.clear()
            self._processing_ms.clear()
            self._window_start_ns = now
            result["error"] = str(self._error) if self._error else None
            return result

    def close(self):
        self._stop.set()
        self._thread.join(timeout=3)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", required=True)
    parser.add_argument("--domain", type=int, default=42)
    parser.add_argument("--topic", default="rt/depth/image64")
    parser.add_argument("--duration", type=float, default=0)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument(
        "--wmp-postprocess",
        action="store_true",
        help="Apply and report the exact NumPy preprocessing used by Go2WWMP",
    )
    parser.add_argument("--output", help="Write JSONL statistics to this file")
    parser.add_argument(
        "--save-sample",
        help="Save latest fresh sample as NPZ; includes depth_wmp with --wmp-postprocess",
    )
    args = parser.parse_args()
    if not args.interface or not args.interface.strip():
        parser.error("--interface is empty; set DEPTH_IF to the actual wired NIC from 'ip -br addr'")
    if args.duration < 0:
        parser.error("--duration must be nonnegative; use 0 to run until interrupted")
    output = None
    cv2 = None
    last_sample = None
    if args.preview:
        try:
            import cv2
        except ModuleNotFoundError as exc:
            parser.error(f"--preview requires OpenCV (cv2): {exc}")
    try:
        with DepthReceiver(args.interface, args.domain, args.topic) as receiver:
            if args.output:
                output = open(args.output, "w")
            start = time.monotonic()
            next_report = start + 10
            while args.duration <= 0 or time.monotonic() - start < args.duration:
                now = time.monotonic()
                sample = receiver.get_latest()
                if sample is not None:
                    if last_sample is None:
                        first = describe_sample(sample, args.wmp_postprocess)
                        first["event"] = "first_frame"
                        line = json.dumps(first)
                        print(line, flush=True)
                        if output:
                            output.write(line + "\n")
                            output.flush()
                    last_sample = sample
                if now >= next_report:
                    data = receiver.stats()
                    data["below_target"] = data["new_frame_hz"] < 50
                    data["stale"] = sample is None
                    if sample is not None:
                        data.update(describe_sample(sample, args.wmp_postprocess))
                    line = json.dumps(data)
                    print(line, flush=True)
                    if output:
                        output.write(line + "\n")
                        output.flush()
                    next_report = now + 10
                if cv2 is not None:
                    cv2.imshow("Go2W received depth", build_preview(cv2, sample, args.wmp_postprocess))
                    if cv2.waitKey(1) & 0xff in (27, ord("q")):
                        break
                time.sleep(0.01)
            final = receiver.stats()
            final["event"] = "final"
            final["received_any"] = last_sample is not None
            if last_sample is not None:
                final.update(describe_sample(last_sample, args.wmp_postprocess))
            line = json.dumps(final)
            print(line, flush=True)
            if output:
                output.write(line + "\n")
                output.flush()
    except KeyboardInterrupt:
        pass
    finally:
        if args.save_sample and last_sample is not None:
            arrays = dict(
                depth_m=last_sample.depth_m,
                valid=last_sample.valid,
                session_id=np.uint64(last_sample.session_id),
                frame_id=np.uint64(last_sample.frame_id),
                device_timestamp_ms=last_sample.source.device_timestamp_ms,
                timestamp_domain=last_sample.source.timestamp_domain,
                capture_monotonic_ns=np.uint64(last_sample.source.capture_monotonic_ns),
                publish_monotonic_ns=np.uint64(last_sample.source.publish_monotonic_ns),
                publish_unix_ns=np.uint64(last_sample.source.publish_unix_ns),
            )
            if args.wmp_postprocess:
                arrays["depth_wmp"] = preprocess_depth_for_wmp(last_sample.depth_m)
            np.savez_compressed(args.save_sample, **arrays)
        if output:
            output.close()
        if cv2 is not None:
            cv2.destroyAllWindows()
    if last_sample is None:
        print("No fresh depth frame was received.", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
