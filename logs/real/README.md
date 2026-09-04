# Go2W 实机消融日志清单

本目录保存笔记本与 Orin NX 的原始实机日志，用于复现模型精度、观测一致性、控制时序和
闭环振荡分析。CSV 保持原样，不在分析过程中重写。新增日志时应同时记录宿主机、入口、
模型、控制命令、是否记录/打印、机器人是否受外力以及可用于比较的时间区间。

## 当前文件

| 文件 | 数据帧 | 大小 | SHA-256 | 含义 |
|---|---:|---:|---|---|
| `policy_fixed_2.csv` | 2024 | 2.7 MB | `d33c9d2757a35a6eaef1b95ffc233e7110687a314a1f1c3b6b9d8346024cde3b` | Orin NX 双进程运行的状态、时序、action 与 MotorCommand |
| `policy_fixed_2_observation.csv` | 2024 | 6.2 MB | `1ad971d77eb4d80729bc330e8c7e0ed994effb8fe02ecc201b082cc985d28244` | 同一次 Orin 运行的 265 维 observation 与 action |
| `policy_laptop_single.csv` | 936 | 1.3 MB | `6eafd18b50cf7dc34f3c2714b762643955e559e707a3f62faa78eba4d8040d96` | 笔记本单进程稳定运行的状态、时序、action 与 MotorCommand |
| `policy_laptop_single_observation.csv` | 936 | 3.0 MB | `ad1d12e5bf7823f9ba9313c4244f3043e10cd906c8f4cf60f01854e5296744b5` | 同一次笔记本运行的 265 维 observation 与 action |

行数包含数据帧，不包含一行表头。四个 CSV 合计约 14 MB。

## 工况和使用限制

- Orin 主日志前 150 帧是 warmup，之后 1874 帧为 active；笔记本日志 936 帧全部为
  active。两次记录的速度命令均为零。
- 用户明确标注两份日志中的坏状态包含人工外推；Orin 后半段长周期尾部还可能包含暴走
  后的通信、电池或其他次生效应。不得用这些尾部数据反推最初抖动的原因。
- 当前跨宿主机比较只使用前半段候选区间内 gyro RMS 最低的连续 5 秒：笔记本
  `1.9–6.9 s`、Orin `4.7–9.7 s`。窗口选择规则及统计见
  `guide/14_laptop_orin_ablation.md`。
- 用户另行确认：当前双进程入口在笔记本实机上同样稳定。该次没有配套 CSV，因此作为
  现场消融事实记录，不伪造定量指标。
- 4.8 阶段在 Orin 上曾短暂表现较好，但用户判断可能是假象；不得把该次观察写成已经
  验证 Orin 双进程链路稳定。

## 可复现结论

- 笔记本与 Orin 的 `model_700.pt` SHA-256 相同：
  `5105a856191fd19f7ee0755b8839f3f5a245b4b6040778351c604b037dba0ebf`。
- 笔记本复放 Orin 的 1874 个 active observation，action 最大绝对误差为
  `1.6689e-06`；模型文件和跨架构推理精度不是剧烈抖动主因。
- 从 Orin 主日志重建 observation，与 observation CSV 逐元素完全一致；Pipe 没有改变
  字段、关节顺序或历史拼接。
- 前半段最佳 5 秒中，两端 policy 周期都约为 20 ms，Orin LowState 更新并不更旧；但
  Orin 的 IMU、腿速、action 和腿目标波动仍为笔记本约 28–42 倍，并存在约 8.5 Hz
  闭环振荡。
- 当前日志没有记录 500 Hz LowCmd 的逐次间隔、CRC/Write 耗时、漏周期和首次采用新
  policy action 的延迟，因此不能据此判断实际下发是否稳定。
