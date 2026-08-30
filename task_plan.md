# CRRL / go2wcr 实机部署阶段计划

## Goal

在保持现有 `driver` 层接口稳定的前提下，将 `/home/robot/simtosim/src` 中的 go2wcr/CRRL 算法接入当前 sim2real 项目，复现并补齐 policy → simulation → real_test 的验证链路，整理 `scripts` 分类，补充准确、简洁、可人工审查的代码注释与分步 Markdown 文档，为最终部署实机做好准备。

## Phases

- [completed] Phase 1: 完整盘点当前项目、go2wcr 源实现、运行入口和已有验证链路
- [completed] Phase 2: 确定 CRRL 网络/控制器适配方案与接口边界，记录风险和不改动项
- [completed] Phase 3: 实现 CRRL policy/controller 与配置、模型加载适配
- [completed] Phase 4: 实现并验证 CRRL 离线/policy 单元测试与 MuJoCo simulation 测试
- [completed] Phase 5: 实现 real_test 入口并进行安全审查（默认不执行真实机器人动作）
- [completed] Phase 6: 重新分类 scripts，更新 README/guide 与逐步操作说明
- [completed] Phase 7: 运行静态检查、可执行性检查和安全回归，整理交付清单
- [completed] Phase 8: 修复 MuJoCo 初始姿态、MotorCommand 打印和 base 高度问题

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

## Next Step

本阶段交付完成；后续仅需在真实硬件条件满足时按 `guide/08_crrl_real_test.md` 执行吊架测试并记录实测数据。
