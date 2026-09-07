#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi
set -euo pipefail
DEPTH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "$DEPTH_ROOT" != /home/unitree/sim2real ]]; then
    echo 'The service template targets /home/unitree/sim2real; adapt it before installation.' >&2
    exit 1
fi
if [[ ${EUID} != 0 ]]; then
    echo 'Run with sudo bash scripts/depth/install_service.sh [--uninstall]' >&2
    exit 1
fi
if [[ "${1:-}" == --uninstall ]]; then
    systemctl disable --now go2w-depth.service
    # Keep the installed file for recovery; disable is sufficient to uninstall startup.
    echo 'Service stopped and disabled; installed unit retained for recovery.'
    exit 0
fi
test -x "$DEPTH_ROOT/build/depth/go2w_depth"
install -m 0644 "$DEPTH_ROOT/depth/go2w-depth.service" /etc/systemd/system/go2w-depth.service
systemctl daemon-reload
systemctl enable --now go2w-depth.service
systemctl status go2w-depth.service --no-pager
