# scripts 目录约定

脚本按“会不会连接机器人”和“验证哪一层”分类。所有可执行实现都放在子目录中，运行时直接调用对应分类目录内的文件。

| 目录 | 用途 | 是否连接机器人 |
|---|---|---:|
| `setup/` | Orin 环境安装和只读验证 | 否 |
| `policy/` | 三种模型的离线检查和 Orin CPU 延时基准 | 否 |
| `simulation/` | go2w/go2wcr/go2wwmp 的 MuJoCo 闭环测试 | 否 |
| `input/` | 键盘、Xbox、原装遥控器输入映射检查 | 只有 `debug_unitree_remote.py` 订阅 LowState |
| `real/` | DDS 驱动只读检查、go2w/go2wcr 实机接管 | 是 |
| `depth/` | D435i 采集、深度 DDS 收发、验收及开机服务安装 | 仅深度话题，不发送运动指令 |

深度服务单独使用 `bash scripts/depth/build.sh`、`run_publisher.sh`、`run_receiver.sh` 和
`run_acceptance.sh`，不需 `source setup.sh robot`。机载指南见
[`../guide/18_d435i_depth_service.md`](../guide/18_d435i_depth_service.md)。

建议按以下顺序执行：

1. `setup/` Orin 环境检查
2. `real/test_dds_driver.py` 驱动只读检查
3. `policy/` 离线检查
4. `simulation/` MuJoCo 检查
5. `input/` 输入设备检查
6. `real/` 实机控制测试

Go2W 抖动消融有两个互斥入口：

- `real/test_policy_real.py`：Orin 双进程 DDS/policy 版本。
- `real/test_policy_real_single_process.py`：从已验证笔记本版本恢复的单进程基线。

二者不能同时运行；详细顺序见 `guide/14_laptop_orin_ablation.md`。

CRRL 对应入口：

- `policy/test_policy_go2wcr_offline.py`
- `policy/benchmark_policy_latency.py`
- `policy/benchmark_go2w_onnx.py`：导出并离线比较 Go2W PyTorch/ONNX 延时
- `simulation/test_mujoco_pipeline_go2wcr.py`
- `simulation/test_mujoco_pipeline_go2wwmp.py`
- `real/test_policy_go2wcr_real.py`
- `real/test_policy_go2wcr_unitree_remote.py`
- `real/test_policy_go2wwmp_real.py`：Go2WWMP 分阶段验收入口
- `real/run_go2wwmp_unitree.py`：已验收的 Unitree 手柄长期运行入口（默认无需参数）

正式入口完成 L2+R2 接管后，A 单击开启航向保持，B 单击关闭；开启时固定
`vx=0.5 m/s` 并根据启用瞬间的目标 yaw 自动计算 `vyaw`。现场步骤见
[`../guide/23_go2wwmp_heading_mode.md`](../guide/23_go2wwmp_heading_mode.md)。

例如，在项目根目录执行：

```bash
python scripts/policy/test_policy_go2wcr_offline.py
python scripts/policy/benchmark_policy_latency.py --policy go2w --threads 1
python scripts/simulation/test_mujoco_pipeline_go2wcr.py
python scripts/simulation/test_mujoco_pipeline_go2wwmp.py --check-only
MUJOCO_GL=egl python scripts/simulation/test_mujoco_pipeline_go2wwmp.py --headless-frames 6
python scripts/real/test_policy_go2wcr_real.py
```

真实机器人脚本必须在架子或吊绳保护下执行；`setup.sh policy/mujoco` 不配置 DDS 网卡。

`scripts/` 根目录不再保留重复的启动脚本。运行前请先按项目说明执行 `setup.sh`，然后直接使用上表和下方列出的分类路径；文档中的路径均为实际文件路径。
