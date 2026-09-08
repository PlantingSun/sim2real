# 20：Go2WWMP 真机数据验证与固定站姿测试

本阶段只验证“domain 0 状态 + domain 42 深度 → WMP 推理输出”的数据链路，并按安全流程测试
固定原地站姿。默认和 print-only 模式都不发送预测的 WMP MotorCommand。

真实动作入口必须由用户现场执行；助手不运行下面的任何实机命令。

## 1. 代码入口

- [scripts/real/test_policy_go2wwmp_real.py](../scripts/real/test_policy_go2wwmp_real.py)：主进程
  持有 Unitree domain 0，子进程持有深度 domain 42 和 WMP；
- [policy/process_worker_go2wwmp.py](../policy/process_worker_go2wwmp.py)：加载 checkpoint、
  接收深度、检查新鲜度、执行 WMP，并通过 Pipe 返回候选 MotorCommand；
- `tests/test_go2wwmp_real_pipeline.py`：只读的有效率和 MotorCommand 传输检查。

两个 domain 可以使用同一物理网卡，但分别配置；深度 worker 不进入 500 Hz LowCmd 线程。

## 2. 现场准备

在笔记本项目环境中：

```bash
cd /home/robot/sim2real_ws
source setup.sh robot
unset CYCLONEDDS_URI ROS_DOMAIN_ID LD_PRELOAD
export WMP_MODEL=models/go2wwmp/model_6000.pt
sha256sum "$WMP_MODEL"          # 记录并与 simulation 使用的 checkpoint 核对
python scripts/real/test_policy_go2wwmp_real.py --help
```

当前笔记本固定网口由 `config/go2w_config.py` 的 `DDS.LAPTOP_NET_IF` 提供，domain 0/42 默认复用
同一网卡；只有更换拓扑时才需要显式传 `--interface` 或 `--depth-interface` 覆盖。当前
`model_6000.pt` 只是候选，运行前应记录 SHA-256 并确认与 simulation 使用的 checkpoint 一致。

## 3. Print-only：不发送 LowCmd

这是第一项真机代码验证。它会：

- 创建 domain 0 的 LowState 只读驱动；
- 创建 domain 42 的深度接收器；
- 加载 WMP 并等待新鲜深度首帧；
- 用真实 LowState、深度和固定零速度命令 `cmd_vel=[0,0,0]` 计算候选 action/MotorCommand；
- 打印 session、frame、valid ratio、深度年龄、LowState 年龄、推理时间和候选关节/轮输出。

它不会调用 `StandUp()`、`ReleaseMode()`，不会启动 LowCmd 线程，也不会执行 `Write()`。

```bash
python scripts/real/test_policy_go2wwmp_real.py \
  --print-only \
  --model "$WMP_MODEL" \
  --duration 30 \
  --log logs/real/go2wwmp_print_only.jsonl
```

通过条件：

- `[READY]` 同时包含 model SHA-256、depth session/frame 和有效率；
- `[SELF CHECK]` 成功；
- `[WMP PRINT]` 持续出现，`valid` 作为诊断统计输出，深度 local age 不超过 100 ms；
- 如启用 `--log`，每行同时记录 `state_tick` 和 `state_age_ms`，便于确认状态没有静默复用；
- `[DONE] ... lowcmd_started=False writes=0`；
- 没有 `FAIL CLOSED`。

任何 session 改变、深度过期、LowState 过期、policy 超时或非法数值都应停止本轮；
有效率下降本身不触发失能，网络输入继续使用协议规定的远平面无效值。

## 4. 原地承重站立：只允许固定 INITIAL_JOINTS_POS

只有 print-only 通过后，才考虑这个步骤。机器人四足/轮保持接地并承重；保护绳或低位保护架只用于
限制异常动作，不用于把机器人完全吊离地面。必须有急停和第二人观察。
此模式的 WMP 输出仍然只打印；LowCmd 只发送固定 `INITIAL_JOINTS_POS`，不发送 WMP 预测动作。

```bash
python scripts/real/test_policy_go2wwmp_real.py \
  --ground-stand --arm \
  --model "$WMP_MODEL" \
  --duration 30 \
  --log logs/real/go2wwmp_hold_stand.jsonl
```

交互顺序：

1. 程序先完成模型、首帧深度和真实 LowState 的只读自检；失败时不会进入下一步。
2. 按 `1` 前机器人必须在地面，程序调用一次 `StandUp()`。
3. 确认机器人已经承重站稳，保护架/绳和急停可靠。
4. 按 `2`，程序调用一次 `ReleaseMode()`；程序先在不发 LowCmd 的状态下重新同步深度
   `session_id`，打印 `[DEPTH SYNC] ... rebased=...`，再启动 500 Hz 固定站姿 LowCmd。
5. 观察固定站姿、LowState、新鲜深度和 `[WMP PRINT]`；先测试 2 秒，再 5 秒，再 10 秒。
6. Ctrl+C 退出；程序进入紧急阻尼并关闭。

深度 session 只在 LowCmd 接管前允许重新基线；接管后只要深度过期、session 改变、LowState 过期、worker 退出、推理超时、
数值非法或观察到异常姿态，立即结束本轮。程序会在已启动 LowCmd 时进入阻尼；物理急停始终优先。
若接管后 session 改变，错误信息会同时打印旧/新 session 和当前 frame，便于回查 Orin 服务日志。
底行的旧有固定无效问题已改为最近真实传感器边缘采样；其余相机原生无效区域仍代表感知盲区，
`2 m` 远平面只避免伪造近障碍，不能证明低矮障碍一定可见。

## 5. 5 秒 WMP action 短测

只有上面的 30 秒固定站姿通过后，才允许显式打开 action。q range 只保留为 MJCF 参考，当前不启用
任何位置限位保护；位置目标 q 不在进入 500 Hz 缓冲前截断或拒绝，允许固定 Kp 通过超限目标产生
所需动态。命令侧 q/dq 均不做限幅；驱动只在 LowState 实测 `dq > 30 rad/s` 时进入紧急阻尼。下面仍是固定 5 秒的
短测；长时间 Xbox 测试见 guide 21，省略 `--duration` 后由 Back/Ctrl+C 停止。

该测试仍需地面承重、低位保护架/保护绳、物理急停和第二人观察；只测 5 秒，不代表已经可以
行走或跨越障碍：

```bash
python scripts/real/test_policy_go2wwmp_real.py \
  --ground-stand --arm --enable-wmp-action \
  --model "$WMP_MODEL" \
  --duration 5 \
  --log logs/real/go2wwmp_action_5s.jsonl
```

通过条件：`[GROUND STAND]` 后出现 action enabled、持续 `[WMP PRINT]`、没有 dq 限位/深度/状态故障，
并且最终 `writes` 正常。任何异常都应立即使用物理急停；程序自身也会进入阻尼。

本轮现场结果（2026-09-08）：用户完成约 5 秒承重原地 action 短测，机器人无明显抖动或摔倒。
`logs/real/go2wwmp_action_15s.jsonl` 有 250 条 step，全部标记 `wmp_action_sent=true`；深度
session/frame 连续，`depth_valid_ratio` 最低约 `0.8643`，没有因有效率下降进入阻尼；dq 静态
检查全部通过。文件名中的 `15s` 只是日志命名，本次实际参数是 `--duration 5`。

## 6. 手柄入口

Xbox 和宇树原装遥控器现在都可以作为 Go2WWMP 的 `cmd_vel` 来源。验收顺序和宇树手柄的
无电机只读、接管、退出流程见 [guide/22_go2wwmp_unitree_remote.md](22_go2wwmp_unitree_remote.md)；
Xbox 的既有流程仍见 [guide/21_go2wwmp_xbox_input.md](21_go2wwmp_xbox_input.md)。

`scripts/real/test_policy_real.py` 和 `scripts/real/test_policy_unitree_remote.py` 是旧的
Go2W/Go2WCR 入口，不能拿来代替 Go2WWMP 的 WMP/depth pipeline。Unitree 手柄模式使用
`test_policy_go2wwmp_real.py --control unitree`，L2+R2 只作为 LowCmd 接管触发，Select 请求退出。

## 7. 暂不做的事情

- 不把无效深度填成近障碍，不把 valid mask 私自加入网络输入；
- 不把 5 秒 action 短测等同于 WMP 行走或跨越障碍通过；
- 不在没有保护架、急停和第二人观察时运行 action 短测。

旧命令中的 `--hold-stand` 仍作为隐藏兼容别名；新流程统一使用 `--ground-stand`。
下一阶段需先分析 action 短测日志，再决定是否进入更长时间或低速移动测试。
