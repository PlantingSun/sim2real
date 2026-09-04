#!/usr/bin/env python3
"""离线查看键盘/Xbox 速度命令；不导入或初始化 DDS driver。"""

import argparse
import time

from config.go2w_config import DDS
from teleop.command_source import KeyboardCommandSource, XboxCommandSource


def main():
    parser = argparse.ArgumentParser(description="offline keyboard/Xbox command monitor")
    parser.add_argument("--control", choices=("keyboard", "xbox"), default="keyboard")
    parser.add_argument("--joystick", default=DDS.DEFAULT_JOYSTICK)
    parser.add_argument("--hz", type=float, default=20.0)
    args = parser.parse_args()
    if args.hz <= 0.0:
        parser.error("--hz must be positive")

    source = (
        KeyboardCommandSource()
        if args.control == "keyboard"
        else XboxCommandSource(args.joystick)
    )
    print("[OFFLINE] this script does not import DDS or connect to the robot")
    try:
        while True:
            sample = source.read()
            vx, vy, vyaw = sample.velocity
            print(
                f"enabled={sample.enabled!s:5s} "
                f"vx={vx:+.3f} vy={vy:+.3f} vyaw={vyaw:+.3f}",
                end="\r",
                flush=True,
            )
            if sample.quit_requested:
                break
            time.sleep(1.0 / args.hz)
    except KeyboardInterrupt:
        pass
    finally:
        source.close()
        print("\n退出输入调试。")


if __name__ == "__main__":
    main()
