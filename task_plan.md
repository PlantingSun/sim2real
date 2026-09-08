# Go2WWMP 笔记本部署与机载深度链路阶段计划

## Goal

Orin NX 只负责 D435i 深度采集、处理与发布；go2wwmp 强化学习控制网络继续部署在笔记本，
通过网线同时接收深度与机器人状态。严格按“跨机只读收图 → 深度质量与 simulation 对齐 →
WMP 离线/只读集成 → 人工代码复审 → 吊架/地面低速 → 障碍递进”验证，最终完成受控跨越障碍。
所有实机代码保持简洁、注释准确、可逐行人工审查；助手不擅自运行任何真实机器人控制入口。

## Prompt

当前 go2w/go2wcr 的“笔记本部署 + 网线”控制已经完成；Orin NX 运行控制策略的路线因实机问题暂停。
go2wwmp 的 simulation pipeline 已完成一轮复审和修正，D435i 机载服务已经实现并开机自启动。
当前从实际笔记本跨机取深度开始，随后处理/验收深度，再实现与 simulation 数值及时序一致的
go2wwmp 笔记本实机入口。所有会发送 LowCmd 或调用 Sport Mode 的步骤必须由用户现场执行。

## Phases

- [completed] Phase 1: 完整盘点当前项目、go2wcr 源实现、运行入口和已有验证链路
- [completed] Phase 2: 确定 CRRL 网络/控制器适配方案与接口边界，记录风险和不改动项
- [completed] Phase 3: 实现 CRRL policy/controller 与配置、模型加载适配
- [completed] Phase 4: 实现并验证 CRRL 离线/policy 单元测试与 MuJoCo simulation 测试
- [completed] Phase 5: 实现 real_test 入口并进行安全审查（默认不执行真实机器人动作）
- [completed] Phase 6: 重新分类 scripts，更新 README/guide 与逐步操作说明
- [completed] Phase 7: 运行静态检查、可执行性检查和安全回归，整理交付清单
- [completed] Phase 8: 修复 MuJoCo 初始姿态、MotorCommand 打印和 base 高度问题
- [completed] Phase 9: 在 MuJoCo pipeline 中添加跟随基座的 D435i 位置可视化标记
- [completed] Phase 10: 调研 D435i 深度参考坐标与公开 Go2W 安装信息
- [paused] Phase 11: 早期 Orin NX 到笔记本 D435i 方案（由 Phase 29 新实现取代）
- [completed] Phase 12: 从零建立 Go2W 机载 Orin NX 使用基础
- [completed] Phase 13: 根据现场设备事实规划联网与 Orin 本地使用（远程传图暂缓）
- [completed] Phase 14: 精简 Orin NX 本地图形桌面入门文档
- [completed] Phase 15: 移植并验证 Go2W WMP MuJoCo pipeline 基线
- [completed] Phase 16: 内置 WMP 推理依赖修正
- [completed] Phase 17: WMP 场景与模型路径基础修正
- [completed] Phase 18: 项目可迁移化
- [completed] Phase 19: 建立 Orin NX 专用 Python 3.8/.venv、CycloneDDS 和 VS Code 环境
- [completed] Phase 20: Orin eth0 上只读验证 DDS driver
- [completed] Phase 21: 离线验证三个 policy，并测量 Orin CPU 单帧延时
- [completed] Phase 22: Xbox command input 现场确认
- [completed] Phase 23: 恢复笔记本稳定基线并完成跨架构精度复放
- [completed] Phase 24: 对比笔记本稳定日志与 Orin 抖动日志
- [completed] Phase 25: 收敛 Orin 专属根因和调试路线
- [completed] Phase 26: 研究 DDS 与 500 Hz LowCmd 路径
- [completed] Phase 27: 完成 C++ DDS A/B 并排除 Python DDS 为主要根因
- [paused] Phase 28: ONNX state→action 延时消融（Orin 控制路线暂停）
- [completed] Phase 29: 完成 D435i 机载服务，并在实际笔记本/网线上验收（用户已完成 guide 19）
- [in_progress] Phase 30: 记录 USB2 无效区域/底部盲区并冻结当前保守质量门槛
- [in_progress] Phase 31: 实现简洁的 go2wwmp 笔记本部署代码和 fail-closed 状态机
- [pending] Phase 32: 完成离线、仿真、录制回放、只读实机数据和时延回归
- [pending] Phase 33: 由用户按吊架 → 地面低速的顺序分级执行实机验收
- [pending] Phase 34: 由用户执行软障碍 → 目标障碍的递进跨越测试

## Decisions

- 现有 driver layer 作为稳定边界，优先复用，不主动修改其行为。
- 当前仓库同时保留显式 laptop/orin profile；Orin 固定 Python 3.8 `.venv` 和 `eth0`，
  笔记本恢复 Conda `unitree_py38` 和已验证网卡，实机入口互不覆盖。
- 先以当前仓库已有模型、配置和控制接口为事实依据；不能把“能导入”误判成“能上实机”。
- 真实机器人测试入口默认必须显式确认/保护，验证阶段只做静态检查或仿真/离线运行。
- 每个阶段的关键发现、变更和验证结果同步到 `findings.md` 与 `progress.md`。
- Orin 不再运行 policy；它只发布 depth domain 42。笔记本保留 Unitree domain 0 控制链，
  WMP 子进程独立订阅深度，避免深度接收进入 500 Hz LowCmd 线程。
- 当前 simulation 默认 checkpoint 候选为 `model_6000.pt`；在同工况比较并记录 SHA-256 前，
  不把文件编号当作最终实机选择依据。
- 深度输入保持 `float32 (64,64)` 米制 `[0,2] m`，接收层不归一化、不翻转、不转置；
  控制器保留训练时的 10 Hz world-model 更新和上一张深度（约 100 ms）历史。
- 深度过期、接收器异常、发布 session 改变、policy 超时/退出、LowState 过期、NaN/Inf、
  关节/轮速越界均按 fail-closed 处理；不得继续复用旧图或旧 action，也不得自动恢复实机动作。
- WMP 专用实机入口默认必须是完全不发送 LowCmd 的 dry-run；真实动作需要显式 `--arm`、
  交互终端、分阶段人工确认和现场物理急停条件，不提供静默绕过确认的默认路径。
- 现有 12 个腿关节 q/dq 限位尚未配置，属于进入真实 WMP 动作前的阻塞审查项；
  未经可靠来源和用户确认，不擅自填写或声称保护完整。

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| 系统默认 `python` 不存在 | 1 | 使用项目指定的 `/home/robot/miniconda3/envs/unitree_py38/bin/python` 完成权重检查 |
| CRRL normalizer 输出 `[1,265]` 与 stage 输入一维拼接失败 | 1 | 在实时推理路径显式 `squeeze(0)`，与原控制器保持一致 |
| 现有命令输入测试期待线速度 `±0.5`，配置实际为 `±1.0` | 1 | 修正测试断言以匹配 `CTRL.COMMAND_LIMITS`，不改变运行配置 |
| CRRL 仿真打印将 `MotorCommand` 当作四元组解包 | 1 | 只调用一次动作转换，直接打印 `MotorCommand` 字段 |
| MuJoCo 初始 base 使用 XML 默认 `z=0.55` | 1 | 恢复 XML 已有 `stand` keyframe，使用 `base_z=0.43` 和对应站姿关节 |
| go2w 仿真入口没有 `--help` 参数 | 1 | 不重复该检查；改用入口编译检查和独立可视化几何验证 |
| 独立 user geom 验证首次断言失败 | 1 | 改用字段诊断确认 MuJoCo `MjvGeom` 的实际存储值，再调整测试断言 |
| 实际 viewer 创建时报 `could not initialize GLFW` | 1 | 检查无 `xvfb-run`/`Xvfb`；以无窗口 MuJoCo 几何验证为可重复验证，保留环境限制 |
| 官方 PDF 截图请求返回 Cache miss | 1 | 使用同一 PDF 的可检索正文和官方网页数据，未改变结论 |
| 首次 RealSense/ROS2 资料检索请求语法错误 | 1 | 修正查询字符串后重新检索官方 RealSense wrapper 和 ROS2 文档 |
| 宇树营销手册页面无法直接打开 | 1 | 使用搜索到的 Go2-W 手册副本和宇树官网产品页交叉核对；不把 NVIDIA 开发套件接口套用到 Go2W |
| 宇树支持页正文无法由浏览工具展开 | 1 | 以用户现场按该官方教程成功验证的结果为设备事实，并保留官方链接；不推测未显示的细节 |
| 系统缺少 `python3.8-venv` | 1 | 使用一次性 `virtualenv` 引导项目 `.venv`，不修改系统 Python |
| CycloneDDS 0.10.2 `idlc` 出现未定义符号 | 1 | 清除 ROS Foxy 的 `LD_LIBRARY_PATH`，避免链接其 CycloneDDS 0.7 |
| MuJoCo/OpenCV 后加载 PyTorch 时报 static TLS 错误 | 3 | 仿真入口固定先导入 PyTorch；移除全局双 `libgomp` 预加载 |
| `git add .gitignore logs/real` 无法创建 `.git/index.lock` | 1 | 工作区允许修改文件但 `.git` 为只读；保留文件变化并通过授权方式仅暂存日志与忽略规则 |
| 原始 CSV 的 CRLF 使 `git diff --cached --check` 报尾随空白 | 1 | 不改写实验原始数据；用 `.gitattributes` 将 `logs/real/*.csv` 标为 binary，原样保存并避免巨量文本 diff |
| 规划目录解析脚本直接执行时报 `permission denied` | 1 | 改用 `sh scripts/resolve-plan-dir.sh`，成功恢复项目根目录规划文件 |
| 当前沙箱读取网卡信息时报 `Cannot open netlink socket` | 1 | 不重复尝试；把笔记本网卡/IP/路由确认列为现场只读步骤，由用户运行并记录 |
| loopback DDS 集成测试无法枚举 `udp` 接口 | 1 | 判定为当前沙箱网络权限限制；授权后仅在专用 domain 89 完成本机模拟收发，不使用机器人 domain 0 |
| 授权后的 domain 89 测试找不到 `build/depth/go2w_depth` | 2 | 确认现有 C++ 构建链面向 Orin/RealSense；自动测试改用 Python DataWriter，domain 89 接收/过期/新会话测试已通过 |
| wrapper 默认寻找不存在的项目 `.venv`，导致用户基础接收直接失败 | 2 | 已改为公共环境解析：显式配置→激活环境→项目 `.venv`→笔记本 `unitree_py38`→系统候选，并在启动前验证依赖；干净 shell 已通过三个 wrapper 的启动检查 |
| guide 命令中的 `"$DEPTH_IF"` 在未执行准备段时展开为空，Python 层报 `Invalid network interface` | 2 | guide 改为 `export DEPTH_IF=...` 并在每条命令使用 `${DEPTH_IF:?}` shell guard；receiver 也增加空参数的 argparse 提示，空变量和有效变量两种路径均已验证 |
| 用户希望现场沿用直接 Python 入口而非 bash wrapper | 1 | guide 19 主流程改为先 `source setup.sh robot`/清理 domain0 环境，再直接运行 Python；wrapper 仅保留为备用入口，三个 Python CLI `--help` 已验证 |
| 深度单测清理 `CYCLONEDDS_URI` 容易被误解为 domain 0/42 不能共存 | 1 | 已用回环接口专用 domain 89/90 同时创建 participant 验证并存；最终部署保留电机 domain 0 与深度 domain 42，各 participant 使用明确配置 |
| 用户希望直接打开 WMP action | 1 | 当前 12 个腿关节 q/dq 限位仍为空，候选腿目标相对初始站姿最大偏差约 0.457 rad；不在承重机器人上启用无界 action，先要求可靠限位与吊架短测安全包络 |

## Next Step

用户已完成 guide 19 的四项深度接收验收，并完成 guide 20 的 print-only 与地面承重固定站姿数据链路。
WMP action 的显式 5 秒入口和限位检查已经写好，下一步是由用户现场执行并分析该短测；尚未进入
更长时间、行走或障碍测试。

## Phase 9 Scope（历史记录）

- 当时仅修改当前仓库的 MuJoCo 仿真入口，不修改外部 `test_com_ws` 模型文件；后续迁移阶段已将资源复制到项目内。
- 使用 viewer 临时几何体显示 D435i 主体和深度镜头位置；不增加碰撞体、质量或传感器。
- 修改完成后进行 Python 语法检查、MuJoCo 场景加载和可视化几何配置验证；不启动实机。

## Phase 10 Scope

- 核对 RealSense 官方产品、数据表、投影/坐标和立体深度资料。
- 核对当前 `simtosim` 深度渲染与 WMP/WMPCR 输入链路。
- 检索公开 Go2/Go2W 的安装和 URDF/TF 配置；不把无精确外参的案例当作本机答案。

## Phase 10 Result

- D435i 是左右红外相机组成的立体深度设备，深度坐标原点在左 IR 成像器中心；RGB 镜头是独立流。
- 当前 WMP/WMPCR 使用未对齐的 raw depth，因此不应把 RGB 镜头中心或 MuJoCo 外壳中心当作深度图参考点。
- 官方 `17.5 mm` 是“底部 `1/4-20` 安装孔中心线 → 左成像器中心”的相机内部尺寸，不能直接证明 Go2W 基座坐标中的历史 `y=-0.022 m`。
- 公开 Go2/Go2W 项目未找到与本机安装方式匹配的精确机身到 D435i 外参；用户已将当前实验坐标最终确定为 `[0.34, -0.0375, 0.09]`。

## Phase 11 Scope

- 先确认 Orin NX 端的 D435i 采集方式、ROS2 发行版、节点和话题，不执行机器人控制。
- 设计只读的图像接收与显示路径，优先复用已有 ROS2/RealSense 软件，不把 USB 相机设备直接假设为可跨网访问。
- 笔记本端显示入口在用户审查后再用于实机；本阶段不修改 `real/` 控制入口，不发送 LowCmd 或 Sport Mode 指令。

## Phase 12 Scope

- 从硬件连接、显示器/键盘/鼠标、SSH、串口、网络和文件传输开始建立 Orin NX 入门路径。
- 区分 NVIDIA 开发套件通用文档与宇树 Go2W 实际载板，所有 IP、接口、账号和系统版本以现场确认结果为准。
- 记录 ARM64、JetPack/CUDA、统一内存、USB、功耗和图形化访问等对后续 D435i/WMP 部署有影响的特性。
- 本阶段只新增入门文档和只读检查步骤，不刷写系统、不修改功耗、不启动相机或机器人控制。

## Phase 13 Scope

- 记录用户已验证的显示器、SSH、账号身份、Ubuntu 版本、网络接口和 D435i USB 枚举结果。
- 在联网前识别 `eth0` 与 Go2W 内部通信的关系，避免更改机器人通信网段或默认路由。
- 后续再决定使用 Orin 本地浏览器、ROS2 话题或 Unitree 视频服务；不把“能联网”等同于“可以安全运行控制代码”。

## Phase 14 Scope

- 保留本地图形桌面、D435i 设备事实和必要的安全边界。
- 将 SSH、网络配置、远程显示和文件传输压缩为备用参考，不删除已验证的现场记录。
- 更新项目索引，明确当前工作流是直接在 Orin 图形桌面操作。

## Phase 15 Scope

- 完整阅读 simtosim 中 go2wwmp 的 config、runner、policy、playback 和控制器入口。
- 复用当前 MuJoCo driver/场景边界，构造与原 WMP 一致的本体状态、命令和深度输入。
- 检查模型加载、观测形状、动作形状/范围和循环时序；不连接、不发送任何实机控制指令。

## Phase 15 Result

- 已完成 `policy/controller_go2wwmp.py` 和 `scripts/simulation/test_mujoco_pipeline_go2wwmp.py`。
- 已完成 checkpoint 严格加载、CPU world model 构造、单步检查和 6 周期无窗口推理验证；已确认动作/观测维度与 simtosim 结构一致。
- 已将共享 XML 相机和 WMP pipeline 统一到用户确认的 `[0.34, -0.0375, 0.09]`；不再保留旧场景位置对比入口。
- 已记录当前机器缺少可用 GLFW/OpenGL context，实际窗口闭环待在 Orin 本地图形桌面上执行；因此 Phase 15 暂保留为 in_progress，未宣称 MuJoCo viewer 验证完成。

## Phase 16 — 内置 WMP 推理依赖修正（completed）

- [x] 将 simtosim 的 WMP 推理所需网络源码和配置直接拷贝到当前项目。
- [x] 删除 tensorboard 兼容桩、外部 `lib` 导入和对 simtosim 源码路径的运行时依赖。
- [x] 重新执行 WMP 单步/多周期验证，并确认文件清单和导入路径完整。

## Phase 17 — WMP 场景与模型路径基础修正（completed）

- [x] 核对本地 checkpoint 位置和 `.gitignore`，从 Git 索引移除旧 `.pt` 文件并保留本地文件。
- [x] 将 WMP/相机位置引用统一为 `[0.34, -0.0375, 0.09]`，移除旧的深度偏移分支。
- [x] 增加约 10 Hz 的深度图显示，不改变 50 Hz 策略循环。
- [x] 在 MuJoCo scene 中增加五级上台阶和五级下台阶，并验证尺寸为高 `0.12 m`、深 `0.25 m`、宽 `0.60 m`。

结果：本地 checkpoint 加载、入口帮助、Python 编译、OpenCV 导入和共享 XML 几何检查均通过；实际图形窗口仍需在 Orin NX 图形桌面上由用户观察确认。

## Phase 18 — 项目可迁移化（completed）

- [x] 盘点当前代码依赖的外部 SDK、MJCF/XML、mesh、配置和运行时资源。
- [x] 将 Unitree SDK2 Python 源码及当前仿真所需 Go2W XML/mesh 复制到项目内，保留许可证和来源说明。
- [x] 将所有入口和文档中的外部绝对路径改为项目相对路径，并让默认场景可从任意项目目录解析。
- [x] 在不连接实机的前提下，验证项目内 SDK 导入、XML 加载、WMP checkpoint、离线策略和 MuJoCo 入口。
- [x] 明确仍属于操作系统/运行环境的依赖边界，避免把“项目文件自包含”误写成“无需安装 Python/CUDA/DDS”。

结果：项目源码、Unitree SDK2 Python、Go2W MuJoCo MJCF/STL 和路径解析已内置；从 `/tmp` 启动的离线与 XML 检查通过。权重仍因 `.gitignore` 规则不进入 Git，目标设备需要另行复制本地 checkpoint。

## Phase 19 — Orin NX 专用环境（completed）

- [x] 核对 aarch64、Ubuntu 20.04.5、L4T R35.3.1、25W mode 3、Python 和 VS Code。
- [x] 确定只使用系统 Python 3.8.10 派生的项目 `.venv`，不安装 Conda、不使用 Python 3.9。
- [x] 安装并锁定 CPU-only PyTorch 2.0.0、NumPy 1.24.4、MuJoCo 3.2.3。
- [x] 将 CycloneDDS C/Python 0.10.2 安装到 `.venv`，隔离 ROS Foxy 的 0.7 动态库。
- [x] 增加可复建安装脚本、只读验证脚本、VS Code 配置和 `guide/12_orin_environment.md`。

结果：环境和无窗口 MuJoCo 场景验证通过，未初始化 DDS。该阶段结束时三个 `.pt` 文件尚未
位于 controller 要求的精确路径，因此当时没有宣称 policy 可执行。

## Phase 20 — Orin DDS driver（completed）

- [x] 静态确认测试入口不会启动 LowCmd 线程或调用 `Write()`。
- [x] 确认 `eth0` 为 `192.168.123.18/24`，并在该接口初始化 CycloneDDS。
- [x] 连续读取 LowState 的 Tick、16 个关节和 IMU 数据，Ctrl+C 正常关闭。
- [x] 修正把 SDK `power_v` 当作 SOC 百分比的命名和显示错误。

结果：Orin 直接作为 DDS 参与者能够稳定订阅机器人状态；本阶段没有发送 LowCmd。

## Phase 21 — Orin policy 与 CPU 延时（completed）

- [x] 三个 checkpoint 均严格加载，观测、动作和 MotorCommand 维度/有限值检查通过。
- [x] go2w 推理补上 `torch.no_grad()`，回归输出不变。
- [x] 1/2/4/8 线程短测后，将 go2w/go2wcr 默认收敛为单个 OpenMP 线程。
- [x] go2w/go2wcr 各执行 2000 个计时帧，P99 分别为 `1.911/3.967 ms`，零超时。
- [x] WMP 使用 4 线程执行 500 帧；100 个 world-model 更新帧全部超过 20 ms。

结果：go2w/go2wcr 满足当前 50 Hz policy 要求，可以进入仿真。WMP 不能仅凭平均吞吐判定
通过，后续需要保持网络语义的推理优化和重新验证。本阶段没有初始化 DDS。

## Phase 22 — Xbox command input（completed）

- [x] 确认 Orin 的 USB/udev 设备身份、稳定 joystick 路径和访问权限。
- [x] 运行输入映射单元测试，不初始化 DDS。
- [x] 用真实设备启动离线监视器，确认节点可打开且未使能时速度为零。
- [x] 按住 A 逐轴确认 `vx/vy/vyaw` 的方向、回中值和限幅。

结果：当前接收器可读，默认路径已固定为本机 udev by-id 链接，手柄方向和回中行为已由
用户现场确认。WMP 暂不进入当前控制链路，只保留后续 cv2 兼容性修复。

## Phase 23 — 笔记本基线恢复与 Orin 抖动消融（complete）

- [x] 从 Git 历史定位笔记本上已验证平稳运行的环境与单进程实机入口
- [x] 在不覆盖 Orin 双进程版本的前提下，恢复可显式选择的笔记本环境和近原版实机入口
- [x] 解析 `logs/real/policy_fixed_2_observation*` 的观测、动作与时间字段
- [x] 使用笔记本侧 `models/go2w/model_700.pt` 对同一观测逐帧复放，并比较模型哈希和输出精度
- [x] 完成离线预检、语法检查和实机运行说明；本阶段不主动初始化 DDS 或下发控制命令

判定原则：如果模型文件哈希一致、相同 265 维输入的动作误差仅为浮点舍入量级，则把
主要排查方向转向 Orin 双进程链路的观测年龄、Pipe 排队/阻塞、动作提交时刻与控制状态机；
如果离线输出已明显分叉，则优先定位模型、归一化、dtype、PyTorch/算子或日志输入差异。

兼容性决策更新：保留 Orin 的 `.venv`、CPU 亲和性和双进程入口作为独立配置，同时恢复
笔记本的 Conda/网卡和单进程基线。以后不再让一套宿主机设置隐式覆盖另一套设置。

结果：模型哈希完全一致；1874 个 active 帧的跨架构最大 action 误差为 `1.6689e-06`，
排除模型传输和推理精度为剧烈抖动主因。笔记本环境、单进程基线、复放统计和实机消融
说明均已完成；实际机器人行为需要用户连接 RJ45 并按安全流程验证。

## Phase 24 — 笔记本稳定日志与 Orin 巨幅抖动根因对比（complete）

- [x] 核对 `policy_laptop_single.csv` 及配套 observation 的完整性、阶段和命令条件
- [x] 与 Orin `policy_fixed_2.csv` 对齐比较策略周期、LowState tick、状态年龄和尾延时
- [x] 对比 IMU、关节状态、raw action、MotorCommand 的变化幅度、频谱和闭环相关性
- [x] 结合单/双进程代码审查，区分资源竞争、跨进程相位延迟、发布节拍及第二发布者风险
- [x] 形成证据分级的根因判断和下一轮最小消融；现有证据不足以直接改动控制行为

当前实验事实：相同笔记本单进程入口在真实 Go2W 上稳定、不抖且鲁棒，用户已保存
`logs/real/policy_laptop_single.csv`。本阶段只离线读取日志，不初始化 DDS 或发送 LowCmd。

结果：按用户现场标注排除人工外推及 Orin 暴走后的长周期尾部，只比较前半段各自 gyro
RMS 最低的连续 5 秒。两端 policy 周期均稳定在约 20 ms，Orin LowState 平均年龄反而更低，
但 Orin 的 IMU、腿速、action 和腿目标波动仍为笔记本约 28–42 倍，并保留约 8.5 Hz
闭环振荡。因此已记录的 50 Hz policy/LowState 路径不是充分解释；尚未测量的 500 Hz
LowCmd 发布节拍、不完整 CPU 隔离、网卡 IRQ 竞争和第二发布者是下一轮最有区分度的检查项。

## Phase 25 — 排除 Pipe 后的 Orin 专属根因排序与调试路线（complete）

- [x] 记录笔记本双进程实机稳定这一新消融结果，并更新已排除项
- [x] 盘点 laptop/orin 仍有差异的控制时序、线程亲和性、DDS 和系统运行环境
- [x] 按证据和可验证性给候选根因排序，避免把振荡结果误当成触发原因
- [x] 设计从只读检查、非控制基准到短时实机 A/B 的逐步调试方案和通过门槛
- [x] 明确每一步只改变一个变量、所需日志字段以及停止条件

边界：本阶段只分析和规划，不初始化 DDS、不发送 LowCmd、不直接修改控制行为。任何实机
消融均由用户按安全流程执行；诊断代码需在下一步得到明确实施请求后再加入。

结果：笔记本当前双进程入口稳定，排除 Pipe 架构本身作为充分原因；Orin 4.8 的短暂正常
按用户说明降级为不可重复历史观察。最高优先级转为当前日志未覆盖的 500 Hz LowCmd
逐周期实时性，其次为 GIL/日志 I/O、CPU/IRQ/DDS 线程布局、DVFS、DDS 环境和第二发布者。
完整证据与八步调试路线已归档，原始实机日志也已解除 Git 忽略并附清单与哈希。

## Phase 26 — DDS 与 500 Hz LowCmd 路径研究（complete）

- [x] 检查项目内 Unitree Python SDK 的 DDS 收发、BQueue、timerfd、CRC 和 IDL 序列化路径
- [x] 在不初始化 DDS 的情况下测量 Orin IDL 编解码、状态复制和 LowCmd CRC 成本
- [x] 核对 Unitree 官方 Python/C++ Go2W 示例及 RL 实机部署的线程、队列和冲突检查
- [x] 只读检查 Orin 功耗模式、CPU governor、当前频率和 `eth0` IRQ affinity
- [x] 形成不改变控制行为的 LowCmd 内存统计字段与分步 A/B 顺序

结果：500 Hz Python DDS 编解码和命令准备平均约占 `1.30 ms/2 ms`，实时余量有限；
现有总写入次数不能反映长空档、Write 尾延时或 timerfd deadline miss。下一步先实现退出时
一次性报告的内存诊断，再由实测决定是否把 DDS 收发移入更严格隔离的进程或 C++ bridge。

## Phase 27 — C++ DDS 独立进程原型（complete）

- [x] 确认 Orin 本机 C++ Unitree SDK、Go2 IDL、CycloneDDS 头文件和库可链接
- [x] 实现 C++ LowState/LowCmd、CRC、500 Hz 绝对时钟、CPU 绑定和 watchdog
- [x] 用固定大小匿名管道连接现有 DriverBase，保留 policy/手柄/日志代码
- [x] 保留 Python 默认后端，新增显式 C++ A/B 开关和一条命令启动
- [x] 完成 Release 构建、Python 语法、包尺寸及 C++/Python CRC 对照
- [x] 用户运行只读 bridge，确认状态率、tick、`writes=0` 和正常退出
- [x] 确认 Sport Mode 持续发布 LowCmd，撤销不成立的 ReleaseMode 前活跃检查
- [x] 改为接管后用最近自身 CRC 集合识别并发 LowCmd 发布者
- [x] 用户吊架运行 C++ print-only，记录 500 Hz RATE/WRITE 摘要
- [x] 用户短时运行 C++ policy，与 Python 后端的抖动和 LowCmd 时序做 A/B

边界：助手没有初始化 DDS、调用 Sport Mode 或发送 LowCmd。C++ 后端保持实验状态，不替换
默认 Python 实机路径。

结果：C++ LowCmd 达到约 500 Hz，Write 平均 `0.124 ms`，但真实 policy 仍产生与 Python
后端相同的约 `8.4 Hz` 振荡。因此 Python DDS/GIL 和 LowCmd Write 节拍不是主要原因。

## Phase 28 — ONNX state→action 延时消融（offline complete, field test pending）

- [x] 安装并锁定 ARM64 CPU ONNX/ONNX Runtime 依赖
- [x] 导出 Go2W `normalizer + actor` 固定形状 ONNX 图
- [x] 用真实 observation 检查 PyTorch/ONNX action 数值一致性
- [x] 对比 actor、完整帧和实际 policy Pipe 往返延时
- [x] 为实机入口增加显式 ONNX 后端和主进程 CPU 绑定，默认仍保持 PyTorch
- [ ] 用户先执行 ONNX `print-only`，只比较 state→action 延时，不发送 policy action

结果：500 帧最大 action 误差 `4.77e-7`；完整帧均值从 `1.809 ms` 降到 `1.204 ms`，
Pipe 往返均值从 `2.507 ms` 降到 `1.878 ms`。下一步只执行 `guide/17` 的 print-only，
达到平均 `3.0 ms`、P99 `4.5 ms` 门槛后才考虑真实动作。

## Phase 29 — D435i 机载深度服务（2026-09-07）

用户将策略部署改回笔记本，Phase 28 及此前机载抖动消融暂停。当前主线仅为相机深度传输。

- [x] 确认相机恢复枚举及实际 USB2 采集能力，记录库和线缆排查结果
- [x] 实现 60 FPS 采集、空间滤波、64×64 米制深度及有效掩码
- [x] 按仿真 58°视场重采样，显式记录 USB2 模式底部一行缺失
- [x] 独立 CycloneDDS domain/topic、共享 IDL、Python 最新帧接收器
- [x] 显式限制 DDS UDP 载荷 1400B、fragment 1280B，互通/超时/重启测试通过
- [x] 编写机载操作指南、笔记本接口文档、实测记录和自动验收工具
- [x] 安装启用 systemd 服务，确认 active/running 及持续真实出图
- [ ] 完成最终服务配置 30 分钟持续测试并记录结果
- [x] 实际笔记本及长网线验收（用户已完成 guide 19 的四项命令）
- [ ] 物理安装/已知距离对齐、实际 USB/网线拔插和设备重启验收

当前入口为 guide/18.5–20；不得把同机 DDS 接收、service enabled 或几何单元测试分别当作
实际跨机传输、实际重启出图或实机相机外参标定已通过。

### Phase 29 执行与退出门槛

1. 在机器人不接管 LowCmd 的状态下，用户分别记录 Orin `CONNECTED/STATS`、笔记本实际有线
   网卡名、两端 IP 和路由；不得照抄示例网卡名，不更改机器人内部网段。
2. 笔记本运行 60 秒只读 receiver，保存 JSONL 和一份 `.npz`；确认形状 `(64,64)`、
   `float32`、全部有限且位于 `[0,2] m`，并实际预览左右/上下方向。
3. 在最终使用的笔记本和网线上运行约 5 分钟 acceptance。每个 10 秒窗口新帧率 `>=50 Hz`、
   最大接收间隔 `<=100 ms`、重复/逆序/畸形/source-lagged 为 0；源帧号缺口单独记录，
   不与网络丢包混为一谈，且不得形成超过 100 ms 的连续陈旧区间。
4. 单独执行笔记本晚启动、receiver 重启、网线拔插、相机 USB 拔插、Orin 服务重启和整机重启。
   相机/服务重启后 `session_id` 必须变化，旧图在约 100 ms 内过期，恢复时间写入记录。
5. 更新 guide 18.5/19.5/20 和证据目录；当前逐步验收以实际跨机 5 分钟结果和恢复测试记录为完成门槛。
   原 30 分钟项目级长稳测试保留为后续可选的正式耐久验收，不阻塞本轮第一步。

## Phase 30 — 深度处理、物理质量与 simulation 对齐（in_progress）

目标：确认网络收到的米制图在几何、数值、时序上能够替代 simulation 的 `render_depth()`，
而不是只证明“有画面”。本阶段不读取或发送任何机器人控制命令。

- [ ] 固定相机安装，记录深度光心相对 base 的 `[0.34, -0.0375, 0.09] m` 和向下 5°姿态；
      若实物安装不同，先改仿真/训练假设或重新评估，不在接收代码中暗补偏移。
- [ ] 对 0.5/1.0/1.5 m 平墙和明确左右/上下位置的近物体采集原始、滤波、64×64、valid mask；
      以深度光心为测距基准，记录中心中位数、P95 误差、静态抖动和有效率。
- [ ] 核对图像方向、58°×58°射线、最近邻重采样、光轴 Z 深度、0–2 m 裁剪、无效填 2 m；
      USB2 底部 1/64 无效行作为已知事实保留，除非 USB3 复测证明可移除。
- [ ] 将实测 `.npz` 直接传给 `ControllerGo2wWMP.preprocess_depth()`，确认接收层没有再次
      归一化、中心化、翻转、转置、补历史或引入额外 100 ms 延迟。
- [ ] 建立可重复的录制样本集及元数据（checkpoint 哈希、相机序列号、模式、处理参数、安装外参）；
      无效比例/中心 ROI 质量的报警和停机阈值根据这组实测基线由用户审查后冻结。
- [ ] 在相同尺寸障碍/地面布局中对比 MuJoCo 与实机深度边缘位置；差异未解释前不进入实机动作。

退出门槛：方向、单位、数值范围、无效处理和相机外参全部可解释；物理误差阈值在采集前写明并
通过；实机样本经现有预处理后的统计与 simulation 输入语义一致。

## Phase 31 — go2wwmp 笔记本部署代码（in_progress）

目标：在不改动已验证 go2w/go2wcr 默认入口的前提下，增加一个可逐行审查的 WMP 专用链路。

建议保持最小文件边界：

- `policy/process_worker_go2wwmp.py`：加载 `ControllerGo2wWMP`，在子进程内订阅 depth domain 42，
  只维护最新帧，并按 50 Hz state、10 Hz depth/WMP 语义返回 MotorCommand 与健康信息。
- `scripts/real/test_policy_go2wwmp_real.py`：主进程只持有 Unitree domain 0、LowState/LowCmd、
  人工阶段确认、日志和 fail-closed 状态机；默认 dry-run 完全不调用 StandUp/ReleaseMode/Write。
- `tests/test_go2wwmp_real_pipeline.py` 与新 guide：覆盖集成故障和明确的用户运行顺序。

当前第 20 步入口采用更小的实际状态机；尚未把 WMP action 解锁为真实动作：

```text
BOOT → MODEL_READY → DEPTH_READY → DRY_RUN_READY
                         └─ --ground-stand --arm → FIXED_GROUND_STAND
任一故障 / Ctrl+C → FAULT（已启动 LowCmd 时先进入阻尼）
session_changed → dry-run reset 并记录，固定站姿 FAULT；depth_stale → FAULT
```

实现要求：

- [x] 模型严格加载、checkpoint SHA-256、新鲜深度和一帧只读 WMP 自检必须在 ReleaseMode 前通过。
- [x] 参数分开命名 `--interface`（电机 domain 0）与 `--depth-interface/domain/topic`（深度 domain 42）；
      即使使用同一物理网卡，也不能让两个协议配置相互覆盖。
- [x] 子进程每个周期都检查 depth receiver 健康；仅在 `needs_depth_update` 时消费图，但不能在
  非更新帧忽略深度已经过期。session 改变时 reset WMP 并要求人工重新 arm。
- [x] 固定站姿在 `ReleaseMode` 后、LowCmd 接管前执行一次无动作 `session_sync`；接管前的相机重启
      可重新建立基线，接管后的 session 改变仍立即故障阻尼。
- [x] 主进程对 policy IPC 使用有界等待，禁止永久 `recv()`；超期、EOF、异常、非法 shape/数值
      都停止本轮。固定站姿阶段任何此类故障都进入阻尼并退出；当前没有自动恢复或自动重臂。
- [ ] 为 `DdsDriver` 增加默认关闭、仅由 WMP 入口显式启用的 LowState/新命令 freshness watchdog，
      防止主进程卡死时 500 Hz 线程无限重复旧 action；任何修改不得改变现有 go2w/go2wcr 默认行为。
- [x] WMP 实机入口默认 dry-run；真实动作必须显式 `--arm`、交互终端、固定站姿接管确认和独立的
      WMP 使能确认。不得提供默认开启或静默跳过阶段确认的选项。
- [ ] 日志已包含 state/depth session+frame、valid ratio、depth/processing/local age、推理时间、
      action 和 MotorCommand；仍需补充显式 IPC/loop deadline、故障原因和状态机迁移字段，且要
      再审查写盘是否会影响控制周期。
- [x] 腿关节 q 限位已按 `assets/go2w_description/mjcf/go2w.xml` 写入 DDS 16 路映射，所有 dq/轮速
      上限按用户要求设为 `30 rad/s`；驱动会在状态和待发送命令两侧检查限位。
- [ ] 完成显式 `--enable-wmp-action --duration 5` 的保护架/急停短测，并分析 action 日志；短测前
      不进入更长时间、移动或障碍测试。

## Phase 32 — 离线、仿真与完全只读端到端验证（pending）

- [ ] 保留并通过现有 WMP 6 项测试、depth transport 测试、go2w/go2wcr 回归。
- [ ] 新增 fake depth 流测试：未收到首帧、过期、重复/逆序、畸形、低有效率、session 改变、
      receiver 异常；验证旧图/旧 action 不会继续进入 WMP。
- [ ] 新增 policy 超时/崩溃、LowState 过期、watchdog、dry-run 零 Write、退出阻尼测试；
      使用 mock driver，不连接机器人。
- [ ] 用固定随机种子和同一 state/depth 序列，对 simulation 调用路径与实机 worker 做逐帧对照，
      核对 10 Hz world-model、连续 5 动作历史、约 100 ms 深度历史及 MotorCommand 映射。
- [ ] 在笔记本对 5500/6000 做同场景、同命令、同种子对比，记录成功率/姿态/漂移/轮速；
      选定 checkpoint 后冻结路径和 SHA-256。
- [ ] 在笔记本运行不少于 10 分钟的完整 worker 基准，分别统计普通帧与 world-model 更新帧；
      20 ms deadline 及 watchdog 阈值以实测最坏分布留出余量后冻结，超期不允许补跑旧周期。
- [ ] 同时运行 live depth domain 42 和只读 LowState domain 0，确认 30 分钟内两者频率、间隔和
      CPU/网络负载正常；全程不启动 LowCmd、不调用 Sport Mode。
- [ ] 最后运行“真实 LowState + 真实深度 → WMP → 仅日志 MotorCommand”的真正 dry-run，
      代码路径必须证明 `writes=0`，且用户检查动作符号、范围、时序和深度对应关系。

退出门槛：代码静态审查、测试、回放、笔记本时延和双 domain 只读并行全部通过；用户逐行审查
WMP 实机入口与安全状态机后，才允许生成现场 `--arm` 命令。

## Phase 33 — 吊架与地面低速实机验收（pending, user-run only）

本阶段所有命令由用户现场执行。助手只提供经过审查的命令、观察项和日志分析，不远程启动控制。

1. 现场准备：机器人周围清场；可靠吊架/低位保护架承重；操作者手持经过确认的物理急停或遥控
   停止手段；第二人观察；电池、网线、相机固定和轮胎方向检查完成。
2. 地面承重固定站姿：保护架/绳只限制异常动作，不卸载；先运行真正 dry-run，再固定站姿 LowCmd
   接管。先 2 s，再 5 s，再 10 s；每轮退出并审查日志，不一次拉长。
3. 吊架下逐轴/逐方向小命令检查；任何方向、轮速符号、姿态或深度画面不一致立即急停，不靠软件
   自动“试着修正”。吊起结果只证明命令方向，不证明落地闭环稳定。
4. 低位保护架内落地零速度，再以最小前进命令短测；每次只改一个变量，逐步增加到计划速度。
5. 无障碍平地完成多次启停、深度遮挡、接收器退出和网线故障演练；感知故障必须退出 ARMED，
   不复用旧图、不自动恢复动作。硬故障必须由 watchdog/阻尼和物理急停兜底。

任一停止条件（深度/LowState 过期、session 变化、policy deadline、非法数值、超限、异常振动、
非预期位移、操作者请求）触发后，本轮结束并回到日志/代码审查，不在现场连续重试。

## Phase 34 — 递进障碍跨越（pending, user-run only）

- [ ] 先用可变形、低高度、无锐边的软障碍；高度按目标障碍的约 25% → 50% → 75% → 100%
      单变量递进，障碍宽度、接近方向、相机姿态和速度均记录。
- [ ] 每一级先仿真复现，再由用户在保护架/急停覆盖下低速接近；一次只跑一个短轨迹，跑后检查
      深度新鲜度、valid ratio、WMP 更新帧时延、姿态、轮速、动作/MotorCommand 和停止距离。
- [ ] 每一级至少连续多次无故障通过并由用户确认机械行为，才进入下一级；失败立即退回上一级，
      不同时改相机、滤波、命令速度和模型。
- [ ] 最终目标障碍的尺寸、材质、速度、成功/失败判据和紧急停止结果形成独立记录；只有多次可重复
      成功、无安全触发且日志与 simulation 假设一致，才宣称 go2wwmp 实机跨越完成。
