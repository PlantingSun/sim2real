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

## 2026-09-04 DDS 与 500 Hz LowCmd 研究

- 完整检查项目内 Unitree SDK2 Python 的 ChannelPublisher、ChannelSubscriber、BQueue、
  RecurrentThread、CRC 和 CycloneDDS 0.10.2 序列化路径。
- 只运行离线 IDL 基准，没有创建 DDS participant 或发送 LowCmd。Orin 上 LowState
  反序列化与 LowCmd 填充/CRC/序列化平均合计约 `1.30 ms`，500 Hz 的 2 ms 预算有限。
- 核对官方 Python/C++ Go2W 示例和 Unitree RL Lab：目标 topic 与 500 Hz 频率一致；
  C++ 实现使用队列 1、C++ 实时发布并检查其他 LowCmd 发布者。
- 只读确认 25W mode 3、8 核 `schedutil`、`eth0` IRQ 当前落在 CPU0；没有据此直接修改
  功耗、governor、IRQ 或线程优先级。
- 新增 `guide/15_dds_lowcmd_research.md`。下一步是在现有 driver 中加入纯内存 LowCmd
  周期、CRC/Write 和 action 首次应用延迟统计，退出时一次性报告。

## 2026-09-04 C++ DDS 独立进程实验后端

- 新增 `cpp/go2w_dds_bridge.cpp` 和 CMake 构建：C++ 独立持有 DDS，500 Hz 线程默认绑定
  CPU1，并在退出时报告发送间隔、CRC、Write 和丢包统计。
- 新增 `CppDdsDriver`，通过匿名管道复用现有 DriverBase；现有 policy、手柄、日志和阶段
  按键无需复制。
- `test_policy_real.py` 增加显式 `--dds-backend cpp`，默认仍为 `python`。
- 新增只读入口和一次性 Sport RPC helper；完整顺序写入 `guide/16_cpp_dds_bridge.md`。
- 已通过 C++ Release 编译、Python 语法、协议尺寸和跨语言 CRC 检查；没有启动 DDS。
- 用户只读验证 CPU1 达到 `500.01 Hz`、最大间隔 `4.65 ms`，且 `writes=0`、无状态丢包；
  CPU5 出现 `17.45 ms` 尖峰，因此后续固定 CPU1。
- 增加 LowCmd 发布者状态回传，并消除 C++ 两条启动信息的并发交错。
- 用户完成更新版 CPU1 五秒复测：`500.02 Hz`、最大间隔 `2.78 ms`、无超过 3 ms 周期、
  `late=0`、`state_drops=0`、`other_lowcmd=0`，允许进入 C++ print-only 吊架测试。
- 两次 print-only 都在 ReleaseMode 前安全停止且 `writes=0`；第二次确认 Sport Mode 在
  站稳后仍持续发布，说明 500 ms 窗口仍无法区分内置控制器。
- 冲突检测已移到接管后：C++ 记录自身最近 16 个 CRC，20 ms 交接期后仅把未知 CRC 判为
  并发发布者。ReleaseMode 前的 Sport 流量单独标记为 `prearm_lowcmd`。
- 用户完成 C++ print-only 接管：8830 次 Write，平均周期 `2.00061 ms`；Write+CRC 平均
  约 `0.1643 ms`，无失败、丢包或并发发布者。最大周期 `8.58 ms`，仅一次超过 5 ms。
- 周期统计已限定为 ARM 后实际发布阶段，不再混入 StandUp、吊起和按键等待时间。
- 用户完成 C++ 真实 policy 测试，机器人仍与 Python 后端一样持续高频抖动。
- 离线分析 `policy_cpp.csv`：固定预热安静，policy 接管后立即形成约 `8.4 Hz` 振荡；
  50 Hz policy、LowState tick、C++ 500 Hz Write 和 observation/action 数值均正常。
- Phase 27 结束：此前把 Python DDS/GIL 视为主因的判断被实测否定，不再扩展 DDS bridge。

## 2026-09-04 Go2W ONNX 延时测试

- 将 ONNX/ONNX Runtime CPU 依赖安装到项目 `.venv` 并写入 Orin 锁文件，没有修改系统 Python。
- 新增离线导出/基准脚本；生成 `models/go2w/model_700.onnx`，模型文件继续由 Git 忽略。
- 用真实 observation 检查 500 帧，最大 action 误差 `4.77e-7`。
- ONNX 完整帧均值/P99 为 `1.204/1.295 ms`，policy Pipe 往返为 `1.878/2.071 ms`；
  PyTorch 对照分别为 `1.809/1.976 ms` 和 `2.507/2.714 ms`。
- 实机入口增加显式 `--policy-backend onnx` 和 `--main-cpus`，默认 PyTorch 行为不变。
- 下一步由用户按 `guide/17_onnx_policy_latency.md` 只运行 print-only，先判断实际
  state→action 是否达到平均 3.0 ms、P99 4.5 ms，再决定是否发送 ONNX policy action。

## 2026-09-07 D435i 独立深度链路

- 收到新的阶段目标：放弃 Orin NX 上运行控制策略，转为“Orin NX 仅采集/发布深度，笔记本通过网线接收、处理并运行 go2wwmp 控制”。
- 本轮只进行项目盘点和规划，不启动 DDS 控制、不发送 LowCmd、不调用 Sport Mode，也不运行任何实机控制入口。
- 已恢复项目根目录现有 `task_plan.md`、`findings.md`、`progress.md`，将保留历史 Orin 调试结论，不覆盖既有记录。
- 规划目录解析脚本直接执行时报 `permission denied`；改用 `sh scripts/resolve-plan-dir.sh` 成功解析到项目根目录，未影响文件。

- 用户决定策略继续在笔记本运行，机载仅采集、处理并通过独立 DDS 发送深度；此前机载推理优化暂停。
- 新增 C++ librealsense/CycloneDDS 发布器、共享 IDL、Python 最新帧接收器、诊断/验收/快照工具。
- 相机线缆及库安装问题由用户排查后恢复枚举；现场仍为 USB2，采用 480×270@60。
- 目标 58°×58°、64×64 米制深度；当前底部一行无传感器覆盖，显式标无效并填 2 m。
- 编译、几何数值、DDS C++/Python 互通、超时及进程重启测试通过；60 秒真实同机收发最低窗口
  59.8256 Hz、最大间隔 36.1856 ms、零帧号缺口及重复。
- 15:50:59 CST 开机服务已安装并启用；30 分钟持续测试占用相机时服务通过锁避免竞争并重试。
- 当前深度交付摘要、笔记本接收和质量记录分别见 guide 18.5/19/19.5；真机 WMP 验证流程见 guide 20。
- 已完整阅读 guide 18/18.5/19/19.5、深度 receiver/验收工具、WMP controller/simulation pipeline、现有
  笔记本实机入口、policy worker 和 DDS driver；本轮没有运行测试或任何 DDS/机器人入口。
- 已将 `task_plan.md` 主目标从“Orin 运行 policy”更新为“Orin 仅发布深度、笔记本运行 go2wwmp”，
  并新增 Phase 29–34 的跨机收图、深度处理、代码集成、只读验证、吊架/地面和障碍递进门槛。
- 识别出进入实机前的两个阻塞项：尚无 go2wwmp 笔记本实机 worker/入口；12 个腿关节 q/dq
  安全限位当前均未配置。计划要求先解决并由用户审查，助手不得自行解锁真实动作。
- 现有最终 MTU 同机服务记录实际约 950 秒，虽通过该区间帧率/间隔/完整性门槛，但明确标记为
  用户提前停止，不计为 30 分钟完成。当前 Next Step 仅为实际笔记本跨机 60 秒只读收图。

## 2026-09-07 笔记本深度接收验收工具

- 用户批准开始 Phase 29 的第一步，要求代码覆盖：基础接收、接收并可视化、约 5 分钟稳定性、
  以及按 go2wwmp 规定执行后处理；完成后同步更新 `guide/19_depth_laptop_integration.md`。
- 本轮只实现和运行离线/模拟深度测试，不初始化机器人 DDS domain 0、不发送 LowCmd、不调用
  Sport Mode；实际 Orin→笔记本链路由用户按 guide 逐步验收。
- 新增 `depth/postprocess.py` 作为纯 NumPy 的唯一 WMP 深度转换；controller 与接收工具共同调用，
  保持 `clip([0,2])/2-0.5` 和既有 simulation 完全一致。
- 接收 CLI 现会在首帧立即报告 shape/dtype/范围/有效率，无帧时返回退出码 2；预览增加米制深度、
  valid mask 和可选 WMP 输入面板；`--wmp-postprocess` 可在 NPZ 中保存 `depth_wmp`。
- 5 分钟 acceptance 增加连续 WMP 后处理检查、`wmp_pass/wmp_failures/min/max` 汇总和末尾 120 帧
  `depth_wmp` 保存；仍只订阅 depth domain 42。
- `guide/19_depth_laptop_integration.md` 已改为四步现场验收：30 秒基础接收、可视化、300 秒稳定性、
  WMP 后处理与离线图片检查。
- 使用笔记本 `unitree_py38` 环境通过 3 项纯离线 depth 测试（2 项集成测试默认跳过）和 6 项 WMP
  pipeline 测试；启用 Python 回环集成后共执行 4 项、仅跳过未构建的 C++ 发布器测试。
  `git diff --check` 通过。测试未创建机器人 domain 0，也未执行机器人控制。
- 首次启用 loopback DDS 集成测试时，CycloneDDS 因当前沙箱无法枚举 UDP 接口而初始化失败；
  该失败发生在 domain 89 participant 创建阶段，没有启动发布器。将改用授权的本机回环测试，
  不在相同受限环境重复，也不使用机器人 domain 0。
- 授权后 domain 89 participant 可创建，但本机缺少面向 Orin/RealSense 的 C++ 发布器构建产物；
  自动测试已改用 Python DataWriter。专用 domain 89 的接收、新鲜度过期、新 session 接受及 WMP
  后处理集成测试全部通过；整个测试未访问 domain 0 或真实机器人。
- 用户把当前跨机稳定性门槛调整为约 5 分钟；guide 19 和 Phase 29 当前门槛均采用 300 秒，
  原 30 分钟记录保留为后续可选耐久测试。
- 最终复测曾发现 wrapper 默认寻找不存在的项目 `.venv`，当时错误地只依赖 guide 中的手工环境变量
  绕过，没有修复启动脚本；用户按基础命令运行后复现了该缺陷。
- 已新增 `scripts/depth/python_env.sh`，receiver、acceptance 和离线查看 wrapper 共用自动环境解析与
  `cyclonedds/numpy` 预检。使用清空 Conda/venv/LD/PYTHONPATH 的干净 shell，三个 wrapper 的
  `--help` 均成功自动选择笔记本 `unitree_py38`；不再要求项目根目录存在 `.venv`。
- receiver 的 first/final 事件现在也写入 JSONL，现场证据不再只存在于终端。
- 使用已有真实 USB2 深度样本生成并人工检查了米制/WMP 离线预览：`(64,64)`、全有限、
  米制范围 `0.28–2.0 m`、WMP 范围 `-0.36–0.5`，无效区域与后处理结果显示正常。
- 用户明确 guide 不需要保留历史措辞。已将 guide 19 重写为当前可执行版本，删除旧的 30 分钟
  可选流程、重复依赖说明和历史背景，只保留四步验收、当前数据约定、接入示例与必要排障。
- 用户再次实测发现 `DEPTH_IF` 未设置时，guide 命令把空字符串传入 receiver，触发 Python traceback。
  已修复：guide 先 `export DEPTH_IF`，每条现场命令使用 `${DEPTH_IF:?}` 立即阻止空值；receiver
  对空接口名返回明确的 argparse 用法错误。空变量 shell guard、空参数入口、有效接口 `--help`
  和全部离线/WMP 测试均通过。
- receiver 现在只在 `DepthReceiver` 成功初始化后创建 JSONL；参数错误不会再留下 0 字节假证据。
- 用户更习惯直接运行 Python。已将 guide 19 四步验收和离线检查全部改为 `python -m depth.receiver`
  或 `python scripts/depth/...`；准备段显式清理电机 domain 0 的 `CYCLONEDDS_URI`，bash wrapper
  仅作为独立调用的备用环境解析器。三个 Python `--help` 入口和未设置 `DEPTH_IF` 的 shell guard
  已验证。
- 已在本机回环接口、专用测试 domain 89/90 中同时创建两个 CycloneDDS participant，验证不同 domain
  可以并存。生产对应关系应是电机 domain 0 + 深度 domain 42；当前 guide 的 `unset` 只用于深度单独
  验收，后续双域实机入口不能把它误用成全局配置。

## 2026-09-07 Go2WWMP 第 20 步真机验证入口

- 用户已完成 guide 19 的四项深度接收验收；对 USB2 底部无效行的处理保持保守：无效像素继续使用
  2 m 远平面并保留 `valid=0`，不做“填近障碍”或盲目插值；有效率只作诊断，不作为 WMP 失能门槛。
- 将旧的深度历史文档整理为 guide 18.5/19.5，并删除过时的 guide 20/21；当前 guide 20 专注于
  domain 0 状态 + domain 42 深度 + WMP 的只读验证和固定站姿门槛。
- 新增 `policy/process_worker_go2wwmp.py`：子进程独占深度 domain 42 和 WMP，按 100 ms 新鲜度、
  有效率、session、有限值和推理时延检查后，通过 Pipe 返回候选 action/MotorCommand；绝不写 LowCmd。
- 新增 `scripts/real/test_policy_go2wwmp_real.py`：`--print-only` 完全只读；`--ground-stand --arm`
  仅在交互确认、StandUp、地面承重/保护架确认和 ReleaseMode 后发送固定 `INITIAL_JOINTS_POS`，WMP
  action 仍只打印；状态年龄和 tick 写入 JSONL。
- 根据首次固定站姿现场结果补充了接管前 `session_sync`：StandUp/人工安全确认等待期间若相机服务重启，
  可在任何 LowCmd 之前重新建立深度 session 基线；LowCmd 接管后的 session 改变仍进入阻尼。
- 用户首次固定站姿实测触发了原有 session fail-closed，已确认 StandUp、ReleaseMode 和固定 LowCmd
  启动成功，未继续运行异常深度链路；下一次需先核对 Orin 服务日志和 `[DEPTH SYNC]` 输出。
- 用户随后完成 `logs/real/go2wwmp_hold_stand_2.jsonl` 固定站姿测试：1500 条记录（约 30 s），
  session 全程不变，深度有效率 `0.9224–0.9387`，深度 local age 最大 `18.59 ms`，LowState
  age P99 `2.15 ms`，WMP 推理 P99 `7.88 ms`，10 Hz 深度更新计数为 300；候选 action 仍未发送。
  该结果允许进入“固定初始站姿、落地保护下的 2/5/10 s 原地站立短测”，不等于允许解锁 WMP 行走。
- 当前 JSONL 主要记录数据链路和候选输出，尚未保存完整实际 LowState 姿态/关节轨迹；后续延长
  原地站立测试前应增加实际 q/dq/IMU 诊断字段。已将入口新名称统一为 `--ground-stand`，旧
  `--hold-stand` 仅作为隐藏兼容别名。
- 用户随后明确 q 限位采用项目 MJCF、所有 dq/轮速上限设为 30；已写入 16 路 DDS 映射并让驱动
  在状态和待发送命令两侧检查。新增显式 `--enable-wmp-action`，只允许带日志、地面保护下最多
  5 秒；当前尚未运行该真实 action 入口。离线回放 hold_stand_2 的全部候选 MotorCommand
  均未触发这组 q/dq 限位。
- 新增 4 项离线安全/传输测试（含严格状态包 shape/finite 校验）；本轮通过 WMP、depth transport、
  编译、CLI help 和 domain 共存检查，
  没有运行真实机器人入口、没有发送 LowCmd 或 Sport Mode。下一步由用户先运行 guide 20 的
  `--print-only`，不要直接进入固定站姿。

## 2026-09-07：首次 5 秒 action 现场故障与处理决定

- 用户在地面承重、保护架/急停覆盖下运行 action 短测；机器人站立较稳定，但约 2 秒内出现单帧
  `depth_valid_ratio=0.8987 < 0.9000`，程序按原规则进入阻尼，用户执行急停。该事件不是 q/dq
  限位越界，且日志中的上一帧 valid 为 0.922。
- 用户明确要求保留低有效率帧的真实性，不用固定站姿替代真实观测，也不因有效率下降直接阻尼；
  已撤回本轮新增的“坏帧容忍/动作回退”逻辑，并进一步移除原有有效率失能门槛。
- 仅完成离线代码回退和测试，未再次启动任何实机控制；后续应先分析无效区域的空间分布和产生原因，
  再由用户决定是否调整发布端或质量阈值。

## 2026-09-08：移除 valid_ratio 运行门槛并准备现场录制

- 用户确认 Orin NX 已修复底部一行数据；按照新的安全要求，`valid_ratio` 只保留为诊断指标，
  不再作为 WMP worker 的失能条件。深度协议现有的无效像素 `valid=0 + depth_m=2.0` 语义保持不变。
- 删除了 worker 的 `min_valid_ratio` 参数和入口参数；深度过期、session 改变、畸形包、NaN/Inf
  仍是独立的数据链路故障，未用删除有效率门槛掩盖这些问题。
- 新增只读 `scripts/depth/record_scene.py`，默认可录制 120 秒完整序列，保存每帧深度、mask、
  session/frame、发送/接收时间戳和有效率，供后续连通域与邻域深度分析；不创建电机 domain 0，
  不发送 LowCmd。
- 新增只读 `scripts/depth/analyze_recording.py`，离线统计有效率、无效连通块、跨帧持久性、
  最大块邻域深度和无效频率热图；分析结果不自动改写网络输入。
- 新增只读 `scripts/depth/replay_recording.py`，可在无相机/无机器人连接时回放三联图；默认压缩
  长空档并在画面标注，避免把 50.9 s 传输空档误看成正常连续运动。
- 更新 guide 19.5/20，明确无效区域暂按远平面进入 WMP，不在没有数据证据时做插值或邻域填补。
- 离线复测通过：16 项 unittest（2 项环境相关跳过）、新录制工具编译/help、录制保存 helper 和
  `git diff --check`；未启动任何实机控制。

## 2026-09-08：scene_walk 录制分析完成

- 用户已运行两分钟录制和离线分析。有效率最小 `0.7397`、中位数 `0.9265`，最大无效连通块
  858 像素；说明复杂场景低有效率是常态，不能恢复 `valid_ratio` 失能门槛。
- 录制中有约 50.9 s 接收空档（frame_id 跳约 3061），故只把它用于无效区域几何分析，不把它
  作为连续链路稳定性验收。
- 对比邻域统计后，暂定继续使用 `valid=0 + depth_m=2.0`；不启用连通域/邻域填补，避免在未
  证明几何关系前改变仿真输入。当前进入下一步：用户现场执行短时原地承重站立测试。

## 2026-09-08：WMP action 5 秒现场短测完成

- 用户完成 `logs/real/go2wwmp_action_15s.jsonl`；250 条 step、全部 `wmp_action_sent=true`、
  无错误行，说明本轮实际进入了 WMP action 发送路径。
- 离线检查确认 session/frame/state_tick 单调、深度与 LowState 新鲜度正常；valid ratio 最低
  `0.8643` 仍被保留并继续运行，没有再次触发旧的有效率阻尼规则。
- q/dq 静态边界检查全部通过；用户现场观察机器人约 5 秒原地站立无抖动/摔倒。该结果仅覆盖
  承重原地 action 短测，不代表手柄行走或障碍跨越。
- 下一项工作调整为：先实现并离线验收 go2wwmp 的手柄命令接入（deadman、断连归零、限速、日志），
  再由用户执行极短低速实机测试；Unitree 原生控制另列独立基线，不与 WMP LowCmd 同时启用。

## 2026-09-08：Go2WWMP 手柄接入完成（待用户只读验收）

- 从本机 `/home/robot/simtosim/src/controller/model/go2wwmp/go2wwmp_config.py` 核对训练范围：
  `vx=[0,1] m/s`、`vy=0`、`vyaw=[-1,1] rad/s`；修正了此前对 `vx=-0.2` 的记忆，不把负向
  vx 放进 WMP 训练包络。
- 新增 WMP 专用 command bounds，控制器、worker、MuJoCo 入口统一使用；Xbox 输入支持 A deadman，
  严格禁用 vy，并将实际 field cap 默认设为 `vx≤0.2`、`|vyaw|≤0.2`。
- 新增 [guide/21_go2wwmp_xbox_input.md]，包含离线映射、print-only 和首次 5 秒 action 流程；
  real JSONL 记录 `command` 与 `command_enabled`，便于验收手柄命令是否按限幅进入网络。
- 已通过 Python 编译、输入映射测试、12 项 WMP/real pipeline unittest、CLI help 和 diff 检查；
  未启动真实机器人控制。下一步由用户先执行 guide 21 第 2、3 节，只读确认手柄映射。

## 2026-09-08：手柄范围调整与命令误用修正

- 按用户要求移除默认 `0.2` 现场上限，real 入口默认允许 `vx=[-0.2,1.0]`、`vy=0`、
  `vyaw=[-1,1]`；`--max-vx/--max-vyaw` 仍可显式收窄。
- 原始训练源码的 `vx=[0,1]` 与该部署扩展有差异，已在 guide 21 和 findings 中明确标注；不把
  负向 vx 宣称为训练分布内证据。
- `test_command_input.py` 增加参数误用提示；它是无设备单元测试，不能带 `--control`。Xbox 实际
  读取必须运行单独的 `debug_command_input.py`。

## 2026-09-08：长时间 Xbox action 和深度预览入口完成

- `--duration` 现在可省略；无限时长 action 仅允许 Xbox，Back/Ctrl+C/输入故障结束，固定命令仍
  需要显式有限 duration。
- Xbox 模式默认每 5 Hz 由 WMP worker 返回深度/valid mask，主进程显示米制深度、valid mask、
  WMP 输入三联图；预览失败或关闭不改变 LowCmd 控制链。
- 更新 guide 21 长测命令，不再要求 duration 或额外深度参数；已通过 py_compile、17 项测试和
  CLI help，未运行真实机器人。

## 2026-09-08：深度预览降为单图 2 Hz

- 长测只渲染一张带无效像素标记的深度图，默认 `--depth-display-hz=2.0`；不再拼接 valid mask
  和 WMP 三联图，以降低图形资源占用。控制与接收时序未改。

## 2026-09-08：允许位置目标超出 q range，保留实测保护

- 用户反馈台阶测试中的位置目标可能需要超出 MJCF q range 以产生固定 Kp 下的目标动态；已删除
  `DdsDriver.send_command()` 对 `q_cmd` 的拒绝，不截断、不改写目标。
- 500 Hz LowState 实测 q/dq 限位检查保持不变；实测越界仍进入紧急阻尼。命令侧 dq 上限、有限值、
  shape 检查保持不变，避免把“目标位置放开”误变成所有安全检查都关闭。
- 已更新 guide 00/20 和离线测试；仅做编译/单测验证，未运行真实控制。

## 2026-09-08：按用户要求关闭全部关节位置保护

- 已同时移除 `DdsDriver` 对位置目标 q 和 LowState 实测 q 的限位急停；q range 仅保留为配置参考，
  不再参与 LowCmd 发送或 500 Hz 保护判断。
- 保留命令侧 `dq` 与 LowState 实测 `dq` 的 `30 rad/s` 超限急停，以及数据/通信故障保护。
- 已更新 guide 00/20、findings 和离线测试；未运行实机控制。

## 2026-09-08：取消命令侧速度保护

- 现场台阶日志的 `J15 |dq_cmd|=30.630` 已核对为 `DDS J15 = CTRL index 11 = RL_foot`，即后左轮；
  Go2WWMP 对轮子使用 `dq` 速度控制，腿部使用 `q` 位置控制，因此并非“位置指令突然变成速度”。
- 按用户要求取消命令侧 q/dq 限幅；`send_command()` 仅保留 shape、NaN/Inf 完整性检查，LowState
  实测 `dq > 30 rad/s` 的急停路径保持不变。
- 已更新 guide、findings、测试；未运行实机控制。

## 2026-09-08：新增 Go2WWMP Unitree 手柄模式

- `test_policy_go2wwmp_real.py --control unitree` 已接入原装遥控器 LowState 解析，速度映射为
  `vx=Ly`、`vy=0`、`vyaw=-Rx`，并统一应用当前 WMP 部署包络。
- Unitree 模式使用 L2+R2 触发 LowCmd 接管、Select 退出；Ground-stand 模式要求机器人先由
  原生 Sport Mode 站稳，不猜测 StandUp 按键组合。新增 guide 22，包含只读和 print-only 验收。
- 已通过 py_compile、17 项离线测试、CLI help 和 diff 检查；尚未运行真实控制入口。

## 2026-09-08：笔记本网口默认值统一配置

- 在 `config/go2w_config.py` 增加 `DDS.LAPTOP_NET_IF="enp0s31f6"` 和
  `DDS.DEPTH_NET_IF`；笔记本常用 domain 0/42 Python 入口现在自动读取同一网口。
- 深度接收、场景录制、稳定性验收和 Go2WWMP real 的 interface 参数均改为可选默认值；只有
  网络拓扑改变时才需要显式覆盖，guide 19/19.5/20/21/22 已移除重复 export 示例。
- 已完成离线编译、单测与 help 检查，未运行实机控制。

## 2026-09-08：Go2WWMP Unitree 正式长期运行入口

- 用户已完成 30 秒实机 action 验收：机器人能从原生站立状态经 L2+R2 启动网络并由 Unitree
  手柄接管，日志为 `logs/real/go2wwmp_unitree_action_30s.jsonl`。
- 日志含 1500 个连续循环，全部 `wmp_action_sent=true`、深度 session 改变为 0；首末 loop 为
  1/1500，最大 LowState age 约 2.77 ms，最大单步推理约 10.70 ms。
- `scripts/real/run_go2wwmp_unitree.py` 已改为完整、独立的正式状态机，不导入或调用任何
  `test_policy_*` 脚本；无参数时直接运行 Unitree + WMP action，不设置 duration，并自动生成日志。
- 遥控器解析/命令源移入正式模块 `teleop/unitree_remote.py`，只读 debug、旧验收入口和正式入口
  共享这一底层映射；正式入口仍只保留 model、log 和关闭深度预览三个可选项。
- 正式接管在 Sport Mode 尚未释放时先同步深度并缓存初始站姿，ReleaseMode 返回后立即启动 LowCmd；
  清理顺序先置阻尼、再等待 WMP 子进程和窗口关闭。未由助手运行实机控制。
- 已通过 Python 3.8 编译、20 项离线单测（2 项按预期跳过）、遥控器映射脚本以及新旧入口的
  `--help` 检查；另有静态测试禁止正式入口导入 `test_policy`，并锁定同步/释放/LowCmd/阻尼顺序。
