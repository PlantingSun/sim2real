# Step 2: 策略层离线测试

## 目标

验证去 ROS 化的 `ControllerGo2w` 推理输出与原始代码一致。

## 步骤

### 1. 确认 PyTorch 已安装

```bash
source setup.sh policy
python -c "import torch; print(torch.__version__)"
```

如未安装:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### 2. 运行离线测试

```bash
cd /home/robot/sim2real_ws
source setup.sh policy
python scripts/test_policy_offline.py
```

### 3. 检查输出

- 16 维动作值无 NaN/Inf
- MotorCommand 腿关节 kp=50, kd=1.0
- MotorCommand 轮子 kp=0, kd=0.5
- build_obs 正确输出 265 维

## 通过标准

- 网络加载成功（打印 Actor/Critic 结构）
- 零状态推理无异常
- 所有断言通过

## 文件清单

| 文件 | 来源 | 说明 |
|------|------|------|
| `policy/actor_critic.py` | 复制 | 改动 import 路径 |
| `policy/normalizer.py` | 复制 | 无改动 |
| `policy/utils.py` | 复制 | 无改动 |
| `policy/controller_go2w.py` | 改写 | 去 ROS, 新增 build_obs/compute_action |
| `models/go2w/model_700.pt` | 复制 | 策略权重 |
| `scripts/test_policy_offline.py` | 新建 | 离线验证 |
