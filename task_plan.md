# CRRL / go2wcr 实机部署阶段计划

## Goal

在保持现有 `driver` 层接口稳定的前提下，将 `/home/robot/simtosim/src` 中的 go2wcr/CRRL 算法接入当前 sim2real 项目，复现并补齐 policy → simulation → real_test 的验证链路，整理 `scripts` 分类，补充准确、简洁、可人工审查的代码注释与分步 Markdown 文档，为最终部署实机做好准备。

## Prompt

该项目是一个sim2real项目，目前已稳步推进完了第X步，利用手柄启动和加载网络和控制机器人。这个项目的宗旨是，因为要运行在实际的机器人上，必须人为二次审查代码，因此需要保证代码的简洁、易读以及注释准确，且为每一步编写md文件。你可以先完整阅读项目代码

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
- [in_progress] Phase 11: 建立 Orin NX 到笔记本的 D435i 画面读取链路（暂缓）
- [in_progress] Phase 12: 从零建立 Go2W 机载 Orin NX 使用基础（转为本地图形桌面）
- [completed] Phase 13: 根据现场设备事实规划联网与 Orin 本地使用（远程传图暂缓）
- [completed] Phase 14: 精简 Orin NX 本地图形桌面入门文档
- [in_progress] Phase 15: 移植并验证 Go2W WMP MuJoCo pipeline

## Decisions

- 现有 driver layer 作为稳定边界，优先复用，不主动修改其行为。
- 先以当前仓库已有模型、配置和控制接口为事实依据；不能把“能导入”误判成“能上实机”。
- 真实机器人测试入口默认必须显式确认/保护，验证阶段只做静态检查或仿真/离线运行。
- 每个阶段的关键发现、变更和验证结果同步到 `findings.md` 与 `progress.md`。

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

## Next Step

当前以 Orin 本地图形桌面为后续相机工作主线；SSH、网络传图和远程显示仅保留为已验证的备用记录。go2wwmp 的模型/观测/动作适配和无窗口验证已完成；待在有图形环境的设备上运行实际 MuJoCo viewer，任何实机代码仍须经过用户审查。

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
