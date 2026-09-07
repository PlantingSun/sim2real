#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi
set -euo pipefail
DEPTH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPTH_DDS_PREFIX="${DEPTH_DDS_PREFIX:-$DEPTH_ROOT/.venv}"
DEPTH_RS_PREFIX="${DEPTH_RS_PREFIX:-/usr}"
export LD_LIBRARY_PATH="$DEPTH_DDS_PREFIX/lib:$DEPTH_RS_PREFIX/lib/aarch64-linux-gnu"
unset CYCLONEDDS_URI
cmake -S "$DEPTH_ROOT/depth" -B "$DEPTH_ROOT/build/depth" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCycloneDDS_DIR="$DEPTH_DDS_PREFIX/lib/cmake/CycloneDDS" \
    -Drealsense2_DIR="$DEPTH_RS_PREFIX/lib/aarch64-linux-gnu/cmake/realsense2" \
    -DCMAKE_BUILD_RPATH="$DEPTH_DDS_PREFIX/lib;$DEPTH_RS_PREFIX/lib/aarch64-linux-gnu"
cmake --build "$DEPTH_ROOT/build/depth" --parallel 2
cd "$DEPTH_ROOT/build/depth"
ctest --output-on-failure
