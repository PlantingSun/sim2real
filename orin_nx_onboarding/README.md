# Go2W 机载 Orin NX 入门

本目录是给当前项目使用的 Orin NX 入门和维护手册。目标是让我们在接入 D435i、WMP 或任何机器人控制前，先理解并验证机载计算机本身。

## 当前学习顺序

1. [直接进入图形桌面](01_first_contact.md)：本地显示器、键盘鼠标和 D435i USB 检查
2. [图形界面说明](03_graphical_access.md)：当前本地工作方式和安全边界
3. [系统特性与环境](04_system_characteristics.md)：ARM64、JetPack、CUDA、统一内存和 USB
4. [当前设备现场档案](05_verified_device_profile.md)：保存已经验证的硬件事实
5. [D435i 读取](../guide/10_realsense_network_view.md)：后续改为 Orin 本地查看/处理主线

备用维护：[远程登录与文件传输](02_network_and_files.md)、[联网与外置天线安全检查](06_networking_safely.md)。

## 总体认识

```text
笔记本：开发、编辑、审查
   │
   │  必要时 SSH / SCP 维护
   │
Orin NX：本地图形桌面、相机采集、GPU 推理、传感器处理
   │
   ├── USB → RealSense D435i
   └── 以太网/DDS → Go2W 与笔记本
```

Orin NX 是一台独立的 Linux 计算机，不是笔记本的远程 USB 扩展。D435i 连接在 Orin NX 上时，只有 Orin NX 能直接打开 `/dev/video*` 或 RealSense USB 设备；笔记本只能接收 Orin NX 转发出来的数据。

## 重要规则

- 不根据网上别人的 IP、用户名、端口或功耗设置猜测本机配置。
- 不刷写系统、不进入 Force Recovery、不修改功耗模式，除非单独确认并由用户审查。
- 当前优先在 Orin 本地图形桌面运行信息查询和相机读取；不启动 LowCmd、Sport Mode、WMP policy 或运动控制。
- 任何准备在实机上运行的代码，都先在本项目中保留清晰注释并交由用户审查。

## 官方资料

- [NVIDIA Jetson AGX Orin Developer Kit Quick Start](https://docs.nvidia.com/jetson/agx-orin-devkit/user-guide/latest/quick_start.html)
- [NVIDIA Jetson AGX Orin Developer Kit Hardware Layout](https://docs.nvidia.com/jetson/agx-orin-devkit/user-guide/hardware_layout.html)
- [NVIDIA Jetson Orin NX Series Modules Data Sheet](https://developer.download.nvidia.com/assets/embedded/secure/jetson/orin_nx/docs/Jetson-Orin-NX-Series-Modules-Datasheet_DS-10712-001_v1.7.pdf)
- [Unitree Go2 ROS2 repository](https://github.com/Unitree-Go2-Robot/go2_robot)
- [Unitree teleimager](https://github.com/unitreerobotics/teleimager)
- [宇树 Go2-W 官方产品页](https://www.unitree-robot.com/cn/go2-w/)
- [宇树 Go2-W 用户手册入口](https://marketing.unitree.com/article/en/Go2-W/User_Manual.html)
- [宇树官方 Module Update 教程](https://support.unitree.com/home/zh/developer/module_update)
