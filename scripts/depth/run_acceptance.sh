#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi
set -euo pipefail
DEPTH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "$DEPTH_ROOT/scripts/depth/python_env.sh"
exec "$DEPTH_RUNTIME_PYTHON" "$DEPTH_ROOT/scripts/depth/acceptance.py" "$@"
