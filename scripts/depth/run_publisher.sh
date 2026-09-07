#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi
set -euo pipefail
DEPTH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export LD_LIBRARY_PATH="${DEPTH_DDS_PREFIX:-$DEPTH_ROOT/.venv}/lib:${DEPTH_RS_PREFIX:-/usr}/lib/aarch64-linux-gnu"
unset CYCLONEDDS_URI LD_PRELOAD
# Hold an advisory lock across exec; diagnostics and synthetic tests do not open a stream.
DEPTH_NEEDS_CAMERA=1
for DEPTH_ARG in "$@"; do
    case "$DEPTH_ARG" in --synthetic|--diagnose|--help) DEPTH_NEEDS_CAMERA=0 ;; esac
done
if [[ "$DEPTH_NEEDS_CAMERA" == 1 ]]; then
    exec 9>"$DEPTH_ROOT/build/depth/camera.lock"
    if ! flock -n 9; then
        echo 'CAMERA_IN_USE: another depth publisher holds the camera lock; stop it first.' >&2
        exit 75
    fi
fi
exec "$DEPTH_ROOT/build/depth/go2w_depth" "$@"
