# 6. 联网和外置天线前的安全检查

本章不是立即执行的安装教程，而是为了避免联网时破坏 Go2W 内部通信。

## 6.1 当前已知网络事实

当前 Orin 的有线接口为：

```text
eth0  UP  192.168.123.18/24
```

它很可能同时参与 Orin 与 Go2W 本体的通信。是否确实如此，要通过当前路由表、接口连线和运行中的服务进一步确认。

在联网前，保持 HDMI 显示器和 SSH 中至少一种进入方式可用，并先执行：

```bash
ip -br addr
ip route
resolvectl status 2>/dev/null || true
nmcli device status 2>/dev/null || true
nmcli connection show 2>/dev/null || true
```

把输出保存下来，作为修改前基线。

## 6.2 推荐的联网优先级

1. 如果 Orin 有独立的 Wi-Fi/4G 接口，优先使用它上网，保留 `eth0` 的机器人通信配置。
2. 如果只能用同一张网卡接入互联网，不要直接切换 `eth0` 的静态地址或删除已有路由；先确认网关、路由优先级和 DDS 使用的接口。
3. 外置天线安装应按照宇树硬件说明确认接口和天线类型；不要在不确定接口用途时向 M8、BAT 或网络口尝试转接。
4. 联网初期不要执行系统大规模升级、刷写 JetPack 或批量安装软件。

## 6.3 联网后的只读验证

联网后先只检查状态：

```bash
ip -br addr
ip route
getent hosts archive.ubuntu.com
```

确认 SSH 仍然可以进入、`eth0` 地址没有被意外覆盖，再测试普通网络访问。不要把网络通了误判为机器人 DDS、RealSense 或 ROS2 都已经配置完成。

## 6.4 在 Orin 上使用 ChatGPT

如果系统已有图形桌面和浏览器，联网后可以直接在 Orin 的浏览器中使用 ChatGPT。这是图形化应用层问题，与当前 Python 控制代码和 D435i 数据链路相互独立。

当前不建议为了“直接使用 ChatGPT”立即安装新的桌面环境、浏览器、API 客户端或自动启动服务。先确认系统版本、网络稳定性和存储空间，再由用户审查安装方案。不要把 ChatGPT/API 密钥写入项目文件或提交到 Git。

## 6.5 禁止事项

- 不修改 `192.168.123.18/24`，除非已确认 Go2W 通信不依赖它
- 不删除默认路由、NetworkManager 连接或 DDS 配置
- 不执行 `sudo apt upgrade`、刷写脚本或 Force Recovery
- 不因为联网成功就启动机器人控制、WMP 或 LowCmd
