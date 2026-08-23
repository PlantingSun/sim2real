# 2026-08-19 配置、环境与控制输入改动记录

这份文件用于在没有 Git 的情况下逐项审查本轮代码。原则是：一个完整改动批次只增加
一份记录文件，但记录中必须覆盖每个被修改、新增或删除的文件。

## 回退说明（当前有效状态）

根据使用者要求，已撤回此前超出明确需求的设计：

- `driver/dds_driver.py` 已恢复原控制逻辑，没有首帧门控、LowState 超时、命令超时或
  `state_received` 属性。本轮对该文件只保留读取新 Ctrl/DDS 配置位置所必需的引用调整。
- `config/go2w_config.py` 现在只有 `CTRL`、`DDS` 两个分区；两张映射表仍是顶层列表，
  数值不变。没有 `MAPPING`、`SAFETY`、`JointLimit` 或关节名称限位结构。
- `DDS.JOINT_LIMITS` 是 12 个普通字典，对应 DDS 0–11；每项仅有
  `q_min/q_max/dq_max` 三个 `None` 占位。
- `setup.sh robot` 已恢复 `UNITREE_NET_IF`（默认 `enp0s31f6`）、`ROS_DOMAIN_ID=0`
  和 `CYCLONEDDS_URI` 网卡绑定；policy/mujoco 模式不设置机器人网卡。
- `scripts/test_policy_real.py` 已恢复“DDS 初始化 → Sport Mode → 模型 → 控制循环”的原顺序，
  只在原循环上保留使用者明确要求的 fixed/keyboard/xbox 输入选择。

以下各节已同步为回退后的当前实现。

## 一、配置结构

### `config/go2w_config.py`

- 将原来的扁平常量拆成 `CTRL`、`DDS` 两个命名空间。
- `CTRL` 只保存策略顺序、网络维度、增益、动作缩放和 50 Hz 策略频率。
- `DDS` 只保存机器人报文顺序、Topic、SDK 常量、网口默认值和 500 Hz 发布频率。
- 两张 gather 映射表保留为顶层列表，数值没有修改。
- `DDS.JOINT_LIMITS` 按 DDS 0–11 列出 12 个普通字典。
- 每个字典的 `q_min/q_max/dq_max` 均为 `None`，由使用者填写。

### `policy/controller_go2w.py`

- 只把 Ctrl 常量改成 `CTRL.*`，映射继续读取顶层列表。
- 观测、网络、动作缩放和映射算法未改变。

### `driver/mujoco_driver.py`

- 只把 Ctrl 常量改成 `CTRL.*`，映射继续读取顶层列表。
- MuJoCo 物理步进和执行器控制方式未改变。

### `scripts/test_mujoco_pipeline.py`

- 用 `DDS.RATE_HZ` 和 `CTRL.POLICY_RATE_HZ` 替代硬编码的 500/50。

## 二、DDS 安全改动

### `driver/dds_driver.py`

- 改为从 `DDS` 分区读取 Topic、频率、stop 值、LIMIT 和 Sport Mode 参数。
- 限位循环、500 Hz 发布、零阶保持、阻尼、CRC 和 Sport Mode 控制逻辑保持原样。

### `scripts/test_policy_real.py`

- 50 Hz 改为读取 `CTRL.POLICY_RATE_HZ`。
- 新增 `--control fixed|keyboard|xbox` 和 `--joystick`。
- 原来的 `--vx/--vy/--vyaw` 固定速度方式保留。
- 初始化顺序仍为 DDS → Sport Mode → 模型 → 控制循环。

### `scripts/test_dds_driver.py`

- 默认网口改为读取 `DDS.DEFAULT_NET_IF`。
- 注意：这个脚本会初始化 `DdsDriver`，因此会创建 LowCmd publisher；它不是只读脚本。

## 三、环境脚本

### `setup.sh`

- 删除自动 source ROS2 和 `RMW_IMPLEMENTATION` 的逻辑。
- 当前 policy、Python MuJoCo 和 Unitree SDK2 驱动均不依赖 ROS2。
- 增加 `policy`、`mujoco`、`robot` 三种依赖检查模式。
- policy/mujoco 模式不设置 DDS 网卡；robot 模式设置 `ROS_DOMAIN_ID`、
  `UNITREE_NET_IF` 和 `CYCLONEDDS_URI`，但仍由机器人脚本负责真正初始化 DDS。
- 已分别在 bash 和 zsh 中验证。

### `.vscode/settings.json`

- Python 解释器指向 `/home/robot/miniconda3/envs/unitree_py38/bin/python3.8`。
- `python.analysis.extraPaths` 指向 `/home/robot/test_com_ws/unitree_sdk2_python`。
- 这只解决编辑器的 import 黄色下划线，不复制或重新安装 SDK。

## 四、控制输入

### `teleop/command_source.py`（新增）

- `FixedCommandSource`：保留固定速度输入并执行速度裁剪。
- `KeyboardCommandSource`：`p` 使能，`w/s/a/d/q/e` 调速，空格归零，Esc 退出。
- 键盘未使能时忽略调速键，避免先输入速度、后使能时突然运动。
- `XboxCommandSource`：直接读取 Linux `/dev/input/js0`，不依赖 ROS 或 pygame。
- Xbox 默认使用 simtosim 的 1/0/3 轴语义；A 键为 deadman，松开输出立即归零。
- 所有输入最终裁剪到 `CTRL.COMMAND_LIMITS`。

### `teleop/__init__.py`（新增）

- 只导出三种命令源和 `CommandSample`，没有运行逻辑。

### `scripts/debug_command_input.py`（新增）

- 离线查看键盘或 Xbox 输出。
- 不导入 `DdsDriver`，不会连接机器人。

### `scripts/debug_unitree_remote.py`（新增）

- 使用 Go2W 的 `unitree_go LowState_` 和 `rt/lowstate`。
- 在同一个文件中解析 40-byte `wireless_remote`，避免增加独立解析模块。
- 只创建 LowState subscriber，不导入 LowCmd、不创建 publisher。
- 当前仅用于确认原装遥控器按键、轴方向、回中误差和失联行为，未接入运动控制。

### `scripts/test_command_input.py`（新增，合并测试）

- 一个文件覆盖映射互逆、限位占位、固定输入裁剪、键盘使能和 Xbox 事件解析。
- 不打开键盘、手柄或 DDS 设备。

## 五、说明文档

- `README.md`：更新三种 setup 模式和三种控制输入用法。
- `guide/00_overview.md`：澄清映射所在的系统边界。
- `guide/01_driver_layer.md`：移除 ROS2 前置条件，改用 robot 模式。
- `guide/02_policy_layer.md`：改用 policy 模式。
- `guide/03_simulation_test.md`：改用 mujoco 模式并说明不会连接实机。
- `guide/04_robot_stand_test.md`：改用 robot 模式。
- `guide/05_robot_walk_test.md`：说明 12 个限位槽由使用者逐项填写。
- `guide/06_command_input.md`：记录键盘、Xbox 和原装遥控器调试步骤。

## 六、为减少文件数量而删除的文件

- 删除 `teleop/unitree_remote.py`，解析逻辑并入只读遥控器调试脚本。
- 删除 `scripts/test_config.py`、`test_unitree_remote_parser.py`、`test_dds_safety.py`，必要的纯离线检查合并到 `test_command_input.py`。
- 删除临时的 `scripts/test_mujoco_headless.py`；正式 MuJoCo 验证仍使用原有 `test_mujoco_pipeline.py`。
- 删除 `.planning/go2w_refactor/` 下的三个内部计划文件。

## 七、建议审查顺序

1. `config/go2w_config.py`：先确认关节名称、两张映射表和待填限位。
2. `policy/controller_go2w.py`、`driver/mujoco_driver.py`：确认只改变配置引用方式。
3. `driver/dds_driver.py`：重点确认初始化不发布、固定首帧和线程启动边界。
4. `teleop/command_source.py`：确认速度方向、裁剪、使能和 deadman。
5. `scripts/test_policy_real.py`：确认连接、释放 Sport Mode 和退出顺序。
6. 两个 debug 脚本：确认离线输入与只读 DDS 的边界。

## 八、验证命令

```bash
source setup.sh policy
python scripts/test_command_input.py
python scripts/test_policy_offline.py

source setup.sh mujoco
python scripts/test_mujoco_pipeline.py
```

本轮自动验证未连接机器人。`test_dds_driver.py`、`test_policy_real.py` 和
`debug_unitree_remote.py` 只有在人工确认网口和机器人状态后才能运行。

## 九、2026-08-20 DDS 状态显示补充

### `scripts/test_dds_driver.py`

- 仅在原有 2 Hz 状态输出中增加 `imu_quat` 和 `imu_accel`。
- quaternion 按 `RobotState` 内部顺序 `[w, x, y, z]` 打印。
- 保留原有 RPY、gyroscope、关节和轮子输出；未修改 DDS 初始化或控制逻辑。

## 十、2026-08-20 LowCmd 分阶段接管

### `driver/dds_driver.py`

- `initialize()` 只初始化 LowState subscriber、LowCmd publisher 和消息对象，不启动线程，
  也不调用 `Write()`。
- 新增 `start_lowcmd_thread()`；没有 pending command 时拒绝启动。
- 启动时先把 pending command 填入 LowCmd 并同步 `Write()` 一次，再启动 500 Hz
  线程。因此第一条实际 LowCmd 就是调用方预先写入的固定指令，不会发空命令或零命令。
- 新增 `stand_up()`，只调用一次 `SportClient.StandUp()`。
- `release_sport_mode()` 只执行一次 `ReleaseMode`，随后轮询 `CheckMode`；删除其中的
  `StandUp/StandDown`，也不会在轮询中重复调用 `ReleaseMode`。
- `shutdown()` 仅在线程已经启动时发送最后的阻尼 LowCmd；线程未启动时不发布。

### `scripts/test_policy_real.py`

- 使用单键阶段控制：`1=StandUp`、`2=ReleaseMode`、`3=固定站姿接管`，`q=退出`。
- 按 `3` 前先构造 `INITIAL_JOINTS_POS` 对应的 DDS 顺序位置、速度和增益，调用
  `send_command()` 写入缓存，再调用 `start_lowcmd_thread()`。
- policy 在固定 LowCmd 已经接管后才加载。
- policy 预测的 `position/velocity/kp/kd` 只打印，不再调用 `send_command()`，
  所以 500 Hz 线程始终发送按 `3` 时写入的固定站姿指令。
- 本阶段没有提供发送 policy 指令的开关；实际 policy 控制留待后续明确修改。

### `guide/04_robot_stand_test.md`

- 改为 StandUp → 人工吊起 → ReleaseMode → 固定位置环 → policy dry-run 的逐键流程。

## 十一、2026-08-20 ReleaseMode 与固定 LowCmd 合并

### `driver/dds_driver.py`

- `release_sport_mode()` 在 `ReleaseMode()` 返回 `code=0` 后立即返回成功。
- 删除 ReleaseMode 后的 `CheckMode` 轮询，避免在释放和 LowCmd 接管之间增加等待。

### `scripts/test_policy_real.py`

- 阶段按键由 `1→2→3` 简化为 `1→2`。
- `1` 仍然只执行 `StandUp`。
- 等待 `2` 时已经构造好固定初始指令，但尚未写入 driver。
- 按 `2` 后依次执行 `ReleaseMode → send_command(initial) → start_lowcmd_thread()`，
  中间没有人工按键或状态轮询。
- 打印 ReleaseMode 返回后到首条 LowCmd `Write()` 调用完成的软件侧耗时。
- policy dry-run 行为不变，预测指令仍然只打印、不发送。

## 十二、2026-08-22 Policy 实机 LowCmd 输出

### 脚本重命名

- `scripts/deploy_go2w.py` 重命名为 `scripts/test_policy_real.py`，与
  `test_policy_offline.py` 区分，并明确该脚本会连接和控制实机。
- README 和 guide 中的运行命令同步使用新文件名。

### `scripts/test_policy_real.py`

- 保留 `1=StandUp`、`2=ReleaseMode 后立即用 INITIAL_JOINTS_POS 接管` 的流程。
- 模型加载期间，500 Hz 线程继续发送固定初始位置环。
- 每次 50 Hz policy 推理后，将转换成 DDS 顺序的 `position/velocity/kp/kd`
  封装为 `MotorCommand` 并调用 `driver.send_command()`。
- 500 Hz 线程随后持续发送最新的 policy 指令；终端标记改为
  `[POLICY ACTIVE] ...（正在发送）`。
- 限位检查、违规后紧急阻尼和 Ctrl+C 退出流程没有修改。

## 十三、2026-08-23 Command Source 数值显示

### `scripts/test_policy_real.py`

- 在原有每 0.5 秒一次的 policy 指令打印位置，增加当前 command source 输出。
- 显示 `enabled`、`vx`、`vy`、`vyaw`，用于实机前核对 Xbox deadman 和摇杆方向。
- 没有修改 Xbox 映射、deadzone、速度裁剪、policy 输入或 LowCmd 发送逻辑。
