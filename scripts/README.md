# scripts 目录约定

脚本按“会不会连接机器人”和“验证哪一层”分为四类。所有可执行实现都放在子目录中，运行时直接调用对应分类目录内的文件。

| 目录 | 用途 | 是否连接机器人 |
|---|---|---:|
| `policy/` | go2w/go2wcr 模型加载、观测和动作离线检查 | 否 |
| `simulation/` | go2w/go2wcr 的 MuJoCo 闭环测试 | 否 |
| `input/` | 键盘、Xbox、原装遥控器输入映射检查 | 只有 `debug_unitree_remote.py` 订阅 LowState |
| `real/` | DDS 驱动只读检查、go2w/go2wcr 实机接管 | 是 |

建议按以下顺序执行：

1. `policy/` 离线检查
2. `simulation/` MuJoCo 检查
3. `input/` 输入设备检查
4. `real/` 实机测试

CRRL 对应入口：

- `policy/test_policy_go2wcr_offline.py`
- `simulation/test_mujoco_pipeline_go2wcr.py`
- `real/test_policy_go2wcr_real.py`
- `real/test_policy_go2wcr_unitree_remote.py`

例如，在项目根目录执行：

```bash
python scripts/policy/test_policy_go2wcr_offline.py
python scripts/simulation/test_mujoco_pipeline_go2wcr.py
python scripts/real/test_policy_go2wcr_real.py
```

真实机器人脚本必须在架子或吊绳保护下执行；`setup.sh policy/mujoco` 不配置 DDS 网卡。

`scripts/` 根目录不再保留重复的启动脚本。运行前请先按项目说明执行 `setup.sh`，然后直接使用上表和下方列出的分类路径；文档中的路径均为实际文件路径。
