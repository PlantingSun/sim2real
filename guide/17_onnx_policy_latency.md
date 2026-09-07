# Go2W ONNX policy 延时测试

本阶段只替换 Go2W 的 `obs_normalizer + actor` 推理后端。观测历史、关节映射、动作缩放、
50 Hz policy 和 500 Hz LowCmd 语义保持不变。默认实机后端仍是 PyTorch。

## 一、离线导出和验证

下面的命令不会初始化 DDS：

```bash
source setup.sh policy
python scripts/policy/benchmark_go2w_onnx.py \
  --observation-log logs/real/policy_cpp_observation.csv \
  --cpus 2 --threads 1 --warmup 100 --iterations 500
```

脚本生成本地文件 `models/go2w/model_700.onnx`。该文件由 `.gitignore` 忽略，换设备后
必须在目标设备重新导出或单独复制。

2026-09-04 在当前 Orin NX、CPU2、单线程上的结果：

| 路径 | mean | P99 |
|---|---:|---:|
| PyTorch actor | 0.667 ms | 0.732 ms |
| ONNX actor | 0.106 ms | 0.128 ms |
| PyTorch 完整帧 | 1.809 ms | 1.976 ms |
| ONNX 完整帧 | 1.204 ms | 1.295 ms |
| PyTorch policy Pipe 往返 | 2.507 ms | 2.714 ms |
| ONNX policy Pipe 往返 | 1.878 ms | 2.071 ms |

真实日志的 500 帧比较中，action 最大绝对误差为 `4.7683716e-07`。生成文件大小
`1214032 bytes`，SHA-256 为
`79f2b7f5ace507307b45bc120d3a0d67f941130e3c4ddca45649902ea52a05b8`。

## 二、只测实机链路延时

ONNX 离线验证通过后，先运行 `print-only`。该模式仍会释放 Sport Mode 并发送固定站姿
LowCmd，因此机器人必须吊起；policy action 只记录、不发送：

```bash
source setup.sh robot
python scripts/real/test_policy_real.py \
  --dds-backend cpp --policy-backend onnx \
  --main-cpus 3 --lowcmd-cpu 1 --policy-cpus 2 --torch-threads 1 \
  --control fixed --vx 0 --vy 0 --vyaw 0 --print-only \
  --log logs/real/policy_onnx_print_only.csv
```

CPU 分配为：现有 `eth0` IRQ 保持 CPU0；C++ LowCmd 线程使用 CPU1；policy 子进程使用
CPU2；主 Python、日志和 C++ DDS 普通线程继承 CPU3。这样不会再让未绑定的主进程抢占
policy CPU2，也不让主进程与网卡 IRQ 共用 CPU0。

先只分析日志，不去掉 `--print-only`。通过标准为 active 阶段：

- `action_state_age_ms` 平均值不超过 `3.0 ms`；
- P99 不超过 `4.5 ms`；
- policy 保持约 50 Hz，LowState tick 没有异常跳变；
- C++ 退出摘要仍无 Write 失败、状态丢包或其他 LowCmd 发布者。

如果达不到该门槛，ONNX 加双进程仍不足以复现笔记本延时，不进入真实动作测试。下一步才
考虑让 C++ DDS 后端下的 ONNX policy 直接运行在主进程，删除 policy Pipe 和一次进程调度。

## 三、当前边界

`--policy-backend onnx` 是显式实验开关；不填写时仍运行原 PyTorch。当前仅完成离线数值和
延时验证，尚未用 ONNX 向机器人发送 policy action。
