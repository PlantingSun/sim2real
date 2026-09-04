# 工作进度记录

## 2026-08-27

- 已读取 `planning-with-files` 技能规范。
- 已建立 `task_plan.md`、`findings.md`、`progress.md`。
- 已完成项目根目录文件的初步清单盘点。
- 已完整阅读当前仓库的 Python、Markdown、shell 入口和相关 simtosim CRRL 源码。
- 已用 `unitree_py38` 环境检查两个 checkpoint：go2w 为 265→16，go2wcr 为 285→16；CRRL critic 输入为 123。
- Phase 1–2 已完成，已确认接口方案和不改动 `driver/` 的边界。
- 已新增 `config.CRRL`、`policy/controller_go2wcr.py` 和 `scripts/test_policy_go2wcr_offline.py`。
- 首次离线运行暴露 normalizer batch 维问题，已修正为显式 `squeeze(0)`，离线测试已重跑通过。
- 已新增 `scripts/test_mujoco_pipeline_go2wcr.py` 和 `scripts/test_policy_go2wcr_real.py`，CRRL policy/simulation/real 入口均已通过 Python 语法编译。
- 回归发现并修正现有 `scripts/test_command_input.py` 的过时线速度断言。
- 已完成 CRRL 原装遥控器入口；通用 `scripts/real/test_policy_unitree_remote.py` 支持 `--policy go2wcr`，并保留独立 CRRL 转发入口。
- 已完成 `scripts/` 四类归档、根目录兼容转发和 `guide/06`–`guide/09` 分步文档。
- 已通过：CRRL 离线模型测试、原有命令输入回归、全仓 Python 语法编译、所有新入口 `--help`、MuJoCo 场景加载和 headless 100 步闭环。
- 未执行：任何 DDS 初始化、LowCmd、Sport Mode 或真实机器人动作。
- 本阶段已完成；后续仅需在真实硬件和吊架保护具备时按 `guide/08_crrl_real_test.md` 记录实测结果。

## 2026-08-29

- 修复 go2wcr MuJoCo 测试中的 MotorCommand 解包错误和重复动作转换。
- 两个 MuJoCo 测试入口改为恢复 XML `stand` keyframe，base 初始高度从默认 `0.55 m` 调整为期望的 `0.43 m`。
- 已验证两个初始姿态 helper、CRRL MotorCommand 打印和无 viewer 单步闭环；未启动 viewer 或真实机器人。
- 删除 `scripts/` 根目录下重复的启动转发脚本，仅保留 `policy/`、`simulation/`、`input/`、`real/` 四个分类目录中的实际入口。
- 更新 `scripts/README.md` 和 `guide/09_scripts_layout.md`，明确要求直接调用分类目录路径，不再使用旧的根目录脚本路径。
- 按测试要求将 go2w 和 go2wcr 的 5 帧历史初始化改为初始站立零运动状态：投影重力为 `(0, 0, -1)`，其余观测量为 0；同步更新 CRRL 离线测试标题和相关说明。

## 2026-08-30

- 完整复核 README、guide/00–09、仿真入口和 MuJoCo driver，确认本次只做仿真显示，不进入实机流程。
- 历史上曾在 `test_mujoco_pipeline.py` 使用 viewer user geom 绘制 D435i；本轮已改为直接写入共享 `test_com_ws` 的 `go2w.xml`。
- 已完成 XML 中 D435i geom 的位置、尺寸和方向检查；实际 viewer 创建因当前环境 GLFW 无法初始化而受限。
- 无窗口验证已通过：标记在基座原方向和旋转后均正确跟随，且未增加物理 geom；实际 viewer 因当前环境 GLFW 无法初始化而未能弹窗，已记录为环境限制。
- Phase 9 完成；未执行任何 DDS 初始化、LowCmd、Sport Mode 或真实机器人动作。

## 2026-08-30 调研补充

- 查阅 RealSense 官方 D435i 页面、Projection 文档、D400 数据表、立体深度原理和 D435/T265 坐标说明。
- 确认官方定义：未对齐的深度流以左 IR 成像器中心为深度坐标原点；对齐到 RGB 后参考坐标才变为 RGB 成像器。
- 核对 `/home/robot/simtosim` 的 Go2W MuJoCo 深度发布和 WMP/WMPCR 回调，确认当前链路使用 raw depth，不做 RGB 对齐。
- 检索 Unitree 官方 Go2 仓库、公开 Go2W 传感器描述和其他 Go2W URDF；未找到与本机安装方式匹配的公开精确外参。`y=-0.022 m` 暂定为合理假设，尚不能标记为已验证。
- 补充确认官方机械基准：D435/D435i 左成像器中心是 depth origin X-Y；从底部 `1/4-20` 安装孔中心线到左成像器中心为 `17.5 mm`。该尺寸仍不能替代 Go2W 基座到安装孔的实测。
- Phase 10 历史记录：仿真曾使用 `y=-0.022 m` 作为临时标记；用户随后将最终实验位置确定为 `[0.34, -0.0375, 0.09]`，当前代码已统一。
- 根据用户确认的基座坐标约定修正相机朝向：长方体前表面改为朝 `+x`，宽度沿 `+y`；红色镜头圆柱轴线保持 `+x`。

## 2026-08-31 D435i 实机读取阶段

- 确认笔记本有 ROS2 Humble 基础环境，但没有 `rqt_image_view` 或 `rviz2`；因此暂不假设笔记本可以直接显示 ROS 图像。
- 新增 `guide/10_realsense_network_view.md`，记录 Orin NX 采集、ROS2 DDS 跨网传输、笔记本只读显示和逐项通过标准。
- 更新 README 增加相机读取指南入口；本阶段仍等待 Orin NX 端的实际驱动、话题和网络发现输出，未启动任何机器人控制。

## 2026-08-31 D435i 实机读取阶段

- 确认笔记本有 ROS2 Humble，但当前 sim2real 项目不依赖 ROS/ROS2；simtosim 相机代码为 ROS1 仿真接口，不能直接作为实机网络读取方案。
- 暂定第一条安全链路为：Orin NX 上 RealSense 驱动发布图像，笔记本通过 ROS2 DDS 只读订阅并显示；不启动 DDS 控制、LowCmd、Sport Mode 或 WMP policy。
- 待从 Orin NX 获取实际发行版、驱动、话题和 DDS 网络配置后，再决定是否新增笔记本端显示脚本和分步 guide。

## 2026-08-31 Orin NX 入门任务

- 新建 `orin_nx_onboarding/`，建立从第一次接触到 D435i 使用的独立学习路径。
- 新增第一次进入、网络与文件传输、图形化访问、系统特性四份文档；明确显示器/键鼠、SSH、串口、SCP/rsync、ROS2 DDS 和视频网络的边界。
- 明确 NVIDIA AGX Orin Developer Kit 的接口资料不能直接替代宇树 Go2W 载板资料；当前不假设默认 IP、用户名、视频接口或 USB gadget 地址。
- 本阶段只准备现场只读检查，不刷写系统、不改功耗、不启动相机或机器人控制；等待用户提供实际载板连接条件后继续。
- 根据宇树 Go2-W 用户手册修正连接判断：扩展坞的 USB3.2 Type-C 用于深度相机，全功能 Type-C 用于显示器，USB-A 用于用户扩展；两个 RJ45 分别连接 Go2-W 本体和用户设备。由于用户现场报告的 Type-C 数量可能与手册图示不完全一致，后续以端口标识为准。

## 2026-08-31 Orin NX 现场验证

- 用户已验证两种进入方式：全功能 Type-C 转 HDMI 外接显示器，以及用户扩展 RJ45 的 SSH。
- 已确认 Orin 身份为 `unitree@ubuntu`，系统为 Ubuntu 20.04.5 LTS，主有线网卡 `eth0` 地址为 `192.168.123.18/24`。
- 已确认 Orin USB 3 总线识别 D435i（USB ID `8086:0b3a`），同时识别键盘和 USB Hub；相机确实连接在 Orin 上。
- 已确认当前 SSH 使用 `eth0`，`usb0`/`rndis0` 未启用；没有使用 USB 虚拟网卡。
- 凭据密码不写入项目文件。下一步在 Orin 上先做软件包/JetPack/RealSense 工具的只读盘点，再尝试独立读取相机。

## 2026-08-31 Orin NX 现场档案

- 用户已验证全功能 Type-C 转 HDMI 外接显示器进入 Ubuntu，以及用户扩展 RJ45 的 SSH 进入。
- 设备事实为 `unitree@ubuntu`、Ubuntu 20.04.5 LTS、`eth0=192.168.123.18/24`；`usb0`/`rndis0` 未启用。
- `lsusb` 已识别 Intel RealSense D435i（`8086:0b3a`），并识别键盘和 USB Hub。
- 新增 `orin_nx_onboarding/05_verified_device_profile.md` 保存上述现场档案；密码不保存。
- 用户准备配置天线和联网；下一步先读取 `ip route`、DNS、存储和内存等只读信息，确认联网不会破坏 Go2W 内部通信。
- 新增 `orin_nx_onboarding/06_networking_safely.md`，明确联网前保留 `eth0=192.168.123.18/24`、先记录路由/DNS、优先使用独立 Wi-Fi/4G、暂不刷写或大规模升级。
- 修正 D435i 网络读取指南：Orin 已知为 Ubuntu 20.04，不能直接假定 ROS2 Humble；先查看 `/opt/ros` 和 `$ROS_DISTRO`，再使用对应环境脚本。

### Go2W WMP MuJoCo pipeline

- 已完整核对 simtosim 的 WMP 控制器、网络结构、world-model 配置、Isaac Gym 训练环境、播放入口和 ROS1 主循环的职责边界。
- 已确认 WMP checkpoint 已复制到当前项目 `models/go2wwmp/model_1750.pt`，约 303.2 MiB，包含 `model_state_dict`、`world_model_dict` 以及训练恢复用的优化器/深度预测器状态；该权重被 `.gitignore` 忽略。
- 已发现需要在移植测试中明确区分“训练时深度归一化”和 simtosim ROS 控制器当前的 `depth - 0.5` 处理：训练环境输出 `[0, 1]`，world-model 的卷积编码器内部再减 `0.5`；若控制器先减一次再送入 encoder，会形成额外偏移。这是 pipeline 审查重点，不能无提示地掩盖。
- 第一次移植检查暴露并修正两个 simtosim→CPU 兼容问题：内部 `MLP` 默认 device 为 `cuda`，以及 PyYAML 将 `1e-4` 解析为字符串；适配层已分别强制 CPU 默认和递归转换数值字符串。
- 已新增 `policy/controller_go2wwmp.py` 与 `scripts/simulation/test_mujoco_pipeline_go2wwmp.py`；checkpoint 严格加载、无窗口单步和 6 周期推理均通过。
- 已确认 WMP 的默认训练深度语义为 `[0,1]`，world-model encoder 内部再减 `0.5`；复现 simtosim ROS 额外减法时，第二次 world-model 更新后的动作与训练模式最大差异约 `0.057`。
- 当前 MuJoCo Viewer/Renderer 仍受本机 `DISPLAY=:1` 无法打开和 OpenGL context 不可用限制，未宣称实际窗口闭环通过；代码路径待在有图形桌面的 Orin/笔记本上运行验证。
- 已完成 Orin 入门文档精简：本地显示器/键鼠为主线，SSH/文件传输和联网安全保留为备用；没有删除现场设备档案。
- 已通过 `git diff --check`、新入口 Python 编译检查和 `--help` 检查；没有执行任何 DDS、LowCmd、Sport Mode 或真实机器人操作。

### WMP 推理依赖内置

- 按用户要求，已将 Actor、Dreamer `models/networks/tools`、Dreamer 包入口和 WMP YAML 配置直接拷贝到当前项目。
- 删除 `import tensorboard`、TensorBoard 日志类、外部 `lib` 导入、运行时 `simtosim_root` 参数和 CPU monkey patch；Dreamer MLP 的默认 device 改为 CPU。
- 重新通过新文件编译、入口 `--help` 和 `--check-only` checkpoint 单步验证；checkpoint、网络源码和配置均从当前项目读取。

### 2026-08-31 WMP 基础修正

- WMP 默认 checkpoint 已改为当前项目 `models/go2wwmp/model_1750.pt`；旧 `go2w`/`go2wcr` 权重从 Git 索引移除但保留在本地，便于既有离线测试继续使用。
- 共享 `go2w.xml`、WMP pipeline 和 go2w D435i viewer 标记统一使用基座坐标 `[0.34, -0.0375, 0.09]`。
- 删除旧 ROS 深度偏移入口；WMP 固定接收训练语义的 `[0, 1]` 深度图。MuJoCo pipeline 增加 OpenCV 黑白灰度深度窗口，按 50 Hz 策略的每五帧约 10 Hz 更新。
- 共享 `go2w_scene.xml` 增加沿 `+x` 的 5 级上行/5 级下行楼梯，每级高 `0.12 m`、深 `0.25 m`、宽 `0.60 m`；最后一级与地面齐平，避免重叠碰撞体。
- 已通过本地 checkpoint `--check-only`、Python 编译、OpenCV 导入和 MuJoCo XML 加载检查；实际 viewer 仍需在有图形桌面的机器上由用户观察。
- 已将共享 XML 中 `depth_camera` 的光轴调整为沿 `+x` 向下 5°；位置保持 `[0.34, -0.0375, 0.09]`，并通过 MuJoCo 相机矩阵检查俯角为 `5.0°`。

### 2026-08-31 项目迁移整理

- 新增 `third_party/unitree_sdk2_python/`，内置 Unitree SDK2 Python 源码、IDL、Go2W 接口和 x86_64/aarch64 CRC 本地库；保留原 BSD-3-Clause 许可证。
- 新增 `assets/go2w_description/`，内置当前 MuJoCo 所需 `go2w.xml`、`go2w_scene.xml`、楼梯场景文件和 9 个 STL 网格；XML 的 mesh 引用全部使用项目内相对路径。
- 新增 `config/paths.py`，统一项目根目录、场景和 checkpoint 路径；仿真、离线和实机入口的默认模型/场景路径已改为项目内路径。
- `setup.sh` 现在从脚本位置识别项目根目录，并优先把项目内 SDK 加入 `PYTHONPATH`；没有固定依赖 `/home/robot/sim2real_ws` 或外部 SDK 工作空间。
- 移除 VS Code 设置中的固定 Conda 解释器路径，迁移到其他设备后由用户选择目标设备的 Python 环境。
- 已在 `/tmp` 作为当前目录时通过本地 SDK/CRC 导入、MuJoCo 场景加载、go2w 离线策略、go2wcr 离线策略、WMP `--check-only` 和 `setup.sh robot` 检查；全程未初始化 DDS 或发送机器人指令。
- 项目文件自包含不等于运行环境自包含：目标设备仍需准备匹配架构的 Python、CycloneDDS、NumPy、PyTorch、OpenCV 和 MuJoCo；`.pt` 权重按既有规则另行复制。

## 2026-09-03 Orin NX 环境配置

- 只读确认当前设备为 aarch64 Ubuntu 20.04.5、L4T R35.3.1、8 核/16 GiB、25W mode 3。
- 确认 `python` 指向 2.7；Python 3.9 无法加载系统 NumPy/OpenCV；项目固定使用系统
  Python 3.8.10 派生的 `.venv`，不安装 Conda。
- 在 `.venv` 中安装 NumPy 1.24.4、CPU-only PyTorch 2.0.0、MuJoCo 3.2.3 和
  CycloneDDS Python 0.10.2；CycloneDDS C 0.10.2 同样安装在 `.venv`。
- 构建时发现系统全局 ROS Foxy 的 `LD_LIBRARY_PATH` 会让 0.10.2 `idlc` 链接到 ROS 的
  CycloneDDS 0.7；清除 ROS 环境变量后构建通过，已将该隔离写入 `setup.sh`。
- MuJoCo/OpenCV 与 ARM64 CPU PyTorch 使用不同 `libgomp`；仿真入口已固定先导入
  PyTorch，且移除 `setup.sh`、VS Code 的全局双库 `LD_PRELOAD`。
- 新增 `requirements/orin.lock`、Orin 环境安装/验证脚本、`.vscode` 配置和
  `guide/12_orin_environment.md`；默认实机网口收敛为 `eth0`。
- 三个 checkpoint 已由用户复制到 controller 要求的精确路径；policy 执行性仍按下一阶段
  顺序单独验证。本环境阶段没有初始化 DDS 或执行任何机器人控制。

## 2026-09-03 Orin DDS driver

- 记录三个目标 checkpoint 的文件大小和 SHA-256，环境验证确认路径全部到位。
- `eth0` 为 `UP / 192.168.123.18/24`；Orin 上的 CycloneDDS 成功订阅 LowState。
- Tick 约每 0.5 秒增加 500，16 个关节和 IMU 数据连续有效，Ctrl+C 正常关闭。
- 测试未启动 LowCmd 线程、未调用 `Write()`，没有发送任何电机指令。
- 修正 `power_v` 被误标成电池 SOC 的问题，状态层现保留电压与电流的真实含义。
- driver 阶段通过；下一步为完全离线的 policy 正确性和 CPU 时延验证。

## 2026-09-03 Orin policy 与延时

- go2w、go2wcr、go2wwmp 的 checkpoint 加载、输入输出和 MotorCommand 离线检查通过。
- 为 go2w 推理补充 `torch.no_grad()`；动作数值回归不变，不再构建无用 autograd 图。
- 新增统一 CPU 基准，测量观测构建、网络推理和 MotorCommand 转换的完整单帧。
- 25W mode 3、单线程长测 2000 帧：go2w P99 `1.911 ms`，go2wcr P99
  `3.967 ms`，均为零 20 ms deadline miss。
- WMP 四线程 500 帧平均 `8.175 ms`，但每五帧的 world-model 更新平均 `31.009 ms`；
  100/100 个更新帧超时，所以 WMP 尚未满足逐帧 50 Hz。
- `setup.sh` 和 VS Code 默认固定 `OMP_NUM_THREADS=1`，为 go2w/go2wcr 保留 DDS 调度余量。

## 2026-09-03 Xbox command input

- Orin USB/udev 识别到 `BEITONG A1T2 BFM DONGLE`（VID/PID `20bc:504d`），对应
  `/dev/input/js0`，稳定路径为 `/dev/input/by-id/usb-BEITONG_BEITONG_A1T2_BFM_DONGLE-joystick`。
- 设备报告 8 个轴、16 个按键，当前用户有权限读取；默认 joystick 参数已改为稳定 by-id 路径。
- `scripts/input/test_command_input.py` 通过；真实离线监视器能够打开设备，未按 A 时持续输出零速度。
- 自动监视期间没有采集到用户移动事件；三个轴的实际方向随后由用户现场逐轴确认。
- 本阶段没有初始化 DDS、LowCmd 或 Sport Mode。

## 2026-09-03 Real-test 代码审查

- 按用户已完成的仿真和 Xbox 验证结果，real test 保持三步：只读 LowState、固定站姿
  LowCmd、固定站姿后接收 Xbox policy。
- 保留键盘 `1`（StandUp）和 `2`（ReleaseMode 后接管）确认流程；没有把按键改成自动动作。
- `DdsDriver.send_command()` 增加 16 路形状和 NaN/Inf 检查，异常时进入紧急阻尼；不做
  关节限幅、动作平滑或网络输出修正。
- Xbox 读取时把设备拔出类 `OSError` 转为已有 RuntimeError 退出路径；结束时仍统一进入
  紧急阻尼。
- 未启动 real test；本阶段没有发送 LowCmd 或调用 Sport Mode。

## 2026-09-03 Sport Mode 恢复

- 根据宇树 SDK2 的 Go2W 示例和 MotionSwitcher API，确认 Go2W 运动模式别名为 `ai-w`，
  对应 `wheeled_sport(go2W)`。
- `ai-w` 恢复已拆为 `scripts/real/select_wheeled_sport.py`；`stand_up()` 恢复为原始单一
  `SportClient.StandUp()` 调用，先单独验证模式恢复，再验证站立。
- 未增加关节站立轨迹、动作限幅或自动 LowCmd；恢复失败会停止流程，不发送 LowCmd。
- 代码只完成静态审查和文档更新，未在机器人上调用该恢复流程。

## 2026-09-04 Step 5 双进程迁移

- `test_policy_real.py` 已迁移为 DDS 主进程 + go2w policy 子进程，复用 4.8 验证过的
  `spawn + Pipe` 架构。
- fixed、keyboard、Xbox、阶段按键、print-only、CSV 和退出阻尼路径均保留。
- 子进程报告模型加载完成后，先以真实状态和零速度命令预热 3 秒；预热期间 LowCmd
  保持固定站姿，不发送 policy action。
- policy 默认 CPU 2、单线程、50 Hz；LowCmd 默认 CPU 1、500 Hz。policy 使用绝对
  deadline，超期时不连续补跑旧周期。
- 只完成语法和静态差异检查，未启动 DDS 或执行实机测试。
- 修正预热语义：未发送的预热 action 不再写入 `last_action` 历史。
- 实机 CSV 已扩展为完整状态/时序/action/MotorCommand，并自动生成独立的 265 维
  observation CSV；新增纯离线 `replay_observation_csv.py` 供笔记本逐帧对比。

## 2026-09-04 笔记本基线恢复与精度消融

- 已确认工作区当前位于 Orin 适配提交 `6fbac4e`，而上一版通用/笔记本代码可从 Git 历史读取。
- 本阶段保留 Orin 双进程入口，计划恢复显式宿主机配置与单进程笔记本基线，不做破坏性回退。
- 已定位坏运行日志 `logs/real/policy_fixed_2.csv` 与对应 265 维输入
  `logs/real/policy_fixed_2_observation.csv`；下一步核对字段、模型哈希和逐帧动作误差。
- 在用户重新连接机器人前只做离线复放与静态预检，不初始化 DDS、不发送 LowCmd。
- 笔记本与 Orin 的 `model_700.pt` SHA-256 均为
  `5105a856191fd19f7ee0755b8839f3f5a245b4b6040778351c604b037dba0ebf`。
- x86_64/PyTorch 2.3.1 对 Orin PyTorch 2.0.0 日志逐帧复放：1874 个 active 帧
  `mean_abs=9.3988e-08`、`rmse=1.4081e-07`、`max_abs=1.6689e-06`，通过 `1e-5` 门槛。
  笔记本使用 1 线程和历史默认 16 线程的统计完全相同。
- 从主 CSV 的状态/命令/上一帧 action 重建全部 2024 帧 265 维 observation，与 policy
  子进程日志逐元素完全一致（最大误差 `0`），排除 Pipe 字段损坏、映射或历史顺序错误。
- 识别并修复预热日志的共享内存假误差：`compute_action()` 改为返回独立 NumPy 副本；
  该问题只影响旧 warmup action 日志，不影响当时 active 控制。
- `setup.sh` 已恢复 laptop/orin 自动 profile；x86_64 使用 Conda `unitree_py38` 和
  `enp0s31f6`，aarch64 保留 `.venv`、`eth0` 和单线程设置。
- 新增从提交 `64c32a0` 恢复的 `test_policy_real_single_process.py`，保留当前 driver
  安全检查，并提供可选同格式日志用于 A/B；未连接或控制机器人。
- 验证通过：Bash/Zsh 语法、Python 编译、laptop policy/robot 环境导入、go2w 离线测试、
  observation 精度复放、6 项 go2wwmp `unittest`。Conda 环境未安装 `pytest`，因此直接
  运行同一 unittest 文件完成测试，不为此改变用户环境。

## 2026-09-04 笔记本稳定实机日志对比

- 用户确认笔记本单进程在同一真实机器人上仍然非常稳定、无明显抖动且抗扰性强。
- 新日志为 `logs/real/policy_laptop_single.csv`；开始与 Orin 抖动日志做时序、状态、动作、
  MotorCommand 和频谱对齐分析。
- 本阶段仅离线分析，不初始化 DDS，不发送机器人控制命令。
- 已确认笔记本主日志和 observation 各含 936 帧，约 18.79 秒，零速度命令且无 warmup；
  字段完整，可与 Orin 的 1874 个 active 帧直接比较。
- 初步定量对比完成：Orin 存在 8.4–8.6 Hz 闭环极限环；IMU、腿速和动作跳变约为稳定
  笔记本的 11–22 倍。Orin 有 30–68 ms 策略周期尾延时，但周期尖峰与动作跳变相关性弱。
- 发现重要混杂变量：Orin 抖动段电压平均 28.59 V、最低 26.76 V，笔记本稳定段约
  31.67 V；Orin 振荡电流最大 52.26 A。
- 分段分析确认 Orin 在 16–24 秒曾达到与笔记本几乎相同的稳定性，说明双进程/DDS 并非
  必然抖动；34–37 秒再振荡与 30–68 ms 调度尖峰同步，其中半数 >30 ms 周期紧随每
  0.5 秒一次的大段终端打印。
- 首帧接管比较显示笔记本动作阶跃反而更大，排除“Orin 第一帧 policy 目标更猛”这一简单解释。
- 用户补充现场标注：后半段坏状态来自人工外推，Orin 长尾属于暴走后的次生现象。分析
  窗口已改为两端前半段未外推的连续最佳稳态，撤回基于后半段自然状态转换的因果解释。
- 生成聚焦图时首次补丁因同一文件同时 Delete/Add 被工具拒绝；未产生文件变化，改用新文件名继续。
- 已按现场标注生成前半段连续最佳 5 秒对比：两端策略周期同为约 20 ms，Orin 无长尾，
  但 IMU、腿速、action 和腿目标波动仍为笔记本约 28–42 倍，并保留 8.5 Hz 谱峰。
- 笔记本 observation/action 936 帧离线复放逐元素误差为零，日志内部一致。
- Phase 24 完成：没有把人工外推后的尾延时、电压或通信异常用于主因判断。当前证据排除
  Pipe 数值损坏、模型精度差、LowState 过旧及前半段 50 Hz policy 失速；没有排除实际
  500 Hz LowCmd 发布抖动、不完整 CPU 隔离、网卡 IRQ 竞争或第二个 LowCmd 发布者。
- 本阶段只完成离线日志和代码路径审查，没有初始化 DDS、发送 LowCmd 或运行实机控制。

## 2026-09-04 排除 Pipe 后的 Orin 专属排查

- 用户已在笔记本运行当前双进程入口，机器人依然稳定，因此“双进程 + 同步 Pipe 架构
  本身”可从首要嫌疑中排除。
- 开始将剩余变量收敛到 Orin 特有的 500 Hz LowCmd 调度、CPU/IRQ/DDS 线程布局、系统
  性能状态和软件运行环境；本阶段先形成逐项消融计划，不运行机器人。
- 用户修正历史判断：4.8 的暂时正常可能只是假象，不作为 Orin 链路稳定的证据；相关
  guide/findings 已改为历史观察并标明不可用于排除根因。
- 已汇总当前证据分级和八步调试顺序；首要新增指标是 500 Hz LowCmd 逐次间隔、CRC/Write
  耗时、漏周期/补跑和 action 首次应用延迟。
- `logs/` 不再被 `.gitignore` 排除；四个原始 CSV 共约 14 MB，新增
  `logs/real/README.md` 记录帧数、工况、有效区间和 SHA-256。未修改原始 CSV。
- 首次暂存因当前沙箱中的 `.git` 只读而失败，未产生部分暂存；授权后已仅暂存
  `.gitignore` 和 `logs/real/`，不包含提交或推送。
- 四个原始 CSV 使用 Python `csv` 默认 CRLF；没有为格式检查改写数据，新增
  `.gitattributes` 将其标为 binary，确保 Git 原样保存且不展开巨量逐行 diff。
