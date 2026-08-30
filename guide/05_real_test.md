# Step 5: 实机测试

固定位置环和零速 policy 已由 `scripts/real/test_policy_real.py` 验证。宇树原装
遥控器入口为 `scripts/real/test_policy_unitree_remote.py`。

## 前置条件

- Step 1–4 全部通过。
- 网线连接机器人，主机 IP 为 `192.168.123.99/24`。
- 机器人周围无障碍，架子或吊绳已经准备好。
- StandUp 完成前，吊具不能妨碍机器人正常站立。
- `DDS.JOINT_LIMITS` 中的 `None` 表示对应限位尚未启用，必须清楚当前保护边界。

## 每次启动的接管顺序

```bash
cd /home/robot/sim2real_ws
source setup.sh robot
```

先确认状态接收正常：

```bash
python scripts/real/test_dds_driver.py
```

Ctrl+C 退出状态检查后再启动实机策略。脚本使用单键确认，不需要按 Enter：

1. 按 `1`：只调用 Sport Mode 的 `StandUp()`，不发送 LowCmd。
2. 机器人完全站稳后，将机器人固定到架子或吊绳上。
3. 按 `2`：调用一次 `ReleaseMode()`；返回成功后立即同步发送固定
   `INITIAL_JOINTS_POS`，随后启动 500 Hz LowCmd 线程。
4. 模型加载完成后，50 Hz policy 开始更新实际发送的 MotorCommand。

按 `2` 前按 `q` 可以退出且不会发送 LowCmd。LowCmd 已启动后，Ctrl+C 或正常退出
会进入紧急阻尼。

## 阶段一：固定位置环接管并核对输出

保持吊绳保护，使用零速度 fixed 输入：

```bash
python scripts/real/test_policy_real.py --control fixed --vx 0 --vy 0 --vyaw 0
```

按上述顺序操作 `1`、吊起、`2`。重点检查：

- `[Handoff]` 显示 ReleaseMode 返回到首条 LowCmd Write 完成的耗时。
- `[LOWCMD ACTIVE]` 显示的固定位置是 `INITIAL_JOINTS_POS` 的 DDS 顺序。
- 第一条 LowCmd 不是零命令、stop 值或阻尼命令。
- 接管瞬间没有明显蹦跳、持续抖动或异常关节角度。

当前脚本不会长期暂停在固定位置环：模型加载期间保持固定位置，模型加载完成后会
自动进入下一阶段。

## 阶段二：依靠网络零速站立

出现以下提示后，policy 已经实际控制机器人：

```text
[POLICY ACTIVE] 预测 MotorCommand（正在发送）
```

保持 `vx=vy=vyaw=0`，至少观察 60 秒：

- `[COMMAND SOURCE]` 应持续显示三个速度为零。
- 机器人能够依靠 policy 保持站立。
- 允许记录轻微可接受抖动，但不能出现逐渐放大的振荡。
- IMU、关节输出和 policy MotorCommand 不应出现 NaN/Inf 或突变。
- 500 Hz 线程持续发送最新 policy 指令，没有触发安全限位或紧急阻尼。

这一阶段通过后退出程序，再单独启动 Xbox 测试。

## 阶段三：使用宇树原装遥控器

先通过机载默认服务让机器人站立，再将机器人固定到吊架。新脚本不会调用 StandUp，
也不读取键盘或 Xbox：

```bash
python scripts/real/test_policy_unitree_remote.py
```

脚本初始化 DDS 并收到原装遥控器数据后：

1. 先松开 `L2+R2`，再同时按下；该组合触发
   `ReleaseMode → INITIAL_JOINTS_POS 首帧 → 500 Hz LowCmd → 加载 policy`。
2. 检查 `[POST-RELEASE REMOTE]`：packet 计数应增加，消息 age 应保持很小，证明
   ReleaseMode 后仍能收到 LowState 中的遥控器字段。
3. 保持三个摇杆回中，确认 `[COMMAND SOURCE]` 的三个速度均为零。
4. 轻微推动左摇杆，让打印的 `vx` 从约 `0.05` 开始。
5. 依次在约 `0.05、0.10、0.20、0.30 m/s` 观察轮子、腿关节和机身稳定性。
6. 小幅测试 `vy` 和 `vyaw`，每次只改变一个方向。
7. 摇杆回中后确认速度归零；Select 退出并进入阻尼。
8. 吊架测试稳定后，才能在地面从最低速度重新开始，旁边必须有人保护。

默认映射为 `vx=Ly`、`vy=-Lx`、`vyaw=-Rx`。不要直接把摇杆推满；满行程会
映射到 `CTRL.COMMAND_LIMITS`。宇树手柄方案没有 deadman，摇杆始终生效；这样无需
长按 A，可避免手柄持续蜂鸣。

`--lowstate-timeout` 默认是 0.20 秒。LowState 停止更新时程序会退出并进入阻尼。
但 `wireless_remote[40]` 没有独立序号：如果 LowState 继续更新却反复携带冻结的旧
手柄字节，仅靠该字段无法判断手柄失联，因此第一次测试必须保持吊架保护。

## 逐关节限位

吊架测试时记录 DDS 0–11 的真实 `q/dq` 范围，再在
`config/go2w_config.py` 中逐项填写 `DDS.JOINT_LIMITS`。必须给正常运动留出裕量，
不要改回统一的循环推导值。四个轮子的速度由 `DDS.WHEEL_VEL_LIMIT` 单独检查。

## 通过标准

- StandUp 期间没有 LowCmd 干扰。
- ReleaseMode 返回后由固定位置环立即、平稳接管。
- 零速 policy 能稳定站立至少 60 秒。
- 宇树手柄 ReleaseMode 后 packet 计数持续增加。
- 宇树手柄摇杆回中时三个速度均为零。
- 从低速开始时，前进、侧向和转向方向正确且机器人保持稳定。
- Ctrl+C 或 Select 退出后正常进入阻尼并关闭。

## 异常处理

| 现象 | 处理 |
|------|------|
| 接管时蹦跳或剧烈抖动 | 立即退出，检查关节映射和初始位置 |
| 网络站立振荡逐渐增大 | 立即退出，检查观测、IMU 和 PD 增益 |
| 摇杆方向错误 | 立即回中并按 Select 退出，只修改新脚本顶部的方向符号 |
| LowState 超时 | 程序应报告异常并进入阻尼；不要继续测试 |
| 触发关节或轮速限位 | 保留违规信息，检查限位值与实际运动范围 |
| 姿态漂移 | 检查 DDS 四元数顺序和陀螺仪数据 |
