# 笔记本接收 Go2W 机载深度

本页用于依次验收：基础接收、实时可视化、5 分钟稳定性和 Go2WWMP 后处理。

所有命令只订阅深度专用的 CycloneDDS domain 42，不初始化机器人 domain 0，不发送 LowCmd，
也不调用 Sport Mode。完成当前四项验收前，不进入实机策略控制。

## 1. 准备

### 1.1 笔记本环境

在笔记本执行：

```bash
cd /home/robot/sim2real_ws
source setup.sh robot
unset CYCLONEDDS_URI ROS_DOMAIN_ID LD_PRELOAD
python -c 'import cyclonedds, numpy, cv2; print("depth laptop environment OK")'
```

这里的 `source setup.sh robot` 只配置现有 Python 和动态库；`unset` 清掉为电机 domain 0 准备的
CycloneDDS 环境，保证下面的 Python 进程只使用深度 domain 42。本页后续直接运行 Python，
不依赖 wrapper 自动寻找环境。若没有先执行这一段，请不要直接复制后面的命令。

这只是本页“深度单独验收”的隔离措施，不代表 domain 0 和 domain 42 不能并存。最终实机部署时，
电机进程可以继续持有 domain 0，深度/WMP 进程持有 domain 42；也可以在同一 Python 进程中创建
两个不同 domain 的 participant。两种 domain 使用同一有线网卡即可，但每个 participant 必须明确
自己的 domain、topic、QoS 和网络配置。

`scripts/depth/run_receiver.sh`、`run_acceptance.sh` 和 `run_inspect_sample.sh` 仍保留给独立
脚本调用使用；它们的作用只是自动解析 Python 环境和清理动态库，不会提供额外的 DDS 功能。

确认笔记本实际使用的有线网卡：

```bash
ip -br addr
ip route
ping -c 3 192.168.123.18
```

当前笔记本固定网口已写入 `config/go2w_config.py` 的 `DDS.LAPTOP_NET_IF`，深度接收默认读取
`DDS.DEPTH_NET_IF`，不需要每次 export。只有更换网线拓扑时才显式传 `--interface` 覆盖。

### 1.2 Orin 发布状态

在 Orin 执行：

```bash
systemctl status go2w-depth.service --no-pager
journalctl -u go2w-depth.service -n 20 --no-pager
```

继续测试前，日志应有 `CONNECTED` 和持续更新的 `STATS`。

## 2. 四步验收

每一步通过后再执行下一步。重复测试时更换输出文件或目录名称，避免覆盖已有证据。

### 2.1 基础接收：30 秒

```bash
python -m depth.receiver --duration 30 \
  --output logs/depth/laptop_receive_step1.jsonl \
  --save-sample logs/depth/laptop_receive_step1.npz
```

通过条件：

- 很快出现 `"event": "first_frame"`；
- `shape` 为 `[64,64]`，`dtype` 为 `float32`；
- `depth_min_m` 和 `depth_max_m` 位于 `[0,2]`；
- 最终出现 `"event": "final"` 和 `"received_any": true`；
- 命令退出码为 0。

若 30 秒内没有新鲜帧，程序打印 `No fresh depth frame was received.` 并返回退出码 2。

### 2.2 实时可视化

```bash
python -m depth.receiver --preview
```

窗口包含：

- 米制深度：0 m 为黑、2 m 为白，无效像素为紫色；
- 有效掩码：白色有效、黑色无效。

最底部一行已使用最近的真实传感器边缘数据，不应再固定整行无效。画面方向应与肉眼一致：左侧物体显示在左侧，
上方物体显示在上方。`STALE / NO DATA` 表示 100 ms 内没有新鲜帧。按 `q` 或 `Esc` 退出。

### 2.3 稳定性：300 秒

输出目录必须不存在：

```bash
python scripts/depth/acceptance.py --duration 300 \
  --wmp-postprocess --output-dir logs/depth/laptop_cable_5min_01
```

检查 `logs/depth/laptop_cable_5min_01/summary.json`：

- `fps_pass: true`：每个完整窗口至少 50 Hz；
- `gap_pass: true`：最大接收间隔不超过 100 ms；
- `integrity_pass: true`：没有重复、逆序、畸形或机载处理超时；
- `wmp_pass: true`、`wmp_failures: 0`；
- 命令退出码为 0。

同时记录 `min_new_frame_hz`、`max_gap_ms` 和各窗口的 `missing`。`missing` 是源帧号缺口，
可能来自相机、机载最新帧覆盖或网络，不能单独把它认定为网线丢包。

### 2.4 Go2WWMP 后处理

```bash
python -m depth.receiver --duration 30 \
  --wmp-postprocess --preview \
  --save-sample logs/depth/laptop_wmp_step4.npz
```

窗口会增加 WMP 输入面板。通过条件：

- `wmp_shape` 为 `[64,64]`，`wmp_dtype` 为 `float32`；
- `wmp_min` 和 `wmp_max` 位于 `[-0.5,0.5]`；
- NPZ 同时包含原始 `depth_m`、`valid` 和处理后的 `depth_wmp`。

离线保存检查图：

```bash
python scripts/depth/inspect_sample.py \
  logs/depth/laptop_wmp_step4.npz \
  --output logs/depth/laptop_wmp_step4.png
```

## 3. 当前数据约定

| 项目 | 当前值 |
|---|---|
| DDS domain | 42，与电机 domain 0 隔离 |
| Topic | `rt/depth/image64` |
| Type | `go2w_depth::DepthFrame` v1 |
| QoS | BEST_EFFORT、KEEP_LAST(1)、VOLATILE |
| 深度 | `float32 (64,64)`，米制光轴 Z 深度，范围 `[0,2]` |
| 有效掩码 | `uint8 (64,64)`，仅允许 0/1；无效像素的深度必须为 2 m |
| 图像方向 | 上方朝上、左侧朝左，不翻转、不转置 |
| 空间模型 | 58°×58°；轻微越界的底行采样最近真实传感器边缘，不做加权平均 |

接收器只保留最新帧，拒绝版本错误、非有限值、越界深度、非法掩码、重复帧和逆序帧。
`get_latest(max_age_ms=100)` 在接收端判断帧是否新鲜；该判断不包含未经校时证明的跨机单向延迟。

WMP 后处理固定为：

```text
depth_wmp = clip(depth_m, 0 m, 2 m) / 2 m - 0.5
```

实现位于 `depth/postprocess.py`，接收验收工具和 `ControllerGo2wWMP` 共用这一份代码。
以后调用 `ControllerGo2wWMP.step()` 时仍传入米制 `depth_m`，不能传入已经处理的 `depth_wmp`，
否则会发生二次后处理。World model 仍按 simulation 已确认的节奏，每 5 个 50 Hz policy 周期更新一次。

## 4. 接入代码示例

```python
from config.go2w_config import DDS
from depth.receiver import DepthReceiver

with DepthReceiver(interface=DDS.DEPTH_NET_IF, domain=42) as receiver:
    sample = receiver.get_latest(max_age_ms=100)
    if sample is None:
        depth_available = False
    else:
        depth_available = True
        depth_m = sample.depth_m   # 传给 ControllerGo2wWMP.step()
        valid = sample.valid       # 仅用于质量检查
```

相机停止、网络中断、接收线程异常或会话切换都必须由后续控制状态机按 fail-closed 处理；
不能长期复用旧深度，也不能让异常直接穿过实时控制线程。

## 5. 排障

无法收图时按顺序检查：

1. Orin journal 是否仍有 `CONNECTED` 和持续更新的 `STATS`；
2. 两端 IP、网卡和路由是否正确，笔记本能否 ping 通 `192.168.123.18`；
3. 两端是否使用相同的 domain 42、topic、IDL 和 QoS；
4. 防火墙或交换机是否阻止该有线网段上的 DDS UDP/组播发现；
5. 是否误用了 ROS 自带的其他 CycloneDDS 库版本。

不要通过全局关闭防火墙来掩盖配置问题。接收统计中的 `malformed`、`duplicates`、
`out_of_order`、`source_lagged`、`new_frame_hz` 和 `interval_ms_max` 可用于定位数据质量或时序问题。
