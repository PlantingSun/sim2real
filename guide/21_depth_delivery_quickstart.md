# 深度传输交付说明：做了什么、怎么看效果

## 现在已经能做什么

Orin 上的 D435i 深度链路已实现并运行：

**D435i → 机载采集/滤波 → 64×64 米制深度 → 网口 DDS → 接收器。**

- **相机采集：** 当前使用 `480×270 @ 60 FPS`，每次发布来自新的相机帧。
- **深度处理：** 空间降噪，按仿真相机的 58° 视场采样为 64×64；深度范围 0–2 m。
  缺测填 2 m，并单独保留有效掩码；不在机载端做策略归一化或人为延迟。
- **网络发布：** 独立 CycloneDDS，默认 `eth0`、domain `42`、话题 `rt/depth/image64`。
  只保存最新帧，使用小 UDP 包分片，避免旧图排队。
- **笔记本接收：** 提供 Python 接收器、实时预览、帧率/丢帧统计和最新图像 API。
  默认超过约 100 ms 未更新时报告深度不可用。
- **开机服务：** `go2w-depth.service` 已安装、启用并实际出图；相机不可用时自动重试。
- **配套工具：** 构建、设备诊断、持续验收、原始/滤波图快照、离线查看和服务启停。

机载端这套程序只处理深度，不运行强化学习网络，不发送机器人运动命令。

## 当前实测效果与限制

60 秒真实采集、机载同机 DDS 收发已经通过：

| 指标 | 结果 |
|---|---:|
| 最低 10 秒窗口新帧率 | 59.83 Hz |
| 最大接收间隔 | 36.19 ms |
| 丢失源帧号 / 重复帧 | 0 / 0 |
| 回调收到图像后的处理耗时 | 通常约 6–7 ms |
| 发布进程内存 | 约 29–31 MiB |

最终服务的小 UDP 包配置也已通过互通、过期和重启测试；30 分钟记录位于
`logs/depth/20260907_service_mtu_30min/`。**仅当出现 `summary.json` 才表示该轮结束**，
其中 `fps_pass`、`gap_pass`、`integrity_pass` 表示相应项目是否通过。

目前线缆实际只协商到 **USB2**。60 FPS 模式匹配仿真视场后，64×64 最底部一行超出传感器范围，
因此这一行标无效并填 2 m。这是已记录的兼容处理。换用确认支持 USB3 的线缆后，可重新检测更高分辨率、
完整视场的 60 FPS 模式。

当前证据是机载上的真实相机与同机 DDS 收发。实际笔记本/长网线、物理相机安装标定、
整机重启和人工拔插恢复仍须现场验证；不要把已有结果理解为这些项目也全部完成。

## 最快查看当前实时效果

在 **Orin 的 Ubuntu 桌面终端**执行：

```bash
cd /home/unitree/sim2real
bash scripts/depth/run_receiver.sh --interface eth0 --preview
```

这会订阅正在运行的服务并显示实时 64×64 深度放大图：**黑色近、白色远，2 m 以上为白色**。
终端每 10 秒打印一次新帧率等统计；按 `q` 或 `Esc` 关闭预览，服务继续运行。
`STALE / NO DATA` 表示没有新鲜图像。缺测填成的白色与真实远处都可能出现，诊断时需结合有效掩码。

如果只有 SSH、没有图形桌面，可以只看统计：

```bash
bash scripts/depth/run_receiver.sh --interface eth0 --duration 30
```

已有离线对比图可直接打开：
[原始深度 / 空间滤波 / 64×64 目标图](../logs/depth/20260907_usb2_initial/raw_processed.png)。
图中的紫色表示无效像素。PNG 是查看用的预览，策略输入应使用米制数组。

## 常用维护命令

```bash
# 看服务是否启用、是否运行
systemctl is-enabled go2w-depth.service
systemctl status go2w-depth.service --no-pager

# 看是否持续出图：应看到 CONNECTED 和每 10 秒一次的 STATS
journalctl -u go2w-depth.service -n 20 --no-pager

# 暂停 / 恢复 / 重启深度服务
sudo systemctl stop go2w-depth.service
sudo systemctl start go2w-depth.service
sudo systemctl restart go2w-depth.service
```

正式使用前检查 `STATS` 约 60 Hz；仅有 `active` 不代表相机已经出图。
使用 `realsense-viewer` 前先停止服务，用完再启动，避免相机被两个程序占用。
`CAMERA_IN_USE` 表示另一个本项目采集进程持有相机锁，结束它后服务会重试。

## 笔记本接入和进一步说明

笔记本只需 NumPy 和 CycloneDDS，不需安装 RealSense SDK。复制代码并准备接收环境后，
把命令中的网卡替换成笔记本实际有线网卡即可。详细命令和协议见：

- [笔记本对接文档](19_depth_laptop_integration.md)：环境、网卡、预览、Python API、数据单位及时间语义。
- [机载完整指南](18_d435i_depth_service.md)：构建、USB 排查、处理配置、自启动和验收。
- [实测记录](20_depth_validation_record.md)：已验证结果、证据路径及仍需现场验证的项目。

接入现有 WMP 时，直接使用 `sample.depth_m`，形状为 `(64,64)`、类型为 `float32`、单位为米。
不要提前归一化，也不要额外增加一帧延迟；现有控制器负责训练所需的处理。
