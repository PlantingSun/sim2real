#!/usr/bin/env python3
"""离线重放 265 维 observation，并与日志中的 action 比较。"""

import argparse
import csv

import numpy as np
import torch

from config.go2w_config import CTRL
from config.paths import model_path
from policy.controller_go2w import ControllerGo2w


def main() -> int:
    parser = argparse.ArgumentParser(description="重放 go2w observation CSV")
    parser.add_argument("csv_path")
    parser.add_argument("--model", default=model_path("go2w/model_700.pt"))
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    controller = ControllerGo2w(args.model)
    errors = []

    with open(args.csv_path, newline="") as handle:
        reader = csv.reader(handle)
        next(reader)
        for row in reader:
            values = np.asarray(row[3:], dtype=np.float32)
            observation = torch.from_numpy(values[:CTRL.NUM_OBS * CTRL.HISTORY_LENGTH])
            expected_action = values[CTRL.NUM_OBS * CTRL.HISTORY_LENGTH:]
            replay_action = controller.compute_action(observation)
            errors.append(np.max(np.abs(replay_action - expected_action)))

    if not errors:
        print("CSV 中没有 observation")
        return 1
    errors = np.asarray(errors)
    print(f"frames={errors.size} mean_max_error={errors.mean():.9g} max_error={errors.max():.9g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
