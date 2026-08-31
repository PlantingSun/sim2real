# Go2W Sim-to-Real 总览

## 项目目标

将 Go2W 强化学习策略从离线推理和 MuJoCo 仿真部署到实物机器人。当前流程按以下
5 步执行：驱动检查、策略检查、仿真检查、控制输入检查、实机测试。

完成基础 go2w 链路后，go2wcr/CRRL 按 `06_crrl_policy_test.md` →
`07_crrl_simulation_test.md` → `08_crrl_real_test.md` 执行；脚本归档规则见
`09_scripts_layout.md`。go2wwmp 当前只进入离线/仿真验证，见 `11_wmp_simulation_test.md`。

| 步骤 | 文档 | 目标 |
|------|------|------|
| 1 | `01_driver_layer.md` | 只读核对 DDS、关节和 IMU 状态 |
| 2 | `02_policy_layer.md` | 离线核对模型输入输出 |
| 3 | `03_simulation_test.md` | 在 MuJoCo 中跑通完整控制链 |
| 4 | `04_command_input.md` | 离线核对键盘、Xbox 和原装遥控器 |
| 5 | `05_real_test.md` | 固定位置环接管、零速 policy 站立、手柄行走 |

## 控制链

```text
test_policy_real.py（50 Hz）
    DdsDriver.get_state()             -> DDS 顺序 RobotState
    ControllerGo2w.build_obs()        -> Ctrl 顺序观测
    ControllerGo2w.compute_action()   -> Ctrl 顺序 action
    action_to_motor_command()         -> DDS 顺序 MotorCommand
    DdsDriver.send_command()          -> 更新最新指令缓存
                                      |
                                      v
DdsDriver 500 Hz 线程
    读取最新缓存 -> 安全限位检查 -> 零阶保持 -> CRC -> rt/lowcmd
```

Policy 以 50 Hz 更新目标，DDS 线程以 500 Hz 重复发送最新目标。驱动不做指令平滑。

## 关节顺序

| 模块 | 顺序 | 映射位置 |
|------|------|----------|
| DDS | 机器人 `motor_state/motor_cmd` 原生顺序 | 驱动边界 |
| Ctrl | `FL → FR → RL → RR`，每条腿含 wheel | 策略内部 |
| MuJoCo | 与 Ctrl 一致 | 仿真驱动边界 |

`CTRL_IDX_FROM_DDS` 和 `DDS_IDX_FROM_CTRL` 保留在 `config/go2w_config.py` 顶层，
数值是当前已经人工核对的版本。Controller 在策略边界映射，MuJoCo driver 在仿真
边界映射。

## 当前配置边界

- `CTRL`：网络维度、初始关节位置、动作缩放、PD 增益、策略频率和速度输入限幅。
- `DDS`：网卡、Domain、Topic、500 Hz 频率、stop 值、关节限位和紧急阻尼参数。
- `DDS.JOINT_LIMITS` 按 DDS 0–11 逐关节列出；`None` 表示该项暂不检查，需要根据
  实机观测结果逐项填写。
- `DDS.WHEEL_VEL_LIMIT` 单独限制四个轮子的速度。

## 环境

```bash
source setup.sh policy   # 离线 policy；不配置机器人网卡
source setup.sh mujoco   # Python MuJoCo；不连接机器人
source setup.sh robot    # Unitree DDS；绑定实机网卡
```

当前 pipeline 不依赖 ROS2。请在目标设备的 VS Code 中选择已经安装好依赖的 Python
解释器；`.vscode/settings.json` 会自动把项目内 `third_party/unitree_sdk2_python`
加入分析路径。

## 实机接管顺序

`DdsDriver.initialize()` 只初始化 LowState subscriber、LowCmd publisher 和消息对象，
不会启动 500 Hz 线程，也不会调用 `Write()`。实机脚本按以下顺序工作：

1. 按 `1` 调用 `StandUp()`，此时没有 LowCmd 发布。
2. 机器人站稳并吊好后按 `2`。
3. `ReleaseMode()` 返回成功后，立即同步发送第一条固定
   `INITIAL_JOINTS_POS` 指令，再启动 500 Hz 线程。
4. 模型加载期间保持发送固定位置环；模型开始推理后，每个 50 Hz 周期用 policy
   指令更新缓存。
5. Ctrl+C、Xbox Back 或输入异常退出时，已启动 LowCmd 的情况下发送紧急阻尼。

## 控制输入

- `fixed`：使用 `--vx/--vy/--vyaw` 指定固定速度。
- `keyboard`：`p` 使能，方向键位增量调速，停用后归零。
- `xbox`：左摇杆控制 `vx/vy`，右摇杆控制 `vyaw`；必须持续按住 A，松开立即
  输出零速度，Back 退出。
- `test_policy_unitree_remote.py` 从 `rt/lowstate.wireless_remote[40]` 读取宇树原装
  遥控器：`L2+R2` 触发 ReleaseMode 接管，摇杆始终生效，Select 退出；默认速度
  映射为 `vx=Ly`、`vy=-Lx`、`vyaw=-Rx`。

所有速度输入最终由 `CTRL.COMMAND_LIMITS` 裁剪。`test_policy_real.py` 每 0.5 秒打印
`enabled/vx/vy/vyaw` 和当前 policy MotorCommand，便于实机核对。

## 安全边界

- `test_dds_driver.py` 只检查 LowState；初始化 publisher 不等于发送 LowCmd。
- `debug_command_input.py` 不连接 DDS；`debug_unitree_remote.py` 只订阅 LowState。
- Xbox 松开 A 只代表速度指令归零，policy 和 LowCmd 仍在运行；退出脚本才进入阻尼。
- 宇树遥控器脚本会检测 LowState 更新时间，但无法识别“LowState 仍更新、其中
  wireless_remote 字节冻结”的情况。
- 宇树遥控器方案没有 deadman；摇杆离开中心就会产生速度指令，回中后由 deadzone
  归零。原装手柄长按按键会蜂鸣，因此不使用 A 持续使能。
- 第一次固定位置接管、第一次零速 policy 和第一次手柄控制都应使用架子或吊绳。
- 当前逐关节限位仍包含 `None` 时，对应字段没有软件保护，不能把它当作已启用的限位。
