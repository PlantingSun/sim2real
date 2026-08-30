#!/usr/bin/env python3
"""go2wcr/CRRL 原装遥控器实机入口，共用已审查的接管和阻尼流程。"""

from scripts.real.test_policy_unitree_remote import main


if __name__ == "__main__":
    # 复用同一份遥控器安全逻辑，只固定策略类型为 go2wcr。
    main("go2wcr")
