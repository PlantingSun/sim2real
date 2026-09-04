#!/usr/bin/env python3
"""在 Orin CPU 上测量完整 policy 单帧延时；不初始化 DDS。"""

import argparse
import csv
from pathlib import Path
import time

import numpy as np
import torch

from config.go2w_config import CTRL, DDS_IDX_FROM_CTRL
from config.paths import model_path
from driver.driver_base import RobotState
from policy.controller_go2w import ControllerGo2w
from policy.controller_go2wcr import ControllerGo2wCR
from policy.controller_go2wwmp import ControllerGo2wWMP


FRAME_BUDGET_MS = 1000.0 / CTRL.POLICY_RATE_HZ


def initial_state() -> RobotState:
    """返回与三个离线测试一致的初始站立零运动状态。"""
    state = RobotState()
    state.joint_positions = CTRL.INITIAL_JOINTS_POS[DDS_IDX_FROM_CTRL].copy()
    return state


def summarize(name: str, latency_ms: np.ndarray, log_path: str = "") -> bool:
    """打印延时分布；P99 不超过单帧预算视为满足 50 Hz。"""
    mean_ms = float(latency_ms.mean())
    p50_ms, p95_ms, p99_ms = np.percentile(latency_ms, (50, 95, 99))
    max_ms = float(latency_ms.max())
    missed = int(np.count_nonzero(latency_ms > FRAME_BUDGET_MS))
    throughput_hz = 1000.0 / mean_ms
    passed = mean_ms <= FRAME_BUDGET_MS and p99_ms <= FRAME_BUDGET_MS
    status = "PASS" if passed else "FAIL"
    print(
        f"[{status}] {name:<18} mean={mean_ms:7.3f} ms  "
        f"P50={p50_ms:7.3f}  P95={p95_ms:7.3f}  "
        f"P99={p99_ms:7.3f}  max={max_ms:7.3f}  "
        f"missed={missed}/{latency_ms.size}  mean_rate={throughput_hz:7.1f} Hz"
    )
    if log_path:
        output_path = Path(log_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("frame", "latency_ms"))
            writer.writerows(enumerate(latency_ms, 1))
        print(f"[Log] policy 延时 CSV: {output_path}")
    return passed


def measure(step, warmup: int, iterations: int, is_update_frame=None):
    """预热后逐帧测时，并标记 WMP world-model 更新帧。"""
    for _ in range(warmup):
        step()

    latency_ms = np.empty(iterations, dtype=np.float64)
    update_frames = np.zeros(iterations, dtype=bool)
    for index in range(iterations):
        if is_update_frame is not None:
            update_frames[index] = is_update_frame()
        start_ns = time.perf_counter_ns()
        step()
        latency_ms[index] = (time.perf_counter_ns() - start_ns) / 1.0e6
    return latency_ms, update_frames


def benchmark_go2w(warmup: int, iterations: int, log_path: str = "") -> bool:
    load_start = time.perf_counter()
    controller = ControllerGo2w(model_path("go2w/model_700.pt"))
    print(f"[LOAD] go2w              {(time.perf_counter() - load_start) * 1000.0:.1f} ms")
    state = initial_state()
    command = np.zeros(3, dtype=np.float32)

    def step():
        observation = controller.build_obs(state, command)
        action = controller.compute_action(observation)
        controller.action_to_motor_command(action)

    latency_ms, _ = measure(step, warmup, iterations)
    return summarize("go2w full frame", latency_ms, log_path)


def benchmark_go2wcr(warmup: int, iterations: int, log_path: str = "") -> bool:
    load_start = time.perf_counter()
    controller = ControllerGo2wCR(model_path("go2wcr/model_1499.pt"))
    print(f"[LOAD] go2wcr            {(time.perf_counter() - load_start) * 1000.0:.1f} ms")
    state = initial_state()
    command = np.zeros(3, dtype=np.float32)

    def step():
        observation = controller.build_obs(state, command)
        action = controller.compute_action(observation)
        controller.action_to_motor_command(action)

    latency_ms, _ = measure(step, warmup, iterations)
    return summarize("go2wcr full frame", latency_ms, log_path)


def benchmark_go2wwmp(warmup: int, iterations: int, log_path: str = "") -> bool:
    load_start = time.perf_counter()
    controller = ControllerGo2wWMP(model_path("go2wwmp/model_1750.pt"))
    print(f"[LOAD] go2wwmp           {(time.perf_counter() - load_start) * 1000.0:.1f} ms")
    state = initial_state()
    command = np.zeros(3, dtype=np.float32)
    depth = np.full(controller.IMAGE_SHAPE, 0.5, dtype=np.float32)

    def step():
        controller.step(state, command, depth)

    latency_ms, update_frames = measure(
        step,
        warmup,
        iterations,
        lambda: controller.counter % controller.UPDATE_INTERVAL == 0,
    )
    passed = summarize("go2wwmp all frames", latency_ms, log_path)
    summarize("  world-model frame", latency_ms[update_frames])
    summarize("  actor-only frame", latency_ms[~update_frames])
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description="Orin CPU policy latency benchmark")
    parser.add_argument(
        "--policy",
        choices=("all", "go2w", "go2wcr", "go2wwmp"),
        default="all",
    )
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=50)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--log", type=str, default="", help="policy 延时 CSV 路径")
    args = parser.parse_args()
    if args.threads < 1 or args.warmup < 1 or args.iterations < 10:
        parser.error("threads/warmup 必须为正数，iterations 至少为 10")

    torch.set_num_threads(args.threads)
    torch.manual_seed(0)
    np.random.seed(0)
    print(
        f"50 Hz budget={FRAME_BUDGET_MS:.1f} ms  "
        f"threads={torch.get_num_threads()}  "
        f"interop={torch.get_num_interop_threads()}  warmup={args.warmup}  "
        f"iterations={args.iterations}"
    )

    benchmarks = {
        "go2w": benchmark_go2w,
        "go2wcr": benchmark_go2wcr,
        "go2wwmp": benchmark_go2wwmp,
    }
    selected = benchmarks if args.policy == "all" else {args.policy: benchmarks[args.policy]}
    results = [benchmark(args.warmup, args.iterations, args.log) for benchmark in selected.values()]
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
