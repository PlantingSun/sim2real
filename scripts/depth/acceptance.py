"""Run an instrumented DDS receive test; optionally launch a camera/synthetic publisher.

Uses dedicated depth topics only. Reports machine-readable evidence, never motion commands.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np
from config.go2w_config import DDS
from depth.postprocess import preprocess_depth_for_wmp
from depth.receiver import DepthReceiver


def process_usage(pid):
    try:
        fields = Path("/proc/{}/stat".format(pid)).read_text().split(")", 1)[1].split()
        return ((int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK"),
                int(fields[21]) * os.sysconf("SC_PAGE_SIZE") / 1024**2)
    except (OSError, IndexError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", default=DDS.DEPTH_NET_IF)
    parser.add_argument("--domain", type=int, default=42)
    parser.add_argument("--duration", type=float, default=1800)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--launch", choices=("camera", "synthetic"))
    parser.add_argument("--allow-partial-fov", action="store_true")
    parser.add_argument("--no-spatial", action="store_true")
    parser.add_argument("--publisher-pid", type=int)
    parser.add_argument(
        "--wmp-postprocess",
        action="store_true",
        help="Continuously validate and save the exact Go2WWMP input conversion",
    )
    args = parser.parse_args()
    if args.duration < 10:
        parser.error("Use at least 10 seconds")
    root = Path(__file__).resolve().parents[2]
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite prior evidence.
    publisher = None
    log = None
    windows = []
    frames = []
    last_key = None
    previous_usage = None
    previous_time = None
    wmp_failures = 0
    wmp_min = None
    wmp_max = None
    try:
        with DepthReceiver(args.interface, domain=args.domain) as receiver:
            if args.launch:
                command = ["bash", str(root / "scripts/depth/run_publisher.sh"), "--interface", args.interface,
                           "--domain", str(args.domain), "--duration", str(args.duration + 20)]
                if args.launch == "synthetic":
                    command.append("--synthetic")
                if args.allow_partial_fov:
                    command.append("--allow-partial-fov")
                if args.no_spatial:
                    command.append("--no-spatial")
                log = (output / "publisher.log").open("w")
                publisher = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                args.publisher_pid = publisher.pid
            deadline = time.monotonic() + 15
            while receiver.get_latest() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            if receiver.get_latest() is None:
                raise RuntimeError("No fresh depth within 15 seconds; see publisher.log or service journal")
            # Allow discovery, camera warmup and first-delivery transient to settle.
            time.sleep(1)
            receiver.stats()
            start = time.monotonic()
            next_report = start + 10
            previous_time = start
            previous_usage = process_usage(args.publisher_pid) if args.publisher_pid else None
            with (output / "receiver.jsonl").open("w") as stream:
                while time.monotonic() - start < args.duration:
                    now = time.monotonic()
                    sample = receiver.get_latest()
                    if sample is not None and (sample.session_id, sample.frame_id) != last_key:
                        last_key = (sample.session_id, sample.frame_id)
                        depth_wmp = None
                        if args.wmp_postprocess:
                            try:
                                depth_wmp = preprocess_depth_for_wmp(sample.depth_m)
                            except (TypeError, ValueError, FloatingPointError):
                                wmp_failures += 1
                            else:
                                current_min = float(np.min(depth_wmp))
                                current_max = float(np.max(depth_wmp))
                                wmp_min = current_min if wmp_min is None else min(wmp_min, current_min)
                                wmp_max = current_max if wmp_max is None else max(wmp_max, current_max)
                        # Last 120 frames support spatial/temporal quality inspection.
                        frames.append((sample.depth_m, sample.valid, sample.frame_id, depth_wmp))
                        frames = frames[-120:]
                    if now >= next_report:
                        stats = receiver.stats()
                        stats["elapsed_s"] = now - start
                        stats["unix_s"] = time.time()
                        stats["fresh"] = sample is not None
                        if args.wmp_postprocess:
                            stats["wmp_failures"] = wmp_failures
                        usage = process_usage(args.publisher_pid) if args.publisher_pid else None
                        if usage and previous_usage:
                            stats["publisher_cpu_percent_one_core"] = 100 * (usage[0] - previous_usage[0]) / (now - previous_time)
                            stats["publisher_rss_mb"] = usage[1]
                        previous_usage, previous_time = usage, now
                        windows.append(stats)
                        line = json.dumps(stats)
                        stream.write(line + "\n")
                        stream.flush()
                        print(line, flush=True)
                        next_report += 10
                    time.sleep(0.005)
                # Include final full window (duration is usually a multiple of 10).
                stats = receiver.stats()
                if stats["window_s"] >= 9.5:
                    stats["elapsed_s"] = time.monotonic() - start
                    stats["unix_s"] = time.time()
                    stats["fresh"] = receiver.get_latest() is not None
                    if args.wmp_postprocess:
                        stats["wmp_failures"] = wmp_failures
                    windows.append(stats)
                    stream.write(json.dumps(stats) + "\n")
            if frames:
                arrays = dict(
                    depth_m=np.stack([f[0] for f in frames]),
                    valid=np.stack([f[1] for f in frames]),
                    frame_id=np.asarray([f[2] for f in frames], dtype=np.uint64),
                )
                if args.wmp_postprocess and all(f[3] is not None for f in frames):
                    arrays["depth_wmp"] = np.stack([f[3] for f in frames])
                np.savez_compressed(output / "last_frames.npz", **arrays)
            fps_pass = bool(windows) and all(w["new_frame_hz"] >= 50 and w["fresh"] and not w["error"] for w in windows)
            gap_pass = bool(windows) and all((w["interval_ms_max"] or 0) <= 100 for w in windows)
            integrity_pass = bool(windows) and all(w["malformed"] == 0 and w["duplicates"] == 0 and
                                                  w["out_of_order"] == 0 and w["source_lagged"] == 0
                                                  for w in windows)
            wmp_pass = not args.wmp_postprocess or (
                wmp_failures == 0
                and wmp_min is not None
                and wmp_max is not None
                and -0.5 <= wmp_min <= wmp_max <= 0.5
            )
            summary = dict(duration_s=time.monotonic() - start, interface=args.interface, domain=args.domain,
                           launch=args.launch,
                           partial_fov=args.allow_partial_fov if args.launch else None,
                           spatial=not args.no_spatial if args.launch else None,
                           windows=len(windows), min_new_frame_hz=min((w["new_frame_hz"] for w in windows), default=0),
                           max_gap_ms=max((w["interval_ms_max"] or 0 for w in windows), default=0),
                           fps_pass=fps_pass, gap_pass=gap_pass, integrity_pass=integrity_pass,
                           wmp_postprocess=args.wmp_postprocess, wmp_pass=wmp_pass,
                           wmp_failures=wmp_failures,
                           wmp_min=wmp_min, wmp_max=wmp_max,
                           note="Same-host receive is not proof of laptop/long-cable delivery" if args.launch else
                                "Confirm sender host and cable topology separately")
            (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            print(json.dumps(summary), flush=True)
            return 0 if fps_pass and gap_pass and integrity_pass and wmp_pass else 2
    finally:
        if publisher:
            publisher.terminate()
            try:
                publisher.wait(timeout=8)
            except subprocess.TimeoutExpired:
                publisher.kill()
                publisher.wait()
        if log:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
