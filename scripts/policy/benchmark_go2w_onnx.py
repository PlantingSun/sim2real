#!/usr/bin/env python3
"""导出并离线测试 Go2W ONNX actor；不会初始化 DDS。"""

import argparse
import csv
import multiprocessing as mp
import os
from pathlib import Path
import time

import numpy as np
import onnx
import onnxruntime as ort
import torch
from torch import nn

from config.go2w_config import CTRL, DDS_IDX_FROM_CTRL
from config.paths import model_path
from driver.driver_base import RobotState
from policy.controller_go2w import ControllerGo2w
from policy.process_worker import run_go2w_policy


class ExportedActor(nn.Module):
    """将训练时的 observation 归一化和 actor 合并为一个 ONNX 图。"""

    def __init__(self, controller: ControllerGo2w):
        super().__init__()
        self.normalizer = controller.obs_normalizer
        self.actor = controller.actor_critic.actor

    def forward(self, observation):
        normalized = torch.clamp(self.normalizer(observation), -CTRL.CLIP_OBS, CTRL.CLIP_OBS)
        return torch.clamp(self.actor(normalized), -CTRL.CLIP_ACTION, CTRL.CLIP_ACTION)


def export_actor(checkpoint: str, output_path: Path) -> ControllerGo2w:
    """导出固定形状的 265→16 actor，并返回同权重的 PyTorch controller。"""
    controller = ControllerGo2w(checkpoint)
    actor = ExportedActor(controller).eval()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    example = torch.zeros((1, CTRL.NUM_OBS * CTRL.HISTORY_LENGTH), dtype=torch.float32)
    torch.onnx.export(
        actor,
        example,
        str(output_path),
        input_names=("observation",),
        output_names=("action",),
        opset_version=17,
        do_constant_folding=True,
    )
    onnx.checker.check_model(onnx.load(str(output_path)))
    return controller


def create_session(path: Path, threads: int) -> ort.InferenceSession:
    """创建单进程、固定线程数的 ARM CPU session。"""
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(
        str(path), sess_options=options, providers=("CPUExecutionProvider",)
    )


def load_observations(path: str, limit: int) -> np.ndarray:
    """优先读取真实 observation；未指定日志时使用确定性的随机输入。"""
    if not path:
        generator = np.random.default_rng(0)
        return generator.standard_normal((limit, 265), dtype=np.float32)
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = [f"obs_{index}" for index in range(265)]
        rows = [[float(row[field]) for field in fields] for _, row in zip(range(limit), reader)]
    if not rows:
        raise RuntimeError(f"observation 日志为空: {path}")
    return np.asarray(rows, dtype=np.float32)


def measure(step, warmup: int, iterations: int) -> np.ndarray:
    """测量单步延时；每次调用都使用同一输入，避免把文件读取计入推理。"""
    for _ in range(warmup):
        step()
    latency_ms = np.empty(iterations, dtype=np.float64)
    for index in range(iterations):
        start = time.perf_counter_ns()
        step()
        latency_ms[index] = (time.perf_counter_ns() - start) / 1.0e6
    return latency_ms


def print_latency(name: str, values: np.ndarray) -> None:
    p50, p95, p99 = np.percentile(values, (50, 95, 99))
    print(
        f"{name:<20} mean={values.mean():.3f} ms  p50={p50:.3f}  "
        f"p95={p95:.3f}  p99={p99:.3f}  max={values.max():.3f}"
    )


def benchmark_full_frame(controller, session, warmup: int, iterations: int):
    """分别测试现有 PyTorch 路径和只替换 actor 后的完整单帧路径。"""
    state = RobotState()
    state.joint_positions = CTRL.INITIAL_JOINTS_POS[DDS_IDX_FROM_CTRL].copy()
    command = np.zeros(3, dtype=np.float32)

    def torch_step():
        observation = controller.build_obs(state, command)
        action = controller.compute_action(observation)
        controller.action_to_motor_command(action)

    torch_latency = measure(torch_step, warmup, iterations)

    controller.reset()

    def onnx_step():
        observation = controller.build_obs(state, command).numpy().reshape(1, -1)
        action = session.run(("action",), {"observation": observation})[0].reshape(-1)
        controller.last_action = torch.from_numpy(action.copy())
        controller.action_to_motor_command(action)

    onnx_latency = measure(onnx_step, warmup, iterations)
    return torch_latency, onnx_latency


def benchmark_roundtrip(backend, checkpoint, onnx_path, cpus, threads, warmup, iterations):
    """复用实机 worker，测量主进程 send 到 recv 的完整 Pipe 往返。"""
    parent, child = mp.get_context("spawn").Pipe()
    process = mp.get_context("spawn").Process(
        target=run_go2w_policy,
        args=(child, checkpoint, cpus, threads, backend, str(onnx_path)),
    )
    process.start()
    child.close()
    if not parent.poll(30.0) or parent.recv() != "ready":
        raise RuntimeError(f"{backend} policy 子进程初始化失败")

    state = RobotState()
    state.joint_positions = CTRL.INITIAL_JOINTS_POS[DDS_IDX_FROM_CTRL].copy()
    command = np.zeros(3, dtype=np.float32)
    request = (
        state.joint_positions,
        state.joint_velocities,
        state.imu_quat,
        state.imu_gyro,
        command,
        False,
    )

    for _ in range(warmup):
        parent.send(request)
        parent.recv()
    roundtrip_ms = np.empty(iterations, dtype=np.float64)
    worker_ms = np.empty(iterations, dtype=np.float64)
    for index in range(iterations):
        start = time.perf_counter_ns()
        parent.send(request)
        result = parent.recv()
        roundtrip_ms[index] = (time.perf_counter_ns() - start) / 1.0e6
        worker_ms[index] = result[-1]

    parent.send(None)
    process.join(timeout=5.0)
    parent.close()
    if process.is_alive():
        process.terminate()
        process.join()
        raise RuntimeError(f"{backend} policy 子进程未正常退出")
    return worker_ms, roundtrip_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Go2W PyTorch/ONNX 离线一致性与延时测试")
    parser.add_argument("--checkpoint", default=model_path("go2w/model_700.pt"))
    parser.add_argument("--output", default=model_path("go2w/model_700.onnx"))
    parser.add_argument("--observation-log", default="")
    parser.add_argument("--cpus", default="", help="进程 CPU 列表，例如 2")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--iterations", type=int, default=1000)
    args = parser.parse_args()
    if args.threads < 1 or args.warmup < 1 or args.iterations < 10:
        parser.error("threads/warmup 必须为正数，iterations 至少为 10")
    cpus = {int(value) for value in args.cpus.split(",")} if args.cpus else None
    if cpus:
        os.sched_setaffinity(0, cpus)

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    output_path = Path(args.output)
    controller = export_actor(args.checkpoint, output_path)
    session = create_session(output_path, args.threads)
    observations = load_observations(args.observation_log, min(args.iterations, 1000))

    with torch.no_grad():
        expected = ExportedActor(controller)(torch.from_numpy(observations)).numpy()
    # 实机图固定为 batch=1；验证时也逐帧调用，保持与部署完全相同的输入形状。
    actual = np.vstack(
        [
            session.run(("action",), {"observation": observation.reshape(1, -1)})[0]
            for observation in observations
        ]
    )
    error = np.abs(expected - actual)
    print(f"[ONNX] {output_path}  size={output_path.stat().st_size} bytes")
    print(
        f"[CHECK] frames={len(observations)}  mean_abs={error.mean():.8g}  "
        f"max_abs={error.max():.8g}"
    )

    sample = observations[0:1]
    torch_actor = ExportedActor(controller).eval()

    def torch_actor_step():
        with torch.no_grad():
            torch_actor(torch.from_numpy(sample))

    def onnx_actor_step():
        session.run(("action",), {"observation": sample})

    print_latency("PyTorch actor", measure(torch_actor_step, args.warmup, args.iterations))
    print_latency("ONNX actor", measure(onnx_actor_step, args.warmup, args.iterations))
    torch_full, onnx_full = benchmark_full_frame(
        controller, session, args.warmup, args.iterations
    )
    print_latency("PyTorch full frame", torch_full)
    print_latency("ONNX full frame", onnx_full)
    torch_worker, torch_roundtrip = benchmark_roundtrip(
        "torch", args.checkpoint, output_path, cpus, args.threads,
        args.warmup, args.iterations
    )
    onnx_worker, onnx_roundtrip = benchmark_roundtrip(
        "onnx", args.checkpoint, output_path, cpus, args.threads,
        args.warmup, args.iterations
    )
    print_latency("PyTorch worker", torch_worker)
    print_latency("PyTorch Pipe", torch_roundtrip)
    print_latency("ONNX worker", onnx_worker)
    print_latency("ONNX Pipe", onnx_roundtrip)


if __name__ == "__main__":
    main()
