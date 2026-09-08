# 21：Go2WWMP 手柄命令接入与只读验收

本步骤只接入 Xbox 手柄的 `cmd_vel`，不测试 Unitree 原生 Sport/High-level 控制。
助手不会运行下面的实机命令；真实 action 仍由用户在保护架、物理急停和第二人观察下执行。

## 1. 命令范围来源

已直接核对 `/home/robot/simtosim/src/controller/model/go2wwmp/go2wwmp_config.py`：

```text
lin_vel_x   = [0.0, 1.0] m/s
lin_vel_y   = [0.0, 0.0] m/s
ang_vel_yaw = [-1.0, 1.0] rad/s
```

因此原始训练分布没有负向 `vx`，也没有侧向 `vy`。本项目按用户确认，将实机部署入口的 `vx`
扩展到 `[-0.2,1.0]`；这属于明确的部署侧 OOD 扩展，不是训练配置本身。仓库中的 WMP 控制器、
worker 和仿真入口会统一按当前部署包络裁剪；这不是 Go2W/Go2WCR 的通用 `COMMAND_LIMITS`。

按用户要求，当前实机手柄默认允许的部署范围是：

```text
vx   ∈ [-0.2, 1.0] m/s
vy   = 0
vyaw ∈ [-1.0, 1.0] rad/s
```

其中 `vx=-0.2…0` 是按用户要求增加的少量倒车范围，超出原始 simtosim 配置的 `vx=[0,1]`；
因此首次实机仍应手动小幅推动，不要直接推满摇杆。`--max-vx` 和 `--max-vyaw` 只允许在
上述部署范围内调整。

## 2. 先做离线输入检查

这一步不初始化 DDS、不连接机器人、不发送 LowCmd。按住 Xbox A 才会输出非零命令，松开 A
立即归零；左摇杆横向始终映射为 `vy=0`，不会把侧向输入送入 WMP。

```bash
cd /home/robot/sim2real_ws
source setup.sh robot
python scripts/input/test_command_input.py
python scripts/input/debug_command_input.py --control xbox --wmp-bounds
```

离线监视时逐轴缓慢移动，并确认：

- 左摇杆纵向正向只产生 `vx`，范围为 `0…1.0`；反向不会产生负 `vx`；
- 左摇杆横向始终显示 `vy=+0.000`；
- 右摇杆横向只产生 `vyaw`，范围为 `-1.0…+1.0`；
- 未按 A 或松开 A 时三个命令立即为零；
- Back 请求退出。

## 3. 真机 print-only：验证手柄命令进入 WMP

网卡默认从 `config/go2w_config.py` 的 `DDS.DEFAULT_NET_IF/DEPTH_NET_IF` 读取；当前笔记本
domain 0/42 共用固定的 `enp0s31f6`，不需要手动 export。只有更换网线拓扑时才显式覆盖。

```bash
export WMP_MODEL=models/go2wwmp/model_6000.pt
```

运行只读入口。它会接收 domain 0 LowState、domain 42 深度并执行 WMP 推理，但不会调用
`StandUp`、`ReleaseMode`、LowCmd 线程或 `Write()`：

```bash
python scripts/real/test_policy_go2wwmp_real.py \
  --print-only --control xbox \
  --model "$WMP_MODEL" \
  --duration 30 \
  --log logs/real/go2wwmp_xbox_print_only.jsonl
```

观察 `[WMP PRINT]` 中的 `cmd=[vx, vy, vyaw]`：

1. 不按 A，必须保持 `[0, 0, 0]`；
2. 按住 A，缓慢向前或小幅倒车，`vx` 不得超过 `1.0` 或低于 `-0.2`；
3. 左摇杆横向怎么动，`vy` 都必须为 `0`；
4. 右摇杆横向只改变 `vyaw`，绝对值不得超过 `1.0`；
5. 松开 A 后命令回到零；
6. 手柄拔出或读取异常时，本轮应报告输入错误并停止，不应继续使用最后一条旧命令。

通过条件是命令字段、`command_enabled`、深度新鲜度和 WMP 推理都正常，且最终
`lowcmd_started=False writes=0`。这一步通过前不要进入 action。

## 4. 长时间 action 手柄测试

只有第 3 节通过后，才允许用户现场执行。机器人必须已经完成过稳定的地面承重站立，保护架/绳、
物理急停和第二人观察全部就绪。下面命令省略 `--duration`，会持续运行到 Ctrl+C、Xbox Back
或输入故障；默认只显示一张深度图，以 2 Hz 刷新，不需要额外的深度参数：

```bash
python scripts/real/test_policy_go2wwmp_real.py \
  --ground-stand --arm --enable-wmp-action --control xbox \
  --model "$WMP_MODEL" \
  --log logs/real/go2wwmp_xbox_long.jsonl
```

现场顺序：

1. 不按 A，先确认机器人只保持原地站姿；
2. 只给很小的 `vx`，立即回中并松开 A；
3. 如无异常，再单独给很小的 `vyaw`；不要同时推两个轴，不要推满摇杆；
4. 出现抖动、姿态发散、方向错误或手柄断连，立即松开 A、按 Ctrl+C，并准备使用物理急停。

深度窗口只显示一张米制深度图，无效像素用紫色标出。按窗口的 `q`/Esc 只关闭预览，不会停止
控制；停止控制使用 Xbox Back 或 Ctrl+C。日志持续写入 `command`、深度质量、
状态年龄、action 和 MotorCommand，长时间测试结束后再离线分析。

此测试验证的是“手柄 → WMP 命令 → action”链路，不等于已经完成自由行走或越障。虽然程序
允许完整的部署范围，第一次长测仍应从小幅输入开始。

## 5. 切换到宇树原装遥控器

当前 Go2WWMP 已提供 `--control unitree`，完整流程见
[guide/22_go2wwmp_unitree_remote.md](22_go2wwmp_unitree_remote.md)。本章节的 Xbox 流程与宇树
手柄流程仍然互斥；不要让两个输入源同时运行。

`test_policy_unitree_remote.py` 仍是旧 Go2W/Go2WCR policy 的独立入口，不能代替 guide 22 的
Go2WWMP WMP/depth pipeline。
