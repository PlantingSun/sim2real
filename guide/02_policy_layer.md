# Step 2: 策略层离线测试

## 目标

验证去 ROS 化的 `ControllerGo2w` 推理输出与原始代码一致。

## 步骤

### 1. 确认 PyTorch 已安装

```bash
source setup.sh policy
python -c "import torch; print(torch.__version__)"
```

依赖只按 `12_orin_environment.md` 安装到项目 `.venv`，不要向系统 Python 执行
`pip install`。

### 2. 运行离线测试

```bash
cd /home/unitree/sim2real
source setup.sh policy
python scripts/policy/test_policy_offline.py
```

### 3. 检查输出

- 16 维动作值无 NaN/Inf
- MotorCommand 腿关节 kp=50, kd=1.0
- MotorCommand 轮子 kp=0, kd=0.5
- build_obs 正确输出 265 维
- `reset()` 会用初始站立零运动状态填满 5 帧历史：重力为 `(0, 0, -1)`，其余运动量和关节位置偏差为 0

## 通过标准

- 网络加载成功（打印 Actor/Critic 结构）
- 零状态推理无异常
- 所有断言通过
- Orin 上完整单帧推理 P99 不超过 20 ms（50 Hz）

## Orin 延时验证

统一基准入口会测量 `build_obs → compute_action → MotorCommand`，不初始化 DDS：

```bash
source setup.sh policy
python scripts/policy/benchmark_policy_latency.py \
  --policy go2w --threads 1 --warmup 100 --iterations 2000
```

2026-09-03 在 25W mode 3 下实测：mean `1.791 ms`，P99 `1.911 ms`，max
`2.295 ms`，2000 帧没有超过 20 ms。详细方法和三种 policy 的结果见
`13_orin_policy_benchmark.md`。

## 文件清单

| 文件 | 来源 | 说明 |
|------|------|------|
| `policy/actor_critic.py` | 复制 | 改动 import 路径 |
| `policy/normalizer.py` | 复制 | 无改动 |
| `policy/utils.py` | 复制 | 无改动 |
| `policy/controller_go2w.py` | 改写 | 去 ROS, 新增 build_obs/compute_action |
| `models/go2w/model_700.pt` | 复制 | 策略权重 |
| `scripts/policy/test_policy_offline.py` | 新建 | 离线验证 |
| `scripts/policy/benchmark_policy_latency.py` | 新建 | Orin CPU 完整单帧延时基准 |
