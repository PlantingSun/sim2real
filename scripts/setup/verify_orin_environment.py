#!/usr/bin/env python3
"""只读验证 Orin 环境；不初始化 DDS，不连接或控制机器人。"""

import importlib.metadata
import os
from pathlib import Path
import platform
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_VERSIONS = {
    "cyclonedds": "0.10.2",
    "mujoco": "3.2.3",
    "numpy": "1.24.4",
    "torch": "2.0.0",
}
MODEL_FILES = (
    "go2w/model_700.pt",
    "go2wcr/model_1499.pt",
    "go2wwmp/model_1750.pt",
)


def check(condition: bool, message: str) -> None:
    """打印一个通过项；失败时立即停止，避免掩盖环境混用。"""
    if not condition:
        raise RuntimeError(message)
    print(f"[OK] {message}")


def main() -> None:
    check(platform.machine() == "aarch64", "CPU 架构为 aarch64")
    check(sys.version_info[:2] == (3, 8), "Python 版本为 3.8")
    check(Path(sys.prefix).resolve() == PROJECT_ROOT / ".venv", "解释器来自项目 .venv")

    for variable_name in ("PYTHONPATH", "LD_LIBRARY_PATH"):
        value = os.environ.get(variable_name, "")
        check("/opt/ros/" not in value, f"{variable_name} 未混入 ROS Foxy")

    check(not os.environ.get("LD_PRELOAD"), "未使用全局 LD_PRELOAD")

    # Jetson 上先加载 PyTorch，可避免随后加载系统 MuJoCo/OpenCV 时耗尽 static TLS。
    import torch
    import mujoco
    import cv2
    import cyclonedds
    import numpy
    import unitree_sdk2py
    import yaml

    from config.go2w_config import DDS
    from driver.dds_driver import DdsDriver
    from policy.controller_go2w import ControllerGo2w
    from policy.controller_go2wcr import ControllerGo2wCR
    from policy.controller_go2wwmp import ControllerGo2wWMP

    for package_name, expected in EXPECTED_VERSIONS.items():
        actual = importlib.metadata.version(package_name)
        check(actual == expected, f"{package_name}=={expected}")

    check(not torch.cuda.is_available(), "当前 PyTorch 为 CPU-only 构建")
    check(
        torch.ones(4, dtype=torch.float32).sum().item() == 4.0,
        "PyTorch CPU 张量计算正常",
    )
    expected_threads = int(os.environ.get("OMP_NUM_THREADS", "1"))
    check(
        torch.get_num_threads() == expected_threads,
        f"PyTorch CPU threads={expected_threads}",
    )
    check(cv2.__version__ == "4.2.0", "复用 JetPack OpenCV 4.2.0")
    check(yaml.__version__ == "5.3.1", "复用系统 PyYAML 5.3.1")
    check(
        str(Path(unitree_sdk2py.__file__).resolve()).startswith(
            str(PROJECT_ROOT / "third_party/unitree_sdk2_python")
        ),
        "Unitree SDK2 Python 来自项目 third_party",
    )
    check(DDS.DEFAULT_NET_IF == "eth0", "Orin 实机默认网口为 eth0")
    check(
        all(
            controller is not None
            for controller in (ControllerGo2w, ControllerGo2wCR, ControllerGo2wWMP)
        ),
        "三个 policy controller 均可导入",
    )
    check(DdsDriver is not None, "DDS driver 可导入但未初始化")
    check(
        (PROJECT_ROOT / ".venv/lib/libddsc.so.0.10.2").is_file(),
        "CycloneDDS C 核心库为 0.10.2",
    )

    model = mujoco.MjModel.from_xml_path(
        str(PROJECT_ROOT / "assets/go2w_description/mjcf/go2w_scene.xml")
    )
    check(model.nu == 16, "MuJoCo Go2W 场景可无窗口加载且包含 16 个执行器")

    missing_models = [
        name for name in MODEL_FILES if not (PROJECT_ROOT / "models" / name).is_file()
    ]
    if missing_models:
        print("[WARN] 尚未复制 checkpoint:")
        for name in missing_models:
            print(f"       models/{name}")
    else:
        print("[OK] 三个 checkpoint 均已复制")

    print("[PASS] Orin 基础环境验证完成；本脚本未初始化 DDS")


if __name__ == "__main__":
    main()
