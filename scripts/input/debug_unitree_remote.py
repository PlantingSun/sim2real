#!/usr/bin/env python3
"""只读订阅 Go2W LowState，检查原装遥控器字节、摇杆和按钮映射。"""

import argparse
import struct
import threading
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_

from config.go2w_config import DDS
from teleop.unitree_remote import UnitreeRemoteState


def main():
    parser = argparse.ArgumentParser(
        description="只订阅 rt/lowstate；不会创建 LowCmd publisher 或发送电机命令"
    )
    parser.add_argument("--interface", default=DDS.DEFAULT_NET_IF)
    parser.add_argument("--hz", type=float, default=10.0, help="终端刷新频率")
    parser.add_argument("--raw", action="store_true", help="同时打印 40-byte 十六进制")
    args = parser.parse_args()
    if args.hz <= 0.0:
        parser.error("--hz must be positive")

    latest = {"state": None, "count": 0}
    lock = threading.Lock()

    def on_lowstate(msg: LowState_):
        try:
            remote = UnitreeRemoteState.parse(msg.wireless_remote)
        except (ValueError, struct.error):
            return
        with lock:
            latest["state"] = remote
            latest["count"] += 1

    # 此脚本仅在这里初始化一个 Subscriber，不导入 LowCmd，也不创建 Publisher。
    print("[READ ONLY] subscribing to Go2W LowState; no motor commands will be sent")
    print(f"interface={args.interface} topic={DDS.LOWSTATE_TOPIC}")
    ChannelFactoryInitialize(DDS.DOMAIN_ID, args.interface)
    subscriber = ChannelSubscriber(DDS.LOWSTATE_TOPIC, LowState_)
    subscriber.Init(on_lowstate, 10)

    period = 1.0 / args.hz
    try:
        while True:
            with lock:
                remote = latest["state"]
                count = latest["count"]
            if remote is None:
                print("waiting for LowState...")
            else:
                buttons = ",".join(remote.active_buttons) or "-"
                print(
                    f"packets={count:8d}  "
                    f"Lx={remote.lx:+.3f} Ly={remote.ly:+.3f} "
                    f"Rx={remote.rx:+.3f} Ry={remote.ry:+.3f}  "
                    f"buttons={buttons}"
                )
                if args.raw:
                    print(remote.raw.hex(" "))
            time.sleep(period)
    except KeyboardInterrupt:
        print("\n退出只读遥控器调试。")


if __name__ == "__main__":
    main()
