# sim2real — Go2W 机载 Orin NX Sim-to-Real 部署

Unitree Go2W 机器人 sim-to-real 控制系统。不使用 ROS/ROS2，纯 Python + PyTorch。

## 架构

```
driver/         关节驱动层 (DDS 实物 / MuJoCo 仿真)
policy/         网络推理层 (纯 PyTorch, 无 ROS)
config/         常量/映射/安全限制
assets/         项目内 MuJoCo XML 和 Go2W 网格
third_party/    项目内 Unitree SDK2 Python 源码
```

安全逻辑嵌入 driver 的 500Hz 发布循环，不单独开线程。

## 快速开始

```bash
cd /home/unitree/sim2real
source setup.sh policy
python scripts/policy/test_policy_offline.py
python scripts/policy/benchmark_policy_latency.py --policy go2w --threads 1

# MuJoCo（不需要 ROS2，也不会连接机器人）
source setup.sh mujoco
python scripts/simulation/test_mujoco_pipeline.py
python scripts/simulation/test_mujoco_pipeline_go2wwmp.py --check-only
MUJOCO_GL=egl python scripts/simulation/test_mujoco_pipeline_go2wwmp.py --headless-frames 6

# 实机 DDS（setup 只检查依赖；运行下面脚本才会打开机器人网络）
source setup.sh robot
python scripts/real/test_dds_driver.py
python scripts/real/test_policy_real.py --control keyboard
python scripts/real/test_policy_real.py --control xbox
python scripts/real/test_policy_unitree_remote.py
```

固定速度模式仍兼容：`python scripts/real/test_policy_real.py --vx 0.1`。键盘/Xbox
可以先用 `scripts/input/debug_command_input.py` 离线检查。原装遥控器用
`scripts/input/debug_unitree_remote.py` 只读订阅检查；确认数据后使用
`scripts/real/test_policy_unitree_remote.py` 触发接管和控制 policy。

CRRL/go2wcr 的分步入口和人工复核标准见：
[`guide/06_crrl_policy_test.md`](guide/06_crrl_policy_test.md)、
[`guide/07_crrl_simulation_test.md`](guide/07_crrl_simulation_test.md)、
[`guide/08_crrl_real_test.md`](guide/08_crrl_real_test.md)。脚本目录约定见
[`scripts/README.md`](scripts/README.md)。

go2wwmp 的网络、深度输入和 MuJoCo pipeline 验证见
[`guide/11_wmp_simulation_test.md`](guide/11_wmp_simulation_test.md)。默认 checkpoint
使用 `models/go2wwmp/model_6000.pt`，不会自动复制或下载。
本轮深度公式、5500/6000 选择、时序 bug 和验证结果详见
[`guide/12_go2wwmp_pipeline_review.md`](guide/12_go2wwmp_pipeline_review.md)。

## Orin NX 环境

- 项目内 `.venv`，基于系统 Python 3.8.10；不使用 Conda 或 Python 3.9
- PyTorch 2.0.0 CPU-only、NumPy 1.24.4、MuJoCo 3.2.3
- 项目内 Unitree SDK2 Python + CycloneDDS 0.10.2
- 复用 JetPack 系统 OpenCV 4.2.0 和 PyYAML 5.3.1

安装、环境复建、VS Code 和验证步骤见
[`guide/12_orin_environment.md`](guide/12_orin_environment.md)。`setup.sh` 已固定为
Orin NX 专用入口，并隔离系统全局 ROS Foxy 的 Python 和 CycloneDDS 0.7 路径。
go2w/go2wcr 已在 25W 模式通过 50 Hz CPU 延时门槛；WMP 的周期性 world-model 帧仍超时。
完整数据见 [`guide/13_orin_policy_benchmark.md`](guide/13_orin_policy_benchmark.md)。

迁移说明：项目内的 MuJoCo 资源位于 `assets/go2w_description`，Unitree SDK2 Python
源码位于 `third_party/unitree_sdk2_python`。策略权重因体积被 `.gitignore` 忽略，迁移时
需要另行复制 `models/README.md` 中列出的本地 checkpoint。

当前管线不依赖 ROS2；旧 `simtosim_ws` 的 ROS 节点应使用它自己的环境。

D435i 在 Orin NX 本地图形桌面采集和显示的只读流程见
[`guide/10_realsense_network_view.md`](guide/10_realsense_network_view.md)。该流程不接入机器人控制。

如果还没有使用过机载 Orin NX，请先阅读
[`orin_nx_onboarding/README.md`](orin_nx_onboarding/README.md)，从硬件连接和登录开始。

当前架构、接管顺序和安全边界见
[`guide/00_overview.md`](guide/00_overview.md)。
