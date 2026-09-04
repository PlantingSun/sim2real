#!/usr/bin/env python3
"""4.7：独立 DDS/LowCmd 进程测试；不加载 policy。"""

import argparse
import time

import numpy as np

from config.go2w_config import CTRL, DDS, DDS_IDX_FROM_CTRL
from driver.dds_driver import DdsDriver
from driver.driver_base import MotorCommand


def fixed_command() -> MotorCommand:
    positions_ctrl = CTRL.INITIAL_JOINTS_POS.copy()
    velocities_ctrl = np.zeros(16, dtype=np.float32)
    kp_ctrl = np.full(16, CTRL.LEG_KP, dtype=np.float32)
    kd_ctrl = np.full(16, CTRL.LEG_KD, dtype=np.float32)
    for index in CTRL.WHEEL_INDICES:
        kp_ctrl[index] = CTRL.WHEEL_KP
        kd_ctrl[index] = CTRL.WHEEL_KD
    return MotorCommand(
        positions_ctrl[DDS_IDX_FROM_CTRL], velocities_ctrl[DDS_IDX_FROM_CTRL],
        kp_ctrl[DDS_IDX_FROM_CTRL], kd_ctrl[DDS_IDX_FROM_CTRL],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="独立 DDS/LowCmd 频率测试")
    parser.add_argument("--interface", default=DDS.DEFAULT_NET_IF)
    parser.add_argument("--lowcmd-cpu", type=int, default=None)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--release", action="store_true", help="启动前执行一次 ReleaseMode")
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("duration 必须为正数")

    driver = DdsDriver(args.interface, lowcmd_cpu=args.lowcmd_cpu)
    if not driver.initialize():
        return 1
    try:
        if args.release and not driver.release_sport_mode():
            return 1
        driver.send_command(fixed_command())
        if not driver.start_lowcmd_thread():
            return 1
        start_count = driver.write_count
        start = time.perf_counter()
        time.sleep(args.duration)
        elapsed = time.perf_counter() - start
        writes = driver.write_count - start_count
        print(f"[DDS RATE] writes={writes} elapsed={elapsed:.3f} s rate={writes / elapsed:.2f} Hz")
        return 0
    finally:
        driver.set_emergency_damping()
        time.sleep(0.1)
        driver.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
