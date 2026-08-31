# 4. Orin NX 的系统特性

## 4.1 它不是普通的 x86 笔记本

Orin NX 通常运行 ARM64 Linux，常见系统栈包括 Jetson Linux、JetPack、CUDA、TensorRT 和 Python。它与当前笔记本可能存在以下差异：

- `uname -m` 通常是 `aarch64`，笔记本可能是 `x86_64`
- Python 包和预编译 wheel 必须支持 ARM64
- GPU 是 Jetson 集成平台的一部分，不应照搬 x86 上的 `nvidia-smi` 使用习惯
- CPU、GPU、内存、相机和其他设备共享平台资源，需要关注温度、内存和功耗
- D435i 的 USB 线接在 Orin 上，RealSense SDK 必须安装在 Orin 上

## 4.2 统一内存与 GPU

Jetson Orin NX 是边缘 AI 平台，适合把传感器采集、预处理和神经网络推理放在机器人附近完成。NVIDIA 官方数据表列出 Orin NX 8GB 和 16GB 两种模块，均为 1024 CUDA cores 和 32 Tensor cores；实际频率和可用性能会受到型号、JetPack、功耗模式、散热和载板影响。[Orin NX 数据表](https://developer.download.nvidia.com/assets/embedded/secure/jetson/orin_nx/docs/Jetson-Orin-NX-Series-Modules-Datasheet_DS-10712-001_v1.7.pdf)

不要把网页上的 TOPS 峰值直接等同于当前机器的实际推理速度。我们后续应先记录实际型号、JetPack/L4T 版本、内存、温度和功耗模式。

## 4.3 常用只读诊断命令

```bash
uname -m
cat /etc/os-release
cat /etc/nv_tegra_release 2>/dev/null || true
tegrastats
```

`tegrastats` 可以观察 CPU、GPU、内存和温度。不要在尚未了解当前配置时自行执行 `nvpmodel -m`、`jetson_clocks` 或刷写命令；这些会改变运行状态。

## 4.4 存储与文件位置

Orin 的系统盘可能是 NVMe、eMMC 或其他载板配置。不要假设 `/home`、模型目录或系统服务位置与笔记本相同。第一次登录只记录：

```bash
df -h
lsblk
free -h
```

代码同步到 Orin 后，应使用独立工作目录，例如 `/home/<用户名>/sim2real_ws`，不要覆盖宇树预装目录。

## 4.5 网络与机器人控制的边界

同一块网卡可能同时承载机器人 DDS 和普通文件/ROS2 图像流，也可能由不同网卡分别承载。网络接口、DDS domain、CycloneDDS/Fast DDS 配置都必须先读取再决定。

本项目现有控制代码使用 Unitree DDS，并且已经完成过实机部署；Orin 入门阶段不修改它。相机读取应先作为独立只读进程验证，之后再讨论是否让 WMP 使用 Orin 上的相机数据。
