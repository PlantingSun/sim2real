# 调研与审查发现

## 2026-08-27

### 当前状态

- 当前工作目录：`/home/robot/sim2real_ws`
- 仓库已包含 `models/go2wcr/model_1499.pt`，说明 CRRL 模型文件已被放入项目，但目前尚未看到对应的 policy/controller 实现。
- 当前已有 `go2w` 实现：`policy/controller_go2w.py`、`config/go2w_config.py`，以及 policy、MuJoCo pipeline、real test 脚本。
- 已有文档覆盖 driver、policy、simulation、command input、real test 五个主题。
- 用户给出的 `/home/robot/simtosim/src/model/go2wcr`、`scripts/lib/controller_go2wcr` 是逻辑路径；实际文件位于 `/home/robot/simtosim/src/controller/model/go2wcr`、`/home/robot/simtosim/src/controller/scripts/lib/controller_go2wcr`，入口为 `/home/robot/simtosim/src/controller/scripts/main_go2wcr.py`。

### 初始待确认事项

- go2wcr 网络的输入/输出张量形状、归一化、历史观测和动作缩放规则。
- go2wcr 控制器与当前 `driver` 层之间是否可直接复用接口。
- MuJoCo 模型是否与 go2wcr 训练时的机器人/关节顺序/控制周期一致。
- 现有 scripts 的依赖关系、默认参数及真实机器人安全开关。

### 已确认的 CRRL 接口

- `Go2wCfg.env.num_observations = 53`、`num_obs_length = 5`、`num_actions = 16`。
- CRRL Actor 输入维度为 `53*5 + 16 + 4 = 285`；Critic 输入维度为 `119 + 4 = 123`，实机只使用 Actor。
- 课程嵌入由每个 stage 的累计 assist 参数生成 `[sin(pi*c_k), cos(pi*c_k), sin(pi*c_{k-1}), cos(pi*c_{k-1})]`，共 4 个 stage；实现按 `pow=1.5` 规则逐项生成并测试，末级 stage 的前一累计值为 `(3/4)^1.5`。
- 原始 CRRL controller 的 `_build_cr_action` 顺序是：从 `prev_action=0` 开始，stage 0/1/2 分别调用 Actor 并累加，stage 3 再调用 Actor 得到最终动作。
- 原始 CRRL controller 仍依赖 ROS 消息和硬编码旧路径，且没有做动作/观测 shape、NaN/Inf 或模型键校验；sim2real 适配需要把这些边界显式化。
- go2w 与 go2wcr 的 53 维本体观测顺序一致：gyro(3)、projected gravity(3)、command(3)、12 个腿关节位置偏差、16 个关节速度、16 个上一动作。
- 训练环境的 assist force、pitch/roll spring 只属于 Isaac Gym 训练阶段；实机 driver 仍只接收标准 `MotorCommand`。
- `models/go2wcr/model_1499.pt` 的 Actor checkpoint 结构实际为 `285 -> 256 -> 256 -> 256 -> 256 -> 16`，Critic 为 `123 -> 512 -> 256 -> 128 -> 1`，normalizer 为 265 维。
- 默认 MuJoCo 场景可加载，包含 16 个 actuator 及 `BodyAcc`、`BodyGyro`、`BodyQuat` 等控制器需要的传感器；headless CRRL 闭环已运行 100 个物理步。
- CRRL 离线零状态输出的原始 action 峰值可能明显大于 1；当前实现仅保持训练配置的 `clip=100`，没有擅自增加未经训练数据支持的动作裁剪。实机前必须以仿真/吊架记录轮速和姿态，并由人工决定是否调整安全边界。
- `scripts/` 已按 `policy`、`simulation`、`input`、`real` 分类；根目录不再保留重复启动入口，运行时直接调用分类目录中的实际文件。
- 本次没有运行 DDS 初始化、Sport Mode、LowCmd 或真实机器人控制；实机效果和方向仍未宣称通过。

## 2026-08-29

- `scripts/simulation/test_mujoco_pipeline_go2wcr.py` 中的 `ControllerGo2wCR.action_to_motor_command()` 返回 `MotorCommand` 数据类，不返回四元组；打印代码必须使用 `.positions/.velocities/.kp/.kd`，且不能重复转换动作。
- `go2w_scene.xml` include 的 `go2w.xml` 已定义 `stand` keyframe，完整 qpos 为 base `z=0.43` 加初始站姿关节；XML 默认 base body `z=0.55` 不是本测试期望的初始站姿。
- 两个 MuJoCo 入口现在恢复完整 `stand` keyframe，随后执行 `mj_forward()`；helper 验证得到 `base_z=0.430 m`、16 个关节角和全零速度。
- go2wcr 无 viewer 单步闭环已成功打印 DDS 顺序 MotorCommand，并成功送入 MuJoCo 执行一步。
- 试验分支将策略历史从数值全零帧改为初始站立零运动帧：5 帧均包含投影重力 `(0, 0, -1)`，角速度、指令、关节偏差、关节速度和上一动作为 0；需由 simulation 和吊架 real test 观察启动瞬态。
