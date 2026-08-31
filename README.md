# sim2real_ws — Go2W Sim-to-Real 部署

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
cd /home/robot/sim2real_ws
source setup.sh policy
python scripts/policy/test_policy_offline.py

# MuJoCo（不需要 ROS2，也不会连接机器人）
source setup.sh mujoco
python scripts/simulation/test_mujoco_pipeline.py
python scripts/simulation/test_mujoco_pipeline_go2wwmp.py --check-only

# 实机 DDS（setup 只检查依赖；运行下面脚本才会打开机器人网络）
source setup.sh robot
python scripts/real/test_dds_driver.py
python scripts/real/test_policy_real.py --control keyboard
python scripts/real/test_policy_real.py --control xbox --joystick /dev/input/js0
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
使用 `models/go2wwmp/model_1750.pt`，不会自动复制或下载。

## 依赖

- Python 3.8+ (conda unitree_py38)
- PyTorch (CPU)
- PyYAML（仅 go2wwmp world model 配置读取）
- OpenCV/cv2（仅 go2wwmp 深度画面显示）
- unitree_sdk2py + CycloneDDS 0.10.x
- MuJoCo 3.1.0+ (仅仿真)

Unitree SDK2 Python 源码和 CRC 本地库已随项目提供；CycloneDDS、Python、NumPy、
PyTorch、OpenCV 和 MuJoCo 仍属于目标设备上的运行环境依赖，需要按设备架构安装。

迁移说明：项目内的 MuJoCo 资源位于 `assets/go2w_description`，Unitree SDK2 Python
源码位于 `third_party/unitree_sdk2_python`。策略权重因体积被 `.gitignore` 忽略，迁移时
需要另行复制 `models/README.md` 中列出的本地 checkpoint。

当前管线不依赖 ROS2；旧 `simtosim_ws` 的 ROS 节点应使用它自己的环境。

D435i 在 Orin NX 本地图形桌面采集和显示的只读流程见
[`guide/10_realsense_network_view.md`](guide/10_realsense_network_view.md)。该流程不接入机器人控制。

如果还没有使用过机载 Orin NX，请先阅读
[`orin_nx_onboarding/README.md`](orin_nx_onboarding/README.md)，从硬件连接、登录和文件传输开始。

当前架构、接管顺序和安全边界见
[`guide/00_overview.md`](guide/00_overview.md)。
