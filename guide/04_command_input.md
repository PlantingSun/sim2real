# Step 4: 控制输入检查

在连接实机前，先离线确认准备使用的输入设备。键盘和 Xbox 已完成离线验证；
当前下一阶段使用宇树原装遥控器。

## 1. Xbox 离线检查

```bash
cd /home/robot/sim2real_ws
source setup.sh policy
ls /dev/input/js*
python scripts/input/debug_command_input.py --control xbox --joystick /dev/input/js0
```

当前映射：

| 操作 | 输出 |
|------|------|
| 左摇杆上下 | `vx` |
| 左摇杆左右 | `vy` |
| 右摇杆左右 | `vyaw` |
| 持续按住 A | 允许输出非零速度 |
| 松开 A | 三个速度立即归零 |
| Back | 退出 |

逐轴缓慢移动，确认终端数值的正负方向、回中值和最大范围。所有值在进入 policy 前
按 `CTRL.COMMAND_LIMITS` 裁剪。方向不符合预期时，不要连接机器人。

## 2. 键盘离线检查（备用）

```bash
source setup.sh policy
python scripts/input/debug_command_input.py --control keyboard
```

- `p`：使能或停用；默认未使能。
- `w/s`：前后，`a/d`：左右，`q/e`：转向。
- 空格或 `x`：速度归零，Esc：退出。
- 未使能时调速键无效；停用时已有速度会立即归零。

## 3. 宇树原装遥控器只读结果

原装遥控器数据可以从 Go2W 的 `rt/lowstate` 中读取，字段为
`wireless_remote[40]`。只读验证命令为：

```bash
source setup.sh robot
python scripts/input/debug_unitree_remote.py --interface enp0s31f6 --raw
```

该脚本只创建 LowState subscriber，不创建 LowCmd publisher。实机已确认：

- `Lx/Ly` 对应左摇杆左右/前后，`Rx/Ry` 对应右摇杆左右/前后。
- 四个轴的范围均为 `-1.000` 到 `+1.000`。
- 终端会同时显示所有当前按下的按键，例如 `L2,A`。

新增的 `test_policy_unitree_remote.py` 使用 `L2+R2` 触发接管，摇杆始终生效，
Select 退出。由于长按按键会持续蜂鸣，宇树手柄方案不使用 A deadman；具体实机
步骤见 `05_real_test.md`。

## 通过标准

- 键盘和 Xbox 的离线输入检查通过。
- 宇树手柄四个轴、量程和多按键同时读取正常。
- 宇树手柄的前后、侧向和转向符号仍需在吊架实机测试中最终确认。

通过后再进入 `05_real_test.md`。
