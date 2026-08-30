# CRRL-3：go2wcr 实机测试

## 前置条件

- `06_crrl_policy_test.md` 和 `07_crrl_simulation_test.md` 通过。
- 已完成原有 driver 层和输入设备检查。
- 机器人由架子或吊绳保护，现场有人可以立即断电/退出。
- `DDS.JOINT_LIMITS` 中的 `None` 仍表示未启用逐项保护，不能视为已完成安全配置。

## 键盘/Xbox 实机入口

```bash
cd /home/robot/sim2real_ws
source setup.sh robot
python scripts/real/test_policy_go2wcr_real.py --control fixed --vx 0 --vy 0 --vyaw 0
```

确认零速 policy 能稳定站立后，再使用：

```bash
python scripts/real/test_policy_go2wcr_real.py --control keyboard
python scripts/real/test_policy_go2wcr_real.py --control xbox --joystick /dev/input/js0
```

脚本的接管顺序与现有 go2w 入口一致：按 `1` 执行 StandUp；站稳并吊好后按 `2` 释放 Sport Mode；ReleaseMode 成功返回后立即发送固定 `INITIAL_JOINTS_POS` 首帧，再启动 500 Hz LowCmd 发布。模型加载期间保持固定站姿，加载后由 go2wcr 50 Hz 更新指令。

策略启动时，5 帧历史会先填充为初始站立零运动状态（投影重力 `(0, 0, -1)`，其余运动量和
关节位置偏差为 0），随后第一帧 LowState 观测会替换最新历史帧。首次实机测试应重点观察
启动后的前 5 个 policy frame。

## 原装遥控器入口

先只读确认遥控器字段：

```bash
python scripts/input/debug_unitree_remote.py --interface enp0s31f6 --raw
```

确认后使用 CRRL 入口：

```bash
python scripts/real/test_policy_go2wcr_unitree_remote.py
```

该入口复用 `test_policy_unitree_remote.py` 的接管和退出阻尼逻辑，仅将策略固定为 go2wcr。松开后再同时按下 `L2+R2` 才触发接管；Select 退出。默认速度映射为 `vx=Ly`、`vy=-Lx`、`vyaw=-Rx`，第一次必须在吊架上从约 `0.05 m/s` 开始逐级增加。

## 通过标准

- ReleaseMode 后首条 LowCmd 是固定站姿，不是零命令或 stop 值。
- 零速 go2wcr 能在吊架保护下稳定观察至少 60 秒。
- 观测、动作和 MotorCommand 始终有限，没有触发安全阻尼。
- 轮子、腿关节和机身方向符合预期；每次只改变一个速度轴。
- Ctrl+C、Select 或输入异常后进入紧急阻尼并关闭。

## 禁止事项

- 不要在没有通过离线/仿真测试时运行实机入口。
- 不要把 `--no-release` 当成安全旁路；它只适用于已经明确处于可接管状态的复核场景。
- 不要在首次测试中直接推满摇杆，也不要在地面跳过吊架测试。
