# 速度输入与原装遥控器调试

## 1. 完全离线检查键盘

```bash
source setup.sh policy
python scripts/debug_command_input.py --control keyboard
```

- `p`：使能/停用；默认未使能
- `w/s`：前后，`a/d`：左右，`q/e`：转向
- 空格或 `x`：立即归零，Esc：退出

## 2. 完全离线检查 Xbox

```bash
source setup.sh policy
ls /dev/input/js*
python scripts/debug_command_input.py --control xbox --joystick /dev/input/js0
```

默认轴映射沿用 simtosim 的 1/0/3：左摇杆纵轴 `vx`、左摇杆横轴
`vy`、右摇杆横轴 `vyaw`。必须持续按住 A 键才有非零输出；松开立即归零，
Back 退出。先在这个离线脚本中确认方向，方向不符时不要连接机器人。

## 3. 部署时选择输入

```bash
source setup.sh robot
python scripts/test_policy_real.py --control keyboard
python scripts/test_policy_real.py --control xbox --joystick /dev/input/js0
```

原固定速度参数仍可用：

```bash
python scripts/test_policy_real.py --control fixed --vx 0.05 --vy 0 --vyaw 0
```

所有输入在进入策略前按 `CTRL.COMMAND_LIMITS` 裁剪。

## 4. 宇树原装遥控器只读调试方案

当前先不把原装遥控器接入运动控制。按以下顺序验证：

1. 机器人放在支架上，但不运行 `test_policy_real.py` 或任何 LowCmd 发布程序。
2. 运行只读订阅：

   ```bash
   source setup.sh robot
   python scripts/debug_unitree_remote.py --interface enp0s31f6 --raw
   ```

3. 逐个按键并逐轴移动，记录 `Lx/Ly/Rx/Ry` 的中位值、正负方向、最大范围，
   同时确认按钮名称和 raw 字节变化。
4. 松手观察至少 30 秒，确认摇杆回中误差和是否有数据中断；据此确定 deadzone
   和失联归零超时。
5. 确认“使能键、急停键、退出键”组合后，再新增原装遥控器命令源；在此之前
   该脚本只解析 `rt/lowstate`，不创建 LowCmd publisher。

SDK 示例默认针对 HG 消息和 `rt/lf/lowstate`；Go2W 必须使用 `unitree_go`
消息以及本项目的 `rt/lowstate`。
