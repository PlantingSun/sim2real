# Orin NX 深度服务：当前操作步骤

当前功能是：D435i 在 Orin 上采集深度，处理为 `64×64` 米制深度，通过 `eth0` 的
CycloneDDS domain 42 发布。服务已经安装为开机自启动，不运行策略，不发送 LowCmd。

## 1. 查看服务是否正常

在 Orin 终端依次执行：

```sh
cd /home/unitree/sim2real
systemctl is-enabled go2w-depth.service
systemctl is-active go2w-depth.service
journalctl -u go2w-depth.service -n 20 --no-pager
```

正常结果：

- 前两条分别显示 `enabled`、`active`；
- 日志出现 `CONNECTED`；
- 日志每 10 秒出现一条 `STATS`，`publish_hz` 约为 60。

如果服务不是 `active`，执行：

```sh
sudo systemctl restart go2w-depth.service
```

## 2. 在 Orin 上查看实时深度

在 Orin 图形桌面的终端执行：

```sh
cd /home/unitree/sim2real
zsh scripts/depth/run_receiver.sh --interface eth0 --preview
```

应看到两个面板：

- `meters`：黑色近、白色远，紫色为相机原生无效点；
- `valid mask`：白色有效、黑色无效。

把物体放在相机前移动，深度轮廓应同步变化。按 `q` 或 `Esc` 退出预览。
这个命令只增加一个接收者，不会中断服务，也不会影响笔记本接收。

如果只有 SSH，没有图形桌面，执行不带窗口的 30 秒检查：

```sh
zsh scripts/depth/run_receiver.sh --interface eth0 --duration 30
```

当前应看到：`new_frame_hz` 约 59–60、`error` 为 `null`，重复和畸形消息为 0。

## 3. 当前 64×64 处理方式

当前相机流为 `480×270 Z16 @60 FPS`，目标输入为 `64×64`、58°×58°、0–2 m。

处理顺序：

```text
Z16 原始深度
→ RealSense 视差域空间滤波（不补洞）
→ 根据 D435i 标定内参投影到 58°×58° 的 64×64 网格
→ 最近邻读取原始深度
→ 转成米并裁剪到 0–2 m
→ 发布 depth_m 和 valid
```

底行问题已经修正。原因是 D435i 标定光心 `ppy=138.657` 不在 270 行图像的几何中心，
导致目标 58° 视场的底行投影比源图最后一行略低约 1.2 个源像素。当前仅把这 64 个投影坐标
夹到最近的真实传感器边缘行；前 63 行坐标不变。

这里继续使用最近邻，而不对邻域深度做加权平均。加权平均会在障碍物边界把前景和背景混成
一个不存在的中间距离。当前修正保留源图最后一行的真实测量；如果该位置本来是 0，仍发布
`valid=0`，不会在 Orin 端填缝。RealSense 的其他无效缝隙也留给笔记本处理。

空间滤波参数仍为 magnitude 2、alpha 0.5、delta 20，时间滤波和 hole filling 默认关闭。
输出 `depth_m` 是 `float32 (64,64)` 米制深度；无效位置的传输值为 2 m，同时 `valid=0`。
笔记本应以 `valid` 判断是否为真实测量。

## 4. 当前需要关注的效果

查看预览时主要确认：

1. 最底行不再固定整行紫色/无效；它应和相机原生最后一行的有效情况一致。
2. 物体左右、上下方向正确，没有翻转或转置。
3. 物体边界没有因缩放变成大面积中间深度。
4. 其余零散紫色区域属于 D435i 原生无效点，当前版本不处理。
5. `journalctl` 中 `publish_hz` 保持约 60。

已有实机原始图与滤波图可以打开查看：

```sh
xdg-open logs/depth/20260907_usb2_initial/raw_processed.png
```

这张旧图记录修正前的固定无效底行。运行第 2 节看到的是修正后的实时结果。

## 5. 服务启停

```sh
# 重启服务
sudo systemctl restart go2w-depth.service

# 暂停服务
sudo systemctl stop go2w-depth.service

# 恢复服务
sudo systemctl start go2w-depth.service
```

要使用 `realsense-viewer`，先停止服务；关闭 Viewer 后再恢复服务。

## 6. 收不到数据时按顺序检查

```sh
systemctl is-active go2w-depth.service
journalctl -u go2w-depth.service -n 30 --no-pager
lsusb
lsusb -t
```

- 没有 `8086:0b3a`：检查 D435i 数据线和接口。
- 有相机但没有 `CONNECTED`：执行 `sudo systemctl restart go2w-depth.service`。
- 日志显示 `CAMERA_IN_USE`：关闭 `realsense-viewer` 或其他相机采集进程，然后重启服务。
- 服务持续输出 `STATS`，但笔记本收不到：按 [笔记本接收步骤](19_depth_laptop_integration.md)
  检查笔记本网卡、IP 和 domain 42。

## 7. 代码改动后才需要重新构建

日常开机和查看不需要执行本节。修改 C++ 后执行：

```sh
cd /home/unitree/sim2real
zsh scripts/depth/build.sh
sudo systemctl restart go2w-depth.service
```

构建末尾应显示 `100% tests passed`。服务首次安装时才执行：

```sh
sudo zsh scripts/depth/install_service.sh
```

笔记本侧严格执行步骤见 [19_depth_laptop_integration.md](19_depth_laptop_integration.md)，
当前交付摘要见 [18.5_depth_delivery_quickstart.md](18.5_depth_delivery_quickstart.md)，
深度质量与 OOD 边界见 [19.5_depth_validation_record.md](19.5_depth_validation_record.md)。
