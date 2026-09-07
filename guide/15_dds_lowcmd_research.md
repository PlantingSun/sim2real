# DDS 与 500 Hz LowCmd 研究

## 目标与边界

本阶段研究 Orin NX 上 `rt/lowstate` 接收和 `rt/lowcmd` 发送的实际代码路径，回答：

1. 500 Hz 循环中每次执行了哪些 Python、CRC 和 CycloneDDS 操作。
2. 当前日志能排除什么，还缺少什么证据。
3. 下一步应测量哪些指标，何时才需要重新拆分进程。

本阶段只进行了源码检查、官方资料核对和离线序列化基准。没有初始化 DDS、调用
Sport Mode 或发送 LowCmd，也没有修改实机控制行为。

## 当前数据路径

`DdsDriver` 所在的主 Python 进程同时承担：

```text
rt/lowstate
  → CycloneDDS DataReader
  → Python 反序列化
  → SDK BQueue/ch_reader
  → DdsDriver._on_lowstate()
  → 最新 RobotState

policy action
  → DdsDriver.send_command()
  → 500 Hz RecurrentThread
  → 填充 LowCmd
  → CRC
  → Python CDR 序列化
  → CycloneDDS DataWriter.write()
  → rt/lowcmd
```

policy 已在独立 Python 子进程中运行，但 LowState、LowCmd、日志、终端输出和主控制线程
仍共享一个 Python 解释器及其 GIL。把 LowCmd 线程绑定到 CPU 1，不能消除同一进程中
Python 线程之间的 GIL 竞争。

## Orin 离线成本

以下结果在 Orin NX 25W 模式、Python 3.8、CycloneDDS Python 0.10.2 下测得。每项预热
100 次、记录 5000 次；只处理本地 IDL 对象，没有创建 DDS participant 或 publisher。

| 操作 | 平均 | P95 | P99 | 最大 |
|---|---:|---:|---:|---:|
| LowState 反序列化 | 0.5817 ms | 0.5935 ms | 0.5989 ms | 0.6250 ms |
| `_on_lowstate()` 数据复制 | 0.0258 ms | 0.0266 ms | 0.0274 ms | 0.0581 ms |
| LowCmd 填充和 CRC | 0.2607 ms | 0.2694 ms | 0.2758 ms | 0.6722 ms |
| LowCmd CDR 序列化 | 0.4274 ms | 0.5265 ms | 0.5916 ms | 0.8912 ms |

LowState 接收和 LowCmd 发送各为 500 Hz。上述平均时间合计约 `1.30 ms`，已经占据
`2 ms` 周期的约 65%，且尚未包括 DataReader `take()`、SDK 队列、锁、安全检查、
CycloneDDS `ddspy_write()`、内核网络发送和线程唤醒。

这个比例不能直接当作 GIL 占用率：部分 ctypes/C 扩展调用可能释放 GIL。但 CycloneDDS
0.10.2 的 IDL 序列化/反序列化和 CRC 打包包含明显的 Python 遍历与 `struct` 操作，说明
当前 500 Hz Python DDS 路径的实时余量并不宽裕。它比 policy 单帧推理速度更值得优先
测量。

## 定时器行为

Unitree Python SDK 的 `RecurrentThread` 使用周期 `timerfd`：

1. 先调用一次 `_control_loop()`。
2. 再对 timerfd 执行阻塞 `read(8)`。
3. 返回后进入下一次 `_control_loop()`。

Linux 的 timerfd 每次读取会返回“自上次读取以来累计发生的过期次数”。当前 SDK 把这
8 字节读入 `buf` 后没有解包，因此不知道该周期是否漏掉过一个或多个 2 ms deadline。
如果控制函数或线程调度延迟超过 2 ms，可能出现一个长发送空档，随后一次紧邻执行；仅用
总 `write_count / duration` 无法描述这种分布。

参考：[Linux timerfd 文档](https://www.kernel.org/pub/linux/docs/man-pages/book/man-pages-6.9.pdf)。

## DDS 收发语义

CycloneDDS Python 0.10.2 的 `DataWriter.write()` 会先调用 IDL 对象的 `serialize()`，再
调用底层 `ddspy_write()`。因此 `_pub.Write()` 的耗时不仅是网络发送，还包含本轮已经
测到的约 0.43 ms Python 序列化。

当前 `ChannelPublisher.Write()` 返回成功或失败，但 `DdsDriver._control_loop()` 没有检查
返回值，也没有记录异常、写入耗时或连续失败次数。

DDS 默认 History 为 `KEEP_LAST(1)`；Unitree Python SDK 又在其上增加长度为 10 的
`BQueue`。该队列满时拒绝新样本而不是替换旧样本。现有前半段日志表明 Orin 的 LowState
在原始振荡窗口内仍然新鲜，因此暂时不把接收队列认定为触发原因；但控制语义上仍应继续
坚持“最新状态优先”。

参考：

- [CycloneDDS 0.10.2 History QoS](https://cyclonedds.io/docs/cyclonedds-cxx/0.10.2/api/core.html)
- [CycloneDDS Python 写入接口](https://cyclonedds.io/docs/cyclonedds-python/latest/cyclonedds.pub.html)

## 与宇树官方实现的差异

宇树 Python Go2W 示例同样使用 `rt/lowstate`、`rt/lowcmd`、CRC 和 2 ms
`RecurrentThread`，说明当前 topic、消息类型和目标频率没有偏离官方 Python 接口。

但宇树 C++ Go2/Go2W 示例有两点不同：

- LowState subscriber 队列长度使用 1，而不是 Python 示例中的 10。
- 500 Hz 的消息复制、CRC、序列化和发布都在 C++ 中完成，不经过 Python IDL 遍历。

宇树当前 RL 实机部署代码还会先订阅 `rt/lowcmd`，检测是否存在其他 LowCmd 发布者。
当前项目没有这项启动前检查。

参考：

- [Unitree SDK2 Python](https://github.com/unitreerobotics/unitree_sdk2_python)
- [Unitree SDK2 C++ Go2W 低层示例](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/go2w/go2w_stand_example.cpp)
- [Unitree RL Lab Go2W 实机入口](https://github.com/unitreerobotics/unitree_rl_lab/blob/main/deploy/robots/go2w/main.cpp)

## 当前 Orin 调度条件

只读检查结果：

- nvpmodel：25W，模式 3。
- CPU governor：8 个核心均为 `schedutil`。
- 空闲检查时核心频率在约 729–1497 MHz 间变化，硬件最大约 1984 MHz。
- `eth0` IRQ 309 的 effective affinity 为 CPU 0。
- LowCmd 当前绑定 CPU 1，policy 绑定 CPU 2，因此没有与已观察到的 `eth0` IRQ 直接
  使用同一核心。

这些是空闲时快照，不能替代实机振荡发生时的同步记录。动态调频仍可能影响线程唤醒和
序列化尾延时，但没有同场数据前不能把 25W 或 `schedutil` 直接判为根因。

## 现阶段结论

1. policy 推理和 observation 数值已通过跨架构验证，不是主因。
2. 原始振荡窗口内 50 Hz policy 和 LowState 更新正常，不能用它们解释约 8.5 Hz 振荡。
3. 500 Hz Python DDS 路径自身已有较高的编码/解码成本，且与日志、终端和 DDS 回调共享
   GIL；这是明确存在的实时余量风险。
4. 当前最大证据缺口仍是实际 LowCmd start-to-start 周期及 `Write()` 耗时，而不是总写入
   次数。
5. “DDS 有问题”目前应具体表述为：Orin 上 LowCmd 发送节拍、DDS writer、Python GIL
   和系统调度的组合尚未验证；LowState 内容和平均新鲜度暂未发现问题。

## 下一步：只加内存统计

下一次代码修改应只增加诊断，不改变 MotorCommand、控制频率或安全逻辑。500 Hz 线程在
内存中记录：

- 相邻 `_control_loop()` 开始时间间隔。
- `_fill_command()`、CRC 和 `_pub.Write()` 各自耗时。
- `Write()` 成功/失败次数。
- 间隔超过 2、3、5、10 ms 的次数。
- 间隔小于 1 ms 的次数，用来发现长空档后的紧邻执行。
- policy 提交新 action 到该 action 第一次完成 LowCmd Write 的延迟。
- LowState 回调次数、tick 增量和回调间隔。

运行过程中不逐帧打印、不逐帧写盘；退出后一次性输出统计。首先在笔记本稳定链路建立
参考分布，再在 Orin 上按“固定 LowCmd → 加入 policy”的顺序比较。

只有在测得 Orin LowCmd 明显存在长空档或写入尾延时后，才进入真正的架构拆分：将 DDS
收发和安全检查放入不承担日志/终端工作的专用进程，并通过 latest-only 共享状态连接
policy。是否还要把 DDS 接收和发送拆成两个进程，应由测量结果决定；仅把现有两个进程
放到两个终端不会改变调度结构。
