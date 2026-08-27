# Step 1: 驱动层验证

## 目标

验证 `DdsDriver` 能正确：
1. 通过 DDS 订阅机器人的 LowState（关节角度、速度、IMU）
2. 在不启动 LowCmd 线程的情况下输出状态
3. 与现有 `monitor_lowstate.py` 的数据保持一致

## 前置条件

- 网线已连接机器人，主机静态 IP `192.168.123.99/24`
- 机器人已开机
- Conda unitree_py38 + unitree_sdk2py/CycloneDDS 已安装（不需要 ROS2）

## 步骤

### 1. 激活环境

```bash
cd /home/robot/sim2real_ws
source setup.sh robot
```

### 2. 运行驱动测试

```bash
python scripts/test_dds_driver.py
```

如网口名不同，传入参数：
```bash
python scripts/test_dds_driver.py enp0s31f6
```

### 3. 观察输出

终端每 0.5 秒打印：
- Tick 计数和电池电量
- IMU RPY（roll, pitch, yaw）
- IMU quaternion、gyroscope 和 accelerometer
- 12 个腿关节位置和速度（DDS 索引 0-11）
- 4 个轮子位置和速度（DDS 索引 12-15）

### 4. 对比验证

另开终端运行现有脚本：
```bash
cd /home/robot/test_com_ws
source scripts/env_setup.sh
python scripts/monitor_lowstate.py
```

对比两边输出的关节角度和 IMU 数据，确认一致。

## 通过标准

- DdsDriver 初始化成功，并明确打印 LowCmd 发布线程尚未启动
- 关节位置与 monitor_lowstate.py 输出一致（误差 < 0.01 rad）
- IMU quaternion、RPY、gyroscope 和 accelerometer 数据正常
- Tick 计数持续增长（说明 LowState 正常接收）
- 测试期间没有调用 LowCmd `Write()`
- Ctrl+C 退出后打印 "已关闭"

## 文件清单

| 文件 | 说明 |
|------|------|
| `config/go2w_config.py` | 所有常量、关节映射、安全限制 |
| `driver/driver_base.py` | RobotState / MotorCommand 数据类 + DriverBase 抽象类 |
| `driver/dds_driver.py` | DDS 驱动实现（500Hz 发布 + 内嵌安全） |
| `scripts/test_dds_driver.py` | 驱动层验证脚本 |
| `setup.sh` | 环境激活脚本 |
