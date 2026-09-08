#!/usr/bin/env python3
"""Record a read-only depth sequence for offline invalid-region analysis.

This tool subscribes to depth domain 42 only.  It never creates a motor
participant, sends a command, or starts a robot-control process.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np

from config.go2w_config import DDS
from depth.receiver import DepthReceiver


def _save_record(output: Path, frames: list) -> dict:
    if not frames:
        return {"frames": 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing recording: {output}")

    depth_m = np.stack([frame.depth_m for frame in frames]).astype(np.float32)
    valid = np.stack([frame.valid for frame in frames]).astype(np.uint8)
    frame_id = np.asarray([frame.frame_id for frame in frames], dtype=np.uint64)
    session_id = np.asarray([frame.session_id for frame in frames], dtype=np.uint64)
    received_ns = np.asarray(
        [frame.received_monotonic_ns for frame in frames], dtype=np.uint64
    )
    capture_ns = np.asarray(
        [frame.source.capture_monotonic_ns for frame in frames], dtype=np.uint64
    )
    publish_ns = np.asarray(
        [frame.source.publish_monotonic_ns for frame in frames], dtype=np.uint64
    )
    publish_unix_ns = np.asarray(
        [frame.source.publish_unix_ns for frame in frames], dtype=np.uint64
    )
    device_timestamp_ms = np.asarray(
        [frame.source.device_timestamp_ms for frame in frames], dtype=np.float64
    )
    timestamp_domain = np.asarray(
        [frame.source.timestamp_domain for frame in frames], dtype=np.int32
    )
    valid_ratio = np.mean(valid != 0, axis=(1, 2)).astype(np.float32)
    np.savez_compressed(
        output,
        depth_m=depth_m,
        valid=valid,
        frame_id=frame_id,
        session_id=session_id,
        received_monotonic_ns=received_ns,
        capture_monotonic_ns=capture_ns,
        publish_monotonic_ns=publish_ns,
        publish_unix_ns=publish_unix_ns,
        device_timestamp_ms=device_timestamp_ms,
        timestamp_domain=timestamp_domain,
        valid_ratio=valid_ratio,
    )

    received_s = received_ns.astype(np.float64) / 1.0e9
    gaps_ms = np.diff(received_s) * 1000.0 if len(received_s) > 1 else np.empty(0)
    summary = {
        "frames": int(len(frames)),
        "sessions": int(len(set(int(value) for value in session_id))),
        "first_frame": int(frame_id[0]),
        "last_frame": int(frame_id[-1]),
        "duration_s": float(received_s[-1] - received_s[0]) if len(received_s) > 1 else 0.0,
        "frame_hz": float((len(frames) - 1) / (received_s[-1] - received_s[0]))
        if len(received_s) > 1 and received_s[-1] > received_s[0]
        else 0.0,
        "max_gap_ms": float(np.max(gaps_ms)) if gaps_ms.size else 0.0,
        "min_valid_ratio": float(np.min(valid_ratio)),
        "median_valid_ratio": float(np.median(valid_ratio)),
        "max_invalid_pixels": int(np.max(np.count_nonzero(valid == 0, axis=(1, 2)))),
        "output": str(output),
    }
    output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", default=DDS.DEPTH_NET_IF,
                        help=f"深度 DDS 网卡；默认 {DDS.DEPTH_NET_IF}")
    parser.add_argument("--domain", type=int, default=42)
    parser.add_argument("--topic", default="rt/depth/image64")
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--output", required=True, help="输出 NPZ 路径；不会覆盖已有文件")
    args = parser.parse_args()
    if not args.interface.strip():
        parser.error("--interface 不能为空；请在 config/go2w_config.py 中确认固定网口")
    if args.duration <= 0:
        parser.error("--duration 必须为正数")
    if Path(args.output).exists():
        parser.error(f"输出文件已存在，为避免覆盖请更换 --output: {args.output}")

    frames = []
    last_key = None
    start = time.monotonic()
    deadline = start + args.duration
    next_report = start + 10.0
    record_error = None
    try:
        with DepthReceiver(args.interface, domain=args.domain, topic=args.topic) as receiver:
            while time.monotonic() < deadline:
                sample = receiver.get_latest(max_age_ms=200.0)
                if sample is not None:
                    key = (sample.session_id, sample.frame_id)
                    if key != last_key:
                        frames.append(sample)
                        last_key = key
                now = time.monotonic()
                if now >= next_report:
                    ratio = float(np.mean(frames[-1].valid != 0)) if frames else None
                    print(
                        json.dumps({
                            "elapsed_s": now - start,
                            "frames": len(frames),
                            "latest_valid_ratio": ratio,
                        }),
                        flush=True,
                    )
                    next_report += 10.0
                time.sleep(0.001)
    except KeyboardInterrupt:
        print("[STOP] interrupted; saving frames collected so far")
    except Exception as exc:
        print(f"[FAIL] depth recording stopped: {type(exc).__name__}: {exc}")
        record_error = f"{type(exc).__name__}: {exc}"

    if not frames:
        print("[FAIL] no fresh depth frames were recorded")
        return 2
    try:
        summary = _save_record(Path(args.output), frames)
    except Exception as exc:
        print(f"[FAIL] could not save recording: {type(exc).__name__}: {exc}")
        return 2
    summary.update(
        interface=args.interface,
        domain=args.domain,
        topic=args.topic,
        requested_duration_s=args.duration,
    )
    if record_error is not None:
        summary["record_error"] = record_error
    Path(args.output).with_suffix(".json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 2 if record_error is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
