# WMP-1：go2wwmp MuJoCo 仿真验证

本步骤只验证 `go2wwmp` 的模型加载、深度输入、world model、policy 和 MuJoCo `MotorCommand` 链路，不连接机器人，不发送 LowCmd 或 Sport Mode。

## 1. 源码对应关系

网络源码和配置最初依据 `/home/robot/simtosim` 中以下文件，现已直接拷贝到当前项目：

- `src/controller/scripts/lib/controller_go2wwmp/controller_go2wwmp.py`：观测、5 帧历史、5 周期 world-model 更新和动作缩放；
- `src/controller/scripts/lib/actor_critic_wmp.py`：WMP actor 结构；
- `src/controller/scripts/lib/dreamer/models.py`、`networks.py`、`tools.py`：world model；
- `src/controller/scripts/lib/controller_go2wwmp/go2wwmp_configs.yaml`：world-model 配置；
- `models/go2wwmp/model_6000.pt`：当前 simulation pipeline 默认的 Actor/world-model checkpoint；该文件被 `.gitignore` 忽略，不进入 Git；
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

随后运行自动回归测试：

```bash
python -m unittest tests/test_go2wwmp_pipeline.py -v
```

它检查深度数值范围、无效值、yaw command 的 0.25 缩放、启动历史，以及 RSSM 每次收到的
连续 5 帧动作顺序。

## 3. 无窗口 MuJoCo 全链路

Linux 主机即使没有桌面，也可以用 EGL 验证真实 MuJoCo depth renderer：

```bash
source setup.sh policy
MUJOCO_GL=egl python scripts/simulation/test_mujoco_pipeline_go2wwmp.py \
  --headless-frames 6 --vx 0.0
```

这会实际加载场景、渲染 64×64 米制深度、运行 WMP，并把 `MotorCommand` 施加回 MuJoCo。
通过标准包括：相机位置/FOV/光轴检查通过，深度与动作均为有限值，且闭环结束时没有
NaN/Inf。EGL 是否可用取决于目标设备的 MuJoCo/OpenGL 安装。

## 4. MuJoCo viewer 闭环

```bash
source setup.sh mujoco
python scripts/simulation/test_mujoco_pipeline_go2wwmp.py --vx 0.0
```

按空格暂停/继续，按 `Ctrl+C` 退出。程序核对场景中的 `depth_camera` 是否位于已经确认的基座坐标
`[0.34, -0.0375, 0.09]`，并同时核对 58° FOV 和光轴；任一项不一致就停止，不会静默改写场景。
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
  --model models/go2wwmp/model_6000.pt \
  --frames 20
```

当前已验证的 5500 和 6000 都可以使用；默认是 6000。完整差异、深度公式和时序说明见
[`12_go2wwmp_pipeline_review.md`](12_go2wwmp_pipeline_review.md)。

## 5. 深度与时序审查

当前边界固定为：simulation pipeline 向 controller 传 64×64 米制深度，controller 统一执行：

1. NaN、`+Inf`、`-Inf` 按 2 m 远平面处理；
2. 裁剪到 `[0, 2 m]`；
3. 除以 2 并减 0.5，得到训练环境实际使用的 `[-0.5, 0.5]`；
4. Dreamer `ConvEncoder` 按原 checkpoint 网络结构还会再减 0.5。

第 3 步不能删除。训练环境 `normalize_depth_image()` 明确包含该偏移，旧 ROS controller 的
`CallbackDepth()` 也执行了同样处理。此前把 `[0,1]` 直接送进 world model 的版本会导致固定
`+0.5` 的输入分布偏移。

world model 每 5 个 50 Hz policy 周期更新一次，即 10 Hz。MuJoCo 只在这些帧渲染新深度；
controller 仍在每个 policy 周期记录动作，所以 RSSM 更新时收到连续的
`[a0, a1, a2, a3, a4]`，而不是只有最后一帧。

训练环境的 `depth_buffer` 长度为 2，并在更新时选择 `-2` 帧。因此 controller 首次使用当前深度，
此后使用上一张 10 Hz 深度，显式复现约 100 ms 的训练相机延迟；当前图像仍被保存为下一次输入。

真实 D435i 接入前仍需单独确认：深度流格式、有效距离、无效值、分辨率、缩放/裁剪、相机方向和时间同步。不能把 Viewer 中的灰度画面直接送入 WMP。

## 6. 当前验证边界

- 已完成：checkpoint 严格加载、CPU world model、单元回归、EGL depth renderer，以及默认 `model_6000.pt` 在 `vx=0.6` 下的 300 帧无窗口 MuJoCo 闭环；
- 待图形环境具备后：实际 MuJoCo viewer 的长时间姿态与越障表现；
- 未完成也不在本步骤执行：Orin D435i 实机采集、LowCmd、Sport Mode、真实机器人动作。

任何实机代码或相机输入适配，都必须先保留清晰注释并由用户审查。
