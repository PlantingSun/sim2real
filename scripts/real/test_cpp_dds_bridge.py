#!/usr/bin/env python3
"""Read-only test for the C++ DDS bridge; this script never publishes LowCmd."""

import argparse
import time

from config.go2w_config import DDS
from driver.cpp_dds_driver import CppDdsDriver


def main() -> int:
    parser = argparse.ArgumentParser(description="C++ DDS bridge 只读测试")
    parser.add_argument("--interface", default=DDS.DEFAULT_NET_IF)
    parser.add_argument("--lowcmd-cpu", type=int, default=1)
    parser.add_argument("--duration", type=float, default=10.0)
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("duration 必须为正数")

    driver = CppDdsDriver(args.interface, args.lowcmd_cpu, monitor_only=True)
    if not driver.initialize():
        return 1
    try:
        start = time.monotonic()
        first_packets = driver.state_packets
        first_sequence = driver.state_sequence
        first_tick = driver.get_state().tick
        while time.monotonic() - start < args.duration:
            driver.get_state()
            time.sleep(0.002)
        elapsed = time.monotonic() - start
        state = driver.get_state()
        print(
            f"[CPP DDS RX] packets={driver.state_packets - first_packets} "
            f"rate={(driver.state_packets - first_packets) / elapsed:.2f} Hz "
            f"source_delta={driver.state_sequence - first_sequence} "
            f"tick_delta={state.tick - first_tick} "
            f"prearm_lowcmd={int(driver.prearm_lowcmd)} "
            f"other_lowcmd={int(driver.other_lowcmd)}"
        )
        return 0
    finally:
        driver.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
