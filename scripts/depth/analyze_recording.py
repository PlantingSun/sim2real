#!/usr/bin/env python3
"""Analyze invalid-depth regions in a recorded NPZ sequence.

The analysis is read-only: it reports invalid-mask geometry and neighboring
depth statistics but never rewrites the depth image or produces control data.
OpenCV is used only for 8-connected components and the optional heatmap.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import numpy as np


def _percentiles(values):
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return {"min": None, "p50": None, "p95": None, "max": None}
    return {
        "min": float(np.min(values)),
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "max": float(np.max(values)),
    }


def analyze(path: Path, output_json: Path, output_image: Optional[Path] = None) -> dict:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError("analyze_recording.py requires OpenCV (cv2)") from exc

    data = np.load(path, allow_pickle=False)
    if "depth_m" not in data or "valid" not in data:
        raise ValueError("recording must contain depth_m and valid")
    depth = np.asarray(data["depth_m"], dtype=np.float32)
    valid = np.asarray(data["valid"], dtype=np.uint8)
    if depth.ndim == 2 and depth.shape == (64, 64):
        depth = depth[None, ...]
        valid = valid[None, ...]
    if depth.ndim != 3 or depth.shape[1:] != (64, 64) or valid.shape != depth.shape:
        raise ValueError(f"expected depth_m/valid shape (N,64,64), got {depth.shape}/{valid.shape}")
    if not np.isfinite(depth).all() or (depth < 0).any() or (depth > 2).any():
        raise ValueError("recording depth contains values outside finite [0,2]")

    frame_ids = np.asarray(data["frame_id"]).reshape(-1) if "frame_id" in data else None
    session_ids = np.asarray(data["session_id"]).reshape(-1) if "session_id" in data else None
    if frame_ids is not None and frame_ids.size not in (1, depth.shape[0]):
        raise ValueError("frame_id length does not match depth frames")
    if session_ids is not None and session_ids.size not in (1, depth.shape[0]):
        raise ValueError("session_id length does not match depth frames")
    invalid = valid == 0
    valid_ratio = np.mean(~invalid, axis=(1, 2))
    invalid_counts = np.count_nonzero(invalid, axis=(1, 2))
    largest_areas = []
    component_counts = []
    top_components = []
    neighbor_medians = []
    invalid_frequency = np.sum(invalid, axis=0, dtype=np.uint32)
    kernel = np.ones((3, 3), dtype=np.uint8)
    for frame_index, mask in enumerate(invalid):
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            mask.astype(np.uint8), connectivity=8
        )
        areas = stats[1:, cv2.CC_STAT_AREA]
        component_counts.append(max(0, count - 1))
        largest_areas.append(int(np.max(areas)) if areas.size else 0)
        if not areas.size:
            continue
        order = np.argsort(areas)[::-1]
        largest_label = int(order[0] + 1)
        largest = labels == largest_label
        ring = cv2.dilate(largest.astype(np.uint8), kernel, iterations=1).astype(bool)
        ring &= ~largest & ~mask
        ring_values = depth[frame_index][ring]
        if ring_values.size:
            neighbor_medians.append(float(np.median(ring_values)))
        for order_index in order[:3]:
            label = int(order_index + 1)
            area = int(stats[label, cv2.CC_STAT_AREA])
            top_components.append({
                "frame_index": int(frame_index),
                "frame_id": int(frame_ids[min(frame_index, frame_ids.size - 1)])
                if frame_ids is not None else None,
                "area": area,
                "bbox_xywh": [int(stats[label, i]) for i in range(4)],
            })

    top_components.sort(key=lambda item: item["area"], reverse=True)
    pixel_fraction = invalid_frequency.astype(np.float64) / max(1, depth.shape[0])
    top_pixels = []
    for flat in np.argsort(pixel_fraction.ravel())[::-1][:20]:
        y, x = np.unravel_index(flat, pixel_fraction.shape)
        if pixel_fraction[y, x] <= 0:
            break
        top_pixels.append({"x": int(x), "y": int(y), "invalid_fraction": float(pixel_fraction[y, x])})

    summary = {
        "input": str(path),
        "frames": int(depth.shape[0]),
        "sessions": int(len(set(int(value) for value in session_ids)))
        if session_ids is not None else None,
        "valid_ratio": _percentiles(valid_ratio),
        "invalid_pixels": _percentiles(invalid_counts),
        "component_count": _percentiles(component_counts),
        "largest_component_area": _percentiles(largest_areas),
        "largest_component_neighbor_median_m": _percentiles(neighbor_medians),
        "top_components": top_components[:20],
        "top_persistent_invalid_pixels": top_pixels,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    if output_image is not None:
        image = np.rint(np.clip(pixel_fraction, 0, 1) * 255).astype(np.uint8)
        image = cv2.applyColorMap(image, cv2.COLORMAP_TURBO)
        cv2.imwrite(str(output_image), image)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-image", type=Path)
    args = parser.parse_args()
    if not args.recording.is_file():
        parser.error(f"recording not found: {args.recording}")
    output_json = args.output_json or args.recording.with_name(args.recording.stem + "_analysis.json")
    try:
        summary = analyze(args.recording, output_json, args.output_image)
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 2
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
