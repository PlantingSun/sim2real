#!/usr/bin/env python3
"""将 Go2W 的 MotionSwitcher 切回 wheeled_sport，不发送 LowCmd。"""

import argparse
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient

from config.go2w_config import DDS


def main() -> int:
    parser = argparse.ArgumentParser(description="恢复 Go2W wheeled_sport 模式")
    parser.add_argument("--interface", default=DDS.DEFAULT_NET_IF)
    args = parser.parse_args()

    ChannelFactoryInitialize(DDS.DOMAIN_ID, args.interface)
    client = MotionSwitcherClient()
    client.SetTimeout(DDS.SPORT_MODE_TIMEOUT)
    client.Init()

    for _ in range(DDS.SPORT_MODE_MAX_ATTEMPTS):
        status, result = client.CheckMode()
        if status != 0 or result is None:
            print(f"[MotionSwitcher] CheckMode 失败, status={status}")
            return 1

        mode_name = result.get("name", "")
        if mode_name in ("ai-w", "normal-w", "wheeled_sport(go2W)"):
            print(f"[MotionSwitcher] Go2W 模式已就绪: {mode_name}")
            time.sleep(1.0)
            return 0
        if mode_name:
            print(f"[MotionSwitcher] 当前模式不是 Go2W wheeled_sport: {mode_name}")
            return 1

        code, _ = client.SelectMode("ai-w")
        if code != 0:
            print(f"[MotionSwitcher] SelectMode('ai-w') 失败, code={code}")
            return 1
        time.sleep(0.2)

    print("[MotionSwitcher] Go2W 模式恢复超时")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
