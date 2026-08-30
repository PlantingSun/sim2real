#!/usr/bin/env python3
# ============================================================================
# test_dds_driver.py — Step 1: 驱动层验证
#
# 验证 DdsDriver 能正确订阅 LowState、读取关节/IMU 数据。
# 对比现有 monitor_lowstate.py 的输出，确认数据一致。
#
# Usage:
#   source setup.sh robot
#   python scripts/real/test_dds_driver.py [network_interface]
# ============================================================================

import sys
import time
import signal
import numpy as np

from driver.dds_driver import DdsDriver
from driver.driver_base import MotorCommand
from config.go2w_config import DDS


def main():
    net_if = sys.argv[1] if len(sys.argv) > 1 else DDS.DEFAULT_NET_IF
    print(f"=== Step 1: DdsDriver 验证 ===")
    print(f"网口: {net_if}")

    driver = DdsDriver(net_if)
    if not driver.initialize():
        print("初始化失败")
        return

    # 停止标志
    running = True

    def sigint_handler(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, sigint_handler)

    print("\n开始读取状态 (2Hz), Ctrl+C 退出...\n")
    try:
        while running:
            state = driver.get_state()

            # 电池
            print(f"Tick: {state.tick}  |  电池: {state.battery_soc:.1f}%")

            # IMU RPY
            r, p, y = state.imu_rpy
            print(f"IMU RPY: roll={r:.2f}  pitch={p:.2f}  yaw={y:.2f}")

            # 腿关节 (DDS 0-11)
            print("腿关节 pos (DDS 0-11):")
            for i in range(12):
                q = state.joint_positions[i]
                dq = state.joint_velocities[i]
                print(f"  J{i:2d}: q={q:8.4f}  dq={dq:8.4f}", end="")
                if (i + 1) % 3 == 0:
                    print()
            if 12 % 3 != 0:
                print()

            # 轮子 (DDS 12-15)
            print("轮子 pos/vel (DDS 12-15):")
            for i in range(12, 16):
                q = state.joint_positions[i]
                dq = state.joint_velocities[i]
                print(f"  W{i-12}: q={q:8.4f}  dq={dq:8.4f}")

            # IMU quaternion / gyroscope / accelerometer
            qw, qx, qy, qz = state.imu_quat
            print(f"Quat [w,x,y,z]: w={qw:.4f}  x={qx:.4f}  y={qy:.4f}  z={qz:.4f}")
            gx, gy, gz = state.imu_gyro
            print(f"Gyro: x={gx:.4f}  y={gy:.4f}  z={gz:.4f}")
            ax, ay, az = state.imu_accel
            print(f"Accel: x={ax:.4f}  y={ay:.4f}  z={az:.4f}")
            print("-" * 60)

            time.sleep(0.5)
    finally:
        driver.shutdown()
        print("退出。")


if __name__ == "__main__":
    main()
