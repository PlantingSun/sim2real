# Go2W Sim-to-Real 总览

## 项目目标

将 go2w RL 策略部署到实物机器人，分 5 步完成。

## 分层架构

```
┌─ test_policy_real.py (50Hz 主循环) ────────┐
│                                               │
│  state = driver.get_state()   ← RobotState    │
│  obs = controller.build_obs()                  │
│  action = controller.compute_action()          │
│  driver.send_command(cmd)     → MotorCommand  │
│                                               │
│  ┌─ 500Hz 线程（driver 内部）──────────┐    │
│  │  安全检查 → 指令平滑 → 发布 LowCmd    │    │
│  └──────────────────────────────────────┘    │
└───────────────────────────────────────────────┘
```

## 关节映射

| 模块 | 顺序 | 说明 |
|------|------|------|
| DDS | FR→FL→RR→RL→wheels | 机器人原生顺序 |
| Ctrl | FL→FR→RL→RR | 策略网络训练顺序 |
| MuJoCo | FL→FR→RL→RR | 与 Ctrl 一致 |

两张映射表保留为 `go2w_config.py` 的顶层列表；Controller 在策略边界映射，
MuJoCo driver 在仿真边界映射。映射表数值保持为当前已验证版本。

## 步骤

| 步骤 | 内容 | 验证方式 |
|------|------|----------|
| 1 | 驱动层验证 | 与 monitor_lowstate.py 对比 |
| 2 | 策略离线测试 | 与原始 net_test() 对比 |
| 3 | 仿真全流程 | MuJoCo viewer 观察 |
| 4 | 实物站立 | 60s 零速无振荡 |
| 5 | 实物行走 | 0.3m/s 稳定行走 |
