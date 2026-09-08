#!/usr/bin/env python3
"""Play a recorded depth NPZ locally for visual inspection only."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from depth.postprocess import preprocess_depth_for_wmp


def _panel(cv2, image, title):
    image = cv2.resize(image, (320, 320), interpolation=cv2.INTER_NEAREST)
    canvas = np.full((356, 320, 3), 245, dtype=np.uint8)
    canvas[36:] = image
    cv2.putText(canvas, title, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 1)
    return canvas


def _build_view(cv2, depth_m, valid, index, frame_id, session_id, elapsed_s, gap_ms):
    valid_bool = valid.astype(bool)
    meters_u8 = np.rint(np.clip(depth_m, 0, 2) * 127.5).astype(np.uint8)
    meters = cv2.applyColorMap(meters_u8, cv2.COLORMAP_JET)
    meters[~valid_bool] = (255, 0, 255)
    valid_view = cv2.cvtColor((valid_bool.astype(np.uint8) * 255), cv2.COLOR_GRAY2BGR)
    wmp = preprocess_depth_for_wmp(depth_m)
    wmp_u8 = np.rint(np.clip((wmp + 0.5) * 255, 0, 255)).astype(np.uint8)
    wmp_view = cv2.cvtColor(wmp_u8, cv2.COLOR_GRAY2BGR)
    view = np.concatenate(
        [
            _panel(cv2, meters, "meters; magenta=invalid"),
            _panel(cv2, valid_view, "valid mask; white=valid"),
            _panel(cv2, wmp_view, "WMP input; -0.5..+0.5"),
        ],
        axis=1,
    )
    text = (
        f"frame {index + 1}  source={int(frame_id)}  session={int(session_id)}  "
        f"valid={valid_bool.mean():.3f}  t={elapsed_s:.1f}s"
    )
    cv2.putText(view, text, (8, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    if gap_ms > 1000:
        cv2.putText(
            view,
            f"RECORDED GAP {gap_ms / 1000:.1f}s (playback cap applied)",
            (8, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            1,
        )
    return view


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--speed", type=float, default=1.0, help="播放速度倍数")
    parser.add_argument(
        "--max-gap-ms",
        type=float,
        default=1000.0,
        help="回放时单帧间隔的最大等待；设为 60000 可保留完整长空档",
    )
    args = parser.parse_args()
    if not args.recording.is_file():
        parser.error(f"recording not found: {args.recording}")
    if args.speed <= 0 or args.max_gap_ms < 0:
        parser.error("speed 必须为正数，max-gap-ms 不能为负数")

    try:
        import cv2
    except ModuleNotFoundError as exc:
        print(f"[FAIL] replay requires OpenCV (cv2): {exc}")
        return 2
    data = np.load(args.recording, allow_pickle=False)
    required = ("depth_m", "valid", "frame_id", "session_id", "received_monotonic_ns")
    missing = [key for key in required if key not in data]
    if missing:
        print(f"[FAIL] recording missing fields: {missing}")
        return 2
    depth = np.asarray(data["depth_m"], dtype=np.float32)
    valid = np.asarray(data["valid"], dtype=np.uint8)
    if depth.ndim != 3 or depth.shape[1:] != (64, 64) or valid.shape != depth.shape:
        print(f"[FAIL] expected depth/valid shape (N,64,64), got {depth.shape}/{valid.shape}")
        return 2
    frame_id = np.asarray(data["frame_id"]).reshape(-1)
    session_id = np.asarray(data["session_id"]).reshape(-1)
    received_ns = np.asarray(data["received_monotonic_ns"], dtype=np.uint64).reshape(-1)
    if not (len(frame_id) == len(session_id) == len(received_ns) == len(depth)):
        print("[FAIL] recording metadata length does not match frames")
        return 2

    cv2.namedWindow("Go2W depth recording", cv2.WINDOW_NORMAL)
    try:
        for index in range(len(depth)):
            elapsed_s = (int(received_ns[index]) - int(received_ns[0])) / 1.0e9
            gap_ms = 0.0
            if index:
                gap_ms = (int(received_ns[index]) - int(received_ns[index - 1])) / 1.0e6
            view = _build_view(
                cv2,
                depth[index],
                valid[index],
                index,
                frame_id[index],
                session_id[index],
                elapsed_s,
                gap_ms,
            )
            cv2.imshow("Go2W depth recording", view)
            if index + 1 < len(depth):
                recorded_gap_ms = min(gap_ms, args.max_gap_ms)
                wait_ms = max(1, int(recorded_gap_ms / args.speed))
            else:
                wait_ms = 1
            key = cv2.waitKey(wait_ms) & 0xFF
            if key in (27, ord("q")):
                break
            if key == ord(" "):
                while True:
                    pause_key = cv2.waitKey(50) & 0xFF
                    if pause_key in (27, ord("q")):
                        return 0
                    if pause_key == ord(" "):
                        break
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
