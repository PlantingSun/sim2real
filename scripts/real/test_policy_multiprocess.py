#!/usr/bin/env python3
"""4.8：DDS/LowCmd 主进程与 policy 子进程联合测试。"""
import argparse
import multiprocessing as mp
import time

import numpy as np

from config.go2w_config import CTRL, DDS, DDS_IDX_FROM_CTRL
from config.paths import model_path
from driver.dds_driver import DdsDriver
from driver.driver_base import MotorCommand
from policy.process_worker import run_go2w_policy


def fixed_command():
    kp = np.full(16, CTRL.LEG_KP, dtype=np.float32)
    kd = np.full(16, CTRL.LEG_KD, dtype=np.float32)
    for index in CTRL.WHEEL_INDICES:
        kp[index] = CTRL.WHEEL_KP
        kd[index] = CTRL.WHEEL_KD
    zeros = np.zeros(16, dtype=np.float32)
    return MotorCommand(CTRL.INITIAL_JOINTS_POS[DDS_IDX_FROM_CTRL], zeros[DDS_IDX_FROM_CTRL],
                        kp[DDS_IDX_FROM_CTRL], kd[DDS_IDX_FROM_CTRL])


def main():
    parser = argparse.ArgumentParser(description="policy 与 DDS 双进程联合测试")
    parser.add_argument("--interface", default=DDS.DEFAULT_NET_IF)
    parser.add_argument("--policy-cpus", default="2")
    parser.add_argument("--lowcmd-cpu", type=int, default=1)
    parser.add_argument("--torch-threads", type=int, default=1)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--warmup", type=float, default=3.0,
                        help="policy 预热秒数；预热期间不发送 policy action")
    parser.add_argument("--rate", type=float, default=CTRL.POLICY_RATE_HZ,
                        help="policy 频率；0 表示不限速，仅测最大吞吐")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()
    if args.duration <= 0 or args.warmup < 0 or args.torch_threads < 1 or args.rate < 0:
        parser.error("duration 必须为正数，warmup/rate 不能为负数，torch-threads 必须为正数")
    cpus = {int(value) for value in args.policy_cpus.split(",")} if args.policy_cpus else None
    context = mp.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=run_go2w_policy, args=(child, model_path("go2w/model_700.pt"),
                                                             cpus, args.torch_threads))
    driver = DdsDriver(args.interface, lowcmd_cpu=args.lowcmd_cpu)
    if not driver.initialize():
        return 1
    try:
        if args.release and not driver.release_sport_mode():
            return 1
        driver.send_command(fixed_command())
        if not driver.start_lowcmd_thread():
            return 1
        process.start()
        child.close()
        if parent.recv() != "ready":
            raise RuntimeError("policy 子进程初始化失败")
        print(f"[WARMUP] {args.warmup:.1f} s，期间保持 INITIAL_JOINTS_POS，不发送 policy action")
        start = time.perf_counter()
        warmup_end = start + args.warmup
        run_end = warmup_end + args.duration
        report_start = warmup_end
        next_deadline = start
        frames = 0
        active_frames = 0
        while time.perf_counter() < run_end:
            frame_start = time.perf_counter()
            state = driver.get_state()
            active = time.perf_counter() >= warmup_end
            parent.send((state.joint_positions, state.joint_velocities, state.imu_quat,
                         state.imu_gyro, np.zeros(3, dtype=np.float32),
                         not active or args.print_only))
            p, v, kp, kd, _, _, inference_ms = parent.recv()
            if active and not args.print_only:
                driver.send_command(MotorCommand(p, v, kp, kd))
            frames += 1
            if active:
                active_frames += 1
            if active and active_frames % CTRL.POLICY_RATE_HZ == 0:
                report_now = time.perf_counter()
                print(f"[RATE] joint policy={CTRL.POLICY_RATE_HZ / (report_now - report_start):.2f} Hz, "
                      f"inference={inference_ms:.3f} ms")
                report_start = report_now
            if args.rate > 0:
                next_deadline += 1.0 / args.rate
                remaining = next_deadline - time.perf_counter()
                if remaining > 0:
                    time.sleep(remaining)
                else:
                    next_deadline = time.perf_counter()
        parent.send(None)
        process.join(timeout=2.0)
        return process.exitcode or 0
    finally:
        if process.is_alive():
            parent.send(None)
            process.join(timeout=1.0)
            if process.is_alive():
                process.terminate()
        driver.set_emergency_damping()
        time.sleep(0.1)
        driver.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
