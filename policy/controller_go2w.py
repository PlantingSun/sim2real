# ============================================================================
# controller_go2w.py — 去 ROS 化的 go2w RL 控制器
#
# 从 src/controller/scripts/lib/controller_go2w/controller_go2w.py 改写：
#   删除 rospy / Imu / Twist / MotorControl / MotorReturn
#   新增显式方法: build_obs(state, cmd_vel) → obs, compute_action(obs) → action
#
# 观测 53 维 → 历史 5 帧 → 网络输入 265 维 → 动作 16 维
# 内部使用 Ctrl 顺序，输入/输出由调用方做重映射
# ============================================================================

import copy
from collections import deque

import torch
import numpy as np

from policy.actor_critic import ActorCritic
from policy.normalizer import EmpiricalNormalization
from policy.utils import quat_rotate_inverse
from driver.driver_base import RobotState
from config.go2w_config import CTRL, CTRL_IDX_FROM_DDS, DDS_IDX_FROM_CTRL


class ControllerGo2w:
    """go2w 策略控制器（纯 PyTorch，无 ROS 依赖）。"""

    def __init__(self, model_path: str):
        self.num_action = CTRL.NUM_ACTIONS
        self.num_actor_obs = CTRL.NUM_OBS
        self.history_length = CTRL.HISTORY_LENGTH
        self.clip_obs = CTRL.CLIP_OBS
        self.clip_action = CTRL.CLIP_ACTION
        self.pos_scale = CTRL.POS_SCALE
        self.vel_scale = CTRL.VEL_SCALE
        self.initial_pos = torch.tensor(CTRL.INITIAL_JOINTS_POS, dtype=torch.float32)
        self.wheel_indices = torch.tensor(CTRL.WHEEL_INDICES, dtype=torch.long)
        self.dof_mask = CTRL.DOF_MASK

        # 网络
        self.actor_critic = ActorCritic(
            self.num_action,
            self.num_actor_obs * self.history_length,
            119,  # num_critic_obs (not used at inference)
            actor_hidden_dims=CTRL.ACTOR_HIDDEN_DIMS,
            critic_hidden_dims=CTRL.CRITIC_HIDDEN_DIMS,
        )
        self.obs_normalizer = EmpiricalNormalization(
            shape=[self.num_actor_obs * self.history_length], until=1.0e8
        )
        self._load_model(model_path)

        # 状态缓冲
        self.last_action = torch.zeros(self.num_action, dtype=torch.float32)
        self.obs_history = deque(maxlen=self.history_length)
        self.reset()

    def _load_model(self, path: str):
        loaded = torch.load(path, map_location=torch.device("cpu"))
        self.actor_critic.load_state_dict(loaded["model_state_dict"])
        self.actor_critic.eval()
        self.obs_normalizer.load_state_dict(loaded["obs_norm_state_dict"])
        self.obs_normalizer.eval()
        print(f"[ControllerGo2w] 模型已加载: {path}")

    def reset(self):
        """用初始站立零运动状态填充历史缓冲。"""
        self.obs_history.clear()
        initial_frame = torch.zeros(self.num_actor_obs, dtype=torch.float32)
        # 53 维观测中的重力是投影重力，不是四元数；竖直站立时为 (0, 0, -1)。
        initial_frame[3:6] = torch.tensor((0.0, 0.0, -1.0))
        for _ in range(self.history_length):
            self.obs_history.append(initial_frame.clone())
        self.last_action = torch.zeros(self.num_action, dtype=torch.float32)

    def build_obs(self, state: RobotState, cmd_vel: np.ndarray) -> torch.Tensor:
        """从 RobotState 构建观测向量 [265]。

        Args:
            state: 机器人状态（DDS 顺序）
            cmd_vel: 指令速度 [vx, vy, vyaw]
        Returns:
            obs: [265] 维观测向量 (53*5, 逆时间序)
        """
        # DDS → Ctrl 重映射
        jpos_dds = torch.tensor(state.joint_positions, dtype=torch.float32)
        jvel_dds = torch.tensor(state.joint_velocities, dtype=torch.float32)
        jpos_ctrl = jpos_dds[CTRL_IDX_FROM_DDS]
        jvel_ctrl = jvel_dds[CTRL_IDX_FROM_DDS]

        # IMU 四元数 DDS [w,x,y,z] → [x,y,z,w] 供 quat_rotate_inverse
        q = state.imu_quat  # [w,x,y,z]
        grav = quat_rotate_inverse(
            (q[1], q[2], q[3], q[0]),
            (0.0, 0.0, -1.0),
        )

        # 陀螺仪
        gyro = state.imu_gyro  # [x,y,z]

        # 构建 53 维单帧观测
        obs = torch.cat((
            torch.tensor([gyro[0], gyro[1], gyro[2]], dtype=torch.float32),
            torch.tensor(grav, dtype=torch.float32),
            torch.tensor(cmd_vel, dtype=torch.float32),
            (jpos_ctrl - self.initial_pos)[self.dof_mask],  # 12 腿关节偏差
            jvel_ctrl * 0.05,                                 # 16 关节速度
            self.last_action,                                  # 16 上一帧动作
        ))

        self.obs_history.append(copy.deepcopy(obs))
        # 逆时间序拼接: 最新在前
        actor_obs = torch.cat(
            [self.obs_history[self.history_length - i - 1] for i in range(self.history_length)],
            dim=-1,
        )
        return actor_obs

    def compute_action(self, obs: torch.Tensor) -> np.ndarray:
        """网络推理，返回动作 [16]（Ctrl 顺序）。

        Args:
            obs: [265] 维观测向量
        Returns:
            action: [16] 维原始动作（Ctrl 顺序），未经缩放
        """
        obs_norm = self.obs_normalizer(obs)
        obs_norm = torch.clip(obs_norm, -self.clip_obs, self.clip_obs)
        action = self.actor_critic.actor(obs_norm.detach()).detach().flatten()
        action = torch.clip(action, -self.clip_action, self.clip_action)
        self.last_action = action
        return action.numpy()

    def action_to_motor_command(self, action: np.ndarray) -> np.ndarray:
        """将网络原始动作转换为 DDS 顺序的 MotorCommand 所需数据。

        Args:
            action: [16] 原始动作（Ctrl 顺序）
        Returns:
            pos_dds: 目标位置 [16]（DDS 顺序），轮子位置为 0
            vel_dds: 目标速度 [16]（DDS 顺序），腿关节速度为 0
            kp_dds: kp [16]（DDS 顺序）
            kd_dds: kd [16]（DDS 顺序）
        """
        action_t = torch.tensor(action, dtype=torch.float32)

        # 缩放
        scaled = action_t * self.pos_scale
        scaled[self.wheel_indices] = action_t[self.wheel_indices] * self.vel_scale
        output = scaled + self.initial_pos

        pos_ctrl = np.zeros(16, dtype=np.float32)
        vel_ctrl = np.zeros(16, dtype=np.float32)
        kp_ctrl = np.zeros(16, dtype=np.float32)
        kd_ctrl = np.zeros(16, dtype=np.float32)

        for i in range(16):
            if i in CTRL.WHEEL_INDICES:
                pos_ctrl[i] = 0.0
                vel_ctrl[i] = float(output[i])
                kp_ctrl[i] = CTRL.WHEEL_KP
                kd_ctrl[i] = CTRL.WHEEL_KD
            else:
                pos_ctrl[i] = float(output[i])
                vel_ctrl[i] = 0.0
                kp_ctrl[i] = CTRL.LEG_KP
                kd_ctrl[i] = CTRL.LEG_KD

        # Ctrl → DDS 重映射
        pos_dds = pos_ctrl[DDS_IDX_FROM_CTRL]
        vel_dds = vel_ctrl[DDS_IDX_FROM_CTRL]
        kp_dds = kp_ctrl[DDS_IDX_FROM_CTRL]
        kd_dds = kd_ctrl[DDS_IDX_FROM_CTRL]

        return pos_dds, vel_dds, kp_dds, kd_dds
