"""Pure NumPy depth conversion shared by diagnostics and Go2WWMP."""

from __future__ import annotations

import numpy as np


IMAGE_SHAPE = (64, 64)
DEPTH_NEAR_M = 0.0
DEPTH_FAR_M = 2.0
DEPTH_CENTER = 0.5


def preprocess_depth_for_wmp(depth_m: np.ndarray) -> np.ndarray:
    """Convert 64x64 metric Z depth to the WMP training input range.

    The sender already replaces invalid measurements with the 2 m far plane.
    This function also treats non-finite values as far for simulation safety,
    clips to [0, 2] m, normalizes to [0, 1], then subtracts 0.5 exactly as
    the reviewed Go2WWMP simulation pipeline does.
    """
    depth = np.asarray(depth_m, dtype=np.float32)
    if depth.shape != IMAGE_SHAPE:
        raise ValueError(f"WMP metric depth must have shape {IMAGE_SHAPE}, got {depth.shape}")
    depth = np.nan_to_num(
        depth,
        copy=True,
        nan=DEPTH_FAR_M,
        posinf=DEPTH_FAR_M,
        neginf=DEPTH_FAR_M,
    )
    depth = np.clip(depth, DEPTH_NEAR_M, DEPTH_FAR_M)
    depth = (depth - DEPTH_NEAR_M) / (DEPTH_FAR_M - DEPTH_NEAR_M)
    return np.ascontiguousarray(depth - DEPTH_CENTER, dtype=np.float32)
