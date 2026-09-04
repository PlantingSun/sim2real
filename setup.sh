#!/usr/bin/env bash
# Orin NX 项目环境入口。必须 source；本脚本不会初始化 DDS 或连接机器人。
#
# 用法：
#   source setup.sh policy  # NumPy + CPU PyTorch
#   source setup.sh mujoco  # 额外检查 MuJoCo、OpenCV 和 PyYAML
#   source setup.sh robot   # 额外检查 Unitree SDK2/CycloneDDS，并绑定 eth0

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

if [ ! -x "$SIM2REAL_VENV/bin/python" ]; then
    echo "[ERROR] 缺少 $SIM2REAL_VENV"
    echo "        请按 guide/12_orin_environment.md 创建环境"
    return 1 2>/dev/null || exit 1
fi

# 只使用项目内 Python 3.8 环境，不回退到 Conda 或系统 Python。
# shellcheck disable=SC1091
source "$SIM2REAL_VENV/bin/activate"
if ! python -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 8))'; then
    echo "[ERROR] .venv 不是 Python 3.8 环境"
    return 1 2>/dev/null || exit 1
fi

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

export PYTHONPATH="$SIM2REAL_ROOT:$SIM2REAL_VENDOR"
export CYCLONEDDS_HOME="$SIM2REAL_VENV"
export LD_LIBRARY_PATH="$SIM2REAL_VENV/lib"
# 小型实时 Actor 单线程延时更稳定；WMP 调优时可在 source 前显式覆盖。
export OMP_NUM_THREADS="${SIM2REAL_TORCH_THREADS:-1}"

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

# Orin 的 eth0 已现场确认为 192.168.123.18/24；仅 robot 模式配置 DDS。
if [ "$SIM2REAL_MODE" = "robot" ]; then
    SIM2REAL_NET_IF="${UNITREE_NET_IF:-eth0}"
    export ROS_DOMAIN_ID=0
    export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces>
        <NetworkInterface name=\"${SIM2REAL_NET_IF}\" priority=\"default\" multicast=\"default\" />
    </Interfaces></General></Domain></CycloneDDS>"
fi

echo ""
echo "sim2real ready"
echo "  mode   : $SIM2REAL_MODE"
echo "  python : $(python --version 2>&1) ($VIRTUAL_ENV)"
echo "  root   : $SIM2REAL_ROOT"
echo "  threads: $OMP_NUM_THREADS (PyTorch/OpenMP)"
echo "  ROS2   : isolated (current pipeline does not require it)"
if [ "$SIM2REAL_MODE" = "robot" ]; then
    echo "  DDS IF : $SIM2REAL_NET_IF"
    echo "  DDS    : network configured; initialized only by a robot script"
else
    echo "  DDS    : network not configured"
fi

unset SIM2REAL_SETUP_FILE
unset SIM2REAL_MISSING_MODULES
unset -f _sim2real_check_module
