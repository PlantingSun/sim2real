#!/usr/bin/env bash
# sim2real_ws 环境准备（必须 source，不会初始化 DDS 或连接机器人）
#
# 用法：
#   source setup.sh policy  # NumPy + PyTorch（默认）
#   source setup.sh mujoco  # 额外检查 MuJoCo
#   source setup.sh robot   # 额外检查 Unitree SDK2/CycloneDDS
#
# ROS2 不属于当前纯 Python 管线的运行依赖。需要旧 ROS 工具时请在另一个终端
# 手动 source /opt/ros/humble/setup.*，避免污染离线测试环境。

SIM2REAL_MODE="${1:-policy}"
case "$SIM2REAL_MODE" in
    policy|mujoco|robot) ;;
    *)
        echo "[ERROR] 未知模式 '$SIM2REAL_MODE'，可选: policy | mujoco | robot"
        return 1 2>/dev/null || exit 1
        ;;
esac

SIM2REAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM2REAL_CONDA_SH=""
if [ -n "${CONDA_EXE:-}" ]; then
    SIM2REAL_CONDA_SH="$(cd "$(dirname "$CONDA_EXE")/.." && pwd)/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    SIM2REAL_CONDA_SH="$HOME/miniconda3/etc/profile.d/conda.sh"
fi

if [ ! -f "$SIM2REAL_CONDA_SH" ]; then
    if command -v python >/dev/null 2>&1; then
        echo "[WARN] 未找到 Conda，使用当前 Python: $(command -v python)"
    else
        echo "[ERROR] 找不到 Conda，也找不到可用的 python"
        return 1 2>/dev/null || exit 1
    fi
else
    # shellcheck disable=SC1090
    source "$SIM2REAL_CONDA_SH"
    if ! conda activate unitree_py38; then
        echo "[ERROR] 无法激活 Conda 环境 unitree_py38"
        return 1 2>/dev/null || exit 1
    fi
fi

case ":${PYTHONPATH:-}:" in
    *":$SIM2REAL_ROOT:"*) ;;
    *) export PYTHONPATH="$SIM2REAL_ROOT${PYTHONPATH:+:$PYTHONPATH}" ;;
esac
SIM2REAL_VENDOR="$SIM2REAL_ROOT/third_party/unitree_sdk2_python"
case ":${PYTHONPATH:-}:" in
    *":$SIM2REAL_VENDOR:"*) ;;
    *) export PYTHONPATH="$SIM2REAL_VENDOR${PYTHONPATH:+:$PYTHONPATH}" ;;
esac

SIM2REAL_MISSING_MODULES=""
_sim2real_check_module() {
    python -c "import $1" >/dev/null 2>&1 || \
        SIM2REAL_MISSING_MODULES="$SIM2REAL_MISSING_MODULES $1"
}

_sim2real_check_module numpy
_sim2real_check_module torch
if [ "$SIM2REAL_MODE" = "mujoco" ]; then
    _sim2real_check_module mujoco
elif [ "$SIM2REAL_MODE" = "robot" ]; then
    _sim2real_check_module unitree_sdk2py
    _sim2real_check_module cyclonedds
fi

if [ -n "$SIM2REAL_MISSING_MODULES" ]; then
    echo "[ERROR] 缺少 Python 模块:$SIM2REAL_MISSING_MODULES"
    unset -f _sim2real_check_module
    return 1 2>/dev/null || exit 1
fi

# 实机模式明确绑定机器人网卡；policy/mujoco 模式不设置 DDS 网卡。
if [ "$SIM2REAL_MODE" = "robot" ]; then
    NET_IF="${UNITREE_NET_IF:-enp0s31f6}"
    export ROS_DOMAIN_ID=0
    export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces>
        <NetworkInterface name=\"${NET_IF}\" priority=\"default\" multicast=\"default\" />
    </Interfaces></General></Domain></CycloneDDS>"

    if [ -d /tmp/cyclonedds/install/lib ]; then
        export CYCLONEDDS_HOME=/tmp/cyclonedds/install
        export LD_LIBRARY_PATH="$CYCLONEDDS_HOME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    fi
fi

echo ""
echo "sim2real_ws ready"
echo "  mode   : $SIM2REAL_MODE"
echo "  python : $(python --version 2>&1)"
echo "  root   : $SIM2REAL_ROOT"
echo "  ROS2   : not sourced (current pipeline does not require it)"
if [ "$SIM2REAL_MODE" = "robot" ]; then
    echo "  DDS IF : $NET_IF"
    echo "  DDS    : network configured; initialized only by a robot script"
else
    echo "  DDS    : network not configured"
fi

unset SIM2REAL_MISSING_MODULES
unset -f _sim2real_check_module
