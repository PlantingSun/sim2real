# D435i 机载深度服务：采集、处理、DDS 与开机启动

本阶段 Orin 只承担深度采集和传输，控制网络在笔记本运行。深度程序不加载策略、
不创建 LowCmd 发布者，不调用 Sport Mode。笔记本接口见
[19_depth_laptop_integration.md](19_depth_laptop_integration.md)，现场记录见
[19.5_depth_validation_record.md](19.5_depth_validation_record.md)。

## 1. 当前连接与已知限制

2026-09-07 已识别 D435I `336222074436`，固件 `5.13.0.55`。用户通过补装系统
librealsense 库、排查原 Type-C 数据线恢复识别。当前系统安装的是 librealsense **2.58.4**；
旧 ROS Noetic 的 **2.50.0** 仍在，但本服务明确链接 `/usr` 下的新库。

当前连接 **USB 2.1 / 480 Mbps**，不是 USB3：

| Z16 模式 | 本次枚举的最高帧率 | 能否完整覆盖目标视场 |
|---|---:|---|
| 848×480 | 10 FPS | 能 |
| 640×480 | 30 FPS | 能 |
| 480×270 | 60 FPS | 缺失底部一行目标像素 |
| 256×144 | 90 FPS | 视场明显不足，不采用 |

当前配置使用 `480×270 @ 60 FPS`，**每帧都是新的相机帧**。目标仍为 58°×58°、64×64，
不拉伸较窄的实机视场来冒充仿真视场。越界的底部一行占 1.5625%，填 2 m，`valid=0`。
该行为由 `--allow-partial-fov` 显式启用，最多允许 2% 的无效边缘；不传此选项时要求完整覆盖。

后续换成确认支持 USB3 的数据线，执行诊断并检查 `lsusb -t` 出现 **5000M 或更高**。
程序优先选择能覆盖目标视场的 `848×480@60`，再尝试 `640×480@60`、`480×270@60`。
不自动退到 30 FPS，不把重复帧计为新帧。恢复完整覆盖后可从配置删除 `--allow-partial-fov`。
USB3 模式、图像效果必须重新实测，不根据接口外形或线缆名称判断。

## 2. 构建与诊断

以下命令在 Orin 执行。不要同时使用 RealSense Viewer、ROS 相机节点和本服务打开相机。

```bash
cd /home/unitree/sim2real
dpkg-query -W '*realsense*'
lsusb
lsusb -t
rs-enumerate-devices
bash scripts/depth/build.sh
bash scripts/depth/run_publisher.sh --diagnose
```

已配置 RealSense apt 源的本机可用下面的命令补装软件；复建其他 Jetson 时先按
[官方 Jetson 安装说明](https://github.com/realsenseai/librealsense/blob/master/doc/installation_jetson.md)
核对系统和软件源，勿直接给 Tegra 内核安装通用桌面 DKMS。

```bash
sudo apt install librealsense2-utils librealsense2-dev librealsense2-udev-rules
```

构建依赖：CMake、C++17 编译器、OpenCV C++ core/imgproc、librealsense、CycloneDDS 0.10.2
及 idlc。当前 CycloneDDS 前缀为项目 `.venv`，RealSense 前缀为 `/usr`。
必要时用 `DEPTH_DDS_PREFIX`、`DEPTH_RS_PREFIX` 指定其他前缀；本构建脚本面向 Orin aarch64。
无需安装 pyrealsense2、PyTorch、ROS wrapper 或更改现有控制代码。

启动脚本主动隔离 ROS 的动态库路径。直接运行二进制而继承 ROS Foxy 环境可能出现
`ddsi_sertype_v0`、`DDS_XTypes_TypeMapping_desc` 等符号错误；应使用提供的启动脚本。
不同版本的 Python CycloneDDS 和 libddsc 也不能混用。

```bash
# 一次性前台采集；Ctrl-C 退出。服务运行时先停止服务，避免抢占相机。
bash scripts/depth/run_publisher.sh --interface eth0 --allow-partial-fov --duration 60

# 诊断工具：只读列出 USB、网络、内核连接日志和 SDK 流模式
bash scripts/depth/diagnose.sh
```

USB 排查顺序：`lsusb` 是否存在 `8086:0b3a` → 实际速率 → SDK 是否识别 → 流模式 → 真实帧率。
`lsusb` 完全看不到设备时，优先查数据线、供电、连接路径、USB 控制器；不能只归因于 SDK。
已经枚举但 SDK 无法打开时，再查 udev 权限、占用、库版本和内核后端。
SDK 识别不了设备时查看 `journalctl -k -b`，但不要把历史 Type-C 报错直接当作本次根因。

## 3. 处理与仿真对齐

链路为：Z16 → 视差域保边空间滤波 → Z16 → 内参映射采样 → 米制转换 → 无效值处理 → DDS。
相机只开启 depth，不开启 RGB、IMU 或 RGB 对齐。采集回调只写容量 1 的最新帧缓存，处理慢时覆盖
旧帧并计数。SDK 自动曝光优先级设为不牺牲帧率；实际曝光仍须靠真实数据验收。

- 空间滤波默认开启：magnitude=2、alpha=0.5、delta=20、空间补洞=0。
- 时间滤波默认关闭；实验可加 `--temporal`，但运动拖影需另验收。
- 独立补洞默认关闭；`--hole-filling 0|1|2` 对应 SDK 的 left/farthest/nearest。
- `--no-spatial` 可作无空间滤波对照。不要在机器人运动时随意更改训练输入处理配置。
- 原始无效零值和非有限值最终填 2 m；有效的远处值裁剪为 2 m。
- `valid=1` 表示该输出采样位置原始深度和处理后深度均有效；补洞不会把原始无效点标成有效。

处理顺序参考 [RealSense 官方滤波说明](https://github.com/realsenseai/librealsense/blob/master/doc/post-processing-filters.md)。
本默认配置只用空间处理以减少历史图像拖影，尚不能声称消除了所有噪点。

仿真参照是现有 Go2W WMP：64×64，水平/垂直视场 58°，范围 0–2 m；MuJoCo 相机位于
base 的 `[0.34, -0.0375, 0.09]`，姿态见现有 XML。重采样通过 RealSense 内参及畸变模型投影目标射线，
使用最近邻以避免跨越障碍边缘混合前后景。输出是光轴 Z 深度，不是沿射线的欧氏距离。
不左右翻转、不上下翻转、不转置。发布端不做网络归一化，不额外增加训练延迟。

保存同帧原始/滤波/目标图及映射，便于之后复核：

```bash
bash scripts/depth/run_publisher.sh --interface eth0 --allow-partial-fov \
  --duration 5 --snapshot /tmp/depth_capture.yml
.venv/bin/python scripts/depth/inspect_sample.py /tmp/depth_capture.yml \
  --output /tmp/depth_capture.png
```

快照写盘会拉长该帧处理耗时，因此不要在帧率验收或正式服务中开启 `--snapshot`。
可视化只用于检查；网络接收的是 float32 米制图，不是 PNG 或伪彩色图。

完整几何验收需实际摆放相机和已知物体：固定安装，核对左右/上下方向；正对距离已知的平墙
（例如 0.5/1/1.5 m，以深度光心为测量基准）；比较中心区域距离；然后在相同相机姿态、
相同尺寸台阶/地面的仿真场景比较边缘像素位置。统计有效率、区域中位数、P95 绝对误差和
静止序列抖动。当前静态样本不提供真实物体的已知距离，不能据此宣称已完成物理标定。

## 4. 开机服务

配置文件为 `config/depth-service.env`。当前固定序列号，网卡 `eth0`、domain `42`、话题
`rt/depth/image64`。`DEPTH_EXTRA_ARGS` 可放额外 CLI 参数，由 systemd 分词，不做 shell 执行。

```bash
cd /home/unitree/sim2real
sudo bash scripts/depth/install_service.sh
systemctl is-enabled go2w-depth.service
systemctl status go2w-depth.service --no-pager
journalctl -u go2w-depth.service -n 30 --no-pager
```

安装脚本将单位文件复制到 `/etc/systemd/system` 并执行 enable/start；使用普通用户 `unitree`
运行，不依赖桌面登录或交互式 shell。网络未就绪、进程异常会重启；相机未接入/读帧超时
会停止发图并重新打开设备。`active` 仅说明进程活着，**有 `CONNECTED` 和持续 `STATS` 才说明在出图**。
每次相机重连重建滤波器并生成新的会话号。

所有提供的相机启动入口共用 `build/depth/camera.lock`。已有测试占用时，新服务会报告
`CAMERA_IN_USE` 并重试；原测试结束后自动获得相机。该锁不约束外部 Viewer/ROS 程序，仍需手动避免同时打开。

```bash
# 改配置后重启；仅改 EnvironmentFile 不需要 daemon-reload
sudo systemctl restart go2w-depth.service

# 暂停后用 Viewer/独立诊断程序；用完恢复
sudo systemctl stop go2w-depth.service
sudo systemctl start go2w-depth.service

# 取消自启动并停止；保留安装文件以便恢复
sudo bash scripts/depth/install_service.sh --uninstall
```

如果 sudo 要求密码，需要在自己的机载终端输入；不要在对话或日志里提供密码。
重启机器验证需现场安排：重启后不登录图形桌面，从笔记本接收器确认恢复数据，再查看
`journalctl -b -u go2w-depth.service`。安装成功不等于已做断电/重启验收。

## 5. 持续运行与故障验收

```bash
# 服务已运行：30 分钟接收验收。输出目录必须是未存在的新目录。
bash scripts/depth/run_acceptance.sh --interface eth0 --duration 1800 \
  --output-dir logs/depth/service_30min

# 服务未运行：工具自行启动并最终停止相机进程，同时记录 CPU/RSS。
bash scripts/depth/run_acceptance.sh --interface eth0 --launch camera \
  --allow-partial-fov --duration 1800 --output-dir logs/depth/standalone_30min
```

报告包含每 10 秒新帧率、缺失/重复帧、接收间隔和机载处理耗时分位数；同机启动时记录
发布进程 CPU/RSS，保存最后 120 张图、`receiver.jsonl`、`summary.json` 和发布日志。
针对已有服务，可额外传 `--publisher-pid`，PID 从 `systemctl show -p MainPID --value go2w-depth` 获取。
不要在已有服务占用相机时使用 `--launch camera`。

正常窗口目标：新帧率 ≥50 Hz、无超过 100 ms 的接收中断、无畸形数据；持续 30 分钟。
人为拔插 USB/网线单独测试，不混入正常稳定性统计。拔相机后图像必须过期，重接后出现新会话；
网线重接、笔记本晚启动也需恢复。程序不会重复旧图维持表面帧率。

机载上绑定 eth0 的同机收发证明软件和相机链路工作，**不证明数据已经经过长网线或笔记本网卡**。
最后必须按笔记本文档，在实际笔记本和计划使用的网线上重复 30 分钟测试。
