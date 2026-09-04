#!/usr/bin/env python3
"""离线重放 265 维 observation，并与日志中的 Orin action 比较。"""

import argparse
import csv
import hashlib
import platform
from pathlib import Path

import numpy as np
import torch

from config.go2w_config import CTRL
from config.paths import model_path
from policy.controller_go2w import ControllerGo2w


def summarize(name, errors, frame_ids):
    """打印一组逐元素绝对误差统计，并返回组内最大误差。"""
    if not errors:
        print(f"{name}: frames=0")
        return 0.0
    matrix = np.stack(errors)
    row_max = matrix.max(axis=1)
    worst = int(np.argmax(row_max))
    print(
        f"{name}: frames={matrix.shape[0]} "
        f"mean_abs={matrix.mean():.9g} rmse={np.sqrt(np.mean(matrix ** 2)):.9g} "
        f"mean_frame_max={row_max.mean():.9g} max_abs={row_max[worst]:.9g} "
        f"worst_loop={frame_ids[worst]}"
    )
    print(
        f"{name}: per_action_max="
        + np.array2string(matrix.max(axis=0), precision=9, separator=", ")
    )
    return float(row_max[worst])


def main() -> int:
    parser = argparse.ArgumentParser(description="重放 go2w observation CSV")
    parser.add_argument("csv_path")
    parser.add_argument("--model", default=model_path("go2w/model_700.pt"))
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument(
        "--atol", type=float, default=1e-5,
        help="非 warmup 帧允许的最大绝对误差（默认 1e-5）",
    )
    args = parser.parse_args()
    if args.threads < 1 or args.atol < 0:
        parser.error("threads 必须为正数，atol 不能为负数")

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    controller = ControllerGo2w(args.model)
    groups = {"active": ([], []), "warmup": ([], [])}
    expected_width = 3 + CTRL.NUM_OBS * CTRL.HISTORY_LENGTH + CTRL.NUM_ACTIONS

    with open(args.csv_path, newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        if len(header) != expected_width:
            raise ValueError(f"CSV 应有 {expected_width} 列，实际为 {len(header)}")
        for line_number, row in enumerate(reader, start=2):
            if len(row) != expected_width:
                raise ValueError(
                    f"第 {line_number} 行应有 {expected_width} 列，实际为 {len(row)}"
                )
            values = np.asarray(row[3:], dtype=np.float32)
            observation = torch.from_numpy(values[:CTRL.NUM_OBS * CTRL.HISTORY_LENGTH])
            expected_action = values[CTRL.NUM_OBS * CTRL.HISTORY_LENGTH:]
            replay_action = controller.compute_action(observation)
            group = "warmup" if int(row[2]) else "active"
            groups[group][0].append(np.abs(replay_action - expected_action))
            groups[group][1].append(int(row[1]))

    if not groups["active"][0] and not groups["warmup"][0]:
        print("CSV 中没有 observation")
        return 1

    model_bytes = Path(args.model).read_bytes()
    print(
        f"runtime: arch={platform.machine()} torch={torch.__version__} "
        f"numpy={np.__version__} threads={args.threads}"
    )
    print(f"model_sha256={hashlib.sha256(model_bytes).hexdigest()}")
    active_max = summarize("active", *groups["active"])
    summarize("warmup", *groups["warmup"])
    if active_max > args.atol:
        print(f"FAIL: active max_abs {active_max:.9g} > atol {args.atol:.9g}")
        return 2
    print(f"PASS: active max_abs {active_max:.9g} <= atol {args.atol:.9g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
