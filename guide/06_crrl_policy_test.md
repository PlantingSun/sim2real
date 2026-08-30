# CRRL-1：go2wcr 策略离线测试

## 目标

确认 `model_1499.pt` 能在当前无 ROS 的 policy 层加载，并确认观测、课程嵌入、四阶段残差推理和 DDS 电机指令的维度与顺序。

## 关键接口

| 项目 | 数值 |
|---|---:|
| 单帧观测 | 53 |
| 历史帧数 | 5 |
| 归一化观测 | 265 |
| 上一动作 | 16 |
| 课程嵌入 | 4 |
| Actor 输入 | 285 |
| Actor 输出 | 16 |
| Critic 输入 | 123（实机不使用） |

CRRL Actor 每次调用只预测一个残差动作。控制器按 stage 0、1、2 累加三次残差，再以 stage 3 预测最终残差；每次新测试都从零动作开始。课程嵌入按照训练配置 `pow=1.5` 生成，不能改成全零或只使用最后一个标量。

控制器 `reset()` 会把 5 帧历史初始化为初始站立零运动状态：投影重力为 `(0, 0, -1)`，
角速度、速度指令、关节位置偏差、关节速度和上一动作均为 0。这里的“零运动状态”不是
53 维数值全零；四元数和绝对关节角度不直接进入策略观测，分别通过投影重力和关节位置偏差体现。

## 执行

```bash
cd /home/robot/sim2real_ws
source setup.sh policy
python scripts/policy/test_policy_go2wcr_offline.py
```

也可以显式指定模型：

```bash
python scripts/policy/test_policy_go2wcr_offline.py --model models/go2wcr/model_1499.pt
```

## 通过标准

- Actor 首层为 `285 → 256`，末层为 `256 → 16`。
- 课程嵌入形状为 `(4, 4)`，正余弦值有限。
- 初始站立零运动状态得到 265 维观测和 16 维有限动作。
- `MotorCommand` 为 DDS 顺序；腿关节为位置环，轮子为速度环。
- 没有导入 DDS、没有创建 publisher、没有发送机器人指令。

## 人工复核点

- 不要把 `models/go2wcr/model_1499.pt` 当作普通 go2w 模型加载；两者 Actor 输入维度不同。
- 当前零状态输出动作范围只用于接口检查，不代表实机安全范围。动作缩放、轮速和姿态稳定性必须经过仿真及吊架测试。

## 文件

- `policy/controller_go2wcr.py`：纯 PyTorch CRRL 推理与 MotorCommand 转换。
- `config/go2w_config.py`：`CRRL` 网络和课程参数；电机参数复用 `CTRL`。
- `models/go2wcr/model_1499.pt`：CRRL checkpoint。
- `scripts/policy/test_policy_go2wcr_offline.py`：本步骤测试入口。
