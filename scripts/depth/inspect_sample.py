"""Visualize measured depth snapshots; never changes the source data."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def panel(depth, mask, title):
    scaled = np.rint(np.clip(np.nan_to_num(depth, nan=2), 0, 2) * 127.5).astype(np.uint8)
    colored = cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)
    colored[~mask.astype(bool)] = (255, 0, 255)
    image = cv2.resize(colored, (512, 512), interpolation=cv2.INTER_NEAREST)
    canvas = np.full((560, 512, 3), 240, dtype=np.uint8)
    canvas[48:] = image
    cv2.putText(canvas, title, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)
    return canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--output", required=True, help="New PNG path")
    args = parser.parse_args()
    if Path(args.output).exists():
        parser.error("Output exists; choose a new path")
    if args.input.endswith(".npz"):
        with np.load(args.input) as data:
            depth, valid = data["depth_m"], data["valid"]
            if depth.ndim == 3:
                depth, valid = depth[-1], valid[-1]
        panels = [panel(depth, valid, "64x64 meters; invalid = magenta")]
    else:
        data = cv2.FileStorage(args.input, cv2.FILE_STORAGE_READ)
        if not data.isOpened():
            raise RuntimeError("Cannot open snapshot")
        raw = data.getNode("raw_depth_m").mat()
        filtered = data.getNode("filtered_depth_m").mat()
        depth = data.getNode("depth64_m").mat()
        valid = data.getNode("valid64").mat()
        data.release()
        panels = [panel(raw, np.isfinite(raw) & (raw > 0), "Raw Z depth (aspect stretched for view)"),
                  panel(filtered, np.isfinite(filtered) & (filtered > 0), "Spatial filtered (same frame)"),
                  panel(depth, valid, "Target 58deg 64x64; invalid = magenta")]
    print(json.dumps(dict(shape=list(depth.shape), finite=bool(np.isfinite(depth).all()),
                          min_m=float(np.min(depth)), max_m=float(np.max(depth)),
                          valid_ratio=float(np.mean(valid != 0))), indent=2))
    if not cv2.imwrite(args.output, np.concatenate(panels, axis=1)):
        raise RuntimeError("Failed to save PNG")


if __name__ == "__main__":
    main()
