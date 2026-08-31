# WMP-1：go2wwmp MuJoCo 仿真验证

本步骤只验证 `go2wwmp` 的模型加载、深度输入、world model、policy 和 MuJoCo `MotorCommand` 链路，不连接机器人，不发送 LowCmd 或 Sport Mode。

## 1. 源码对应关系

网络源码和配置最初依据 `/home/robot/simtosim` 中以下文件，现已直接拷贝到当前项目：

- `src/controller/scripts/lib/controller_go2wwmp/controller_go2wwmp.py`：观测、5 帧历史、5 周期 world-model 更新和动作缩放；
- `src/controller/scripts/lib/actor_critic_wmp.py`：WMP actor 结构；
- `src/controller/scripts/lib/dreamer/models.py`、`networks.py`、`tools.py`：world model；
- `src/controller/scripts/lib/controller_go2wwmp/go2wwmp_configs.yaml`：world-model 配置；
- `models/go2wwmp/model_1750.pt`：当前项目中的 Actor/world-model checkpoint；该文件被 `.gitignore` 忽略，不进入 Git；
- `src/controller/model/go2wwmp/go2wwmp.py`、`playwmp.py`、`wmp_runner.py`：训练环境、播放和训练恢复语义的参考。

当前项目的 `policy/controller_go2wwmp.py` 不引入 simtosim 的 ROS1 或 Isaac Gym 运行依赖；Actor、Dreamer 网络和配置均已内置。checkpoint 从 simtosim 拷贝到当前项目后只保存在本机，不进入 Git。
配置读取使用 PyYAML；如果当前 Python 环境没有 `yaml` 模块，先由用户审查依赖安装方案。
带窗口运行还需要当前 Python 环境中的 `cv2`；本机已验证 OpenCV 4.13.0 可导入。

## 2. 先做无窗口检查

在项目根目录执行：

```bash
source setup.sh policy
python scripts/simulation/test_mujoco_pipeline_go2wwmp.py --check-only
```

通过时应看到：

- `obs_now=53`；
- `history=250`；
- `wm_feature=512`；
- `action=16`；
- 成功打印 DDS 顺序的 16 路 `MotorCommand`。

该命令不会加载 MuJoCo 场景、打开窗口或接触机器人，适合先由用户审查网络输入输出。

## 3. MuJoCo 闭环

```bash
source setup.sh mujoco
python scripts/simulation/test_mujoco_pipeline_go2wwmp.py --vx 0.0
```

按空格暂停/继续，按 `Ctrl+C` 退出。程序把场景中的 `depth_camera` 固定到已经确认的基座坐标
`[0.34, -0.0375, 0.09]`，深度图渲染为 64×64 米制深度，再按训练环境的 `[0, 2 m] → [0, 1]`
规则输入 WMP。
当前 XML 相机光轴沿基座 `+x` 并向下俯视 5°。

运行时会打开 `go2wwmp depth` OpenCV 窗口，以约 10 Hz 显示当前黑白深度图；按 `q` 或 `Esc`
可退出。若只做无窗口的 MuJoCo 检查，可增加 `--no-depth-display`。

也可以限制策略帧数，便于小规模观察：

```bash
python scripts/simulation/test_mujoco_pipeline_go2wwmp.py --frames 20 --vx 0.0
```

如果模型不在默认位置，用显式参数指定：

```bash
python scripts/simulation/test_mujoco_pipeline_go2wwmp.py \
  --model models/go2wwmp/model_1750.pt \
  --frames 20
```

## 4. 深度归一化审查

当前入口固定使用训练语义：深度先按 `[0, 2 m] → [0, 1]` 归一化，再由 world-model 的卷积编码器
内部完成中心化。旧 ROS 链路中额外的 `0.5` 偏移不再保留，也不再作为可选输入模式。

真实 D435i 接入前仍需单独确认：深度流格式、有效距离、无效值、分辨率、缩放/裁剪、相机方向和时间同步。不能把 Viewer 中的灰度画面直接送入 WMP。

## 5. 当前验证边界

- 已完成：checkpoint 严格加载、CPU world model 构造、单步观测/动作和 6 帧无窗口 WMP 推理；
- 待图形环境具备后：实际 MuJoCo viewer、depth_camera 渲染和闭环姿态表现；
- 未完成也不在本步骤执行：Orin D435i 实机采集、LowCmd、Sport Mode、真实机器人动作。

任何实机代码或相机输入适配，都必须先保留清晰注释并由用户审查。
