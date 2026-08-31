# 1. 直接进入 Orin NX 图形桌面

当前主线是在 Orin NX 本地完成 D435i 读取和后续推理。SSH、文件传输和串口只作为备用维护方式，分别见 [02_network_and_files.md](02_network_and_files.md) 和 [05_verified_device_profile.md](05_verified_device_profile.md)。

## 1.1 设备关系

```text
Go2W       = 机器人本体、电机和运动控制
Orin NX    = 机载 ARM64 Linux 计算机
D435i      = 通过 USB 连接在 Orin NX 上的深度相机
```

Orin 上电不等于机器人已经进入运动模式。本阶段不启动 LowCmd、Sport Mode、WMP 或其他运动控制程序。

## 1.2 已验证的本地连接

1. 机器人保持安全静止，遥控器和急停手段放在手边。
2. 使用扩展坞的全功能 Type-C → HDMI 转换器连接显示器。
3. 使用 USB-A 连接键盘和鼠标。
4. 上电后进入 Ubuntu 图形桌面，登录用户 `unitree`。
5. D435i 保持连接在标注为深度相机的 USB 3 接口。

宇树 Go2-W 手册将全功能 Type-C 用于显示器、USB3.2 Type-C 用于深度相机、USB-A 用于用户扩展。实际操作以端口旁的标识为准，不要仅凭 Type-C 外形判断用途。[Go2-W 官方产品页](https://www.unitree-robot.com/cn/go2-w/)

## 1.3 图形桌面中的第一次检查

打开终端，只读取以下信息：

```bash
whoami
hostname
uname -m
cat /etc/os-release
ip -br addr
lsusb
command -v realsense-viewer || true
command -v rs-enumerate-devices || true
ls -l /dev/video* 2>/dev/null || true
```

已知现场结果为：`unitree@ubuntu`、Ubuntu 20.04.5 LTS、`eth0=192.168.123.18/24`，并且 `lsusb` 能看到 D435i `8086:0b3a`。USB 枚举成功只说明系统看到了相机，不等于 SDK 或图形查看器已经可用。

## 1.4 本章完成标准

- 能在 Orin 本地看到 Ubuntu 图形桌面。
- 能打开终端并确认当前用户确实是 Orin 上的 `unitree`。
- 能确认 D435i 已经连接并被 USB 识别。
- 不修改网络、功耗或系统软件，不启动机器人控制。
