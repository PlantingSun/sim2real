# WMP-2：Go2WWMP simulation pipeline 复审与修复记录

本文记录 2026-09-04 对 `/home/robot/simtosim/src` 训练、播放、ROS controller 和 MuJoCo
深度发布代码的逐层复审结果。目标是让当前 sim2real pipeline 的输入数值和时序与 WMP
checkpoint 的训练语义一致。

本步骤只涉及离线推理和 MuJoCo，不初始化 DDS，不发送 LowCmd 或 Sport Mode 指令。

## 1. 当前结论

- `model_5500.pt` 和 `model_6000.pt` 均能严格加载并运行完整 MuJoCo 深度闭环；当前默认使用 6000。
- simulation pipeline 向 controller 传入 `64×64` 的正数米制深度，不在调用侧归一化或减 0.5。
- controller 内部必须执行 `clip(depth_m, 0, 2) / 2 - 0.5`。
- 上式中的 `-0.5` 是训练环境已有的必要步骤，不能删除；但也不是把整张图固定设为 `-0.5`。
- Dreamer `ConvEncoder` 按原网络代码还会再执行一次 `obs -= 0.5`。这看起来像两次中心化，
  但 checkpoint 就是在这一数值链路上训练的，部署阶段不能单方面“修正”网络结构。
- world model 是 10 Hz，policy 是 50 Hz；RSSM 每次更新必须收到连续 5 个 policy action。
- 训练相机使用两帧 depth buffer，并选择上一张图；当前实现复现了约 100 ms 的深度延迟。

## 2. Checkpoint 选择

默认模型：

```text
models/go2wwmp/model_6000.pt
```

5500 和 6000 使用同一网络结构，均已通过 strict state-dict 加载。可以显式切换：

```bash
source setup.sh policy

MUJOCO_GL=egl python scripts/simulation/test_mujoco_pipeline_go2wwmp.py \
  --model models/go2wwmp/model_5500.pt --headless-frames 6 --vx 0.6

MUJOCO_GL=egl python scripts/simulation/test_mujoco_pipeline_go2wwmp.py \
  --model models/go2wwmp/model_6000.pt --headless-frames 6 --vx 0.6
```

不要仅凭编号判断哪个模型更好。最终应在同一场景、同一命令、同一随机种子和相同运行长度下，
比较摔倒次数、base 姿态、横向漂移、轮速峰值和通过楼梯的成功率。

## 3. 深度为什么必须减 0.5

### 3.1 训练环境的真实处理

Isaac Gym 训练环境取得的是负号表示的米制深度。`go2wwmp.py` 的处理顺序为：

```text
Isaac Gym depth（负米制）
→ 裁剪到 [-2, 0]
→ 乘以 -1，变为 [0, 2] m
→ 除以 2
→ 减去 0.5
→ world-model image，范围 [-0.5, 0.5]
```

MuJoCo `Renderer` 返回正数米制深度，因此当前 controller 使用等价公式：

```text
depth_train = clip(depth_m, 0 m, 2 m) / 2 m - 0.5
```

典型数值如下：

| 米制深度 | 进入 world model 前 |
|---:|---:|
| 0.0 m | -0.50 |
| 0.5 m | -0.25 |
| 1.0 m | 0.00 |
| 1.5 m | +0.25 |
| ≥2.0 m | +0.50 |

因此，“应该要 `-0.5`”的准确含义是：归一化后还要减去 `0.5`。不是所有像素都改成
`-0.5`，也不是调用 `controller.step()` 前手动把米制图减去 `0.5`。

### 3.2 为什么 encoder 还会再减一次

`policy/dreamer/networks.py` 中的 `ConvEncoder.forward()` 有原地操作：

```python
obs -= 0.5
```

所以卷积层实际看到的范围为 `[-1, 0]`：

```text
clip(depth_m, 0, 2) / 2 - 0.5 - 0.5
```

训练环境在 encoder 前已经减过一次，encoder 又减一次；训练 runner、playback 和 checkpoint
共同证明这是训练时的真实链路。此前将 `[0,1]` 直接送入 encoder，会让卷积输入整体增加
`0.5`，与训练分布不一致。

### 3.3 无效值和 D435i 注意事项

- MuJoCo 远处或无命中像素可大于 2 m，统一裁剪为 2 m，对应 `+0.5`。
- NaN、`+Inf`、`-Inf` 按远平面 2 m 处理，避免把无命中误认为贴近相机的障碍。
- D435i 的无效深度通常可能以数值 0 表示。0 m 在当前公式中代表最近距离并映射为 `-0.5`，
  因此以后接实物相机时，采集适配层必须先识别“无效 0”，将其替换为 2 m 或采用经审查的
  hole-filling 方案；不能直接把原始 D435i 数组送入 controller。
- 当前 simulation pipeline 没有对深度图转置、翻转或按 RGB 对齐。MuJoCo 实测图像上方为远景、
  下方为地面，与训练相机的图像方向一致。

## 4. 深度和动作的时间关系

训练设置：

```text
policy:       50 Hz，每 20 ms 一次
depth/WMP:    10 Hz，每 5 个 policy step 一次
depth buffer: 2 张，world model 选择上一张
```

当前实现首次使用当前深度初始化缓存；此后每次 world-model 更新消费上一张 10 Hz 深度，
同时保存当前图供下一次使用，等价于约 100 ms 的相机延迟。

动作历史必须每 20 ms 写入一次：

```text
第 1 次 RSSM 更新：初始零动作历史
第 2 次 RSSM 更新：[a0, a1, a2, a3, a4]
第 3 次 RSSM 更新：[a5, a6, a7, a8, a9]
```

旧 controller 只在 10 Hz 更新时写入一次动作，第二次实际得到 `[0,0,0,0,a4]`，已修复。

由于 ConvEncoder 使用原地减法，延迟缓存和传给 Torch 的数组必须断开共享内存。当前实现对
缓存值和返回值都进行复制，避免上一张图在下一次使用时被再次减去 0.5。

## 5. 其他观测修复

- yaw command 按训练配置乘以 `0.25`；`vx`、`vy` 保持 1.0 缩放。
- WMP 五帧本体历史恢复为训练 runner 的初始化方式：四帧全零，再插入当前一帧观测。
- prop 观测增加 NaN/Inf 检查，并按训练配置裁剪到 `[-100,100]`。
- Actor action 在写入历史和转换 MotorCommand 前裁剪到 `[-100,100]`。
- `--check-only` 的初始关节数据先从 Ctrl 顺序转换成 DDS 顺序，避免 controller 二次重排后
  得到错误的“站立状态”。

## 6. 相机和仿真入口修复

程序启动时检查以下训练参数，不再静默覆盖 XML：

- 基座局部位置：`[0.34, -0.0375, 0.09] m`；
- 64×64 方形图像的 FOV：58°；
- 光轴：沿基座 `+x`，向下 5°。

新增 `--headless-frames` 后，可以在没有 GLFW viewer 的环境里实际运行：

```text
MuJoCo physics
→ depth Renderer
→ 米制深度预处理和延迟缓存
→ Dreamer world model
→ WMP Actor
→ DDS 顺序 MotorCommand
→ 回写 MuJoCo actuator
```

这比 `--check-only` 更完整；`--check-only` 只用于快速验证 checkpoint 和一帧网络接口。

## 7. 本轮验证结果

- `model_5500.pt`：strict load 和 6 帧 EGL MuJoCo 闭环通过。
- `model_6000.pt`：strict load 和 6 帧 EGL MuJoCo 闭环通过。
- `model_6000.pt`、`vx=0`：100 帧闭环通过。
- `model_6000.pt`、`vx=0.6`：300 帧/6 s 闭环通过；最终 base 约为
  `[4.268, 0.227, 0.396] m`，越过楼梯所在的 x=0.8–3.3 m 范围。
- 6 项自动测试通过：深度范围/无效值、深度延迟与缓存隔离、yaw 缩放、启动历史、连续动作历史、
  深度更新节拍。
- Go2W 和 Go2WCR 原有离线回归通过。
- 未执行任何实机通信或机器人动作。

## 8. 仍需人工确认

无窗口闭环证明数值链路和物理循环可以运行，但不能替代视觉审查。下一步在图形桌面分别运行
5500 和 6000，观察站姿、轮速方向、横向漂移、接近台阶时的动作以及上下台阶过程：

```bash
source setup.sh mujoco

python scripts/simulation/test_mujoco_pipeline_go2wwmp.py \
  --model models/go2wwmp/model_5500.pt --vx 0.6

python scripts/simulation/test_mujoco_pipeline_go2wwmp.py \
  --model models/go2wwmp/model_6000.pt --vx 0.6
```

在完成上述对照和日志记录前，不应仅根据一次无窗口轨迹决定实机 checkpoint。
