#!/usr/bin/env python3
"""Execute one Sport Mode RPC in a short-lived helper process."""

import argparse

from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.sport.sport_client import SportClient

from config.go2w_config import DDS


def stand_up() -> int:
    client = SportClient()
    client.SetTimeout(DDS.SPORT_MODE_TIMEOUT)
    client.Init()
    code = client.StandUp()
    print(f"[Sport helper] StandUp code={code}")
    return 0 if code == 0 else 1


def release_mode() -> int:
    client = MotionSwitcherClient()
    client.SetTimeout(DDS.SPORT_MODE_TIMEOUT)
    client.Init()
    status, result = client.CheckMode()
    if status != 0 or result is None:
        print(f"[Sport helper] CheckMode 失败, status={status}")
        return 1
    mode_name = result.get("name", "")
    if not mode_name:
        print("[Sport helper] Sport Mode 已经释放")
        return 0
    code, _ = client.ReleaseMode()
    print(f"[Sport helper] ReleaseMode '{mode_name}', code={code}")
    return 0 if code == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interface", default=DDS.DEFAULT_NET_IF)
    parser.add_argument("--action", choices=("standup", "release"), required=True)
    args = parser.parse_args()
    ChannelFactoryInitialize(DDS.DOMAIN_ID, args.interface)
    return stand_up() if args.action == "standup" else release_mode()


if __name__ == "__main__":
    raise SystemExit(main())

