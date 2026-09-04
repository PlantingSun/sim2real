# CRRL-2：go2wcr MuJoCo 仿真测试

## 目标

验证 `MujocoDriver`、`ControllerGo2wCR` 和 `MotorCommand` 可以闭环运行。仿真驱动和 DDS 驱动共享同一外部接口，因此本步骤不连接机器人。

## 执行

```bash
cd /home/unitree/sim2real
source setup.sh mujoco

# 零速站立
python scripts/simulation/test_mujoco_pipeline_go2wcr.py --vx 0.0

# 慢速前进；首次只使用很小速度
python scripts/simulation/test_mujoco_pipeline_go2wcr.py --vx 0.2
```

场景或模型可显式指定：

```bash
python scripts/simulation/test_mujoco_pipeline_go2wcr.py \
  assets/go2w_description/mjcf/go2w_scene.xml \
  --model models/go2wcr/model_1499.pt
```

空格暂停/继续，Ctrl+C 退出。仿真入口不会初始化 DDS。

场景加载完成后，程序会在等待第一次按空格期间恢复 XML 的 `stand` keyframe：base 高度为
`z=0.43 m`，16 个关节为 `CTRL.INITIAL_JOINTS_POS`，并执行一次 `mj_forward()`；初始
画面和正式仿真都从站立姿态开始。

## 通过标准

- MuJoCo 场景和模型加载成功。
- 零速时机器人不出现持续放大的姿态振荡。
- 非零 `vx` 时机器人运动方向正确；再逐一测试 `vy`、`vyaw`。
- 没有 NaN/Inf、异常关节目标或明显轮速失控。
- 记录仿真中动作和轮速的峰值，作为实机吊架测试的初始观察项。

## 人工复核点

训练环境中的 assist force、pitch/roll spring 只在 Isaac Gym 训练阶段存在；本部署控制器不会把它们伪装成实机补偿。仿真稳定也不能替代吊架实测。
