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
- simtosim ROS 控制器的额外 `depth - 0.5` 仅作为历史 bug 记录，不再进入当前 controller 或测试参数；WMP 始终采用训练语义深度 `[0,1]`，由 encoder 内部减 `0.5`。
- WMP 仿真测试将加入约 10 Hz 的 OpenCV 深度图窗口；窗口显示不参与策略计算，策略仍保持 50 Hz。
- 台阶将加入共享的 `go2w_scene.xml`：沿基座 `+x` 放置，宽度沿 `y` 为 `0.60 m`，每个踏步深度 `0.25 m`、高度差 `0.12 m`，连续五级上升后五级下降；机器人从原点朝台阶前进。

## 2026-08-31 项目迁移盘点

- 当前仓库已由用户提交保存；本轮目标是让项目源码和仿真资源不再依赖 `/home/robot/test_com_ws` 等外部路径。
- Unitree SDK2 Python 源码位于 `/home/robot/test_com_ws/unitree_sdk2_python`，约 3.0 MB；其中包含 `unitree_sdk2py`、架构相关 CRC 本地库和 BSD-3-Clause 许可证。
- 当前 Go2W MuJoCo 资源位于 `/home/robot/test_com_ws/src/descriptions/go2w_description`，约 46 MB；当前入口实际需要 `mjcf/go2w.xml`、`mjcf/go2w_scene.xml` 和 `meshes/*.stl`，而不是 ROS/DAE/URDF 全套资源。
- SDK 源码仍导入 `cyclonedds`，并依赖 Python 解释器、NumPy、OpenCV、PyTorch、MuJoCo 等运行时包；复制 SDK 源码不能替代这些系统/环境依赖。
- 迁移方案：在项目内增加 `third_party/unitree_sdk2_python/` 和 `assets/go2w_description/`，入口默认路径基于项目根目录解析；仿真/离线模式不初始化 DDS，实机模式仍需用户审查网络接口后执行。

## 2026-09-03 Orin NX 环境结论

- 当前系统的正确项目基座是 `/usr/bin/python3.8`；Python 3.9 会误用为 3.8 编译的系统
  NumPy 路径且缺少 `cv2`，Python 2.7 则是裸 `python` 的旧默认值。
- `.venv` 激活本身没有推理开销。CPU 推理性能由 PyTorch/BLAS 构建、线程数、CPU 频率、
  25W 功耗和网络结构决定，不由 Conda 与 venv 的选择决定。
- PyPI 提供可用的 CPython 3.8/aarch64 wheel：PyTorch 2.0.0 和 MuJoCo 3.2.3；当前
  PyTorch 明确为 CPU-only，`torch.cuda.is_available()` 为 false。
- 系统 MuJoCo/OpenCV 与 PyTorch wheel 使用不同的 `libgomp`；后加载 PyTorch 会触发
  static TLS 错误。仿真入口固定先导入 PyTorch，避免用全局双 `libgomp` 预加载污染进程。
- 宇树 SDK 固定 CycloneDDS 0.10.2。系统 ROS Foxy 同时带有 CycloneDDS 0.7，若保留
  `/opt/ros/foxy` 的 `LD_LIBRARY_PATH`，0.10.2 `idlc` 会出现未定义符号；清除 ROS 路径后
  同一源码和对象文件链接成功。
- 当前仓库没有 ONNX 模型或 PyTorch→ONNX 等价性验证，故不把 ONNX Runtime 加入基础环境。
  应先复制 `.pt`、测量 50 Hz 单步延迟与抖动，再判断是否转换。

## 2026-09-03 Orin DDS driver 结论

- Orin 的 `eth0` 可直接发现机器人 LowState publisher；迁移不改变 DDS topic、Domain ID 或
  消息类型，主要变化是网络接口和策略进程所在主机。
- 实测 LowState Tick 约为 1 kHz，关节和 IMU 数据稳定；driver 只读阶段通过。
- SDK `LowState.power_v`/`power_a` 表示电压/电流。项目此前将 `power_v` 保存为
  `battery_soc` 并打印百分号，语义错误但未进入策略观测；已修正字段名和输出。

## 2026-09-03 Orin policy 延时结论

- 50 Hz 对应 20 ms 单帧预算；只看平均吞吐会掩盖周期性超时，因此同时记录 P99、最大值
  和 deadline miss 数量。
- go2w/go2wcr 在单线程完整 policy pipeline 中分别达到 P99 `1.911/3.967 ms`，2000 帧
  均无超时。相比 2/4/8 线程，单线程已有充足余量且更少争用 CPU。
- WMP actor-only P99 为 `2.832 ms`，但四线程 world-model 更新帧平均 `31.009 ms`；
  其总体平均吞吐虽超过 50 Hz，仍不满足每 20 ms 产生新动作的当前同步实现。
- 不能通过降低 world-model 更新频率直接掩盖问题，因为这会改变训练/部署语义。ONNX、
  TorchScript、量化或异步更新均需单独做数值等价性与时序验证后才能采用。

## 2026-09-03 Xbox 输入结论

- Orin 当前接收器不是 USB VID/PID 意义上的 Microsoft Xbox 设备，而是 `BEITONG A1T2 BFM
  DONGLE`（`20bc:504d`）；应以 udev 稳定名称识别，不把 `js0` 编号写死为硬件身份。
- 当前 Linux joystick 节点报告 8 轴/16 按键；现有 `XboxCommandSource` 的默认接口
  `axis_indices=(1,0,3)`、A=button 0、Back=button 6 仍需通过实际按键事件确认，不能仅凭
  接收器名称推断。
- 离线输入程序只读取 joystick API，不导入 DDS；未使能时返回零速度，速度进入 policy 前仍
  按 `CTRL.COMMAND_LIMITS` 裁剪。

## 2026-09-03 Real-test 审查结论

- real test 进程只导入 Unitree SDK/CycloneDDS、NumPy 和 CPU policy；不导入 ROS、MuJoCo 或
  WMP，当前 OpenMP 隔离不会与实机路径叠加冲突。
- `setup.sh robot` 固定 `eth0`、Domain 0、`rt/lowstate`/`rt/lowcmd` 和 500 Hz；这些参数
  与前面的 Orin DDS 只读验证一致，无需为本地运行增加笔记本网络分支。
- `DdsDriver.initialize()` 只创建 LowState subscriber 和 LowCmd publisher，不写 LowCmd；
  `1` 执行一次 StandUp，`2` 执行 ReleaseMode，成功后才发送固定站姿首帧。
- 固定站姿首帧、模型加载期间的零阶保持和 Ctrl+C/Back 后的紧急阻尼路径均保留。新增的
  command shape/NaN 检查只拒绝坏数据，不改变合法网络输出。

## 2026-09-03 Sport Mode 恢复结论

- `ReleaseMode()` 后 `CheckMode()` 返回空模式，直接调用 `SportClient.StandUp()` 不足以
  恢复 Go2W 的高层运动服务。
- 宇树官方 SDK2 MotionSwitcher 示例将轮式机器人模式写为 `ai-w`；官方 Go2W 示例将其
  映射为 `wheeled_sport(go2W)`。恢复操作应使用 `SelectMode("ai-w")`，再调用 `StandUp()`。
- 已将模式恢复拆为 `scripts/real/select_wheeled_sport.py`；`DdsDriver.stand_up()` 保持单一
  `SportClient.StandUp()` 调用，便于分别验证模式切换和站立请求。

## 2026-09-03 Orin 机载控制异常排查

- `test_policy_real.py --log <path>` 记录每个策略周期的 LowState、命令速度、推理耗时和
  实际发送的 MotorCommand；不指定参数时运行路径不变。
- 官方 SDK2 低层示例使用 2 ms（500 Hz）周期发布 `rt/lowcmd`，所以必须同时检查
  policy 50 Hz 周期和 LowCmd 500 Hz 发布线程，而不能只看平均推理耗时。
- 当前优先排查 CPU 调度抖动、DDS 上的其他 LowCmd 发布者、ReleaseMode 后接管时序，
  以及状态/动作顺序或单位不一致。日志中的 `state_tick`、`loop_dt_ms` 和输出 `p/v`
  可先区分这些类别。

## 2026-09-03 分层频率结果

- 纯 go2w policy：500 帧平均约 1.76 ms，无一帧超过 10 ms。
- 实机 print-only：约 35.1 Hz，`loop_dt_ms` 平均 22.2 ms；说明即使不发送 policy
  action，LowCmd 线程或 DDS/CPU 调度也会造成额外竞争。
- 实机完整 policy：约 32.3 Hz，`loop_dt_ms` 平均 25.7 ms；相比 print-only 进一步
  变慢，说明发送路径和完整动作处理仍有额外开销。
- 这不是“多线程必然失败”，而是 Python policy、500 Hz DDS 回调和系统调度共享 CPU
  时产生抖动；下一步应测量线程 CPU 占用并隔离 policy 与 LowCmd 的核/进程。

## 2026-09-03 双进程联合验证

- 4.8 `print-only` 联合测试在模型加载后稳定约 49.1–49.4 Hz，policy 推理约 2.1–2.3 ms。
- 去掉 `--print-only` 后曾短暂观察到较好表现；用户后来判断这可能只是假象，不能作为
  Orin 双进程链路已经稳定或进程隔离已经解决问题的证据。
- 4.7 只用总写入次数得到约 500 Hz，没有记录逐次间隔、漏周期或 Write 耗时。当前参数为
  policy CPU2、LowCmd CPU1、PyTorch 1 thread、policy 50 Hz，但隔离完整性仍未验证。

## 2026-09-04 policy_mp.csv 抖动分析

- 1765 个记录周期约 35.64 秒；活跃阶段约 49.45 Hz，循环耗时平均 4.66 ms，policy
  推理 P50/P95/P99 分别约 2.33/2.59/2.83 ms，最大 3.65 ms。
- LowState tick 没有重复或倒退，绝大多数相邻 policy 帧的 tick 增量为 20；未发现足以
  解释持续抖动的状态断流或计算超时。
- 预热固定姿态时，腿部目标相邻帧平均变化约 0.001–0.004 rad；实际闭环接管且速度命令
  为零时，部分关节平均变化约 0.10–0.13 rad，单帧最大变化约 0.35–0.48 rad。
- 结论：当前证据排除“Orin 算力不足”和明显 DDS 状态丢失；抖动是 policy 接管后形成的
  闭环振荡。下一步应比较笔记本/Orin 的模型哈希、PyTorch 版本和完全相同 observation
  的 action，并补充 IMU、原始 action、状态接收时刻及命令提交时刻日志。
- 当前 Orin 模型 SHA-256：
  `5105a856191fd19f7ee0755b8839f3f5a245b4b6040778351c604b037dba0ebf`；运行环境为
  aarch64、PyTorch 2.0.0、NumPy 1.24.4。

## 2026-09-04 笔记本同 observation 精度复放

- 笔记本 `model_700.pt` SHA-256 与 Orin 完全相同，先排除了权重文件传输或版本错误。
- 笔记本 x86_64、PyTorch 2.3.1、NumPy 1.19.5、单线程复放 1874 个 active 帧：
  `mean_abs=9.3988e-08`、`rmse=1.4081e-07`、`max_abs=1.6689e-06`。换算到腿关节目标
  不超过 `4.18e-07 rad`，换算到轮速不超过 `1.67e-05 rad/s`，不可能解释剧烈抖动；
  改用历史默认 16 线程复放后统计完全相同。
- 使用主日志状态、命令和上一帧 action 重建 2024 帧 observation，与 policy 子进程保存
  的 265 维输入逐元素完全相同（最大误差 `0`）。Pipe 没有损坏字段、关节顺序或历史；
  尚未排除的是跨进程往返尾延时和动作提交时刻，而不是消息内容精度。
- 旧日志 150 个 warmup 帧的 action 被 `last_action.zero_()` 通过共享 Torch/NumPy 内存
  一并清零，造成 `max_abs=0.862` 的假误差；active 帧不走该清零分支，因此不受影响。
  控制器现已返回 action 副本，后续 warmup 日志将保留真实网络输出。
- `policy_fixed_2.csv` active 段平均 49.27 Hz；推理 P99 3.253 ms、IPC P99 12.515 ms、
  action 生成时状态年龄 P99 14.137 ms；无重复/倒退 tick。action 到日志 MotorCommand
  的最大映射误差约 `2e-06`。
- 同一段相邻 raw action 的最大变化为 `2.007`，相邻腿关节目标最大变化约 `0.502 rad`；
  日志确认了闭环振荡本身，但没有证明触发源。下一步实机消融应先运行笔记本单进程
  基线，再依次改变 PyTorch 线程数和进程架构。

## 2026-09-04 笔记本稳定单进程实机日志（初检）

- `policy_laptop_single.csv` 与 `_observation.csv` 均为 936 个数据帧加表头，时间约
  18.79 秒；所有行 `warmup=0`、命令速度为零，与 Orin active 零速阶段可比较。
- 笔记本单进程日志没有 IPC，首帧推理约 2.07 ms，末帧约 0.39 ms；日志字段齐全，
  包含与 Orin 相同的状态、action、MotorCommand 和 265 维 observation。
- 用户现场确认该段控制稳定、无明显抖动且抗扰性强；因此后续数值差异可直接作为
  “稳定闭环”与“剧烈振荡闭环”的对照，而不仅是离线推理对照。
- 去掉每段最初 1 秒后，笔记本/Orin 的策略平均频率分别为 `49.76/49.27 Hz`；平均值
  接近，但笔记本最大周期 `21.99 ms`，Orin 有 51 帧超过 25 ms、23 帧超过 30 ms，
  最大 `67.72 ms`。Orin 的平均/P99 action 状态年龄为 `4.91/14.14 ms`，笔记本仅
  `2.12/3.60 ms`。
- 机械与闭环差异远大于频率均值差：Orin/笔记本的 IMU gyro RMS 为 `0.486/0.022 rad/s`，
  腿关节速度 RMS 为 `1.000/0.061 rad/s`，相邻 action 平均绝对变化为 `0.128/0.011`，
  相邻腿目标平均变化为 `0.0371/0.00327 rad`。
- Orin 的 gyro 三轴和代表性 action 在约 `8.4–8.6 Hz` 有一致主峰，高频能量显著；这是
  已形成的闭环极限环，不是随机单帧噪声。策略周期与 action 最大跳变的相关系数只有
  `0.045`，正常 20 ms 帧中同样存在大动作，因此“策略平均频率不足”不能独自解释抖动。
- Orin 段电池电压平均/最低为 `28.59/26.76 V`，电流平均/最大为 `5.70/52.26 A`；笔记本
  段为 `31.67/31.62 V`、`2.16/4.20 A`。Orin 电压和电流相关系数 `-0.995`，说明巨大
  电流和压降主要随振荡同步出现；但 Orin 启动电压本就低于笔记本，低电量/电压余量仍是
  未控制的实验变量，不能直接归咎于进程通信。
- 当前 CPU 隔离并不完整：只把 policy 子进程固定在 CPU2、LowCmd Python 线程固定在
  CPU1；DDS 接收回调、CycloneDDS 内部线程和主进程未从 CPU2 排除。因此仍可能有资源
  干涉，但现有 policy 日志只能看到 IPC/策略尾延时，尚未测量实际 500 Hz LowCmd Write
  的逐周期抖动，也不能排除第二个 `rt/lowcmd` 发布者。
- 代码对比确认 laptop single 与 Orin dual 同时改变了四项：是否 Pipe、LowCmd CPU1
  亲和性、PyTorch 线程数、warmup/绝对 deadline。因此当前实验只能证明“整套 Orin
  双进程方案”有问题，不能只凭这一对实验把根因锁定为 Pipe。
- Unitree SDK `RecurrentThread` 以 Linux timerfd 驱动 2 ms 循环；当前 driver 只累计
  `write_count`，没有记录每次 `_pub.Write()` 的开始间隔、耗时或 timerfd missed
  expirations。单独的 500 Hz 测试通过不能替代抖动发生时的同场测量。
- Orin 双进程采用同步 `Pipe.send()`/`recv()`，不会积压多帧旧 observation；但主进程会
  阻塞等待 policy，且 DDS/主进程线程仍可能抢占 policy CPU。现有观察更符合“未完全隔离
  的调度尾延时可能触发/加剧一个 8.5 Hz 闭环极限环”，而不是“Pipe 数值传错”。
- Orin 同一份日志不是单一工况：active 前约 15 秒持续振荡，16–24 秒数值较小，之后包含
  人工外推和暴走次生状态。16–24 秒低波动片段不能证明 Orin 双进程/DDS 已形成可重复的
  稳定闭环，当前根因判断不依赖该片段。
- Orin 16–24 秒稳定窗口仍有比笔记本更高的固定 action 年龄（P99 `5.36 ms` vs
  `3.60 ms`），但没有振荡；初始 1–13 秒振荡窗口的 action 年龄 P99 也仅 `8.11 ms`。
  因此额外约 2–5 ms 延迟不是振荡的充分条件，不能把平均 IPC 延迟直接当根因。
- 两端首次 policy 接管也不支持“Orin 第一条动作过猛”：Orin 首帧腿目标最大偏离固定
  站姿 `0.115 rad`，笔记本反而为 `0.206 rad`；笔记本仍快速收敛。
- Orin 34–37 秒再振荡窗口与严重调度尾延时同步：周期最大 `67.72 ms`、IPC 最大
  `34.72 ms`、action 年龄最大 `36.58 ms`。30 ms 以上周期事件有一半恰好发生在每 25
  个 active 帧的大段终端打印之后；Orin 的数组打印和每帧双 CSV flush 是明显干扰源，
  但其余一半尖峰以及初始振荡仍需 LowCmd cadence/CPU/外部扰动证据解释。
- 事件因果方向尚不能由现有日志唯一确定：32.6–33.9 秒先出现数次周期尖峰，约 34 秒
  才进入最大振荡，支持“时序尖峰可能触发”；但用户是否在该处施加扰动未记录，且振荡
  也会带来 52 A 电流、压降和更多系统负载，可能反过来放大时序异常。

### 现场标注修正

- 用户明确说明两份日志中的明显坏状态均包含人工外推，Orin 长周期尾部可能是暴走后的
  通信、电池或其他次生现象；不得用这些尾部数据反推原始根因。
- 后续根因比较只使用两端前半段未外推区间，并在其中选择连续 2–5 秒最佳稳态；不再把
  Orin 后半段的恢复/再振荡解释为系统自然状态切换，也不把尾部 30–68 ms 尖峰作为主证据。
- 在现场标注后的前半段候选区间内，以最低 gyro RMS 选择连续最佳 5 秒：笔记本
  `1.9–6.9 s`，Orin `4.7–9.7 s`。两者策略周期几乎相同：平均 `20.095/20.001 ms`，
  最大 `21.708/22.932 ms`；Orin 该窗口没有长周期尾部。
- 即便只看这两个最佳窗口，Orin/笔记本仍有数量级差异：gyro RMS
  `0.4368/0.0104 rad/s`（约 42 倍）、腿 dq RMS `1.0937/0.0374 rad/s`（约 29 倍）、
  action 元素帧差均值 `0.2648/0.00946`（约 28 倍）、腿目标帧差均值
  `0.07785/0.00275 rad`（约 28 倍）。Orin 约 8.5 Hz 谱峰仍清晰存在。
- 最佳窗口内 DDS 状态在 Orin 反而更新得更鲜：取状态平均年龄 `0.297 ms`，笔记本
  `0.927 ms`；差异发生在后续推理/IPC，action 就绪平均年龄为 `4.279/2.050 ms`。
  Orin 多出的约 `2.23 ms` 主要是较慢推理和进程调度，但周期仍稳定 50 Hz。
- 因此用户要求的“忽略长尾”结论是：记录到的 policy 周期抖动不是前半段巨大振荡的
  直接解释。仍未排除的 DDS 干涉特指未记录的 500 Hz LowCmd Write cadence、CPU1/网卡
  IRQ 竞争或第二发布者，而不是 LowState 新鲜度或 50 Hz policy 周期。
- 本轮不能下结论说“Pipe/DDS 就是根因”：Pipe 内容已逐元素一致，前半段 50 Hz 周期无
  尾延时，且 Orin 取到的 LowState 更新更及时。能够成立的更窄判断是，双进程使
  state→action 平均年龄增加约 `2.23 ms`，可能降低相位裕度；若仍有通信/调度干涉，最
  可疑位置在当前日志完全看不到的 500 Hz LowCmd Write 侧和未完整隔离的系统线程。
- 用户已在笔记本运行当前双进程入口并确认实机仍然稳定，因此“双进程 + 同步 Pipe 架构
  本身”可排除为充分原因。不能排除的是 Orin 较弱实时性下的额外调度延迟及其与 DDS、
  GIL、日志 I/O、CPU/IRQ 布局的组合效应。
- 4.8 在 Orin 上短暂表现较好的历史观察已按用户说明降级，不能用来证明 Orin 链路可靠。
  当前最高优先级是直接测量 500 Hz start interval、CRC/Write 耗时、漏周期/补跑和新
  action 首次下发延迟，而不是继续比较 50 Hz 平均频率。
