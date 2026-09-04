# Step 5：Go2W 实机测试

本阶段使用 `scripts/real/test_policy_real.py`。该入口在一条命令中启动两个进程：

- 主进程：DDS 通信和 500 Hz LowCmd 发送。
- policy 子进程：50 Hz 网络推理，默认绑定 CPU 2，PyTorch 使用 1 个线程。

当前先完成普通 Go2W policy 的实机验证。宇树原装遥控器和最终通过标准保留在文档后部，
暂不进行。

## 一、每次测试前的准备

进入项目并加载机器人环境：

```bash
cd /home/unitree/sim2real
source setup.sh robot
```

确认以下条件：

- Orin NX 通过 `eth0` 连接机器人。
- 机器人周围无障碍，急停和吊绳可立即使用。
- 按 `1` 执行 StandUp 时，机器人必须在地面上。
- 机器人完全站稳后再吊起，最后才能按 `2` 释放 Sport Mode。
- 执行过 `ReleaseMode()` 或程序进入阻尼后，下次测试前必须先恢复 `ai-w`。

恢复 `ai-w` 的命令如下。它只切换模式，不发送 LowCmd：

```bash
python scripts/real/select_wheeled_sport.py
```

看到下面的信息才表示恢复成功：

```text
[MotionSwitcher] Go2W 模式已就绪: ai-w
```

## 二、正常启动和调试流程

### 2.1 只检查 DDS 状态，不发送任何 LowCmd

机器人保持正常模式，运行：

```bash
python scripts/real/test_dds_driver.py
```

确认以下数据持续刷新且数值合理：

- `Tick` 持续增加。
- 16 个关节的位置和速度正常。
- IMU 四元数、角速度和加速度正常。
- 没有 NaN、Inf 或明显不连续的跳变。

按 Ctrl+C 退出。此脚本不会调用 `ReleaseMode()`，也不会发送 LowCmd。

### 2.2 只验证双进程和 50 Hz，不发送 policy 动作

只有需要检查频率、预热或进程通信时才运行：

```bash
python scripts/real/test_policy_real.py \
  --control fixed --vx 0 --vy 0 --vyaw 0 \
  --print-only
```

操作顺序：

1. 机器人在地面时按 `1`，执行 StandUp。
2. 确认机器人完全站稳。
3. 将机器人吊起并确认吊具可靠。
4. 按 `2`，释放 Sport Mode 并启动 500 Hz 固定站姿 LowCmd。
5. 等待 3 秒预热结束，观察 `[RATE] policy` 是否稳定在约 50 Hz。
6. 按 Ctrl+C 退出，程序进入紧急阻尼。

注意：`--print-only` 只表示“不发送 policy 预测动作”。按 `2` 后仍会发送固定的
`INITIAL_JOINTS_POS`，因此也必须完成站立和吊起流程。

### 2.3 正常启动零速度 policy

正式发送 policy 动作时运行：

```bash
python scripts/real/test_policy_real.py \
  --control fixed --vx 0 --vy 0 --vyaw 0
```

仍然严格按照 `1 → 站稳 → 吊起 → 2` 的顺序操作：

1. 按 `1`：Sport Mode 执行 StandUp，此时没有 LowCmd。
2. 机器人站稳后吊起。
3. 按 `2`：执行一次 `ReleaseMode()`，随后立即启动固定站姿 LowCmd。
4. policy 加载并预热 3 秒。预热期间网络会计算，但不会发送预测动作。
5. 出现 `[POLICY ACTIVE]` 后，policy 开始以约 50 Hz 更新动作；LowCmd 始终以
   500 Hz 重复发送最新命令。
6. 观察机器人零速度站立状态，按 Ctrl+C 退出并进入阻尼。

预热阶段的 `last_action` 始终为 16 维零向量。机器人实际收到的是固定
`INITIAL_JOINTS_POS`；对于当前控制器，零 action 映射后的目标与该固定站姿一致。

### 2.4 使用 Xbox 手柄

零速度 policy 验证完成后运行：

```bash
python scripts/real/test_policy_real.py --control xbox
```

同样按照 `1 → 站稳 → 吊起 → 2` 接管。A 未按下时速度命令为零；按住 A 后才接收摇杆
命令。先小幅测试一个方向，松开 A 后确认速度立即归零，Back 或 Ctrl+C 退出。

Xbox 映射：左摇杆纵轴为 `vx`，左摇杆横轴为 `vy`，右摇杆横轴为 `vyaw`，A 为
deadman，Back 为退出。不要直接推满摇杆。

## 三、当前需要执行的测试：完整日志和 observation

当前任务是发送真实 policy 动作，同时记录 Orin NX 上的完整闭环数据。不要添加
`--print-only`。

### 3.1 启动前

如果上一次程序已经按 `2` 接管，或者机器人当前处于阻尼模式，先恢复 `ai-w`：

```bash
python scripts/real/select_wheeled_sport.py
```

然后重新确认 DDS 状态：

```bash
python scripts/real/test_dds_driver.py
```

确认正常后按 Ctrl+C 退出状态检查。

### 3.2 运行并保存日志

保持吊绳保护，运行：

```bash
python scripts/real/test_policy_real.py \
  --control fixed --vx 0 --vy 0 --vyaw 0 \
  --log logs/real/policy_mp.csv
```

按以下顺序操作：

1. 机器人在地面时按 `1`。
2. 等待 StandUp 完成并确认机器人站稳。
3. 吊起机器人。
4. 按 `2` 启动接管。
5. 等待 3 秒预热和 policy 频率稳定。
6. 先记录一段无扰动站立数据，再进行数次轻微、可控的扰动。
7. 数据足够后按 Ctrl+C，程序进入阻尼并关闭。

该命令会生成两份文件：

- `logs/real/policy_mp.csv`：状态年龄、循环/IPC/推理耗时、命令、完整 LowState、
  raw action 和发送的 `p/v/kp/kd`。
- `logs/real/policy_mp_observation.csv`：每帧 265 维 observation 和对应的 16 维
  raw action，用于跨计算机复现推理。

两份日志都会逐行 flush。记录会带来少量磁盘开销，正常运行时不加 `--log` 即可关闭。

### 3.3 在 Orin NX 上离线复现

实机测试结束后，该命令只读取 CSV 和模型，不连接机器人：

```bash
python scripts/policy/replay_observation_csv.py \
  logs/real/policy_mp_observation.csv \
  --model models/go2w/model_700.pt --threads 1
```

记录输出的 `mean_error` 和 `max_error`。

### 3.4 复制到笔记本后对比

先在 Orin NX 和笔记本分别执行：

```bash
sha256sum models/go2w/model_700.pt
```

只有两端 SHA-256 完全相同才能继续比较。将以下两项复制到笔记本：

- `logs/real/policy_mp_observation.csv`
- `models/go2w/model_700.pt`

在笔记本的项目环境中执行同一条离线复现命令：

```bash
python scripts/policy/replay_observation_csv.py \
  logs/real/policy_mp_observation.csv \
  --model models/go2w/model_700.pt --threads 1
```

比较两端的 `mean_error` 和 `max_error`。误差接近浮点舍入范围，说明相同 observation
在两台计算机上产生的 action 基本一致；误差明显时再检查模型、PyTorch 版本和计算架构。

## 四、退出和下一次重启

- 按 `2` 前按 `q`：退出且不会启动 LowCmd。
- LowCmd 启动后按 Ctrl+C、Back 或正常结束：程序发送紧急阻尼并关闭。
- 进入阻尼后不能直接再次 StandUp。下一次运行前先执行
  `python scripts/real/select_wheeled_sport.py`。
- 发生剧烈抖动、异常抬腿、超速或姿态快速发散时立即退出，不要等待测试自动结束。

## 附：宇树原装遥控器入口

```bash
python scripts/real/test_policy_unitree_remote.py
```

该入口使用 `L2+R2` 触发接管，Select 退出；它不是当前 Xbox 三步流程的必要步骤。

Xbox 映射为左摇杆纵轴→`vx`、左摇杆横轴→`vy`、右摇杆横轴→`vyaw`；A 是 deadman，
Back 退出。不要直接推满摇杆；满行程会映射到 `CTRL.COMMAND_LIMITS`。

## 逐关节限位

吊架测试时记录 DDS 0–11 的真实 `q/dq` 范围，再在
`config/go2w_config.py` 中逐项填写 `DDS.JOINT_LIMITS`。必须给正常运动留出裕量，
不要改回统一的循环推导值。四个轮子的速度由 `DDS.WHEEL_VEL_LIMIT` 单独检查。

## 通过标准

- StandUp 期间没有 LowCmd 干扰。
- ReleaseMode 返回后由固定位置环立即、平稳接管。
- 预热期间不发送 policy action，预热后 policy 稳定在约 50 Hz。
- 零速 policy 能稳定站立至少 60 秒。
- Xbox 松开 A 时三个速度均为零。
- Xbox 按住 A 后三个轴方向、回中值和限幅正确。
- 从低速开始时，前进、侧向和转向方向正确且机器人保持稳定。
- Ctrl+C 或 Back 退出后正常进入阻尼并关闭。

## 异常处理

| 现象 | 处理 |
|------|------|
| 接管时蹦跳或剧烈抖动 | 立即退出，检查关节映射和初始位置 |
| 网络站立振荡逐渐增大 | 立即退出，检查观测、IMU 和 PD 增益 |
| 摇杆方向错误 | 立即回中并按 Select 退出，只修改新脚本顶部的方向符号 |
| LowState 超时 | 程序应报告异常并进入阻尼；不要继续测试 |
| 触发关节或轮速限位 | 保留违规信息，检查限位值与实际运动范围 |
| 姿态漂移 | 检查 DDS 四元数顺序和陀螺仪数据 |
