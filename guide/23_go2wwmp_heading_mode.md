# 23：Go2WWMP 航向保持模式

航向保持只加入正式入口 `scripts/real/run_go2wwmp_unitree.py`。机器人完成原有 L2+R2 接管后，
操作者可以用原装遥控器临时开启或关闭；模型加载、深度时序、WMP action 和 500 Hz LowCmd
流程均不改变。助手不会运行本页的实机命令。

## 1. 按键和行为

| 操作 | 结果 |
|---|---|
| 单击 A | 开启航向保持，并把按下时的 IMU yaw 记为目标朝向 |
| 单击 B | 关闭航向保持，恢复 `vx=Ly`、`vy=0`、`vyaw=-Rx` 的手动命令 |
| Select | 退出正式入口，并按原流程进入阻尼 |

程序只响应 A/B 的新按下沿，不需要长按。刚进入 WMP action 循环时会先记录一次按键状态；
因此接管前已经按住 A 不会自动开启，必须松开后重新单击。

开启后的 WMP 命令固定为：

```text
vx   = 0.5 m/s
vy   = 0
error = wrap(target_yaw - current_yaw) 到 [-pi, pi]
vyaw = clip(1.0 * error, -1.0, 1.0) rad/s
```

正负 π 附近使用最短角度误差，不会因为 yaw 从 `+pi` 跳到 `-pi` 而反向绕一整圈。航向模式
开启期间 Ly/Rx 不参与速度命令；B 关闭后当前摇杆位置会立即恢复生效。关闭前先把摇杆回中。

再次选择目标朝向时，先按 B 关闭，把机器人调整到新朝向，再单击 A；开启状态下重复按 A
不会更新目标。

## 2. 启动和现场检查

环境和正式入口仍使用原命令：

```bash
cd /home/robot/sim2real_ws
source setup.sh robot
python scripts/real/run_go2wwmp_unitree.py
```

操作顺序：

1. 机器人先在原生 Sport Mode 站稳，确认保护架/绳、物理急停和第二人观察就绪。
2. 松开 L2+R2，再同时按下二者，完成原有 WMP LowCmd 接管。
3. 保持 A/B 松开，先确认手动命令和零速站立正常。
4. 选择无障碍、距离足够的直线路径，单击 A。终端应打印 `[HEADING ON]`、目标 yaw 和
   `vx=0.500m/s`。
5. 第一次只运行极短距离；观察机器人是否朝启用瞬间的方向前进，偏航后是否产生正确方向的
   `vyaw` 修正。
6. 把摇杆回中后单击 B。终端应打印 `[HEADING OFF]`，随后恢复手动 Ly/Rx 命令。
7. Select 或 Ctrl+C 结束整次运行；B 只关闭航向模式，不停止 WMP 或 LowCmd。

第一次验证不要直接在窄通道、台阶或硬障碍前开启。若修正方向相反、转向迅速饱和、IMU yaw
跳变或机器人偏离目标方向，立即按 B、Select 或使用物理急停，本轮结束后检查日志，不在现场
连续修改符号重试。

## 3. 日志

主 JSONL 每周期额外记录：

- `heading_mode`：本周期是否开启；
- `heading_event`：新开启为 `"enabled"`、新关闭为 `"disabled"`，其他周期为 `null`；
- `heading_target_yaw_rad`：目标 yaw，关闭时为 `null`；
- `heading_current_yaw_rad`：本周期 IMU yaw；
- `heading_error_rad`：包角后的目标误差，关闭时为 `null`。

`command` 始终是最终送入 WMP 的命令，因此航向模式开启时应为
`[0.5, 0.0, heading_error_rad]`，第三项达到边界时会裁剪到 `[-1,1]`。完整日志格式见
[22.5](22.5_go2wwmp_log_format.md)。

## 4. 代码边界

- `teleop/heading_mode.py`：纯 NumPy/数学计算和按键沿状态，不访问 DDS；
- `teleop/unitree_remote.py`：继续负责遥控器解析，同时向正式入口提供本周期按键快照；
- `scripts/real/run_go2wwmp_unitree.py`：在读取 LowState/遥控器后调用航向模块，把最终命令送入 WMP。

航向模式只改变 WMP 的 `[vx,vy,vyaw]` 输入。深度过期、LowState 过期、session 改变、worker
异常、Select/Ctrl+C 和既有 fail-closed/阻尼顺序全部保持不变。
