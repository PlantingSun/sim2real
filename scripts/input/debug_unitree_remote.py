#!/usr/bin/env python3
"""只读订阅 Go2W LowState，检查原装遥控器字节、摇杆和按钮映射。"""

import argparse
from dataclasses import dataclass
import struct
import threading
import time
from typing import Dict, Tuple

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_

from config.go2w_config import DDS


@dataclass(frozen=True)
class UnitreeRemoteState:
    """Go2W LowState.wireless_remote[40] 的解析结果。"""

    lx: float
    ly: float
    rx: float
    ry: float
    buttons: Dict[str, bool]
    raw: bytes

    @classmethod
    def parse(cls, wireless_remote) -> "UnitreeRemoteState":
        raw = bytes(wireless_remote)
        if len(raw) != 40:
            raise ValueError(f"wireless_remote must be 40 bytes, got {len(raw)}")

        byte1, byte2 = raw[2], raw[3]
        buttons = {
            "R1": bool(byte1 & (1 << 0)),
            "L1": bool(byte1 & (1 << 1)),
            "Start": bool(byte1 & (1 << 2)),
            "Select": bool(byte1 & (1 << 3)),
            "R2": bool(byte1 & (1 << 4)),
            "L2": bool(byte1 & (1 << 5)),
            "F1": bool(byte1 & (1 << 6)),
            "F3": bool(byte1 & (1 << 7)),
            "A": bool(byte2 & (1 << 0)),
            "B": bool(byte2 & (1 << 1)),
            "X": bool(byte2 & (1 << 2)),
            "Y": bool(byte2 & (1 << 3)),
            "Up": bool(byte2 & (1 << 4)),
            "Right": bool(byte2 & (1 << 5)),
            "Down": bool(byte2 & (1 << 6)),
            "Left": bool(byte2 & (1 << 7)),
        }
        lx = struct.unpack_from("<f", raw, 4)[0]
        rx = struct.unpack_from("<f", raw, 8)[0]
        ry = struct.unpack_from("<f", raw, 12)[0]
        ly = struct.unpack_from("<f", raw, 20)[0]
        return cls(lx=lx, ly=ly, rx=rx, ry=ry, buttons=buttons, raw=raw)

    @property
    def active_buttons(self) -> Tuple[str, ...]:
        return tuple(name for name, pressed in self.buttons.items() if pressed)


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
