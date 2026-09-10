# 22：Go2WWMP 宇树原装遥控器

本步骤把 Go2WWMP 的速度命令来源从 Xbox 切换为 Go2-W 原装遥控器。遥控器数据来自
`rt/lowstate.wireless_remote[40]`，不走 Linux joystick。摇杆映射保持已经核对的方向：

```text
vx   = Ly（前后）
vy   = 0（WMP 禁用侧向）
vyaw = -Rx（左右转向）
```

实机部署包络为 `vx=[-0.2,1.0] m/s`、`vy=0`、`vyaw=[-1.0,1.0] rad/s`，并使用 `0.10`
deadzone。宇树手柄没有 Xbox A deadman；回中会给零速度，Select 请求退出。

正式入口接管后还支持航向保持：单击 A 锁定当前 yaw 并固定 `vx=0.5 m/s`，单击 B 关闭并
恢复 Ly/Rx 手动命令。该功能不属于前面的短时验收入口，完整说明见
[guide 23](23_go2wwmp_heading_mode.md)。

## 1. 先做只读遥控器检查

这一步只订阅 LowState，不创建 LowCmd publisher：

```bash
source setup.sh robot
python scripts/input/debug_unitree_remote.py \
  --hz 10
```

确认 `Lx/Ly/Rx/Ry` 会随手柄变化、按钮名称正确、数据持续刷新。按 Ctrl+C 退出。

## 2. WMP print-only

这一步不调用 `StandUp`、`ReleaseMode`、LowCmd 线程或 `Write()`，只检查遥控器命令是否进入
WMP。它可以持续运行到 Select 或 Ctrl+C；如只做 30 秒检查，可以加 `--duration 30`：

```bash
python scripts/real/test_policy_go2wwmp_real.py \
  --print-only --control unitree \
  --model "$WMP_MODEL" \
  --duration 30 \
  --no-depth-display \
  --log logs/real/go2wwmp_unitree_print_only.jsonl
```

观察 `[WMP PRINT] cmd=[vx, vy, vyaw]`：不动摇杆时应接近零，`vy` 始终为零，松开/回中后命令
应回零；Select 会结束只读循环。通过后才能进入接管。

## 3. 已完成的短时接管验收

此入口不猜测宇树原生 `StandUp` 按键组合。运行前，机器人必须已经由原生 Sport Mode 站稳，
并且保护架/绳、物理急停和第二人观察已就绪。程序启动后等待手柄的 **L2+R2 新按下沿**：

```bash
python scripts/real/test_policy_go2wwmp_real.py \
  --ground-stand --arm --enable-wmp-action --control unitree \
  --model "$WMP_MODEL" \
  --duration 5 \
  --no-depth-display \
  --log logs/real/go2wwmp_unitree_action_5s.jsonl
```

流程是：

1. 确认机器人已在原生 Sport Mode 站稳；
2. 松开 L2+R2，再同时按下 L2+R2，程序调用 `ReleaseMode()` 并发送固定初始站姿；
3. 后续 WMP action 由宇树手柄的 Ly/Rx 控制；
4. Select、Ctrl+C、输入超时、深度/状态故障或实测 `dq>30 rad/s` 会停止本轮并进入阻尼。

第一次只给极小前进或转向命令，不同时推两个轴，不直接推满摇杆。这个入口仍是 WMP
LowCmd 控制，不是 Unitree 原生 Sport/High-level 与 WMP 并行运行。

30 秒实机测试已经完成：机器人能从站立状态由 L2+R2 启动网络并接管控制，日志为
`logs/real/go2wwmp_unitree_action_30s.jsonl`。后续正常使用不再重复填写这些验收参数。

## 4. 正式长期运行

每个新终端先在项目根目录执行一次 `source setup.sh robot`（只配置 Python/DDS 环境，不发送
控制指令）。机器人再由原装手柄在 Sport Mode 下站稳，保护架/绳和物理急停就绪后，直接运行：

```bash
python scripts/real/run_go2wwmp_unitree.py
```

无参数时已经固定为当前验收配置：

- 使用 `models/go2wwmp/model_6000.pt`；
- 从 `go2w_config.py` 读取笔记本固定网口，同时接收 domain 0 和 domain 42；
- 使用宇树手柄，`vx=Ly`、`vy=0`、`vyaw=-Rx`；
- 接管后可单击 A 开启航向保持、单击 B 关闭；开启时固定 `vx=0.5 m/s` 并自动计算 `vyaw`；
- 完成只读自检后等待 L2+R2 新按下沿，再释放 Sport Mode 并发送 WMP action；
- 不设运行时长，Select 或 Ctrl+C 退出；
- 显示一幅 2 Hz 深度预览，并自动写入 `logs/real/go2wwmp_unitree_时间.jsonl`。

自动日志采用一行一个控制周期的 JSONL，完整字段、Ctrl/DDS 数组顺序、未记录内容、Python
读取方式和容量估算见 `22.5_go2wwmp_log_format.md`。其中 `positions/velocities` 是下发目标，
不是电机实测反馈。正式入口还会默认生成同名 `_obs/` 目录，保存 timestamp、WMP 观测、
LowState 观测和实际深度更新帧；可用 `--no-observation-log` 关闭。

`run_go2wwmp_unitree.py` 是完整、独立的正式状态机，不会导入或调用
`test_policy_go2wwmp_real.py`。它只复用稳定的底层模块：DDS 驱动、WMP worker 和
`teleop/unitree_remote.py` 遥控器解析。因此以后给正式运行增加功能时，不需要继续向验收脚本
叠加模式分支。

正式入口还把接管顺序固定为：在 Sport Mode 仍保持站立时先完成深度 session 同步并缓存初始
站姿，随后才调用 `ReleaseMode()`，返回后立即启动 500 Hz LowCmd。退出时先切换到阻尼，再关闭
WMP 子进程和显示窗口。

如需换 checkpoint、指定日志名、关闭预览或管理观测归档，只保留以下可选项：

```bash
python scripts/real/run_go2wwmp_unitree.py --model models/go2wwmp/model_6000.pt
python scripts/real/run_go2wwmp_unitree.py --log logs/real/my_run.jsonl
python scripts/real/run_go2wwmp_unitree.py --no-depth-display
python scripts/real/run_go2wwmp_unitree.py --observation-dir logs/real/my_run_obs
python scripts/real/run_go2wwmp_unitree.py --no-observation-log
```

启动后先松开 L2+R2，再同时按下二者接管。程序不会自行调用 StandUp，也不会在运行结束后
恢复 Sport Mode；Select/Ctrl+C 或故障退出时，若 LowCmd 已接管，则进入阻尼。因此退出前仍要保证
机器人受保护，不能把 Select 当成原生坐下键。

### OpenCV/VS Code 提示

当前 `opencv-python` 使用 Qt 显示深度窗口。项目会在创建窗口前自动把 wheel 中不存在的
`cv2/qt/fonts` 修正为系统已有的 DejaVu 字体目录，因此不需要下载字体；该设置只影响预览窗口，
不会改变深度数据或控制循环。

`.vscode/settings.json` 已默认选择笔记本的 `unitree_py38`。如果 `import cv2` 仍有黄色下划线，说明
VS Code 保存了旧解释器选择：执行一次 **Python: Select Interpreter**，选择
`/home/robot/miniconda3/envs/unitree_py38/bin/python`，然后执行 **Developer: Reload Window**。

助手不会运行以上实机命令；设备、模型或网络配置变更后应重新执行第 1、2 节，并始终保持物理急停可用。
