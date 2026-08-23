# ============================================================================
# dds_driver.py — DDS 实物驱动后端
#
# 实现 DriverBase 接口，通过 Unitree SDK2 (CycloneDDS) 与机器人通信。
# 安全逻辑嵌入 500Hz 发布循环：限位检测 → 零阶保持(ZOH) → 发布。
# 不做指令平滑——与仿真保持一致，PD 控制器和物理惯性自带平滑效果。
# ============================================================================

import time
import threading
import numpy as np

from unitree_sdk2py.core.channel import (ChannelFactoryInitialize,
                                          ChannelPublisher,
                                          ChannelSubscriber)
from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.idl.default import (unitree_go_msg_dds__LowCmd_,
                                         unitree_go_msg_dds__LowState_)
from unitree_sdk2py.utils.crc import CRC
from unitree_sdk2py.utils.thread import RecurrentThread
from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient
from unitree_sdk2py.go2.sport.sport_client import SportClient

from driver.driver_base import DriverBase, RobotState, MotorCommand
from config.go2w_config import DDS


class DdsDriver(DriverBase):

    def __init__(self, net_if: str = DDS.DEFAULT_NET_IF):
        self._net_if = net_if
        self._pub = None
        self._sub = None
        self._low_cmd = None
        self._thread = None
        self._running = False
        self._crc = CRC()

        self._state_lock = threading.Lock()
        self._cmd_lock = threading.Lock()
        self._latest_state = RobotState()
        self._pending_cmd = MotorCommand()
        self._has_pending_cmd = False

        self._emergency = False
        self._violation_msg = ""

    # ── DriverBase 接口 ───────────────────────────────────────────────────

    def initialize(self) -> bool:
        print(f"[DdsDriver] 初始化 DDS, 网口: {self._net_if}")
        ChannelFactoryInitialize(DDS.DOMAIN_ID, self._net_if)

        self._sub = ChannelSubscriber(DDS.LOWSTATE_TOPIC, LowState_)
        self._sub.Init(self._on_lowstate, 10)

        self._low_cmd = unitree_go_msg_dds__LowCmd_()
        self._low_cmd.head[0] = 0xFE
        self._low_cmd.head[1] = 0xEF
        self._low_cmd.level_flag = 0xFF
        self._low_cmd.gpio = 0
        for i in range(20):
            self._low_cmd.motor_cmd[i].mode = 0x01
            self._low_cmd.motor_cmd[i].q = DDS.POS_STOP_F
            self._low_cmd.motor_cmd[i].dq = DDS.VEL_STOP_F
            self._low_cmd.motor_cmd[i].kp = 0.0
            self._low_cmd.motor_cmd[i].kd = 0.0
            self._low_cmd.motor_cmd[i].tau = 0.0

        self._pub = ChannelPublisher(DDS.LOWCMD_TOPIC, LowCmd_)
        self._pub.Init()

        print("[DdsDriver] 初始化完成, LowCmd 发布线程尚未启动")
        return True

    def start_lowcmd_thread(self) -> bool:
        """立即发送当前缓存指令，然后启动 500Hz LowCmd 发布线程。"""
        if self._thread is not None:
            print("[DdsDriver] LowCmd 发布线程已经启动")
            return False

        with self._cmd_lock:
            if not self._has_pending_cmd:
                print("[DdsDriver] 拒绝启动：尚未写入初始电机指令")
                return False
            cmd = self._pending_cmd

        # 第一个实际发出的 LowCmd 就是调用方预先写入的固定指令。
        self._fill_command(cmd)
        self._low_cmd.crc = self._crc.Crc(self._low_cmd)
        self._pub.Write(self._low_cmd)

        self._running = True
        self._thread = RecurrentThread(
            interval=1.0 / DDS.RATE_HZ,
            target=self._control_loop,
        )
        self._thread.Start()
        print("[DdsDriver] 固定初始指令已发送, 500Hz LowCmd 线程已启动")
        return True

    def get_state(self) -> RobotState:
        with self._state_lock:
            return self._latest_state

    def send_command(self, cmd: MotorCommand) -> None:
        with self._cmd_lock:
            self._pending_cmd = cmd
            self._has_pending_cmd = True

    def set_emergency_damping(self) -> None:
        if not self._emergency:
            self._emergency = True
            print("\n[DdsDriver] !! 紧急阻尼 — 全部电机进入阻尼模式")

    def shutdown(self) -> None:
        lowcmd_started = self._thread is not None
        self._running = False
        if lowcmd_started:
            self._thread.Wait()
            self._fill_damping()
            self._low_cmd.crc = self._crc.Crc(self._low_cmd)
            self._pub.Write(self._low_cmd)
            time.sleep(0.05)
        print("[DdsDriver] 已关闭")

    # ── DDS 回调 ──────────────────────────────────────────────────────────

    def _on_lowstate(self, msg: LowState_):
        state = RobotState()
        state.tick = msg.tick
        state.battery_soc = msg.power_v

        jp = np.zeros(16, dtype=np.float32)
        jv = np.zeros(16, dtype=np.float32)
        jt = np.zeros(16, dtype=np.float32)
        for i in range(16):
            ms = msg.motor_state[i]
            jp[i] = ms.q
            jv[i] = ms.dq
            jt[i] = ms.tau_est
        state.joint_positions = jp
        state.joint_velocities = jv
        state.joint_torques = jt

        q = msg.imu_state.quaternion
        state.imu_quat = np.array([q[0], q[1], q[2], q[3]], dtype=np.float32)
        g = msg.imu_state.gyroscope
        state.imu_gyro = np.array([g[0], g[1], g[2]], dtype=np.float32)
        a = msg.imu_state.accelerometer
        state.imu_accel = np.array([a[0], a[1], a[2]], dtype=np.float32)
        r = msg.imu_state.rpy
        state.imu_rpy = np.array([r[0], r[1], r[2]], dtype=np.float32)

        with self._state_lock:
            self._latest_state = state

    # ── 500Hz 控制循环（安全逻辑嵌入此处）────────────────────────────────

    def _control_loop(self):
        if not self._running:
            return

        with self._state_lock:
            state = self._latest_state
        with self._cmd_lock:
            cmd = self._pending_cmd
            has_cmd = self._has_pending_cmd

        if not self._emergency:
            violation = self._check_limits(state)
            if violation:
                self._emergency = True
                self._violation_msg = violation
                print(f"\n[DdsDriver] !! 安全限位违规: {violation}")

        if self._emergency or not has_cmd:
            self._fill_damping()
        else:
            self._fill_command(cmd)

        self._low_cmd.crc = self._crc.Crc(self._low_cmd)
        self._pub.Write(self._low_cmd)

    # ── 安全检测 ──────────────────────────────────────────────────────────

    def _check_limits(self, state: RobotState):
        for i in range(12):
            limits = DDS.JOINT_LIMITS[i]
            q = state.joint_positions[i]
            dq = state.joint_velocities[i]
            if limits["q_min"] is not None and q < limits["q_min"]:
                return f"J{i} q={q:.3f} < q_min={limits['q_min']:.3f}"
            if limits["q_max"] is not None and q > limits["q_max"]:
                return f"J{i} q={q:.3f} > q_max={limits['q_max']:.3f}"
            if limits["dq_max"] is not None and abs(dq) > limits["dq_max"]:
                return f"J{i} |dq|={abs(dq):.3f} > dq_max={limits['dq_max']:.3f}"

        if DDS.WHEEL_VEL_LIMIT is not None:
            for i in range(12, 16):
                dq = state.joint_velocities[i]
                if abs(dq) > DDS.WHEEL_VEL_LIMIT:
                    return f"W{i-12} |dq|={abs(dq):.3f} > limit={DDS.WHEEL_VEL_LIMIT}"
        return None

    # ── LowCmd 填充 ───────────────────────────────────────────────────────

    def _fill_damping(self):
        for i in range(20):
            self._low_cmd.motor_cmd[i].mode = 0x01
            self._low_cmd.motor_cmd[i].q = DDS.POS_STOP_F
            self._low_cmd.motor_cmd[i].dq = 0.0
            self._low_cmd.motor_cmd[i].kp = 0.0
            self._low_cmd.motor_cmd[i].kd = DDS.EMERGENCY_DAMPING_KD
            self._low_cmd.motor_cmd[i].tau = 0.0

    def _fill_command(self, cmd: MotorCommand):
        """零阶保持：直接写入 controller 发来的目标，不做平滑。"""
        for i in range(16):
            mc = self._low_cmd.motor_cmd[i]
            mc.mode = 0x01
            mc.q = cmd.positions[i]
            mc.dq = cmd.velocities[i]
            mc.kp = cmd.kp[i]
            mc.kd = cmd.kd[i]
            mc.tau = cmd.torques[i]

    # ── Sport Mode 释放 ───────────────────────────────────────────────────

    def stand_up(self) -> bool:
        """通过 Sport Mode 发送一次 StandUp 请求，不启动 LowCmd。"""
        print("[DdsDriver] 执行 StandUp...")
        sc = SportClient()
        sc.SetTimeout(DDS.SPORT_MODE_TIMEOUT)
        sc.Init()
        code = sc.StandUp()
        if code != 0:
            print(f"[DdsDriver] ✗ StandUp 失败, code={code}")
            return False
        print("[DdsDriver] ✓ StandUp 请求已发送")
        return True

    def release_sport_mode(self) -> bool:
        """只释放当前 Sport Mode，不执行 StandUp 或 StandDown。"""
        print("[DdsDriver] 释放 Sport Mode...")
        msc = MotionSwitcherClient()
        msc.SetTimeout(DDS.SPORT_MODE_TIMEOUT)
        msc.Init()

        status, result = msc.CheckMode()
        if status != 0 or result is None:
            print(f"[DdsDriver] ✗ CheckMode 失败, status={status}")
            return False
        if not result.get("name", ""):
            print("[DdsDriver] ✓ Sport Mode 已经处于释放状态")
            return True

        mode_name = result.get("name", "unknown")
        print(f"  当前模式: '{mode_name}' → 执行一次 ReleaseMode...")
        code, _ = msc.ReleaseMode()
        if code != 0:
            print(f"[DdsDriver] ✗ ReleaseMode 失败, code={code}")
            return False

        print("[DdsDriver] ✓ ReleaseMode 返回成功，立即进入 LowCmd 接管阶段")
        return True

    @property
    def emergency(self) -> bool:
        return self._emergency
