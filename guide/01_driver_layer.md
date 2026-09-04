# Step 1: 驱动层验证

## 目标

验证 `DdsDriver` 能正确：

1. 通过 DDS 订阅机器人的 LowState（关节角度、速度、IMU）
2. 在不启动 LowCmd 线程的情况下输出状态
3. 确认状态字段含义和实际更新速率

## Orin 上的网络关系

原先策略进程运行在笔记本上，笔记本通过扩展坞网口加入机器人所在的局域网。现在策略进程
直接运行在扩展坞内的 Orin 上。从 DDS 应用的角度看，只是参与者从笔记本迁移到 Orin：

```text
以前：机器人内置计算机/网络 ─ 扩展坞 ─ 笔记本上的 DDS 进程
现在：机器人内置计算机/网络 ─ 扩展坞内 Orin 的 DDS 进程
```

LowState/LowCmd 的 topic、Domain ID 和消息类型不变。外部笔记本不再位于实时控制路径，
但 Orin 必须把 CycloneDDS 明确绑定到与机器人互通的 `eth0`。多网卡时绑定错误仍会导致
DDS 发现不到机器人。

## 前置条件

- Orin 的 `eth0` 保持现场地址 `192.168.123.18/24`
- 机器人已开机
- Python 环境可导入 CycloneDDS；Unitree SDK2 Python 源码已随项目提供（不需要 ROS2）

## 步骤

### 1. 激活环境

```bash
cd /home/unitree/sim2real
source setup.sh robot
```

### 2. 运行驱动测试

```bash
python scripts/real/test_dds_driver.py
```

Orin 专用默认网口为 `eth0`。需要显式传入时：
```bash
python scripts/real/test_dds_driver.py eth0
```

### 3. 观察输出

终端每 0.5 秒打印：

- Tick 计数，以及 SDK `power_v`/`power_a` 给出的电池电压和电流
- IMU RPY（roll, pitch, yaw）
- IMU quaternion、gyroscope 和 accelerometer
- 12 个腿关节位置和速度（DDS 索引 0-11）
- 4 个轮子位置和速度（DDS 索引 12-15）

### 4. 独立验证

本项目已内置 Unitree SDK2 Python 源码；本步骤只使用当前项目的
`test_dds_driver.py` 做只读状态检查，不依赖另一个工作空间中的监视脚本。

## 通过标准

- DdsDriver 初始化成功，并明确打印 LowCmd 发布线程尚未启动
- 16 个关节位置/速度持续更新且没有 NaN/Inf
- IMU quaternion、RPY、gyroscope 和 accelerometer 数据正常
- Tick 计数持续增长（说明 LowState 正常接收）
- 测试期间没有调用 LowCmd `Write()`
- Ctrl+C 退出后打印 "已关闭"

## 2026-09-03 Orin 实测记录

- `eth0`：`UP`，`192.168.123.18/24`。
- DDS 初始化成功，并打印 `LowCmd 发布线程尚未启动`。
- Tick 从 `4197523` 持续增长，约每 0.5 秒增加 500，符合约 1 kHz LowState 更新。
- 16 个关节、IMU quaternion/RPY/gyroscope/accelerometer 均连续收到合理数值。
- `power_v`/`power_a` 复测约为 `30.4 V / 1.3 A`。原代码误命名为 `battery_soc` 并
  打印百分号，现已改成 `battery_voltage`/`battery_current`，不再推测 SDK 没有提供的 SOC。
- Ctrl+C 后打印 `DdsDriver 已关闭`；本次未调用 `start_lowcmd_thread()` 或 LowCmd `Write()`。

结论：Orin 上的 driver 只读阶段通过。下一步是离线 policy 加载、输出维度、数值范围和
CPU 时延验证，仍不发送 LowCmd。

## 文件清单

| 文件 | 说明 |
|------|------|
| `config/go2w_config.py` | 所有常量、关节映射、安全限制 |
| `driver/driver_base.py` | RobotState / MotorCommand 数据类 + DriverBase 抽象类 |
| `driver/dds_driver.py` | DDS 驱动实现（500Hz 发布 + 内嵌安全） |
| `scripts/real/test_dds_driver.py` | 驱动层验证脚本 |
| `setup.sh` | 环境激活和项目内 SDK 路径准备脚本 |
