# Step 5: 实物行走测试

⚠ **在 Step 4 通过后执行。逐级增加速度。**

## 前置条件

- Step 4 通过（零速站立 60s 无异常）
- 已记录 Step 4 中的关节运动范围

## 步骤

### 1. 复核逐关节限位

`config/go2w_config.py` 的 `DDS.JOINT_LIMITS` 已按 DDS 0–11
显式列出每个关节，但限制值保留为 `None`，需要根据你的实机验证结果填写：

例：
```python
JOINT_LIMITS = [
    {"q_min": None, "q_max": None, "dq_max": None},  # DDS 0
    {"q_min": None, "q_max": None, "dq_max": None},  # DDS 1
    # ...一直到 DDS 11
]
```

`None` 表示跳过对应检查。在吊架低速测试中记录真实工作范围后，再逐项填写
`q_min/q_max/dq_max`；不要改回统一推导式。

### 2. 渐进增加前进速度

```bash
# Level 1: 微速 (支架上)
python scripts/test_policy_real.py --vx 0.05

# Level 2: 慢速 (支架上)
python scripts/test_policy_real.py --vx 0.1

# Level 3: 慢速 (地面，需有人扶)
python scripts/test_policy_real.py --vx 0.1

# Level 4: 中速 (地面)
python scripts/test_policy_real.py --vx 0.2

# Level 5: 快速 (地面)
python scripts/test_policy_real.py --vx 0.3
```

每次运行 30 秒，观察：
- 腿关节运动范围是否合理
- 轮子旋转是否平稳
- 机器人是否稳定不倒下

### 3. 测试转向

```bash
python scripts/test_policy_real.py --vx 0.1 --vyaw 0.2
```

### 4. 测试侧向

```bash
python scripts/test_policy_real.py --vy 0.1
```

## 通过标准

- 0.3 m/s 稳定行走
- 腿关节 + 轮子协调运动
- 无安全限位违规
- 转向和侧向正常

## 故障处理

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 机器人倒下 | 策略未泛化到实物 | 减小速度，检查 IMU |
| 关节振荡 | kp/kd 不匹配 | 调整 LEG_KD |
| 轮子打滑 | kd 太小 | 增大 WHEEL_KD |
| 姿态漂移 | IMU 数据异常 | 检查 DDS 四元数格式 |
