#!/usr/bin/env python3
"""在独立 policy 进程中测量 go2w 延时；不初始化 DDS。"""

import argparse
import multiprocessing as mp
import os
import time

import numpy as np
import torch

from config.go2w_config import CTRL, DDS_IDX_FROM_CTRL
from config.paths import model_path
from driver.driver_base import RobotState
from policy.controller_go2w import ControllerGo2w


def worker(conn, cpus, threads, warmup, iterations):
    if cpus:
        os.sched_setaffinity(0, cpus)
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    state = RobotState()
    state.joint_positions = CTRL.INITIAL_JOINTS_POS[DDS_IDX_FROM_CTRL].copy()
    command = np.zeros(3, dtype=np.float32)
    controller = ControllerGo2w(model_path("go2w/model_700.pt"))

    def step():
        obs = controller.build_obs(state, command)
        action = controller.compute_action(obs)
        controller.action_to_motor_command(action)

    for _ in range(warmup):
        step()
    latency = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        step()
        latency.append((time.perf_counter_ns() - start) / 1.0e6)
    conn.send(latency)
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="独立 policy 进程延时测试")
    parser.add_argument("--cpus", default="", help="policy 进程 CPU 列表，例如 2,3")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=50)
    parser.add_argument("--iterations", type=int, default=500)
    args = parser.parse_args()
    cpus = {int(value) for value in args.cpus.split(",")} if args.cpus else None
    parent, child = mp.Pipe(False)
    process = mp.get_context("spawn").Process(
        target=worker, args=(child, cpus, args.threads, args.warmup, args.iterations)
    )
    process.start()
    latency = np.asarray(parent.recv(), dtype=np.float64)
    process.join()
    print(
        f"process policy: mean={latency.mean():.3f} ms, "
        f"p99={np.percentile(latency, 99):.3f} ms, "
        f"max={latency.max():.3f} ms, rate={1000.0 / latency.mean():.1f} Hz"
    )
    return process.exitcode


if __name__ == "__main__":
    raise SystemExit(main())
