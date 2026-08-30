# ============================================================================
# controller_go2wcr.py — 去 ROS 化的 CRRL/go2wcr 控制器
#
# CRRL 的 Actor 不是一次直接输出动作，而是对四个课程 stage 依次预测
# 残差动作。每次调用都从零动作开始，前三个 stage 累加残差，第四个 stage
# 生成最终动作。观测、动作和电机顺序与 ControllerGo2w 保持一致。
# ============================================================================

from collections import deque

import numpy as np
import torch

from config.go2w_config import (
    CTRL,
    CRRL,
    CTRL_IDX_FROM_DDS,
    DDS_IDX_FROM_CTRL,
)
from driver.driver_base import MotorCommand, RobotState
from policy.actor_critic import ActorCritic
from policy.normalizer import EmpiricalNormalization
from policy.utils import quat_rotate_inverse


class ControllerGo2wCR:
    """纯 PyTorch CRRL 控制器，不依赖 ROS 或具体驱动后端。"""

    def __init__(self, model_path: str):
        self.initial_pos = torch.tensor(CTRL.INITIAL_JOINTS_POS, dtype=torch.float32)
        self.wheel_indices = torch.tensor(CTRL.WHEEL_INDICES, dtype=torch.long)
        self.dof_mask = torch.tensor(CTRL.DOF_MASK, dtype=torch.bool)

        self.actor_critic = ActorCritic(
            CTRL.NUM_ACTIONS,
            CRRL.ACTOR_OBS_DIM,
            CRRL.CRITIC_OBS_DIM,
            actor_hidden_dims=CRRL.ACTOR_HIDDEN_DIMS,
            critic_hidden_dims=CRRL.CRITIC_HIDDEN_DIMS,
        )
        self.obs_normalizer = EmpiricalNormalization(
            shape=[CTRL.NUM_OBS * CTRL.HISTORY_LENGTH],
            until=1.0e8,
        )
        self._load_model(model_path)

        self.curriculum_embeddings = self._build_curriculum_embeddings()
        self.last_action = torch.zeros(CTRL.NUM_ACTIONS, dtype=torch.float32)
        self.obs_history = deque(maxlen=CTRL.HISTORY_LENGTH)
        self.reset()

    @staticmethod
    def _build_curriculum_embeddings() -> torch.Tensor:
        """按训练配置构造四个 stage 的 [当前, 上一阶段] 正余弦嵌入。"""
        stage_ids = np.arange(1, CRRL.NUM_ASSIST_STAGES + 1, dtype=np.float32)
        cumulative = (stage_ids / CRRL.NUM_ASSIST_STAGES) ** CRRL.ASSIST_CURRICULUM_POWER
        previous = np.concatenate((np.zeros(1, dtype=np.float32), cumulative[:-1]))
        embeddings = np.stack(
            (
                np.sin(np.pi * cumulative),
                np.cos(np.pi * cumulative),
                np.sin(np.pi * previous),
                np.cos(np.pi * previous),
            ),
            axis=1,
        )
        return torch.tensor(embeddings, dtype=torch.float32)

    def _load_model(self, path: str) -> None:
        """加载并校验 Actor/normalizer；推理只使用 Actor。"""
        loaded = torch.load(path, map_location=torch.device("cpu"))
        if not isinstance(loaded, dict):
            raise ValueError(f"模型文件格式错误: {path}")
        if "model_state_dict" not in loaded or "obs_norm_state_dict" not in loaded:
            raise KeyError("模型必须包含 model_state_dict 和 obs_norm_state_dict")

        self.actor_critic.load_state_dict(loaded["model_state_dict"])
        self.obs_normalizer.load_state_dict(loaded["obs_norm_state_dict"])
        self.actor_critic.eval()
        self.obs_normalizer.eval()

        actor_input = self.actor_critic.actor[0].in_features
        actor_output = self.actor_critic.actor[-1].out_features
        if (actor_input, actor_output) != (CRRL.ACTOR_OBS_DIM, CTRL.NUM_ACTIONS):
            raise ValueError(
                "CRRL Actor 维度不匹配: "
                f"got {actor_input}->{actor_output}, "
                f"expected {CRRL.ACTOR_OBS_DIM}->{CTRL.NUM_ACTIONS}"
            )
        print(f"[ControllerGo2wCR] 模型已加载: {path}")

    def reset(self) -> None:
        """用初始站立零运动状态填充历史观测；新一轮测试必须调用。"""
        self.obs_history.clear()
        initial_frame = torch.zeros(CTRL.NUM_OBS, dtype=torch.float32)
        # 53 维观测中的重力是投影重力，不是四元数；竖直站立时为 (0, 0, -1)。
        initial_frame[3:6] = torch.tensor((0.0, 0.0, -1.0))
        for _ in range(CTRL.HISTORY_LENGTH):
            self.obs_history.append(initial_frame.clone())
        self.last_action.zero_()

    def build_obs(self, state: RobotState, cmd_vel: np.ndarray) -> torch.Tensor:
        """从统一 RobotState 构造 265 维历史观测（最新帧在前）。"""
        jpos_dds = torch.as_tensor(state.joint_positions, dtype=torch.float32)
        jvel_dds = torch.as_tensor(state.joint_velocities, dtype=torch.float32)
        jpos_ctrl = jpos_dds[CTRL_IDX_FROM_DDS]
        jvel_ctrl = jvel_dds[CTRL_IDX_FROM_DDS]

        q_w, q_x, q_y, q_z = state.imu_quat
        gravity = quat_rotate_inverse(
            (q_x, q_y, q_z, q_w),
            (0.0, 0.0, -1.0),
        )
        gyro = torch.as_tensor(state.imu_gyro, dtype=torch.float32)
        command = torch.as_tensor(cmd_vel, dtype=torch.float32)
        if command.shape != (3,):
            raise ValueError(f"cmd_vel 必须是 [vx, vy, vyaw]，实际为 {command.shape}")

        frame = torch.cat(
            (
                gyro,
                torch.as_tensor(gravity, dtype=torch.float32),
                command,
                (jpos_ctrl - self.initial_pos)[self.dof_mask],
                jvel_ctrl * 0.05,
                self.last_action,
            )
        )
        if frame.shape != (CTRL.NUM_OBS,):
            raise RuntimeError(f"单帧观测维度错误: {frame.shape}")

        self.obs_history.append(frame.clone())
        return torch.cat(
            [self.obs_history[-i - 1] for i in range(CTRL.HISTORY_LENGTH)],
            dim=0,
        )

    def compute_action(self, obs: torch.Tensor) -> np.ndarray:
        """执行四 stage CRRL 推理，返回 Ctrl 顺序的原始动作。"""
        if obs.shape != (CTRL.NUM_OBS * CTRL.HISTORY_LENGTH,):
            raise ValueError(f"obs 必须是 265 维，实际为 {tuple(obs.shape)}")

        with torch.no_grad():
            # Checkpoint 的 normalizer 保存为 [1, 265]，一维实时观测需要去掉 batch 维。
            normalized = self.obs_normalizer(obs).squeeze(0)
            normalized = torch.clamp(normalized, -CRRL.CLIP_OBS, CRRL.CLIP_OBS)
            previous_action = torch.zeros(CTRL.NUM_ACTIONS, dtype=torch.float32)

            for stage in range(CRRL.NUM_ASSIST_STAGES - 1):
                actor_input = torch.cat(
                    (normalized, previous_action, self.curriculum_embeddings[stage])
                )
                previous_action += self.actor_critic.actor(actor_input)

            actor_input = torch.cat(
                (normalized, previous_action, self.curriculum_embeddings[-1])
            )
            action = previous_action + self.actor_critic.actor(actor_input)
            action = torch.clamp(action, -CRRL.CLIP_ACTION, CRRL.CLIP_ACTION)

        self.last_action = action.clone()
        return action.numpy()

    def action_to_motor_command(self, action: np.ndarray) -> MotorCommand:
        """将 Ctrl 顺序动作转换为 DDS 顺序 MotorCommand。"""
        action_t = torch.as_tensor(action, dtype=torch.float32)
        if action_t.shape != (CTRL.NUM_ACTIONS,):
            raise ValueError(f"action 必须是 16 维，实际为 {tuple(action_t.shape)}")

        scaled = action_t * CTRL.POS_SCALE
        scaled[self.wheel_indices] = action_t[self.wheel_indices] * CTRL.VEL_SCALE
        target = scaled + self.initial_pos

        positions = np.zeros(CTRL.NUM_ACTIONS, dtype=np.float32)
        velocities = np.zeros(CTRL.NUM_ACTIONS, dtype=np.float32)
        kp = np.zeros(CTRL.NUM_ACTIONS, dtype=np.float32)
        kd = np.zeros(CTRL.NUM_ACTIONS, dtype=np.float32)
        for index in range(CTRL.NUM_ACTIONS):
            if index in CTRL.WHEEL_INDICES:
                velocities[index] = float(target[index])
                kp[index] = CTRL.WHEEL_KP
                kd[index] = CTRL.WHEEL_KD
            else:
                positions[index] = float(target[index])
                kp[index] = CTRL.LEG_KP
                kd[index] = CTRL.LEG_KD

        return MotorCommand(
            positions=positions[DDS_IDX_FROM_CTRL],
            velocities=velocities[DDS_IDX_FROM_CTRL],
            kp=kp[DDS_IDX_FROM_CTRL],
            kd=kd[DDS_IDX_FROM_CTRL],
        )
