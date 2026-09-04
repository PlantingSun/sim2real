# Go2W 笔记本 / Orin NX 抖动消融

## 目标与边界

本轮先回答两个互相独立的问题：

1. Orin 与笔记本是否加载了同一份 `model_700.pt`，相同的 265 维 observation 是否产生
   相同 action。
2. 保持模型、控制器、关节映射、增益和 DDS driver 不变，只把双进程 `Pipe` 恢复为
   已验证过的单进程控制循环后，机器人是否仍然剧烈抖动。

离线检查不会初始化 DDS。实机检查必须由操作者连接机器人后手动执行，且同一时刻只能有
一个 LowCmd 发布者。

## 截至 2026-09-04 的统一结论

用户已在笔记本上运行当前双进程入口，实机仍然稳定、无明显抖动。因此“双进程 + 同步
Pipe 架构本身”不是抖动的充分原因；Pipe 内容一致性也已由逐元素复放验证。这个结果不
等于 Orin 上的跨进程调度开销完全无影响，只说明问题必须包含 Orin 特有条件。

4.8 阶段在 Orin 上曾短暂表现较好，但用户认为可能只是假象。本报告不再用这一现象证明
Orin 能稳定运行，也不依赖 Orin 后半段的短暂恢复或暴走尾部推导根因。

当前证据强度如下：

1. 已排除为主因：模型文件差异、跨架构推理数值误差、Pipe 字段/历史损坏、MotorCommand
   映射错误、前半段 50 Hz policy 失速、LowState 过旧。
2. 最高优先级未验证项：Orin 上实际 500 Hz LowCmd 的逐次发布节拍。现有 timerfd 循环
   忽略漏周期计数；若 CRC 或 DDS Write 超过 2 ms，可能形成长空档和补跑突发。
3. 与上一项耦合的高优先级因素：LowCmd Python 线程与主进程日志/终端输出争用 GIL，
   CPU1 与网卡 IRQ/DDS 线程竞争，以及 `schedutil` 动态调频造成的短时延迟。
4. 可能的放大因素：Orin state→action 平均年龄比笔记本多约 2.23 ms，可能降低闭环
   相位裕度；但现有数据不足以把 28–42 倍振幅单独归因于它。
5. 次级待查项：CycloneDDS 实际加载库/配置差异、其他 `rt/lowcmd` 发布者、Sport Mode
   释放与低层接管状态差异。

## 已完成的离线结论

坏运行日志为：

- `logs/real/policy_fixed_2.csv`：2024 帧完整状态、时序、action 和 MotorCommand。
- `logs/real/policy_fixed_2_observation.csv`：2024 帧、每帧 265 维网络输入和 16 维 Orin action。

两端模型 SHA-256 均为：

```text
5105a856191fd19f7ee0755b8839f3f5a245b4b6040778351c604b037dba0ebf
```

笔记本使用 x86_64、Python 3.8.20、PyTorch 2.3.1、NumPy 1.19.5、单线程重放；Orin
记录环境为 aarch64、PyTorch 2.0.0、NumPy 1.24.4。1874 个实际控制帧的比较结果：

| 指标 | 结果 |
|---|---:|
| 平均绝对 action 误差 | `9.3988e-08` |
| action RMSE | `1.4081e-07` |
| 最大绝对 action 误差 | `1.6689e-06` |
| 最大误差所在循环 | `1920` |

该最大误差换算到控制量，腿关节位置不超过约 `4.18e-07 rad`，轮速不超过约
`1.67e-05 rad/s`，远小于可引起肉眼可见抖动的量级。因此可排除模型文件错误以及
x86/aarch64、PyTorch 2.3.1/2.0.0 的推理精度差异是本次剧烈抖动的主因。
笔记本改用历史默认的 16 个 PyTorch 线程复放，统计结果也逐项相同。

另外使用主进程日志里的关节位置、关节速度、IMU 和速度命令，按同一 `last_action` 与
五帧历史规则重建全部 2024 帧 observation，再与 policy 子进程保存的 265 维输入比较：
所有元素误差均为 `0`。这排除了 Pipe 序列化造成字段损坏、关节顺序改变或历史拼接错误；
但它不排除跨进程往返的尾延时和 action 提交时刻对闭环的影响。

前 150 帧是预热帧。该次旧日志中的 action 因 NumPy/Torch 共享内存被历史清零操作一并
清成零，离线重放得到的则是网络原始输出，两者不能直接做精度比较。控制器现已返回独立
action 副本，后续日志不会再有该问题；复放脚本也把 `active` 和 `warmup` 分开，默认
只用 active 帧决定 PASS/FAIL。

坏运行 active 段的时序证据：

| 指标 | P50 | P95 | P99 | 最大值 |
|---|---:|---:|---:|---:|
| 推理耗时 | 2.437 ms | 2.833 ms | 3.253 ms | 3.716 ms |
| IPC 往返 | 3.740 ms | 7.385 ms | 12.515 ms | 34.720 ms |
| 取状态时状态年龄 | 0.572 ms | 1.982 ms | 2.742 ms | 10.501 ms |
| action 生成时状态年龄 | 4.268 ms | 8.916 ms | 14.137 ms | 36.582 ms |

实际平均频率为 `49.27 Hz`，没有重复或倒退的 LowState tick。action 到 MotorCommand 的
重新映射最大误差仅约 `2e-06`。因此现有日志也不支持“模型算不动”“DDS 状态断流”或
“action 转电机命令写错”作为主要原因。

但日志确实记录到了闭环振荡：相邻 action 单元素最大变化 `2.007`，对应相邻腿关节目标
最大变化约 `0.502 rad`。这是抖动的表现，不足以单独判断是双进程时序、机载 DDS 调度、
其他 LowCmd 发布者，还是接管状态差异触发了振荡。

## 前半段最佳稳态对比（现场标注后修正）

用户确认两份日志后部的坏状态包含人工外推，并要求忽略 Orin 暴走后的长周期尾部。因此
整段 P99、最大电流和后半段恢复/再振荡不再作为根因证据。比较范围改为外推前的前半段，
并在各自候选区间内选择 gyro RMS 最低的连续 5 秒：

- 笔记本单进程：active `1.9–6.9 s`。
- Orin 双进程：active `4.7–9.7 s`。

| 指标 | 笔记本最佳 5 s | Orin 最佳 5 s | Orin / 笔记本 |
|---|---:|---:|---:|
| policy 平均周期 | 20.095 ms | 20.001 ms | 1.00× |
| policy 最大周期 | 21.708 ms | 22.932 ms | 1.06× |
| 取状态平均年龄 | 0.927 ms | 0.297 ms | 0.32× |
| action 就绪平均年龄 | 2.050 ms | 4.279 ms | 2.09× |
| IMU gyro RMS | 0.0104 rad/s | 0.4368 rad/s | 41.9× |
| 腿关节速度 RMS | 0.0374 rad/s | 1.0937 rad/s | 29.2× |
| action 元素帧差均值 | 0.00946 | 0.26481 | 28.0× |
| 腿目标帧差均值 | 0.00275 rad | 0.07785 rad | 28.3× |

Orin 在该窗口没有长周期尾部，50 Hz 节拍甚至比笔记本略整齐，LowState 也更新得更鲜；
但状态和 policy 输出仍以约 `8.5 Hz` 同步振荡。因此前半段巨幅抖动不能用“平均帧率不足”
或“LowState 太旧”解释。

双进程仍增加了约 `2.23 ms` 的固定 state→action 延迟，但这主要来自 Orin 较慢推理和
一次进程调度/序列化。它可能减少闭环相位裕度，却不能凭当前数据单独解释 28–42 倍振幅。
尤其是 Pipe 内容已逐元素验证无误，而且当前双进程入口已由用户在笔记本实机上验证稳定。
因此 Pipe 架构本身可排除；Orin 上多出的固定调度开销仍作为闭环裕度因素保留。

当前仍需重点验证的是日志没有覆盖的 500 Hz LowCmd 发送侧：

1. `_pub.Write()` 的真实周期、最大间隔和调用耗时。
2. LowCmd 线程固定到 CPU1 后，是否与 `eth0` IRQ、CycloneDDS 或其他系统线程竞争。
3. DDS/主进程线程没有从 policy CPU2 排除，现有“CPU 隔离”并不完整。
4. 是否存在第二个 `rt/lowcmd` 发布者与当前进程交替下发命令。

因此当前判断不是“DDS 与 policy 完全无干涉”，而是：**已记录的 50 Hz policy 路径没有
足以解释抖动的周期异常；如果干涉成立，更可能发生在未记录的 500 Hz LowCmd/CPU 调度
一侧。** 下一轮应先给 LowCmd 线程增加内存内统计，关闭高频数组打印和逐帧 flush，再在
相同支撑条件下做最短零速测试。电量只作为实验条件记录，不用暴走后的压降解释前半段根因。

## 后续调试顺序

每一步只改变一个变量，前一步没有得到可解释数据时不进入后一步：

1. **加入无扰动诊断。** 在内存中统计 500 Hz start-to-start 间隔、CRC 耗时、`Write()`
   耗时/失败数、超过 2/3/5/10 ms 的次数、短于 1 ms 的补跑次数，以及新 policy action
   从提交到第一次 LowCmd Write 的延迟。运行期间不逐帧打印、不逐帧写盘，退出后一次输出。
2. **建立稳定参考分布。** 在笔记本双进程稳定运行中采集同一组 LowCmd 指标；接受标准
   以这份实测分布为基线，不凭空指定绝对 P99。
3. **Orin 固定站姿隔离。** 先只运行固定 LowCmd、不加载 policy，比较 Orin 与笔记本的
   500 Hz 分布。若此时已有长空档/补跑，问题在 policy 之前，应先查 CPU、IRQ、DDS Write。
4. **Orin policy 最小路径。** 使用零速度、关闭 CSV 和大数组打印运行最短测试。如果固定
   LowCmd 正常而加入 policy 后异常，重点检查 GIL、主进程/DDS 线程布局和 action 应用延迟。
5. **单独恢复观测项。** 依次只开启内存时序统计、缓冲日志、终端摘要；哪一步使 LowCmd
   分布或机器人行为劣化，就锁定对应干扰源。原先每帧两个 CSV `flush()` 不应与基线同时开启。
6. **按测量结果重新放置 CPU。** 先读取 `eth0` IRQ 和各线程实际 CPU，再选择不承载 IRQ
   的核心给 LowCmd；同时限制主进程/DDS 内部线程不要进入 policy 核。不要未经测量直接
   上实时优先级，以免反过来饿死 DDS 接收或系统线程。
7. **验证性能状态。** 记录 nvpmodel、CPU governor、实时频率、温度和降频标志；只在发现
   DVFS/热降频与长空档同步后，才做固定性能模式 A/B。
8. **最后检查 DDS/接管。** 核对 Orin 实际加载的 CycloneDDS 动态库和配置，确认只有一个
   `rt/lowcmd` 发布者，并记录 ReleaseMode 前后模式及首条 LowCmd 的真实时间。

若机器人开始形成明显 8.5 Hz 振荡，应立即停止该次测试；长时间暴走数据不用于判断触发源。

## 本轮代码改动

### 双宿主机环境

`setup.sh` 现在按架构自动选择：

- x86_64：`laptop`，恢复 Conda `unitree_py38`、`enp0s31f6` 和笔记本原来的 PyTorch
  默认线程行为。
- aarch64/arm64：`orin`，继续使用项目 `.venv`、`eth0` 和单线程 OpenMP 设置。

可用 `SIM2REAL_HOST=laptop` 或 `SIM2REAL_HOST=orin` 强制覆盖。`DDS.DEFAULT_NET_IF`
和默认手柄路径也随宿主机选择，命令行 `--interface` 仍有最高优先级。

### 单进程实机基线

新增 `scripts/real/test_policy_real_single_process.py`。控制循环恢复自 Git 提交
`64c32a0` 的已验证版本：DDS 和 policy 在同一 Python 进程，不使用
`multiprocessing`/`Pipe`，并保留当前安全检查和两阶段接管。默认不指定
`--torch-threads`，以复现原笔记本环境；可选 `--log` 记录与 Orin 相同格式的数据。

### 精度复放

`ControllerGo2w.compute_action()` 现在返回独立 NumPy 副本，避免预热阶段清零
`last_action` 时连带修改已生成的 action 日志。

`scripts/policy/replay_observation_csv.py` 现在会检查 CSV 列数，打印宿主机、PyTorch、
NumPy、模型 SHA-256、active/warmup 分组统计和每个 action 通道的最大误差。active
最大绝对误差默认需不超过 `1e-5`。

## 笔记本下一次实机测试顺序

先进入项目并确认环境输出中显示 `host: laptop`、`DDS IF: enp0s31f6`：

```bash
cd /home/robot/sim2real_ws
source setup.sh robot
```

如果笔记本网卡名发生变化，不修改代码，显式覆盖：

```bash
UNITREE_NET_IF=<实际网卡名> source setup.sh robot
```

连接 RJ45 后先做只读状态检查：

```bash
python scripts/real/test_dds_driver.py
```

确认 tick、关节和 IMU 持续正常更新后按 Ctrl+C。然后确保没有 Orin 程序、SDK 示例或
其他终端仍在发布 `rt/lowcmd`，吊绳保护就绪，再运行第一组单进程消融：

```bash
python scripts/real/test_policy_real_single_process.py \
  --control fixed --vx 0 --vy 0 --vyaw 0
```

按原流程操作：机器人在地面按 `1` 执行 StandUp，完全站稳后吊起，再按 `2` 释放并
接管。发生剧烈抖动时立即 Ctrl+C，不等待日志积累。

第一组既不要指定 `--torch-threads`，也不要打开日志；这样最接近历史上成功的笔记本
运行，并避免逐帧 flush 混入额外时延。若它稳定，再用下列命令只消融线程数：

```bash
python scripts/real/test_policy_real_single_process.py \
  --control fixed --vx 0 --vy 0 --vyaw 0 --torch-threads 1
```

需要定量分析时再单独运行日志组：

```bash
python scripts/real/test_policy_real_single_process.py \
  --control fixed --vx 0 --vy 0 --vyaw 0 \
  --log logs/real/policy_laptop_single.csv
```

## 结果如何解释

- 笔记本单进程恢复平稳：模型与控制参数无误，优先排查 Orin 双进程/调度/接管链路。
- 笔记本单进程也抖：进程拆分不是必要条件，应继续对比当前 DDS driver、机器人模式、
  接管初态及是否存在第二个 LowCmd 发布者。
- 默认线程稳定、单线程抖：PyTorch 线程配置影响闭环；再用离线时序和实机日志确认。
- 笔记本单进程和当前双进程入口均已由用户确认稳定：进程架构本身不是充分原因，后续只
  排查 Orin 特有的运行时和下发链路；不要与其他 LowCmd 入口同时运行。

每次测试后保留主 CSV 和自动生成的 `_observation.csv`，并记录是否抖、开始抖动的循环
附近时间、机器人是否吊起、按 `2` 前的姿态以及当时运行中的 LowCmd 程序。
