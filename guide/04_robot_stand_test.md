# Step 4: 固定站姿接管 + Policy 实机输出

⚠ **关键安全步骤，请逐条执行。**

## 前置条件

- 网线连接机器人，主机 IP `192.168.123.99/24`
- 机器人开机，初始放在地面，周围无障碍
- 架子或吊绳已经准备好，但在 StandUp 完成前不要妨碍机器人站立
- Step 1 通过（DdsDriver 读写正常）
- Step 2 通过（策略推理正常）

## 步骤

### 1. 激活环境

```bash
cd /home/robot/sim2real_ws
source setup.sh robot
```

### 2. 验证 DDS 通信

```bash
python scripts/test_dds_driver.py
```
确认关节/IMU 数据正常后 Ctrl+C 退出。当前 `initialize()` 不启动 LowCmd 线程，
因此这个测试只读取状态，不发送 LowCmd。

### 3. 启动分阶段接管

```bash
python scripts/test_policy_real.py --vx 0 --vy 0 --vyaw 0
```

脚本使用单键控制，不需要按 Enter：

1. 按 `1`：只调用 Sport Mode 的 `StandUp()`，此时没有 LowCmd 发布。
2. 等机器人完全站稳后，将机器人固定到架子/吊绳上。
3. 脚本会提前构造固定 `INITIAL_JOINTS_POS` 指令，但此时仍不发布。
4. 按 `2`：调用一次 `ReleaseMode()`；RPC 返回成功后不等待 `CheckMode` 轮询，
   立即写入并同步发送固定位置环，然后启动 500 Hz 线程继续发送同一条指令。
   终端会打印从 ReleaseMode 返回到首条 LowCmd Write 完成的软件调用耗时。
5. 随后加载 policy。policy 以 50 Hz 推理，每一帧都将预测的
   `position/velocity/kp/kd` 写入 DdsDriver，由 500 Hz 线程持续发送；
   每 0.5 秒打印一次当前正在发送的预测指令。

任一阶段按 `q` 可退出。按 `2` 之前退出时，脚本不会发送 LowCmd。

### 4. 观察

- `[LOWCMD ACTIVE]` 后显示的固定指令应是 `INITIAL_JOINTS_POS` 的 DDS 顺序。
- 模型加载完成前，实际发送指令保持为固定 `INITIAL_JOINTS_POS`。
- 后续 `[POLICY ACTIVE]` 明确标记为“正在发送”。
- 机器人由吊绳保护，观察从固定位置环切换到 policy 后是否稳定。

### 5. 退出

按 Ctrl+C：若 500 Hz 线程已经启动，则进入紧急阻尼并退出；若尚未按 `2`，
则直接退出且不发送 LowCmd。

## 通过标准

- `StandUp` 期间没有 LowCmd 干扰
- 按 `2` 后，`ReleaseMode` 返回时能立即用固定位置环接管
- policy 加载完成后，预测指令持续更新到 DDS LowCmd
- 无明显蹦跳或持续抖动
- Ctrl+C 后正常进入阻尼并退出

## 异常处理

| 现象 | 处理 |
|------|------|
| 关节剧烈抖动 | 立即 Ctrl+C，检查关节映射 |
| 按 `2` 后机器人不动作 | 检查 ReleaseMode 返回值和 DDS 通信 |
| 某个关节角度异常 | 记录角度值，检查限位设置 |
