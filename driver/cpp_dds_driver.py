"""DriverBase client for the standalone C++ DDS/LowCmd process."""

import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
from typing import Optional

import numpy as np

from config.go2w_config import DDS
from driver.driver_base import DriverBase, MotorCommand, RobotState


_STATE_MAGIC = 0x53544154
_COMMAND_MAGIC = 0x434D4421
_VERSION = 1
_ARM = 1 << 1
_DAMPING = 1 << 2
_STOP = 1 << 3
_STATE_EMERGENCY = 1 << 1
_STATE_OTHER_LOWCMD = 1 << 3
_STATE_PREARM_LOWCMD = 1 << 4
_STATE_STRUCT = struct.Struct("<IHHQQI63f")
_COMMAND_STRUCT = struct.Struct("<IHHQQ80f")


class CppDdsDriver(DriverBase):
    """Keep the existing DriverBase API while C++ owns all DDS work."""

    def __init__(self, net_if: str = DDS.DEFAULT_NET_IF, lowcmd_cpu: Optional[int] = 1,
                 binary: str = "build/cpp/go2w_dds_bridge", monitor_only: bool = False):
        root = Path(__file__).resolve().parents[1]
        self._root = root
        self._binary = Path(binary) if Path(binary).is_absolute() else root / binary
        self._net_if = net_if
        self._lowcmd_cpu = lowcmd_cpu if lowcmd_cpu is not None else -1
        self._monitor_only = monitor_only
        self._process: Optional[subprocess.Popen] = None
        self._state_fd: Optional[int] = None
        self._latest_state = RobotState()
        self._latest_command = MotorCommand()
        self._has_command = False
        self._armed = False
        self._emergency = False
        self._other_lowcmd = False
        self._prearm_lowcmd = False
        self._sequence = 0
        self._state_sequence = 0
        self._state_packets = 0
        self._command_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._state_ready = threading.Event()
        self._heartbeat_stop = threading.Event()
        self._state_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None

    def initialize(self) -> bool:
        if not self._binary.is_file():
            print(f"[CppDdsDriver] 找不到 {self._binary}")
            print("请先执行: cmake -S cpp -B build/cpp && cmake --build build/cpp -j2")
            return False
        state_read, state_write = os.pipe()
        self._state_fd = state_read
        command = [str(self._binary), "--interface", self._net_if,
                   "--cpu", str(self._lowcmd_cpu), "--state-fd", str(state_write)]
        if self._monitor_only:
            command.append("--monitor-only")
        environment = os.environ.copy()
        environment["LD_LIBRARY_PATH"] = "/usr/local/lib"
        environment["GCOV_PREFIX"] = "/tmp/sim2real_gcov"
        environment["GCOV_PREFIX_STRIP"] = "10"
        self._process = subprocess.Popen(
            command, cwd=str(self._root), env=environment,
            stdin=subprocess.PIPE, bufsize=0, pass_fds=(state_write,),
        )
        os.close(state_write)
        if self._process.stdin is not None:
            os.set_blocking(self._process.stdin.fileno(), False)
        self._state_thread = threading.Thread(target=self._state_loop,
                                              name="cpp-dds-state", daemon=True)
        self._state_thread.start()
        if not self._state_ready.wait(5.0):
            print("[CppDdsDriver] 5 秒内没有收到 LowState")
            self.shutdown()
            return False
        print(f"[CppDdsDriver] C++ DDS 已连接, 网口: {self._net_if}")
        return True

    def start_lowcmd_thread(self) -> bool:
        if self._monitor_only or not self._has_command or self._armed:
            return False
        self._armed = True
        self._send_command(_ARM)
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop,
                                                  name="cpp-dds-heartbeat", daemon=True)
        self._heartbeat_thread.start()
        print("[CppDdsDriver] C++ 500Hz LowCmd 已启动")
        return True

    def get_state(self) -> RobotState:
        with self._state_lock:
            return self._latest_state

    def send_command(self, cmd: MotorCommand) -> None:
        arrays = (cmd.positions, cmd.velocities, cmd.kp, cmd.kd, cmd.torques)
        if any(np.asarray(values).shape != (16,) for values in arrays):
            self.set_emergency_damping()
            raise RuntimeError("MotorCommand 必须包含 16 路电机数据")
        if any(not np.isfinite(values).all() for values in arrays):
            self.set_emergency_damping()
            raise RuntimeError("MotorCommand 包含 NaN/Inf")
        with self._command_lock:
            self._latest_command = cmd
            self._has_command = True
        if self._armed:
            self._send_command(0)

    def set_emergency_damping(self) -> None:
        if not self._emergency:
            self._emergency = True
            print("\n[CppDdsDriver] !! 紧急阻尼")
        self._heartbeat_stop.set()
        self._send_packet(_DAMPING, np.zeros(80, dtype=np.float32))

    def shutdown(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=0.2)
        self._send_packet(_DAMPING | _STOP, np.zeros(80, dtype=np.float32))
        if self._process is not None:
            try:
                self._process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                self._process.wait(timeout=1.0)
            self._process = None
        if self._state_thread is not None:
            self._state_thread.join(timeout=0.2)
        if self._state_fd is not None:
            os.close(self._state_fd)
            self._state_fd = None
        print("[CppDdsDriver] 已关闭")

    def stand_up(self) -> bool:
        return self._run_sport_action("standup")

    def release_sport_mode(self) -> bool:
        return self._run_sport_action("release")

    def _run_sport_action(self, action: str) -> bool:
        script = self._root / "scripts/real/sport_mode_once.py"
        result = subprocess.run(
            [sys.executable, str(script), "--interface", self._net_if, "--action", action],
            cwd=str(self._root), check=False,
        )
        return result.returncode == 0

    def _heartbeat_loop(self) -> None:
        """Refresh only the watchdog; C++ performs the 500 Hz zero-order hold."""
        while not self._heartbeat_stop.wait(0.02):
            self._send_command(0)

    def _send_command(self, flags: int) -> None:
        with self._command_lock:
            command = self._latest_command
            values = np.concatenate((command.positions, command.velocities, command.kp,
                                     command.kd, command.torques)).astype(np.float32)
        self._send_packet(flags, values)

    def _send_packet(self, flags: int, values: np.ndarray) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            return
        with self._write_lock:
            self._sequence += 1
            packet = _COMMAND_STRUCT.pack(
                _COMMAND_MAGIC, _VERSION, flags, self._sequence, time.monotonic_ns(), *values
            )
            try:
                os.write(process.stdin.fileno(), packet)
            except (BrokenPipeError, OSError):
                self._emergency = True

    def _state_loop(self) -> None:
        process = self._process
        if process is None or self._state_fd is None:
            return
        fd = self._state_fd
        while True:
            packet = os.read(fd, _STATE_STRUCT.size)
            if not packet:
                return
            if len(packet) != _STATE_STRUCT.size:
                continue
            data = _STATE_STRUCT.unpack(packet)
            if data[0] != _STATE_MAGIC or data[1] != _VERSION:
                continue
            values = np.asarray(data[6:], dtype=np.float32)
            state = RobotState(
                joint_positions=values[0:16].copy(),
                joint_velocities=values[16:32].copy(),
                joint_torques=values[32:48].copy(),
                imu_quat=values[48:52].copy(),
                imu_gyro=values[52:55].copy(),
                imu_accel=values[55:58].copy(),
                imu_rpy=values[58:61].copy(),
                tick=data[5], received_monotonic_ns=data[4],
                battery_voltage=float(values[61]), battery_current=float(values[62]),
            )
            with self._state_lock:
                self._latest_state = state
                self._state_sequence = data[3]
                self._state_packets += 1
                self._emergency = self._emergency or bool(data[2] & _STATE_EMERGENCY)
                self._other_lowcmd = self._other_lowcmd or bool(data[2] & _STATE_OTHER_LOWCMD)
                self._prearm_lowcmd = bool(data[2] & _STATE_PREARM_LOWCMD)
            self._state_ready.set()

    @property
    def emergency(self) -> bool:
        return self._emergency

    @property
    def state_sequence(self) -> int:
        with self._state_lock:
            return self._state_sequence

    @property
    def state_packets(self) -> int:
        with self._state_lock:
            return self._state_packets

    @property
    def other_lowcmd(self) -> bool:
        with self._state_lock:
            return self._other_lowcmd

    @property
    def prearm_lowcmd(self) -> bool:
        with self._state_lock:
            return self._prearm_lowcmd

    @property
    def write_count(self) -> int:
        return 0  # Exact write statistics are printed by C++ on shutdown.
