# Step 3: 仿真全流程测试

## 目标

在 MuJoCo 中跑通 driver + policy 完整流程，验证集成正确。

## 前置条件

- MuJoCo 3.1.0+ 已安装
- Step 2 通过

## 步骤

### 1. 安装 MuJoCo (如未安装)

```bash
pip install mujoco
```

### 2. 运行仿真

```bash
cd /home/robot/sim2real_ws
source setup.sh mujoco

# 零速站立测试
python scripts/simulation/test_mujoco_pipeline.py "" 0.0

# 慢速行走测试
python scripts/simulation/test_mujoco_pipeline.py "" 0.2
```

默认场景和 STL 网格来自项目内的 `assets/go2w_description`，不依赖外部 MuJoCo 工作空间。

这里直接使用 Python MuJoCo，不 source ROS2，也不会初始化 DDS 或连接实机。

程序加载场景后会恢复 XML 中的 `stand` keyframe：base 高度为 `z=0.43 m`，16 个关节
为 `CTRL.INITIAL_JOINTS_POS`，并保持暂停状态；因此在第一次按空格前，机器人已经显示
为初始站姿，而不是所有关节角度为 0 的竖直姿态。

策略控制器初始化时会将 5 帧历史填充为初始站立零运动状态，而不是数值全零帧：投影重力为
`(0, 0, -1)`，关节位置偏差、关节速度、角速度、指令和上一动作均为 0。

共享 `go2w.xml` 已直接包含 D435i 的可视化标记：蓝色长方体和红色深度镜头中心均为基座局部坐标
`[0.34, -0.0375, 0.09]`，镜头朝向基座 `+x`。标记属于 XML 中的非碰撞 geom，会随基座移动和转动；
`test_mujoco_pipeline.py` 本身不再绘制 D435i。
XML 中的 `depth_camera` 位置相同，光轴沿 `+x` 并向下俯视 5°。

### 3. 观察

- MuJoCo viewer 中机器人应维持站姿
- vx=0.2 时机器人向前行走
- 腿关节和轮子协调运动
- 按空格键暂停/继续

## 通过标准

- 机器人站姿稳定，不倒下
- cmd_vel 非零时平稳行走
- 无关节抖动或异常角度
