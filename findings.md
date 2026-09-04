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

## 2026-08-30

- 当前 `scripts/simulation/test_mujoco_pipeline.py` 使用项目内 `assets/go2w_description/mjcf/go2w_scene.xml`，该场景再 include 项目内的 `go2w.xml`；所需 MJCF/mesh 已纳入仓库。
- 外部 `go2w.xml` 的 `base` 局部坐标系已有 `depth_camera` 相机；当前相机位置和可视化标记均直接维护在该 XML 中。
- 历史验证曾使用 MuJoCo viewer 的 `user_scn` 临时几何体；当前已改为在共享 `go2w.xml` 的 `base` body 中直接添加两个不参与物理的 XML geom。
- 初始验证曾使用过渡坐标 `[0.34, 0.0, 0.096]` 和 `[0.34, -0.022, 0.096]`；该坐标已被用户最终确认的 `[0.34, -0.0375, 0.09]` 替代。
- 当前站立姿态下标记的期望世界坐标为 `[0.34, -0.0375, 0.52]`；`MjvGeom` 会将圆柱输入尺寸保存为 `[radius, radius, half_length]`。
- 在基座原方向及绕 `z` 轴旋转两种状态下，历史 user geom 的位置和方向验证通过；当前 XML geom 使用 `contype=0`、`conaffinity=0`，不参与碰撞。当前环境实际 viewer 因 GLFW 无法初始化，未完成窗口截图检查。

## 2026-08-30 调研：D435i 深度参考点

- RealSense 官方 D435i 页面说明：D435i 在 D435 的立体深度能力上增加了 IMU；深度技术为立体深度，深度视场角约 `87° × 58°`，机身尺寸约 `90 × 25 × 25 mm`。
- RealSense 官方 Projection 文档说明：每个视频流都有独立的 3D 坐标系，`[0, 0, 0]` 位于该流对应的物理成像器中心；点坐标轴为 `x` 向右、`y` 向下、`z` 向前。
- 同一官方文档说明：深度通常由一个或多个红外成像器产生，RGB 流可以位于不同物理位置；不同流之间要用标定的 extrinsics 平移/旋转转换。因此“深度图像对应的位置”应优先解释为深度成像器/深度坐标系，不是 RGB 镜头或外壳几何中心。
- 官方 D435/D435i 文档还说明左右红外图像默认已校正，深度图与左 IR 流像素对齐；这支持把深度参考点放在深度立体模组的参考位置，但不能仅凭官网尺寸推出机器人坐标中的 `y=-0.022 m`。

### 本地 WMP 链路与公开 Go2W 案例

- 共享 `go2w.xml` 的 `depth_camera` 已更新为基座局部 `[0.34, -0.0375, 0.09]`，光轴保持朝 `+x` 并向下俯视 `5°`。
- `/home/robot/simtosim/src/simulator/scripts/go2w_mujoco.py` 直接以 `depth_camera` 渲染 64×64 深度图并发布 `/depth_camera/image_raw`；没有执行深度到 RGB 的对齐。
- `go2wwmp` 和 `go2wwmpcr` 的 `CallbackDepth()` 直接 reshape raw depth，并送入 64×64 image 输入；因此后续 WMP 参考的是 raw depth stream 的深度坐标系。
- Unitree-Go2-Robot 的公开 Go2 仓库只给出安装 `ros-humble-realsense2-camera` 和启动方式，没有公布 Go2W 机身到 D435i 的精确 TF/外参；其公开 issue #37 还在请求 D435i 安装支架模型，不能作为本机安装尺寸的证据。
- 一个公开的 Go2W 传感器描述项目把 D435i 安装在 PiPER 机械臂腕部，并明确说明其外参来自组合 URDF；这与本机“基座前部固定相机”不是同一安装方案。另一个公开 robot_lab Go2W URDF 未包含 D435i 相机，说明公开 Go2W 模型之间并无统一的机身相机外参。

### 对历史 `y=-0.022 m` 假设的判断

- 已证实：若当前程序使用未经对齐的 D435i `depth` 流，参考点应是左 IR 成像器中心（D435i 深度立体模组的深度坐标原点），不是 RGB 镜头中心。
- 尚未证实：`y=-0.022 m` 是否就是本机左 IR 成像器中心。官方的 `17.5 mm` 是从相机底部 1/4-20 安装孔中心线到左成像器的偏移，参考基准不同，不能直接等同于 Go2W 基座的 `y=-22 mm`。
- [推断] 若本机基座 `y=0` 恰好对应相机安装中心线，并且相机朝向/左右方向与模型一致，则 `22 mm` 的量级与 D435i 的 `50 mm` 双目 baseline（单侧约 `25 mm`）相近，作为右侧镜头可视化标记是合理的初始假设；但要确定深度原点符号和具体镜头，仍需要核对安装孔/支架基准或读取实机 RealSense extrinsics。
- 官方资料还给出 D435/D435i 深度起始面的 Z 偏移约 `-4.2 mm`（相对于前盖玻璃的定义），所以深度距离的 Z 零点也不能简单当作外壳前表面；这不影响当前先核对横向 `y` 位置的步骤。
- 官方 D400 系列数据表给出更具体的机械基准：D435/D435i 的 depth origin X-Y 是左成像器中心；从机身底部 `1/4-20` 三脚架安装孔中心线到左成像器中心的横向偏移为 `17.5 mm`。这个数值可以用于从相机安装孔反推深度原点，但不能直接替代“Go2W 基座坐标到安装孔”的测量。
- 官方 D435/T265 对齐说明明确区分两种情况：未对齐的 D435 depth frame 与左 IR 成像器中心重合；执行 depth-to-color 对齐后，深度点会转换到 RGB 成像器中心坐标系。当前 `go2wwmp`/`go2wwmpcr` 走的是 raw depth，因此应按前一种解释。
- 根据用户确认的基座坐标约定 `+x` 前、`+y` 左、`+z` 上，长方体标记已绕基座 `+z` 旋转 90°：相机宽度沿 `y`，厚度沿 `x`，前表面朝 `+x`。红色圆柱的轴线继续保持 `+x`。

## 2026-08-31 D435i 网络读取准备

- 当前笔记本环境可见 `/opt/ros/humble/bin/ros2`，`ROS_VERSION=2`、`ROS_DISTRO=humble`；当前 `sim2real_ws` README 明确声明本项目不依赖 ROS/ROS2。
- `/home/robot/simtosim` 的相机输入仍是 ROS1 `rospy` 代码，WMP/WMPCR 订阅 `/depth_camera/image_raw`；其 MuJoCo 节点发布的是 `32FC1` 的仿真深度图，不是实机 D435i 的标准 RealSense话题。
- 因此，实机第一步应把相机采集/网络传输/画面显示作为独立只读链路验证：Orin NX 通过 USB 采集并运行 RealSense ROS2 驱动，笔记本通过 ROS2 DDS 订阅显示；暂不接入 WMP 或任何机器人控制入口。
- 需要在 Orin NX 上确认实际 ROS2 发行版、`realsense2_camera` 是否安装、相机节点是否已启动，以及两台设备的 ROS2 domain/DDS 网络发现配置；这些信息不能从当前笔记本仓库推断。
- RealSense 官方 ROS2 wrapper 文档确认 Humble 受支持；当前版本推荐使用 `ros2 launch realsense2_camera rs_launch.py`，默认命名空间通常为 `/camera/camera`，可发布 `/camera/camera/color/image_raw`、`/camera/camera/depth/image_rect_raw` 和对应 `camera_info`/extrinsics 话题。
- ROS2 官方多机发现文档说明，节点可通过同一子网的 DDS multicast 自动发现；若网络设备或交换机不转发 multicast，则需要配置指定 peer/discovery server。`ROS_LOCALHOST_ONLY` 不能设为 `1`，两端还应保持相同 `ROS_DOMAIN_ID`。
- 本轮首次官方资料检索因 JavaScript 字符串书写错误失败一次；随后改用合法查询成功取得官方 RealSense wrapper 与 ROS2 文档，未影响判断。

## 2026-08-31 Orin NX 入门任务

- NVIDIA 官方 Jetson 文档把设备访问分为 headed（显示器、键盘、鼠标直接连接）和 headless（通过另一台电脑进入）两类；这为入门顺序提供了框架，但 NVIDIA AGX Orin Developer Kit 的载板接口不能直接当作宇树 Go2W 扩展坞接口。
- NVIDIA 开发套件文档中，显示器接口是 DisplayPort，USB Type-A 可作为主机连接 USB 设备，USB-C UFP 可用于 USB device mode/虚拟网卡，micro-B 可用于 Debug UART；这些端口能力只对对应 NVIDIA 开发套件载板成立，当前 Go2W 机载载板仍待实物确认。
- NVIDIA 将 Jetson Orin NX 定位为小型、低功耗边缘 AI 计算平台；官方产品线页面给出 Orin NX 系列最高约 157 TOPS，并强调 JetPack/CUDA-X 软件栈和多传感器接口。实际可用性能还取决于 8GB/16GB 型号、JetPack、功耗模式、散热和载板。
- Unitree-Go2-Robot 公开 ROS2 仓库说明 D435i/RealSense 驱动应在机器人内部安装运行；这支持“Orin 采集、笔记本接收”的分工，但仓库没有给出本机 Go2W 载板的登录 IP、账号或显示接口。
- Unitree Robotics 的公开 `teleimager` 项目支持 ARM 架构的 Jetson Orin NX，能够采集 UVC/OpenCV/RealSense 相机，并通过 ZeroMQ PUB-SUB 或 WebRTC 发布视频；它可作为后续非 ROS2 视频通道候选，但不能替代当前首先确认的系统登录、USB 设备和网络状态。
- 新任务的安全边界：先做电源/显示/键鼠或终端登录、系统信息、网络、USB 和文件传输验证；不刷写系统、不改功耗、不安装大套件、不启动机器人控制、不接入 LowCmd/Sport Mode。
- NVIDIA 官方 Orin NX 数据表列出 8GB/16GB 两种模块，均为 1024 CUDA cores、32 Tensor cores；旧资料与 JetPack Super Mode 资料中的 TOPS 数值口径不同，因此入门文档应优先记录设备实际型号、JetPack/L4T 版本和当前功耗模式，不把宣传峰值直接当作现场性能。
- NVIDIA 官方开发套件文档提供了 headed/headless 两种进入方式和 USB 虚拟网卡/Debug UART 方式；但 Go2W 使用的是宇树载板，是否具备对应端口和地址必须现场确认。
- Unitree 官方组织下的 `teleimager` 文档给出了可选的视频网络方案：Orin NX 端启动 image server，笔记本端用 `--host <Orin IP>` 的 image client，或浏览器访问 WebRTC 端口；它支持 RealSense，但需额外安装其依赖，暂不作为系统入门的第一条路径。

### Go2-W 扩展坞接口与官方推荐进入方式

- 宇树 Go2-W 用户手册的扩展坞接口图/说明列出：`M8` 为雷达接口；两个 `BAT` 为 `16–60V` 电源输入；一个千兆 RJ45 连接 Go2-W，另一个千兆 RJ45 用于用户扩展；`USB-A` 为 `5V/1A` 用户扩展；`USB3.2 Type-C` 用于连接深度相机；另一个“全功能 Type-C”用于连接显示器。
- 因此对于没有传统 HDMI/DP 的 Go2W 扩展坞，官方推荐的首次图形化进入路径是使用“全功能 Type-C → 显示器”的转换线/扩展坞，再通过 USB-A 连接键盘鼠标。D435i 应占用标注为深度相机的 USB 接口。
- 当前用户描述的实体接口数量与手册中可能存在差异，不能仅凭外观把唯一 Type-C 端口判断为显示输出或相机输入；应以端口旁的文字/图标和实际线缆连接确认。若确实只有一个 Type-C，需要优先确认它是否为“全功能 Type-C”还是“USB3.2 Type-C 相机口”。
- 手册 PDF 的网页正文/图示来自 `marketing.unitree.com/article/en/Go2-W/User_Manual.html`；当前浏览工具不能直接打开该营销页面，但可检索到其手册副本中的接口原文，结论以手册接口说明为依据。

### 现场已验证的 Orin NX 状态（用户提供）

- 进入方式已验证：扩展坞全功能 Type-C 经转换器连接外部 HDMI 显示器可用；用户扩展 RJ45 通过 SSH 进入可用。
- 登录身份：`whoami=unitree`，主机名为 `ubuntu`。凭据中的密码不写入仓库、日志或示例命令。
- 系统：Ubuntu `20.04.5 LTS (Focal Fossa)`，说明后续 ROS2/RealSense 软件版本必须先按 Ubuntu 20.04 和实际 JetPack/L4T 版本匹配，不能直接套用笔记本的 ROS2 Humble 环境。
- 网络：`eth0` 为 `UP`，地址为 `192.168.123.18/24`；`lo` 为本地回环；`docker0` 为 `172.17.0.1/16`；`l4tbr0`、`rndis0`、`usb0` 当前为 `DOWN`。这确认当前 SSH 使用有线 `eth0`，而不是 USB gadget 链路。
- USB：Bus 002 的 USB 3 root hub 下识别到 `8086:0b3a Intel(R) RealSense(TM) Depth Camera 435i`；键盘和 USB Hub 也被识别。D435i 已经在 Orin NX 侧完成物理连接和 USB 枚举。
- 以上信息由用户现场执行命令得到，属于当前设备事实；下一步可以进入“Orin 本地软件盘点”，但仍不启动相机流或机器人控制。

## 2026-08-31 Go2W WMP 仿真移植核对

- simtosim 的 WMP 推理入口由 `src/controller/scripts/main_go2wwmp.py` 驱动，频率为 50 Hz；它订阅本体 IMU、电机状态、速度命令和 `depth_camera/image_raw`，然后调用 `ControllerGo2wWMP.UpdateObs()` 与 `UpdateAction()`。
- `src/controller/scripts/lib/controller_go2wwmp/controller_go2wwmp.py` 的实际推理输入为角速度、投影重力、3 维速度命令、12 个腿关节位置偏差、16 个关节速度、上一动作和 5 帧历史；深度/world model 更新每 5 个策略周期执行一次。
- WMP 深度输入是 `64×64×1`，来自 `32FC1`；原控制器先做 `depth - 0.5`，因此 simtosim 的 MuJoCo 深度被裁剪到 `[0, 2] m` 后再除以 `2`，进入网络的范围约为 `[-0.5, 0.5]`。
- WMP actor 结构为 `ActorCriticWMP`：历史编码器输出 48 维，world-model 确定性特征经编码器输出 40 维，最后与当前本体/命令/上一动作向量拼接后输出 16 维原始动作；腿关节使用 `0.25` 位置缩放，轮关节使用 `10.0` 速度缩放。
- world model 配置来自 `go2wwmp_configs.yaml`，默认 CPU、64×64 图像、RSSM `stoch=32, discrete=32, deter=512`，并把 `num_actions` 从 16 扩展为 `16×5=80` 以匹配 5 帧动作历史。
- WMP checkpoint 已复制到当前项目 `/home/robot/sim2real_ws/models/go2wwmp/model_1750.pt`（约 318 MB）；由于 `.gitignore` 的 `*.pt` 规则，它只作为本地运行文件，不进入 Git。
- simtosim WMP 源码还包括 Isaac Gym 训练环境 `go2wwmp.py`、地形 `go2wwmp_terrain.py`、训练/恢复 runner `wmp_runner.py` 和 Isaac Gym 播放入口 `playwmp.py`。当前 MuJoCo 验证只需要其网络/观测/动作定义，不应引入 Isaac Gym 或 ROS1 依赖。
- go2wwmp 的训练相机位置和共享 MuJoCo `depth_camera` 均已统一为 `[0.34, -0.0375, 0.09]`；pipeline 不再提供旧场景相机或额外深度偏移模式。
- 新适配已通过严格 checkpoint 加载、`obs_now=53`、`history=250`、`wm_feature=512`、16 维动作检查和 6 周期推理；`MotorCommand` 已按当前项目的 DDS 顺序输出。
- 无窗口环境下可以验证网络链路，但本机 `DISPLAY=:1` 无法创建 GLFW/OpenGL context，故真实 `Renderer` 深度帧和 viewer 闭环必须在 Orin 本地图形桌面或其他可用图形环境中复测。
- WMP 推理依赖已直接内置到当前项目：`policy/actor_critic_wmp.py`、`policy/dreamer/{models,networks,tools}.py`、`policy/dreamer/__init__.py` 和 `config/go2wwmp_configs.yaml`；`controller_go2wwmp.py` 不再导入 `tensorboard`、外部 `lib` 或 simtosim 源码路径。
- 内置 Dreamer `MLP` 默认设备已改为 CPU，删除了训练专用 TensorBoard logger；checkpoint 默认从项目内 `models/` 读取。

## 2026-08-31 WMP 场景基础修正

- 用户已将 WMP checkpoint 放入当前项目 `models/go2wwmp/model_1750.pt`；由于 `*.pt` 已加入 `.gitignore`，旧的 Git 跟踪权重应从索引移除但保留本地文件，避免破坏现有 go2w/go2wcr 离线运行。
- D435i/WMP 相机位置已统一为基座坐标 `[0.34, -0.0375, 0.09]`，包括共享 XML 相机、WMP pipeline 和 go2w 可视化标记。
- [已由 2026-09-04 逐行复审修正] 先前曾把 ROS controller 的 `depth - 0.5` 判作额外偏移；训练环境源码证明该偏移属于 checkpoint 的真实输入语义，当前 controller 已恢复。
- WMP 仿真测试将加入约 10 Hz 的 OpenCV 深度图窗口；窗口显示不参与策略计算，策略仍保持 50 Hz。
- 台阶将加入共享的 `go2w_scene.xml`：沿基座 `+x` 放置，宽度沿 `y` 为 `0.60 m`，每个踏步深度 `0.25 m`、高度差 `0.12 m`，连续五级上升后五级下降；机器人从原点朝台阶前进。

## 2026-08-31 项目迁移盘点

- 当前仓库已由用户提交保存；本轮目标是让项目源码和仿真资源不再依赖 `/home/robot/test_com_ws` 等外部路径。
- Unitree SDK2 Python 源码位于 `/home/robot/test_com_ws/unitree_sdk2_python`，约 3.0 MB；其中包含 `unitree_sdk2py`、架构相关 CRC 本地库和 BSD-3-Clause 许可证。
- 当前 Go2W MuJoCo 资源位于 `/home/robot/test_com_ws/src/descriptions/go2w_description`，约 46 MB；当前入口实际需要 `mjcf/go2w.xml`、`mjcf/go2w_scene.xml` 和 `meshes/*.stl`，而不是 ROS/DAE/URDF 全套资源。
- SDK 源码仍导入 `cyclonedds`，并依赖 Python 解释器、NumPy、OpenCV、PyTorch、MuJoCo 等运行时包；复制 SDK 源码不能替代这些系统/环境依赖。
- 迁移方案：在项目内增加 `third_party/unitree_sdk2_python/` 和 `assets/go2w_description/`，入口默认路径基于项目根目录解析；仿真/离线模式不初始化 DDS，实机模式仍需用户审查网络接口后执行。

## 2026-09-04 Go2WWMP 深度链路复审（已完成）

- simtosim MuJoCo 发布端 `go2w_mujoco.py` 的原始路径是：`Renderer.render()` → clip 到 `[0, 2] m` → 除以 `2` → 以 `32FC1` 发布，因此 ROS 消息中的数值语义为 `[0, 1]` 的 2 m 归一化深度。
- simtosim 旧 `ControllerGo2wWMP.CallbackDepth()` 随后执行 `depth - 0.5`，把消息变为 `[-0.5, 0.5]`；训练环境源码确认该行为是 checkpoint 所需语义。
- 修复前的 `render_depth()` 会把 NaN/+Inf 当作 2 m、-Inf 当作 0 m，再裁剪归一化；controller 则要求输入已经是有限的 `[0,1]`。修复后 renderer 只返回米制深度，controller 把所有非有限值按远平面处理并统一生成训练输入，且已有独立回归测试。
- 训练环境 `Go2wWMP.normalize_depth_image()` 明确执行 `(depth_m / 2) - 0.5`，所以 world-model 收到的是 `[-0.5, 0.5]`，而不是 `[0,1]`。Dreamer `ConvEncoder.forward()` 还会再执行 `obs -= 0.5`；无论这项网络内部设计是否理想，部署必须匹配训练 checkpoint 的真实输入分布。
- 因而 simtosim 旧 ROS controller 的 `depth - 0.5` 与训练数据一致；当前 sim2real controller/pipeline 省略该中心化是确定的输入分布偏移 bug。修复应建立清晰的单一边界：pipeline 产生米制深度，controller 负责按训练配置做裁剪和中心化，避免调用方把“已归一化”误当“网络输入”。
- 训练相机是 64×64、水平 FOV 58°，安装 pitch 在 `[-10°, 0°]` 随机化；当前 MuJoCo 方形相机 `fovy=58°`，因此水平 FOV 也为 58°，固定 -5° 位于训练范围中。
- RSSM `obs_step()` 在首帧会在 `prev_state is None` 时把 prev_action 强制置零，因此当前首帧传入的 80 维零动作不会改变初始化行为。
- 修复前 controller 只在 `counter % 5 == 0` 时向 `wm_action_history` 写入一次 `last_action`，第二次更新实际给出 `[0,0,0,0,a4]`；现已改为每个 policy step 记录动作，RSSM 收到 `[a0,a1,a2,a3,a4]`。
- 训练观测对 yaw command 使用 `commands_scale[2] = obs_scales.ang_vel = 0.25`；修复前 WMP controller 与 simtosim 旧 ROS controller 均遗漏，当前移植层已按训练分布补齐。
- 训练环境在策略前把观测裁剪到 `[-100,100]`；当前 controller 已增加完整 prop 的 finite 检查和同范围裁剪，阻止 NaN/Inf 或异常速度污染策略状态。
- 训练 runner/playback 的策略历史初始化为全零，再只插入当前一帧观测；修复前 WMP `reset()` 把全部 5 帧 gravity 预填成 `-1`，当前已恢复“4 帧零 + 1 帧当前观测”的训练语义，未改动 go2w/go2wcr controller。
- 当前项目场景可在 `MUJOCO_GL=egl` 下无窗口渲染真实 depth buffer；站立姿态得到 64×64 float32 米制深度，范围约 `0.634–40.001 m`。上方无命中/远景接近 40 m、下方地面约 0.824 m，说明 Renderer 输出是米制距离且图像上下方向符合“上方远、下方近”；送入网络前必须裁剪到 2 m。
- XML 相机在站立姿态下的基座局部光轴实测为约 `[0.9962, 0, -0.0872]`，即沿 `+x` 向下 5°；位置 `[0.34,-0.0375,0.09]`、方形画面的 `fovy=58°` 均与当前训练配置一致。
- 修复后的真实 checkpoint + EGL 集成闭环已运行 6 个 50 Hz policy 帧，分别在第 1、6 帧渲染/更新深度；相机检查、world model、Actor、MotorCommand 回写和 MuJoCo 物理步均成功，状态保持有限。
- 训练 `depth_buffer` 长度为 2，更新后通过 `[:, -2]` 选择上一张图；除首次初始化两张相同图外，world model 实际消费约 100 ms 前的 10 Hz 深度。当前 controller 已显式保留上一张预处理深度以复现该延迟。
- 训练环境在执行物理前把 Actor action 裁剪到 `[-100,100]`；当前 controller 也在写入 RSSM 动作历史和转换 MotorCommand 前应用相同裁剪。
- 原 `--check-only` 用 Ctrl 顺序的初始关节数组直接构造了声明为 DDS 顺序的 `RobotState`，导致 controller 再映射后得到错误站姿；现已先用 `DDS_IDX_FROM_CTRL` 转换，离线单步与真实 driver 接口一致。
- Dreamer `ConvEncoder.forward()` 会执行原地 `obs -= 0.5`，而 `torch.as_tensor(numpy_array)` 共享底层内存。增加延迟缓存时若直接返回缓存数组，缓存会被修改并在下一次再减 0.5；当前 `_select_delayed_depth()` 对保存值和返回值都显式复制，避免重复中心化。
- 工作区当前 WMP 默认 checkpoint 已切换为 `model_6000.pt`，本地另有 1750/3500/5500；保留该默认选择并同步 README/guide，100 帧集成验证使用 6000 严格加载通过。
- `model_6000.pt` 在 `vx=0.6 m/s` 下完成 300 个 policy 帧（6 s 仿真）的 EGL 闭环，最终 base 约为 `[4.268, 0.227, 0.396] m`。机器人从 x=0 越过了场景楼梯所在的 x=0.8–3.3 m 区域，过程中 60 次深度更新、策略动作和 MuJoCo 状态均保持有限；实际姿态细节仍需 viewer 人工观察。
