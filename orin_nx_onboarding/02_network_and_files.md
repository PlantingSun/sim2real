# 2. 远程维护备用说明

当前不以 SSH、远程桌面或网络传图为主线。Orin 已经可以直接使用图形桌面；本文件只保留以后编辑代码、复制日志时需要的最小信息。

## 2.1 当前已验证

用户扩展 RJ45 可以 SSH 登录 Orin，当前 Orin 为 `unitree@ubuntu`，`eth0=192.168.123.18/24`。密码不写入项目文件。

```bash
ssh unitree@192.168.123.18
```

如果地址或网络拓扑发生变化，应以 Orin 本地终端中的 `ip -br addr` 为准，不要套用旧地址。

## 2.2 小文件传输

从笔记本复制一个文件到 Orin：

```bash
scp /home/robot/sim2real_ws/README.md unitree@192.168.123.18:/home/unitree/
```

从 Orin 取回日志：

```bash
scp unitree@192.168.123.18:/home/unitree/result.txt /home/robot/sim2real_ws/
```

首次传输只使用明确的小文件和明确的目标目录。暂不使用带 `--delete` 的同步命令，也不要覆盖宇树预装目录。

## 2.3 边界

- SSH/SCP 只用于维护，不代表相机 USB 设备能直接被笔记本打开。
- 相机数据优先在 Orin 本地查看、处理和保存。
- 网络配置、DDS 和机器人通信保持不变；联网安全注意事项见 [06_networking_safely.md](06_networking_safely.md)。
