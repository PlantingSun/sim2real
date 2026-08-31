# D435i 实机画面读取：Orin 本地图形桌面

当前主线是在 Orin NX 的 Ubuntu 桌面直接读取和显示 D435i。相机通过 USB 连接 Orin，笔记本不直接打开相机设备，也暂不做 ROS2 跨网传图。

## 1. 先确认软件和设备

在 Orin 本地打开终端，只做读取检查：

```bash
lsusb
rs-enumerate-devices
command -v realsense-viewer || true
ls -l /dev/video* 2>/dev/null || true
```

当前现场已确认 `lsusb` 能看到 `Intel(R) RealSense(TM) Depth Camera 435i`，USB ID 为 `8086:0b3a`。如果 `rs-enumerate-devices` 能识别相机，优先尝试 `realsense-viewer`。

## 2. 使用 RealSense Viewer

在 Orin 图形桌面的终端执行：

```bash
realsense-viewer
```

在窗口中先打开 Color、Depth 或 Infrared 流，观察画面是否随目标变化。第一轮只验证：

- 彩色画面是否正常；
- 深度画面是否正常变化；
- 左右、上下和前方方向是否符合安装姿态；
- D435i 是否稳定工作而不是反复断连。

不要在 Viewer 阶段启动 WMP、LowCmd、Sport Mode 或任何运动控制程序。

## 3. 若 Viewer 不存在

先记录以下结果，不要直接在 Ubuntu 20.04 的 Orin 上套用笔记本的 ROS2 Humble 安装命令：

```bash
cat /etc/os-release
cat /etc/nv_tegra_release 2>/dev/null || true
command -v apt
command -v ros2 || true
ls /opt/ros 2>/dev/null || true
```

之后再根据实际 JetPack/L4T 和软件源选择 RealSense SDK 或 ROS2 wrapper。安装新软件前保留可用的图形桌面和 SSH 入口，并由用户审查安装方案。

## 4. 与 WMP 的关系

当前 `simtosim` 的 WMP 使用 `64×64`、单通道 `32FC1` 深度输入；实机 D435i 输出还需要单独确认流格式、分辨率、裁剪/缩放、无效值处理和归一化，不能把 Viewer 中看到的灰度画面直接送进网络。

网络传图、ROS2 DDS、ZeroMQ/WebRTC 和笔记本显示均属于备用方案，暂不作为本阶段任务。完成 Orin 本地读取后，再单独设计“相机数据 → WMP 输入”的只读验证。

## 5. 本阶段通过标准

- Orin 本地 Viewer 能稳定打开 D435i；
- Color、Depth/Infrared 至少各有一条流可观察；
- 已记录流的分辨率、帧率、格式和安装方向；
- 没有启动 WMP、LowCmd、Sport Mode 或其他机器人控制入口。
