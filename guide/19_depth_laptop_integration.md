# 笔记本接收 Go2W 机载深度

本接口是 **CycloneDDS 自定义 IDL**，不是 ROS `sensor_msgs/Image`，也不是 RealSense 原生 DDS。
不要求笔记本安装 RealSense SDK。接收器不发送机器人命令；与笔记本策略在不同 DDS domain 工作。

## 1. 最小依赖与启动

复制本项目的 `depth/`、`scripts/depth/` 和 `requirements/depth-laptop.txt` 即可。
建议使用已有且验证过的 CycloneDDS 0.10.2 环境，或新建 Python 3.8–3.11 环境：

```bash
python3 -m venv .venv-depth
.venv-depth/bin/python -m pip install -r requirements/depth-laptop.txt
```

若平台没有可用的 CycloneDDS wheel，需先安装/构建同版本 CycloneDDS C 库 0.10.2，再以
`CYCLONEDDS_HOME` 指定安装前缀安装 Python binding。不要混用 ROS 附带的其他版本。
Orin 已有的 `.venv` 环境无需重装。OpenCV 仅预览时需要，纯接收只需 NumPy 和 CycloneDDS。

笔记本网卡应与 Orin `192.168.123.18/24` 连通，使用没有地址冲突的 `192.168.123.x/24`；
网卡名通过 `ip -br addr` 确认。以下 `enp3s0` 是示例，必须替换成自己的有线网卡：

```bash
DEPTH_PYTHON="$PWD/.venv-depth/bin/python" \
DEPTH_DDS_PREFIX="$PWD/.venv-depth" \
  bash scripts/depth/run_receiver.sh --interface enp3s0 --duration 60

# 已有本项目 .venv 时不需要上面两个环境变量
bash scripts/depth/run_receiver.sh --interface enp3s0 --preview
```

预览中黑色为 0 m、白色为 2 m；无数据显示 `STALE / NO DATA`。画面不是训练输入的归一化结果。
可用 `--output /tmp/depth_stats.jsonl --save-sample /tmp/depth_sample.npz` 保存统计与米制样本。
输出路径由调用方指定，接收器的这两个选项会覆盖同名文件，保留证据时请使用新文件名。

## 2. 协议约定（v1）

| 项目 | 固定值/语义 |
|---|---|
| DDS domain | 默认 42，双方必须相同；不复用电机 domain 0 |
| Topic | `rt/depth/image64` |
| Type name | `go2w_depth::DepthFrame`，`@final`，无 key |
| QoS | BEST_EFFORT、KEEP_LAST(1)、VOLATILE |
| Depth | `float depth_m[4096]`，行优先，reshape 为 `(64,64)` |
| 单位与方向 | 米，光轴 Z 深度；图像上方朝上，左侧朝左，不翻转/转置 |
| 数值 | 所有值有限，范围 `[0,2]`；缺测填 2，较远有效值裁剪为 2 |
| 有效性 | `octet valid[4096]`，0/1；原始缺测、视场外为 0，真实远处可为 1 |
| 空间模型 | 58°×58° 虚拟针孔相机，源内参重采样；当前 USB2 下最底部一行无效 |

完整字段及顺序以 `depth/DepthFrame.idl` 为准；Python 对应类在 `depth/receiver.py`。
64×64 float 本体约 0.98 MB/s @60Hz，加掩码约 **1.23 MB/s**，还需计算 CDR/RTPS/UDP 开销。
端序和分片交给 DDS/CDR；不要直接把 UDP 包当成 float 数组。该类型一次消息约 20 KiB，
大于以太网 MTU，双方必须使用 DDS 的分片重组。
启动实现显式设置 `MaxMessageSize=1400B`、`FragmentSize=1280B`，使普通 MTU 1500 网络上的
深度数据使用小 UDP 包传输，避免默认 14720B 载荷带来的 IP 层分片。自写接收端请沿用这两个设置。

`version` 必须为 1。`session_id` 是发布会话的随机标识；相机重新打开/发布进程重启后变化。
`frame_id` 是相机源帧号，不是人为补齐的发布计数。相同会话同帧号是重复帧；源帧号缺口
可能来自相机、机载最新帧覆盖或网络，不能仅凭接收器将其归因于丢包。
只运行一个正式发布者；模拟发送也应使用独立测试 domain，避免混入正式输入。

时间字段：

- `device_timestamp_ms` / `timestamp_domain`：SDK 原始时间及域。0=硬件时钟，1=系统时间，
  2=全局时间；模拟源为 -1。不同域不能直接相减。
- `capture_monotonic_ns`：机载回调**收到深度帧**的单调时间，不是曝光开始时间。
- `publish_monotonic_ns`：机载调用 DDS write 前的单调时间；与上项之差是回调后处理耗时，
  不包含曝光、USB 传输或网络传输。
- `publish_unix_ns`：发布前系统 UTC 时间。只有两机校时及同步误差经过验证，才能估计网络单向延迟。
- 接收器另外记录笔记本自己的 `received_monotonic_ns`，仅用于本地新鲜度。

## 3. 接入策略

先使用接收示例验证连接，再在笔记本推理进程中创建一个 `DepthReceiver`。
运行该进程时同样需要隔离 ROS 动态库路径并加载 CycloneDDS 0.10.2。

```python
from depth.receiver import DepthReceiver

with DepthReceiver(interface="enp3s0", domain=42) as depth_receiver:
    # 放入现有策略周期中；接收器内部线程只维护最新图像。
    sample = depth_receiver.get_latest(max_age_ms=100)
    if sample is None:
        # 向现有控制状态机报告深度不可用；不要持续使用缓存旧图。
        depth_available = False
    else:
        depth_available = True
        depth_m = sample.depth_m       # float32 (64,64)，可传给现有 WMP
        valid_mask = sample.valid      # uint8 (64,64)，独立质量诊断
        source_key = (sample.session_id, sample.frame_id)
```

`get_latest()` 返回独立数组副本。相机停止/USB 断开后，默认约 100 ms 内变成 `None`。
判定年龄为“机载回调后处理耗时 + 笔记本收到帧后的等待时间”，**不包含未知网络传输时间**。
对端历史帧在极端网络排队后才送达的情形，必须借助可靠校时才能严格约束完整帧龄。
接收器丢弃已识别的重复/逆序帧和处理年龄超过 100 ms 的帧；线程异常会在 API 调用中抛出。

WMP 当前处理为 `clip(depth_m,0,2)/2 - 0.5`，之后模型内部还有既有中心化逻辑。
传给现有控制器时不要提前归一化或再次填充延迟。现有 world model 每五个 policy 周期更新一次，
对应 50 Hz policy 下的 10 Hz；接收 60 Hz 深度并不要求修改这个节奏。
已有控制器维护训练所需的一帧历史，由它管理，不能让发送端再加 100 ms 延迟。
无效掩码用于诊断，不直接增加为网络额外通道。

## 4. 收发验收与排障

```bash
# 在实际笔记本运行；发送端是机载开机服务
DEPTH_PYTHON="$PWD/.venv-depth/bin/python" \
DEPTH_DDS_PREFIX="$PWD/.venv-depth" \
  bash scripts/depth/run_acceptance.sh --interface enp3s0 --duration 1800 \
  --output-dir logs/depth/laptop_long_cable_30min
```

验收工具先等待首帧并预热，再按 10 秒窗口记录数据。正常连续 30 分钟，每窗口新帧率 ≥50 Hz，
最大接收间隔 ≤100 ms；否则退出码 2 并保留失败证据。先确认当前链路，然后用计划中的长网线复测。
人工拔线/拔相机、发送端重启、笔记本晚启动作为单独恢复测试，并记录恢复时间。

无法收图时按顺序检查：机载 journal 是否有 `CONNECTED` 和持续 `STATS`；两端接口是否选对；
domain/topic/type/QoS 是否一致；地址是否冲突；防火墙是否允许该有线网段上的 DDS UDP。
domain 42 的标准端口基址是 `7400 + 250×42 = 17900`，发现/数据及 participant 单播端口在此基础上分配。
不要通过全局关闭防火墙掩盖配置问题。交换机/网络需允许 DDS 发现所用的组播；此版本使用默认组播发现。

程序的 JSON 包含 `new_frame_hz`、`missing`、`duplicates`、`out_of_order`、`malformed`、
`source_lagged`、`sessions`、接收间隔与处理耗时 P50/P95/P99/max。计数累计，帧率/分位数按报告窗口。
常规 CLI 每 10 秒打印；API 的分位数最多保存最近 4096 个样本以限制内存。
同机测试结果不能替代本节的实际跨机验收。
