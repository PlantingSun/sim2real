#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi
set -euo pipefail
DEPTH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export LD_LIBRARY_PATH="${DEPTH_DDS_PREFIX:-$DEPTH_ROOT/.venv}/lib"
export PYTHONPATH="$DEPTH_ROOT"
unset CYCLONEDDS_URI LD_PRELOAD
exec "${DEPTH_PYTHON:-$DEPTH_ROOT/.venv/bin/python}" "$DEPTH_ROOT/scripts/depth/acceptance.py" "$@"
