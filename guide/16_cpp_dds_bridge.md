# C++ DDS 独立进程实验

## 目标

本实验只替换 DDS/LowCmd 后端，不修改 policy、observation、关节映射、PD 参数或 50 Hz
控制语义。原 Python DDS 后端仍是默认值，便于进行单变量 A/B 对比。

```text
policy 子进程（Python，50 Hz，CPU 2）
        ↕ multiprocessing.Pipe
流程/手柄/日志（Python 主进程）
        ↕ 固定大小匿名管道
DDS + LowState + LowCmd（C++，500 Hz，CPU 1）
        ↕ CycloneDDS
Go2W
```

C++ 进程是控制阶段唯一创建 DDS participant 的常驻进程。StandUp 和 ReleaseMode 仍由
短生命周期 Python helper 调用；RPC 返回后 helper 立即退出，不参与 500 Hz 控制。

## 文件

- `cpp/go2w_dds_bridge.cpp`：DDS、CRC、500 Hz 绝对时钟、限速检查和 watchdog。
- `driver/cpp_dds_driver.py`：保持 `DriverBase` 接口，把状态和命令转换为固定二进制包。
- `scripts/real/sport_mode_once.py`：只执行一次 StandUp 或 ReleaseMode 后退出。
- `scripts/real/test_cpp_dds_bridge.py`：只读 LowState，不发布 LowCmd。
- `scripts/real/test_policy_real.py --dds-backend cpp`：一条命令启动完整实验架构。

匿名管道中的 StatePacket 为 280 字节，CommandPacket 为 344 字节，均小于 Linux
`PIPE_BUF`，单包写入不会与另一包交错。状态使用专用文件描述符，避免 SDK 的终端输出
混入二进制状态；C++ 诊断正常显示在终端。

## 一、构建和离线检查

构建不会连接机器人：

```bash
cd /home/unitree/sim2real
cmake -S cpp -B build/cpp -DCMAKE_BUILD_TYPE=Release
cmake --build build/cpp -j2
```

离线 CRC 自检：

```bash
LD_LIBRARY_PATH=/usr/local/lib \
GCOV_PREFIX=/tmp/sim2real_gcov GCOV_PREFIX_STRIP=10 \
build/cpp/go2w_dds_bridge --crc-test
```

当前 Orin 输出应为：

```text
73953690
```

该非零电机测试向量已与项目内 Python SDK 核对一致；此外默认 LowCmd 两端也得到相同的
`115701709`。C++ SDK 使用
`/usr/local/lib` 中配套的 CycloneDDS；Python 仍使用 `.venv/lib`。两者位于不同进程，
不能把其中一套动态库路径全局替换成另一套。

## 二、只读 LowState 测试

这是用户首先应该执行的步骤。它会创建 DDS subscriber 和 publisher 对象，但 C++ bridge
处于 `monitor-only`，不会调用 LowCmd `Write()`，也不会调用 Sport Mode：

```bash
source setup.sh robot
python scripts/real/test_cpp_dds_bridge.py --duration 10 --lowcmd-cpu 1
```

确认：

- `[CPP DDS RX] rate` 接近 LowState 实际更新率。
- `tick_delta` 持续增加。
- 退出摘要中 `writes=0`。
- `other_lowcmd=0`。`prearm_lowcmd` 只表示 Sport Mode 当前是否在发布，不是冲突。
- 没有 symbol lookup error、进程残留或大量 `state_drops`。

本步骤不需要吊起机器人，也不需要 ReleaseMode。
只读阶段尚未发送自己的 LowCmd，因此不会把 Sport Mode 的发布者判为冲突。

## 三、固定 LowCmd + policy print-only

只读测试通过后，机器人严格执行“地面站立 → 站稳 → 吊起 → 释放”的流程：

```bash
python scripts/real/test_policy_real.py \
  --dds-backend cpp \
  --control fixed --vx 0 --vy 0 --vyaw 0 \
  --print-only
```

`--print-only` 仍会在按 `2` 后发送固定 `INITIAL_JOINTS_POS`，只是不发送 policy 预测
动作。因此该步骤必须吊起。C++ bridge 在收到首条带 ARM 标志的固定命令之前不发布
LowCmd；之后 C++ 以 500 Hz 对最新命令做零阶保持。

Python 每 20 ms 刷新一次 watchdog。若 Python 进程消失、命令超过 100 ms 未刷新、
LowState 超过 100 ms 未更新或轮速超过现有限值，C++ 会进入阻尼，持续约 500 ms 后退出。
C++ 会一直监听 `rt/lowcmd`。由于实测确认 Sport Mode 在站稳后仍持续发布，ReleaseMode
前的消息只能记录为 `prearm_lowcmd`，不能据此拒绝释放。ReleaseMode 返回后立即开始发送
固定 LowCmd；20 ms 交接期后，subscriber 收到的 CRC 若不属于 C++ 最近发送的 16 个
LowCmd，才判定为并发发布者并进入阻尼。

退出时重点保存两行：

```text
[CPP DDS RATE] ...
[CPP DDS WRITE] ...
```

它们包含实际 500 Hz 开始间隔、最大间隔、超过 3/5/10 ms 的次数、紧邻周期、DDS Write
耗时、CRC 耗时、失败次数和状态管道丢包数。运行中不逐帧写这些诊断，避免测量本身干扰
LowCmd。

## 四、短时真实 policy A/B

只有第三步频率和退出阻尼均正常后，才去掉 `--print-only`：

```bash
python scripts/real/test_policy_real.py \
  --dds-backend cpp \
  --control fixed --vx 0 --vy 0 --vyaw 0 \
  --log logs/real/policy_cpp.csv
```

第一次只做短时零速度吊架测试，不施加大扰动。停止后同时保留：

- `policy_cpp.csv` 和 `policy_cpp_observation.csv`。
- C++ 的 RATE/WRITE 两行退出摘要。
- 是否仍存在约 8.5 Hz 抖动的现场观察。

对照组仍使用原命令，不加 `--dds-backend cpp`：

```bash
python scripts/real/test_policy_real.py \
  --control fixed --vx 0 --vy 0 --vyaw 0
```

只有 C++ 组的 LowCmd 间隔明显更稳定且机器人抖动显著减小，才能确认 Python DDS/GIL 是
主要原因。如果 C++ 的 500 Hz 时序很好但机器人仍同样抖动，应停止继续扩展架构，转向
其他 Orin 特有变量。

## 当前状态

代码已完成编译、Python 语法检查、跨语言包尺寸检查和两组 CRC 对照。尚未运行会发布
LowCmd 的 C++ 测试，因此 C++ 后端仍标记为实验功能，默认后端保持 `python`。

首次只读测试结果：CPU1 为 `500.01 Hz`，最大间隔 `4.65 ms`；CPU5 为 `499.93 Hz`，
最大间隔 `17.45 ms`。两组均为 `writes=0`、`state_drops=0`。后续固定使用 CPU1。
更新后的 CPU1 五秒只读复测通过：LowState `500.02 Hz`，循环最大间隔 `2.78 ms`，
`over_3/5/10ms=0/0/0`、`under_1ms=0`、`late=0`、`state_drops=0`，并且两处
`other_lowcmd=0`、`writes=0`。可以进入第三步 print-only 吊架测试。

前两次 print-only 均在 ReleaseMode 前被旧版保护逻辑拦截，`writes=0`。第二次确认
Sport Mode 在站稳后仍持续发布 `rt/lowcmd`，因此保护逻辑已经改成上述接管后 CRC 判定。

第三次 print-only 完成实际接管：`writes=8830`，平均周期 `2.00061 ms`、最大
`8.58 ms`，超过 3/5/10 ms 分别为 `6/1/0`；DDS Write 平均/最大
`0.1236/0.3113 ms`，CRC 平均/最大 `0.0407/0.0965 ms`。没有 Write 失败、状态丢包或
并发发布者。随后统计范围已收紧为 ARM 后实际 LowCmd 阶段，排除人工按键等待阶段。

真实 policy A/B 也已完成，日志为 `logs/real/policy_cpp.csv`。C++ 后端下机器人仍出现与
Python 后端相同的约 `8.4 Hz` 剧烈振荡；预热固定 LowCmd 阶段保持安静，振荡从 policy
接管后开始。因此 C++ 实验排除了 Python DDS/GIL 和 LowCmd Write 节拍是主要原因，后续
不再扩展 DDS bridge，转向缩短 Orin 的 state→action 延迟。
