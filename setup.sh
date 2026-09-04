#!/usr/bin/env bash
# 笔记本/Orin NX 共用环境入口。必须 source；本脚本不会初始化 DDS 或连接机器人。
#
# 用法：
#   source setup.sh policy  # NumPy + CPU PyTorch
#   source setup.sh mujoco  # 额外检查 MuJoCo、OpenCV 和 PyYAML
#   source setup.sh robot   # 额外检查 Unitree SDK2/CycloneDDS，并绑定对应实机网卡
#
# 默认按 CPU 架构选择宿主机：x86_64=laptop，aarch64=orin。需要强制指定时：
#   SIM2REAL_HOST=laptop source setup.sh robot
#   SIM2REAL_HOST=orin source setup.sh robot

SIM2REAL_MODE="${1:-policy}"
case "$SIM2REAL_MODE" in
    policy|mujoco|robot) ;;
    *)
        echo "[ERROR] 未知模式 '$SIM2REAL_MODE'，可选: policy | mujoco | robot"
        return 1 2>/dev/null || exit 1
        ;;
esac

# setup.sh 同时支持 Bash 和本机默认的 Zsh。
if [ -n "${BASH_VERSION:-}" ]; then
    SIM2REAL_SETUP_FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
    SIM2REAL_SETUP_FILE="${(%):-%N}"
else
    echo "[ERROR] 请在 Bash 或 Zsh 中 source setup.sh"
    return 1 2>/dev/null || exit 1
fi

SIM2REAL_ROOT="$(cd "$(dirname "$SIM2REAL_SETUP_FILE")" && pwd)"
SIM2REAL_VENV="$SIM2REAL_ROOT/.venv"
SIM2REAL_VENDOR="$SIM2REAL_ROOT/third_party/unitree_sdk2_python"

SIM2REAL_HOST_PROFILE="${SIM2REAL_HOST:-auto}"
if [ "$SIM2REAL_HOST_PROFILE" = "auto" ]; then
    case "$(uname -m)" in
        aarch64|arm64) SIM2REAL_HOST_PROFILE="orin" ;;
        *) SIM2REAL_HOST_PROFILE="laptop" ;;
    esac
fi
case "$SIM2REAL_HOST_PROFILE" in
    laptop|orin) ;;
    *)
        echo "[ERROR] SIM2REAL_HOST='$SIM2REAL_HOST_PROFILE'，可选: auto | laptop | orin"
        return 1 2>/dev/null || exit 1
        ;;
esac

# 当前系统全局加载了 ROS Foxy。纯 Python 控制链不使用 ROS，因此清除其搜索路径，
# 防止 ROS 自带 CycloneDDS 0.7 覆盖宇树 SDK 要求的 CycloneDDS 0.10.2。
unset PYTHONPATH
unset LD_LIBRARY_PATH
unset LD_PRELOAD
unset AMENT_PREFIX_PATH
unset CMAKE_PREFIX_PATH
unset COLCON_PREFIX_PATH
unset ROS_DISTRO
unset ROS_DOMAIN_ID
unset ROS_PYTHON_VERSION
unset ROS_VERSION
unset CYCLONEDDS_URI

if [ "$SIM2REAL_HOST_PROFILE" = "orin" ]; then
    if [ ! -x "$SIM2REAL_VENV/bin/python" ]; then
        echo "[ERROR] 缺少 $SIM2REAL_VENV"
        echo "        请按 guide/12_orin_environment.md 创建环境"
        return 1 2>/dev/null || exit 1
    fi
    # shellcheck disable=SC1091
    source "$SIM2REAL_VENV/bin/activate"
    if ! python -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 8))'; then
        echo "[ERROR] .venv 不是 Python 3.8 环境"
        return 1 2>/dev/null || exit 1
    fi
    export CYCLONEDDS_HOME="$SIM2REAL_VENV"
    export LD_LIBRARY_PATH="$SIM2REAL_VENV/lib"
    # Orin 上小型 Actor 单线程延时更稳定。
    export OMP_NUM_THREADS="${SIM2REAL_TORCH_THREADS:-1}"
else
    SIM2REAL_CONDA_SH=""
    if [ -n "${CONDA_EXE:-}" ]; then
        SIM2REAL_CONDA_SH="$(cd "$(dirname "$CONDA_EXE")/.." && pwd)/etc/profile.d/conda.sh"
    elif [ -f "${HOME}/miniconda3/etc/profile.d/conda.sh" ]; then
        SIM2REAL_CONDA_SH="${HOME}/miniconda3/etc/profile.d/conda.sh"
    fi
    if [ ! -f "$SIM2REAL_CONDA_SH" ]; then
        echo "[ERROR] 笔记本模式找不到 Conda 初始化脚本"
        return 1 2>/dev/null || exit 1
    fi
    # shellcheck disable=SC1090
    source "$SIM2REAL_CONDA_SH"
    if ! conda activate unitree_py38; then
        echo "[ERROR] 无法激活 Conda 环境 unitree_py38"
        return 1 2>/dev/null || exit 1
    fi
    # 与已验证的笔记本 Git 版本一致：默认由 PyTorch 决定线程数；需要时仍可显式覆盖。
    if [ -n "${SIM2REAL_TORCH_THREADS:-}" ]; then
        export OMP_NUM_THREADS="$SIM2REAL_TORCH_THREADS"
    else
        unset OMP_NUM_THREADS
    fi
    if [ -d /tmp/cyclonedds/install/lib ]; then
        export CYCLONEDDS_HOME=/tmp/cyclonedds/install
        export LD_LIBRARY_PATH="$CYCLONEDDS_HOME/lib"
    fi
fi

export PYTHONPATH="$SIM2REAL_ROOT:$SIM2REAL_VENDOR"

SIM2REAL_MISSING_MODULES=""
_sim2real_check_module() {
    python -c "import $1" >/dev/null 2>&1 || \
        SIM2REAL_MISSING_MODULES="$SIM2REAL_MISSING_MODULES $1"
}

_sim2real_check_module torch
_sim2real_check_module numpy
if [ "$SIM2REAL_MODE" = "mujoco" ]; then
    _sim2real_check_module mujoco
    _sim2real_check_module cv2
    _sim2real_check_module yaml
elif [ "$SIM2REAL_MODE" = "robot" ]; then
    _sim2real_check_module cyclonedds
    _sim2real_check_module unitree_sdk2py
fi

if [ -n "$SIM2REAL_MISSING_MODULES" ]; then
    echo "[ERROR] 缺少 Python 模块:$SIM2REAL_MISSING_MODULES"
    unset -f _sim2real_check_module
    return 1 2>/dev/null || exit 1
fi

# 仅 robot 模式配置 DDS。Orin 默认 eth0；笔记本恢复已验证的 enp0s31f6。
if [ "$SIM2REAL_MODE" = "robot" ]; then
    if [ "$SIM2REAL_HOST_PROFILE" = "orin" ]; then
        SIM2REAL_DEFAULT_NET_IF="eth0"
    else
        SIM2REAL_DEFAULT_NET_IF="enp0s31f6"
    fi
    SIM2REAL_NET_IF="${UNITREE_NET_IF:-$SIM2REAL_DEFAULT_NET_IF}"
    export SIM2REAL_NET_IF
    export ROS_DOMAIN_ID=0
    export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces>
        <NetworkInterface name=\"${SIM2REAL_NET_IF}\" priority=\"default\" multicast=\"default\" />
    </Interfaces></General></Domain></CycloneDDS>"
fi

echo ""
echo "sim2real ready"
echo "  host   : $SIM2REAL_HOST_PROFILE ($(uname -m))"
echo "  mode   : $SIM2REAL_MODE"
echo "  python : $(python --version 2>&1) (${VIRTUAL_ENV:-${CONDA_PREFIX:-unknown}})"
echo "  root   : $SIM2REAL_ROOT"
echo "  threads: ${OMP_NUM_THREADS:-PyTorch default} (PyTorch/OpenMP)"
echo "  ROS2   : isolated (current pipeline does not require it)"
if [ "$SIM2REAL_MODE" = "robot" ]; then
    echo "  DDS IF : $SIM2REAL_NET_IF"
    echo "  DDS    : network configured; initialized only by a robot script"
else
    echo "  DDS    : network not configured"
fi

unset SIM2REAL_SETUP_FILE
unset SIM2REAL_CONDA_SH
unset SIM2REAL_DEFAULT_NET_IF
unset SIM2REAL_MISSING_MODULES
unset -f _sim2real_check_module
