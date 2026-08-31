# 5. 当前设备现场档案

本文件记录用户现场已经验证的信息。密码、密钥和其他认证凭据不记录在项目中。

用户确认：当前显示器连接、SSH 进入和模块操作方式均按照[宇树官方 Module Update 教程](https://support.unitree.com/home/zh/developer/module_update)完成并验证。

## 5.1 进入方式

| 方式 | 状态 | 说明 |
|---|---|---|
| 全功能 Type-C → HDMI → 外接显示器 | 已验证 | 可进入图形化 Ubuntu 桌面 |
| 用户扩展 RJ45 → SSH | 已验证 | 可从笔记本登录 Orin |
| USB/串口调试 | 未验证 | 暂不需要，除非网络和显示均不可用 |

## 5.2 登录和系统

```text
Linux user: unitree
hostname: ubuntu
OS: Ubuntu 20.04.5 LTS (Focal Fossa)
```

密码不写入此文件，也不写入命令、截图、Git commit 或聊天记录模板。

## 5.3 网络

```text
eth0    UP       192.168.123.18/24
lo      UNKNOWN  127.0.0.1/8
docker0 DOWN     172.17.0.1/16
l4tbr0  DOWN
rndis0  DOWN
usb0    DOWN
```

当前已知：SSH 使用 `eth0`，没有使用 USB gadget 网络。默认网关、路由表、DNS 和其他无线接口仍需在 Orin 上进一步读取。

## 5.4 USB 设备

```text
Bus 002 Device 002: ID 8086:0b3a Intel Corp.
Intel(R) RealSense(TM) Depth Camera 435i
```

同时识别到 USB 3 root hub、USB Hub 和键盘。该结果证明 D435i 已在 Orin NX 侧完成 USB 枚举；它不等于 RealSense SDK 或 ROS2 驱动已经安装。

## 5.5 下一步安全检查

联网或安装软件之前，先在 Orin 上保存以下只读结果：

```bash
ip -br addr
ip route
resolvectl status 2>/dev/null || true
lsusb
df -h
free -h
```

如果准备启用 Wi-Fi/4G/外部网络，先确认它不会改变机器人通信使用的 `eth0` 路由。不要直接修改 `192.168.123.18/24`，也不要删除现有路由。

## 5.6 现场事实与推断的区分

- 已验证：显示器进入、SSH 进入、用户名、主机名、Ubuntu 版本、`eth0` 地址、D435i USB 枚举。
- 尚未验证：JetPack/L4T 版本、GPU 驱动、RealSense SDK、ROS2、默认网关、Wi-Fi/4G 状态、是否安装浏览器。
- 不应推断：任何默认密码、其他机器的 IP、NVIDIA 开发套件的 USB 虚拟网卡地址、Orin 是否能直接运行当前笔记本 Python 环境。
