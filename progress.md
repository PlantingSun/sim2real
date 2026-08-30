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
