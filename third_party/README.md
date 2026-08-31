# 项目内第三方源码

`unitree_sdk2_python/` 是 Unitree SDK2 Python 源码的项目内副本，保留原 BSD-3-Clause
许可证和架构相关 CRC 本地库。项目通过 `setup.sh` 将其加入 `PYTHONPATH`，因此运行入口
不需要再引用另一个工作空间中的 SDK 源码。

SDK 仍需要目标设备安装匹配架构的 Python、CycloneDDS 和 NumPy。不要把 x86_64 的
Python/CycloneDDS 二进制环境直接复制到 Jetson Orin NX；应在目标设备上安装对应 ARM64
运行时。
