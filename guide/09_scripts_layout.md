# scripts 目录管理

脚本按用途放入五个子目录，避免环境、离线检查、仿真和实机入口混在一起：

| 目录 | 内容 |
|---|---|
| `scripts/setup/` | Orin 环境安装和只读验证 |
| `scripts/policy/` | go2w/go2wcr 模型离线验证 |
| `scripts/simulation/` | go2w/go2wcr/go2wwmp MuJoCo 闭环 |
| `scripts/input/` | 键盘、Xbox、原装遥控器输入检查 |
| `scripts/real/` | DDS 只读检查和 go2w/go2wcr 实机控制 |

`scripts/` 根目录不保留重复的启动脚本，运行时直接调用上述分类目录中的实际文件。项目文档统一使用这些分类路径；不要再使用旧的 `scripts/test_*.py` 或 `scripts/debug_*.py` 根目录路径。只有 `scripts/input/debug_unitree_remote.py` 和 `scripts/real/` 下的入口会访问机器人 DDS，`setup/`、`policy/` 与 `simulation/` 不应连接实机。

新增 CRRL 文件如下：

- `scripts/policy/test_policy_go2wcr_offline.py`
- `scripts/simulation/test_mujoco_pipeline_go2wcr.py`
- `scripts/simulation/test_mujoco_pipeline_go2wwmp.py --check-only`
- `scripts/real/test_policy_go2wcr_real.py`
- `scripts/real/test_policy_go2wcr_unitree_remote.py`

从项目根目录运行时，直接使用实际文件路径，例如：

```bash
python scripts/policy/test_policy_go2wcr_offline.py
python scripts/simulation/test_mujoco_pipeline_go2wcr.py
python scripts/real/test_policy_go2wcr_real.py
```
