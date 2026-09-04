#!/usr/bin/env bash
# 在机载 Orin NX 上创建本项目唯一的 Python 3.8 环境。
# 本脚本会联网下载依赖，但不会使用 sudo、修改系统 Python 或连接机器人。

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
LOCK_FILE="$PROJECT_ROOT/requirements/orin.lock"
CYCLONEDDS_COMMIT="9995905bce6c4cf9f740d6438bbf7fcfd1c83dfd"
TEMP_DIR="$(mktemp -d /tmp/sim2real-orin-env.XXXXXX)"

cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

if [ "$(uname -m)" != "aarch64" ]; then
    echo "[ERROR] 本脚本只用于 aarch64 Orin NX"
    exit 1
fi
if ! command -v python3.8 >/dev/null 2>&1; then
    echo "[ERROR] 找不到系统 Python 3.8"
    exit 1
fi
for command_name in cmake git; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "[ERROR] 缺少系统命令: $command_name"
        exit 1
    fi
done

# 不让系统全局 ROS Foxy 的 Python 路径或 CycloneDDS 0.7 参与构建。
unset PYTHONPATH
unset LD_LIBRARY_PATH
unset LD_PRELOAD
unset AMENT_PREFIX_PATH
unset CMAKE_PREFIX_PATH
unset COLCON_PREFIX_PATH
unset ROS_DISTRO
unset ROS_PYTHON_VERSION
unset ROS_VERSION

if ! "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
    echo "[1/4] 创建项目内 Python 3.8 虚拟环境"
    python3.8 -m pip install \
        --no-cache-dir \
        --target "$TEMP_DIR/virtualenv" \
        virtualenv==20.26.6
    PYTHONPATH="$TEMP_DIR/virtualenv" python3.8 -m virtualenv \
        --system-site-packages "$VENV_DIR"
else
    echo "[1/4] 复用已有 .venv"
fi
if ! "$VENV_DIR/bin/python" -c \
    'import sys; raise SystemExit(sys.version_info[:2] != (3, 8))'; then
    echo "[ERROR] 已有 .venv 不是 Python 3.8 环境"
    exit 1
fi

if [ ! -f "$VENV_DIR/lib/libddsc.so.0.10.2" ]; then
    echo "[2/4] 构建 CycloneDDS 0.10.2 核心库"
    git clone --depth 1 --branch 0.10.2 \
        https://github.com/eclipse-cyclonedds/cyclonedds.git \
        "$TEMP_DIR/cyclonedds"
    if [ "$(git -C "$TEMP_DIR/cyclonedds" rev-parse HEAD)" != "$CYCLONEDDS_COMMIT" ]; then
        echo "[ERROR] CycloneDDS 0.10.2 commit 与审查记录不一致"
        exit 1
    fi
    cmake -S "$TEMP_DIR/cyclonedds" -B "$TEMP_DIR/cyclonedds-build" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="$VENV_DIR" \
        -DBUILD_DDSPERF=OFF \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_TESTING=OFF
    cmake --build "$TEMP_DIR/cyclonedds-build" --parallel 4
    cmake --install "$TEMP_DIR/cyclonedds-build"
else
    echo "[2/4] 复用已有 CycloneDDS 0.10.2 核心库"
fi

echo "[3/4] 安装锁定的 Python 依赖"
export CYCLONEDDS_HOME="$VENV_DIR"
export LD_LIBRARY_PATH="$VENV_DIR/lib"
# 锁文件已列出全部项目内传递依赖；--no-deps 避免解析无关的 Ubuntu 系统包元数据。
"$VENV_DIR/bin/python" -m pip install --no-cache-dir --no-deps -r "$LOCK_FILE"

echo "[4/4] 执行只读环境验证"
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/third_party/unitree_sdk2_python"
export OMP_NUM_THREADS=1
"$VENV_DIR/bin/python" "$PROJECT_ROOT/scripts/setup/verify_orin_environment.py"
