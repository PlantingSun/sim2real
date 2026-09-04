# Step 2：Orin policy 正确性与延时

## 目标和边界

本步骤离线验证 go2w、go2wcr 和 go2wwmp，并测量 Orin CPU 的完整 policy 单帧延时。
基准不导入 Unitree SDK、不初始化 DDS，也不发送 LowCmd。

计时范围如下：

```text
RobotState/深度输入 → 观测构建 → PyTorch 网络 → DDS 顺序 MotorCommand
```

WMP 包含每五帧一次的 world-model 更新，但不包含相机采集、MuJoCo 渲染或 OpenCV 显示。
checkpoint 加载发生在控制循环之前，单独记录而不计入 20 ms 帧预算。

## 测试条件

- Orin NX，aarch64，8 核；NVIDIA power mode 3（25W）。
- CPU governor 为 `schedutil`，两个 CPU policy 的最大频率均为 `1,497,600 kHz`。
- Python 3.8.10 `.venv`，CPU-only PyTorch 2.0.0。
- 50 Hz 对应单帧预算 `20.0 ms`。
- 未修改系统功耗模式或 CPU 频率。

通过标准为 mean 和 P99 均不超过 20 ms，同时报告最大值和超时帧数。平均频率只表示串行
计算吞吐，不能代替逐帧 deadline 检查。

## 正确性检查

```bash
cd /home/unitree/sim2real
source setup.sh policy
python scripts/policy/test_policy_offline.py
python scripts/policy/test_policy_go2wcr_offline.py
python scripts/simulation/test_mujoco_pipeline_go2wwmp.py --check-only --no-depth-display
```

三个模型均通过 checkpoint、观测维度、16 维有限动作和 MotorCommand 检查。

## 可重复延时命令

```bash
source setup.sh policy
python scripts/policy/benchmark_policy_latency.py \
  --policy go2w --threads 1 --warmup 100 --iterations 2000
python scripts/policy/benchmark_policy_latency.py \
  --policy go2wcr --threads 1 --warmup 100 --iterations 2000
python scripts/policy/benchmark_policy_latency.py \
  --policy go2wwmp --threads 4 --warmup 50 --iterations 500
```

程序固定 NumPy/PyTorch 随机种子，先预热，再用 `perf_counter_ns()` 逐帧计时。不要同时运行
其他 CPU 密集任务；温度、后台进程和 `schedutil` 调频仍可能让不同批次略有差异。

## 2026-09-03 结果

| Policy | CPU 线程 | 计时帧 | mean | P99 | max | 超过 20 ms | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|
| go2w 完整帧 | 1 | 2000 | 1.791 ms | 1.911 ms | 2.295 ms | 0 | PASS |
| go2wcr 完整帧 | 1 | 2000 | 3.683 ms | 3.967 ms | 4.246 ms | 0 | PASS |
| go2wwmp 全部帧 | 4 | 500 | 8.175 ms | 32.109 ms | 32.491 ms | 100 | FAIL |
| └ actor-only | 4 | 400 | 2.466 ms | 2.832 ms | 2.928 ms | 0 | PASS |
| └ world-model | 4 | 100 | 31.009 ms | 32.109 ms | 32.491 ms | 100 | FAIL |

模型加载约为 go2w `25.8 ms`、go2wcr `26.0 ms`、go2wwmp `1110.2 ms`。加载发生在开始
50 Hz 循环之前，不构成运行期 deadline miss。

1/2/4/8 线程短测表明：go2w/go2wcr 增加线程的收益很小，8 线程抖动反而更大；单线程
仍有充足余量，并可减少与 500 Hz DDS 线程竞争。因此 `setup.sh` 默认使用
`OMP_NUM_THREADS=1`。WMP 的四线程结果最好，但同步 world-model 帧仍然超时。

## 阶段结论

- go2w 和 go2wcr 已满足 Orin 上的 50 Hz policy 门槛，可以进入 simulation pipeline。
- WMP 只通过功能检查，未通过逐帧 50 Hz 门槛，不进入 WMP 实机测试。
- 不通过降低 world-model 更新频率来绕过超时，因为这会改变模型部署语义。若后续优化
  ONNX/TorchScript/量化或异步执行，必须重新验证输出误差、状态更新顺序和延时分布。
