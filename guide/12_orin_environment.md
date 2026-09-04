# Step 0: Orin NX 环境配置

## 目标和边界

本步骤只建立 Go2W 机载 Orin NX 的唯一 Python/VS Code 环境，并做离线验证。安装和
验证脚本不会初始化 DDS、发布 LowCmd、释放 Sport Mode 或控制机器人。

本仓库后续只服务这台 Orin NX，不再保留笔记本、Conda 或其他 Python 版本的兼容分支。

## 已验证设备事实

| 项目 | 当前值 |
|---|---|
| 架构 | `aarch64` |
| 系统 | Ubuntu 20.04.5 LTS |
| Jetson Linux | L4T R35.3.1 |
| JetPack 代际 | 5.1.1（NVIDIA 的 R35.3.1 配套版本） |
| CPU / 内存 | 8 核 / 16 GiB |
| 功耗模式 | `25W`，nvpmodel mode 3 |
| 项目 Python | `/usr/bin/python3.8`，版本 3.8.10 |
| VS Code | ARM64 1.136.0，Python/Pylance 扩展已安装 |
| 机器人接口 | `eth0`，现场地址 `192.168.123.18/24` |

系统另有 Python 2.7 和 Python 3.9，但不用于本项目：裸命令 `python` 指向 2.7；Python
3.9 无法加载系统为 3.8 编译的 NumPy/OpenCV。项目统一使用基于 Python 3.8 的 `.venv`。

## 为什么使用 `.venv`

- 虚拟环境只改变解释器和包搜索路径，不增加推理循环的计算开销。
- Python 3.8 与 JetPack 系统 OpenCV、宇树 SDK 的 `Python >= 3.8` 要求及旧
  `unitree_py38` checkpoint 验证环境一致。
- `.venv` 位于项目根目录，VS Code 和终端使用同一解释器；新增包不会写入系统 Python。
- 使用 `--system-site-packages` 只为复用 JetPack 已有的 ARM64 OpenCV、PyYAML 和
  PyOpenGL。项目新增包仍安装在 `.venv` 中。

Conda 在这里不会提升运行性能，还会增加一套 ARM 包管理和动态库边界，因此不安装。

## 固定版本

依赖锁文件为 `requirements/orin.lock`。关键版本为：

| 组件 | 版本 | 说明 |
|---|---:|---|
| Python | 3.8.10 | Ubuntu/JetPack 系统解释器 |
| NumPy | 1.24.4 | Python 3.8 的项目内版本 |
| PyTorch | 2.0.0 | PyPI ARM64 CPU-only wheel |
| MuJoCo | 3.2.3 | 已确认提供 CPython 3.8/aarch64 wheel |
| CycloneDDS C/Python | 0.10.2 | 宇树 SDK 固定要求 |
| OpenCV | 4.2.0 | JetPack 系统包 |
| PyYAML | 5.3.1 | Ubuntu 系统包 |

当前不安装 ONNX/ONNX Runtime。仓库还没有 ONNX 模型或等价性测试；先以现有 `.pt`
管线获得 CPU 基线，再单独评估导出误差、单步延迟和抖动，避免同时改变环境和推理后端。

## 创建或修复环境

在联网的 Orin 终端执行：

```bash
cd /home/unitree/sim2real
bash scripts/setup/install_orin_environment.sh
```

该脚本：

1. 用一次性 `virtualenv==20.26.6` 创建 `.venv`，绕过当前系统缺少
   `python3.8-venv` 的问题；不需要 `sudo`。
2. 从官方 tag `0.10.2` 构建 CycloneDDS 到 `.venv`，并核对 commit
   `9995905bce6c4cf9f740d6438bbf7fcfd1c83dfd`。
3. 关闭与运行无关的 `ddsperf`、example 和 test 构建，不修改 DDS 核心行为。
4. 安装锁定依赖并执行只读验证。

不要运行 `sudo pip`、`sudo apt upgrade`、JetPack 刷写或 Conda 安装命令。

## 日常使用

每个新终端只选择一种模式：

```bash
cd /home/unitree/sim2real
source setup.sh policy
source setup.sh mujoco
source setup.sh robot
```

`policy` 和 `mujoco` 不配置机器人 DDS。`robot` 只设置 CycloneDDS 的 `eth0` 绑定；
只有随后显式运行 `scripts/real/` 下的脚本才会初始化 DDS。

当前系统启动环境带有 ROS Foxy 的 `PYTHONPATH` 和 `LD_LIBRARY_PATH`，其中包含
CycloneDDS 0.7。实测它会让 CycloneDDS 0.10.2 的 IDL 工具错误链接旧库。因此
`setup.sh` 会清除 ROS 变量，并只加入项目根目录、内置 SDK 和 `.venv/lib`。

PyPI ARM64 CPU PyTorch 与系统 MuJoCo/OpenCV 使用两套不同的 OpenMP 库。后加载的
PyTorch 会在当前系统出现 `cannot allocate memory in static TLS block`。仿真入口因此
明确先导入 PyTorch，再导入 MuJoCo/OpenCV。项目不使用全局 `LD_PRELOAD`：同时强制加载
两套 `libgomp` 虽然能绕过报错，但会把实现细节注入无关进程，并增加线程池竞争和后续
PyTorch wheel 升级时的维护风险。

`setup.sh` 默认设置 `OMP_NUM_THREADS=1`。短测表明 go2w/go2wcr 使用更多线程没有实际
收益，单线程还能减少与 500 Hz DDS 发布线程的竞争。该设置不改变网络数值；WMP 调优由
基准入口的 `--threads` 单独覆盖。

## VS Code

仓库已提交：

- `.vscode/settings.json`：固定 `.venv/bin/python`、项目源码路径、CycloneDDS 路径和
  `eth0`。
- `.vscode/extensions.json`：只推荐 Python 与 Pylance；本机已安装。

打开 `/home/unitree/sim2real` 后，新建一个终端并确认：

```bash
which python
python --version
```

预期分别为 `/home/unitree/sim2real/.venv/bin/python` 和 `Python 3.8.10`。仓库不提供
一键启动实机控制的 VS Code task/launch，防止误触 LowCmd。

## 只读验证

```bash
source setup.sh mujoco
python scripts/setup/verify_orin_environment.py
```

通过标准：

- Python、架构、关键包版本、CPU-only PyTorch 和项目内 SDK 全部显示 `[OK]`。
- `PYTHONPATH`/`LD_LIBRARY_PATH` 不包含 `/opt/ros/`。
- `LD_PRELOAD` 为空；验证脚本按 PyTorch → MuJoCo/OpenCV 的顺序加载。
- Go2W MuJoCo 场景能无窗口加载，执行器数量为 16。
- 最后一行是 `[PASS]`。

权重不属于 Python 环境。验证脚本要求以下三个被 Git 忽略的精确路径：

```text
models/go2w/model_700.pt
models/go2wcr/model_1499.pt
models/go2wwmp/model_1750.pt
```

不要多套一层 `models/models/`；该目录不会被 controller 使用。2026-09-03 已记录：

| 文件 | 大小（bytes） | SHA-256 |
|---|---:|---|
| `go2w/model_700.pt` | 6,366,674 | `5105a856191fd19f7ee0755b8839f3f5a245b4b6040778351c604b037dba0ebf` |
| `go2wcr/model_1499.pt` | 6,060,386 | `06421c150c387b8476aa69fba51f026ce609232f3bd9954b737a429b9145b690` |
| `go2wwmp/model_1750.pt` | 317,920,547 | `e861a93bbd288fc95867441c0f452a0f3fbdcd981a2ef94757fb2f99e18fa094` |

文件到位和校验一致只证明复制完整；policy 是否可执行、输出是否合理和是否满足 50 Hz，
仍在后续 policy 阶段单独验证。

## 官方依据

- [Unitree SDK2 Python](https://github.com/unitreerobotics/unitree_sdk2_python)：要求
  Python 3.8+、CycloneDDS 0.10.2，并说明从源码安装 CycloneDDS 的流程。
- [Unitree Quick Start](https://support.unitree.com/home/en/developer/Quick_start)：机器人
  网络与 SDK 使用入口。
- [NVIDIA JetPack 5.1.1 安装文档](https://docs.nvidia.com/jetson/jetpack/5.1.1/install-jetpack/index.html)：
  明确 R35.3.1 对应的 JetPack 组件。
- [NVIDIA Jetson PyTorch 安装文档](https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform/index.html)：
  Jetson Python 环境和虚拟环境原则。本项目按需求使用 CPU-only ARM64 wheel。
- [ONNX Runtime Python 文档](https://onnxruntime.ai/docs/get-started/with-python.html)：ARM64
  CPU 包可用；留待性能阶段验证，不属于当前基础环境。
