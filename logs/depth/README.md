# 深度链路验证证据

本目录只记录相机和独立深度 DDS 数据，不含电机命令。

- `20260907_usb2_initial/`：60 秒真实 D435I USB2 / 480×270@60 / 64×64 DDS，
  机载同机收发；含日志、统计、120 张末尾帧及同帧原始/滤波/映射快照。
- `20260907_usb2_pre_mtu_interrupted/`：旧 UDP 参数下约 620 秒的中途测试，为调整分包主动停止，未完成 30 分钟。
- `20260907_service_mtu_30min/`：最终小 UDP 包参数下的实际服务持续测试；查看 `summary.json` 判断是否完成及是否通过。

数据解释、当前缺失的一行视场和未完成的物理/跨机验收见
[`../../guide/20_depth_validation_record.md`](../../guide/20_depth_validation_record.md)。
NPZ/YAML 保留米制真值数据，PNG 仅用于查看。不要用预览 PNG 作为策略输入。
