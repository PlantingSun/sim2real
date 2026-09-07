#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi
set -u
DEPTH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
lsusb
lsusb -t
ip -br addr
dpkg-query -W '*realsense*'
journalctl -k -b --no-pager | rg -i 'usb|xusb|typec|fusb|realsense' | tail -80
bash "$DEPTH_ROOT/scripts/depth/run_publisher.sh" --diagnose
