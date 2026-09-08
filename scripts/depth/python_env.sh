#!/usr/bin/env bash
# Resolve a Python environment that can actually run the depth receiver.
# This file is sourced by the depth wrappers; it never creates a DDS participant.

if [ -z "${DEPTH_ROOT:-}" ]; then
    echo "[ERROR] DEPTH_ROOT is not set by the calling script" >&2
    return 1
fi

_depth_python_works() {
    [ -x "$1" ] && "$1" -c 'import cyclonedds, numpy' >/dev/null 2>&1
}

if [ -n "${DEPTH_PYTHON:-}" ]; then
    if ! _depth_python_works "$DEPTH_PYTHON"; then
        echo "[ERROR] DEPTH_PYTHON is not executable or lacks cyclonedds/numpy: $DEPTH_PYTHON" >&2
        return 1
    fi
    DEPTH_RUNTIME_PYTHON="$DEPTH_PYTHON"
else
    DEPTH_RUNTIME_PYTHON=""
    _depth_candidates=()
    [ -n "${VIRTUAL_ENV:-}" ] && _depth_candidates+=("$VIRTUAL_ENV/bin/python")
    [ -n "${CONDA_PREFIX:-}" ] && _depth_candidates+=("$CONDA_PREFIX/bin/python")
    _depth_candidates+=("$DEPTH_ROOT/.venv/bin/python")
    [ -n "${HOME:-}" ] && _depth_candidates+=("$HOME/miniconda3/envs/unitree_py38/bin/python")
    command -v python >/dev/null 2>&1 && _depth_candidates+=("$(command -v python)")
    command -v python3 >/dev/null 2>&1 && _depth_candidates+=("$(command -v python3)")

    for _depth_candidate in "${_depth_candidates[@]}"; do
        if _depth_python_works "$_depth_candidate"; then
            DEPTH_RUNTIME_PYTHON="$_depth_candidate"
            break
        fi
    done
    if [ -z "$DEPTH_RUNTIME_PYTHON" ]; then
        echo "[ERROR] No Python environment with cyclonedds and numpy was found." >&2
        echo "        Run 'source setup.sh robot' or set DEPTH_PYTHON explicitly." >&2
        return 1
    fi
fi

# Prefer an explicit CycloneDDS installation. Otherwise use the selected
# environment's lib directory and discard inherited ROS library paths.
DEPTH_RUNTIME_PREFIX="${DEPTH_DDS_PREFIX:-${CYCLONEDDS_HOME:-}}"
if [ -z "$DEPTH_RUNTIME_PREFIX" ]; then
    DEPTH_RUNTIME_PREFIX="$(cd "$(dirname "$DEPTH_RUNTIME_PYTHON")/.." && pwd)"
fi
if [ -d "$DEPTH_RUNTIME_PREFIX/lib" ]; then
    export LD_LIBRARY_PATH="$DEPTH_RUNTIME_PREFIX/lib"
else
    unset LD_LIBRARY_PATH
fi

export DEPTH_RUNTIME_PYTHON
export PYTHONPATH="$DEPTH_ROOT"
unset CYCLONEDDS_URI LD_PRELOAD

unset _depth_candidate
unset _depth_candidates
unset -f _depth_python_works
