# ============================================================================
# mujoco_driver.py — MuJoCo 仿真驱动后端
#
# 实现 DriverBase 接口。MuJoCo 关节顺序 = Ctrl 顺序，
# 驱动内部做 Ctrl↔DDS 重映射，对外与 DdsDriver 接口一致。
# ============================================================================

import time
import threading
import numpy as np

import mujoco
import mujoco.viewer

from driver.driver_base import DriverBase, RobotState, MotorCommand
from config.go2w_config import CTRL, CTRL_IDX_FROM_DDS, DDS_IDX_FROM_CTRL


class MujocoDriver(DriverBase):
    """MuJoCo 仿真驱动，对外接口与 DdsDriver 一致（DDS 顺序）。"""

    def __init__(self, xml_path: str, data_hz: int = 500, show_viewer: bool = True):
        self._xml_path = xml_path
        self._data_hz = data_hz
        self._show_viewer = show_viewer

        self._model = None
        self._data = None
        self._viewer = None
        self._running = False
        self._pause = True
        self._joint_num = 0
        self._dt_data = 1.0 / data_hz

        self._state = RobotState()
        self._pending_cmd = MotorCommand()
        self._has_cmd = False
        self._emergency = False

    def initialize(self) -> bool:
        print(f"[MujocoDriver] 加载: {self._xml_path}")
        self._model = mujoco.MjModel.from_xml_path(self._xml_path)
        self._data = mujoco.MjData(self._model)
        self._joint_num = self._model.nu

        # 初始站立姿态
        self._data.ctrl[:] = CTRL.INITIAL_JOINTS_POS

        if self._show_viewer:
            self._viewer = mujoco.viewer.launch_passive(
                self._model, self._data,
                show_left_ui=True, show_right_ui=True,
                key_callback=self._key_callback,
            )
            mujoco.mjv_defaultCamera(self._viewer.cam)
            self._viewer.cam.type = mujoco.mjtCamera.mjCAMERA_TRACKING
            try:
                self._viewer.cam.trackbodyid = self._model.body("base_link").id
            except Exception:
                self._viewer.cam.trackbodyid = self._model.body("base").id

        mujoco.mj_forward(self._model, self._data)
        if self._viewer is not None:
            self._viewer.sync()

        mode = "viewer" if self._show_viewer else "headless"
        print(f"[MujocoDriver] 关节数: {self._joint_num}, 模式: {mode}")
        self._running = True
        return True

    def reset_to_stand(self) -> None:
        """恢复 XML stand keyframe，并同步初始关节控制目标。"""
        if self._joint_num != CTRL.NUM_ACTIONS:
            raise RuntimeError(
                f"MuJoCo actuator 数量错误: {self._joint_num}, "
                f"expected {CTRL.NUM_ACTIONS}"
            )

        keyframe = self._model.key("stand")
        if not np.allclose(keyframe.qpos[-self._joint_num:], CTRL.INITIAL_JOINTS_POS):
            raise RuntimeError("XML stand keyframe 与 CTRL.INITIAL_JOINTS_POS 不一致")
        mujoco.mj_resetDataKeyframe(self._model, self._data, keyframe.id)
        self._data.ctrl[:] = CTRL.INITIAL_JOINTS_POS
        mujoco.mj_forward(self._model, self._data)
        if self._viewer is not None:
            self._viewer.sync()
        print(f"[MujocoDriver] 初始站姿已加载: base_z={self._data.qpos[2]:.3f} m")

    def get_state(self) -> RobotState:
        # 读取 Ctrl 顺序数据，重映射到 DDS 顺序
        qpos = self._data.qpos[-self._joint_num:].copy()
        qvel = self._data.qvel[-self._joint_num:].copy()

        # Ctrl → DDS 重映射
        jpos_dds = qpos[DDS_IDX_FROM_CTRL]
        jvel_dds = qvel[DDS_IDX_FROM_CTRL]

        state = RobotState()
        state.joint_positions = jpos_dds.astype(np.float32)
        state.joint_velocities = jvel_dds.astype(np.float32)
        torques = self._data.qfrc_actuator[-self._joint_num:].copy()
        state.joint_torques = torques[DDS_IDX_FROM_CTRL].astype(np.float32)

        # IMU
        quat = self._data.sensor("BodyQuat").data.copy()  # [w,x,y,z]
        gyro = self._data.sensor("BodyGyro").data.copy()
        acc = self._data.sensor("BodyAcc").data.copy()
        state.imu_quat = np.array([quat[0], quat[1], quat[2], quat[3]], dtype=np.float32)
        state.imu_gyro = gyro.astype(np.float32)
        state.imu_accel = acc.astype(np.float32)
        w, x, y, z = state.imu_quat
        state.imu_rpy = np.array(
            [
                np.arctan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y)),
                np.arcsin(np.clip(2.0 * (w * y - z * x), -1.0, 1.0)),
                np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)),
            ],
            dtype=np.float32,
        )

        return state

    def send_command(self, cmd: MotorCommand) -> None:
        self._pending_cmd = cmd
        self._has_cmd = True

    def set_emergency_damping(self) -> None:
        self._emergency = True
        print("\n[MujocoDriver] !! 紧急阻尼")

    def shutdown(self) -> None:
        self._running = False
        if self._viewer is not None:
            self._viewer.close()
        print("[MujocoDriver] 已关闭")

    def simulate(self):
        """主仿真循环（阻塞）。"""
        if self._viewer is None:
            raise RuntimeError("headless 模式不使用交互式 simulate()")
        thread = threading.Thread(target=self._sync_loop)
        thread.start()

        dt = self._model.opt.timestep
        steps_per_data = int(self._dt_data / dt)

        while self._viewer.is_running() and self._running:
            t_start = time.perf_counter()
            with self._viewer.lock():
                if not self._pause:
                    for _ in range(steps_per_data):
                        if self._has_cmd and not self._emergency:
                            self._apply_command(self._pending_cmd)
                        mujoco.mj_step(self._model, self._data)
                else:
                    mujoco.mj_forward(self._model, self._data)

            elapsed = time.perf_counter() - t_start
            if elapsed < self._dt_data:
                time.sleep(self._dt_data - elapsed)

        thread.join()

    def _apply_command(self, cmd: MotorCommand):
        """将 DDS 顺序指令写入 MuJoCo（Ctrl 顺序）。"""
        # DDS → Ctrl 重映射
        pos_ctrl = cmd.positions[CTRL_IDX_FROM_DDS]
        vel_ctrl = cmd.velocities[CTRL_IDX_FROM_DDS]
        kp_ctrl = cmd.kp[CTRL_IDX_FROM_DDS]
        kd_ctrl = cmd.kd[CTRL_IDX_FROM_DDS]

        for i in range(self._joint_num):
            if i in CTRL.WHEEL_INDICES:
                self._model.actuator_gainprm[i, 0] = kd_ctrl[i]
                self._model.actuator_biasprm[i, 2] = -kd_ctrl[i]
                self._data.ctrl[i] = vel_ctrl[i]
            else:
                self._model.actuator_gainprm[i, 0] = kp_ctrl[i]
                self._model.actuator_biasprm[i, 1] = -kp_ctrl[i]
                self._model.actuator_biasprm[i, 2] = -kd_ctrl[i]
                self._data.ctrl[i] = pos_ctrl[i]

    def _key_callback(self, keycode):
        if chr(keycode) == " ":
            self._pause = not self._pause
            print(f"[MujocoDriver] {'暂停' if self._pause else '运行'}")

    def _sync_loop(self):
        if self._viewer is None:
            return
        while self._viewer.is_running():
            self._viewer.sync()
            time.sleep(0.01)
