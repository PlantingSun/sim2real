# ============================================================================
# controller_go2wwmp.py — 去 ROS 化的 Go2W WMP 控制器
#
# 网络结构和 world-model 定义已拷贝到当前项目；这里不引入 ROS1、Isaac Gym
# 或训练 runner，只保留实机/仿真推理所需的状态、深度和动作链。
# ============================================================================

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Optional

import numpy as np
import torch

from config.go2w_config import CTRL, CTRL_IDX_FROM_DDS, DDS_IDX_FROM_CTRL
from driver.driver_base import MotorCommand, RobotState
from policy.actor_critic_wmp import ActorCriticWMP
from policy.dreamer.models import WorldModel
from policy.utils import quat_rotate_inverse


class ControllerGo2wWMP:
    """Go2W WMP 推理适配器，不依赖 ROS 或具体驱动后端。"""

    IMAGE_SHAPE = (64, 64)
    DEPTH_NEAR_M = 0.0
    DEPTH_FAR_M = 2.0
    DEPTH_CENTER = 0.5
    UPDATE_INTERVAL = 5
    PROP_DIM = CTRL.NUM_ACTIONS * 2 + 9 - 4  # 37，去掉四个轮关节位置
    HISTORY_FRAME_DIM = 50  # gyro(3) + gravity(3) + legs(12) + dq(16) + action(16)
    HISTORY_LENGTH = 5
    HISTORY_DIM = HISTORY_FRAME_DIM * HISTORY_LENGTH
    PRIVILEGED_DIM = 20 + CTRL.NUM_ACTIONS * 2 + 6 + 3
    HEIGHT_DIM = 17 * 11
    ACTOR_OBS_DIM = PRIVILEGED_DIM + PROP_DIM + CTRL.NUM_ACTIONS + HEIGHT_DIM
    WM_FEATURE_DIM = 512
    WM_LATENT_DIM = 40
    COMMAND_SCALE = torch.tensor((1.0, 1.0, 0.25), dtype=torch.float32)

    def __init__(self, model_path: str, config_path=None):
        self.initial_pos = torch.tensor(CTRL.INITIAL_JOINTS_POS, dtype=torch.float32)
        self.wheel_indices = torch.tensor(CTRL.WHEEL_INDICES, dtype=torch.long)
        self.dof_mask = torch.tensor(CTRL.DOF_MASK, dtype=torch.bool)

        self.policy = ActorCriticWMP(
            num_actor_obs=self.ACTOR_OBS_DIM,
            num_critic_obs=self.ACTOR_OBS_DIM,
            num_actions=CTRL.NUM_ACTIONS,
            encoder_hidden_dims=[256, 128],
            wm_encoder_hidden_dims=[64, 64],
            actor_hidden_dims=[512, 256, 128],
            critic_hidden_dims=[512, 256, 128],
            activation="elu",
            init_noise_std=1.0,
            latent_dim=48,
            height_dim=self.HEIGHT_DIM,
            privileged_dim=self.PRIVILEGED_DIM,
            history_dim=self.HISTORY_DIM,
            wm_feature_dim=self.WM_FEATURE_DIM,
            wm_latent_dim=self.WM_LATENT_DIM,
        )

        if config_path is None:
            config_path = Path(__file__).resolve().parents[1] / "config/go2wwmp_configs.yaml"
        wm_config = self._load_world_model_config(Path(config_path))
        wm_config.num_actions *= self.UPDATE_INTERVAL
        self.world_model = WorldModel(
            wm_config,
            {"prop": (self.PROP_DIM,), "image": self.IMAGE_SHAPE + (1,)},
            use_camera=True,
        )
        self._load_checkpoint(model_path)

        self.command = np.zeros(3, dtype=np.float32)
        self.last_action = torch.zeros(CTRL.NUM_ACTIONS, dtype=torch.float32)
        self.obs_history = torch.zeros(self.HISTORY_LENGTH, self.HISTORY_FRAME_DIM)
        self.wm_action_history = torch.zeros(self.UPDATE_INTERVAL, CTRL.NUM_ACTIONS)
        self.previous_depth = None
        self.wm_latent = None
        self.wm_feature = torch.zeros(self.WM_FEATURE_DIM)
        self.is_first = torch.ones(1, dtype=torch.float32)
        self.counter = 0
        self.reset()

    @staticmethod
    def _load_world_model_config(path: Path) -> Namespace:
        """读取本项目内置的 defaults 配置，返回 WorldModel 所需的 Namespace。"""
        if not path.is_file():
            raise FileNotFoundError(f"找不到 WMP world-model 配置: {path}")
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RuntimeError("读取 WMP 配置需要 PyYAML（模块名 yaml）") from exc

        with path.open("r", encoding="utf-8") as stream:
            configs = yaml.safe_load(stream)
        values = configs["defaults"]
        values = ControllerGo2wWMP._coerce_numeric_strings(dict(values))
        values["device"] = "cpu"
        return Namespace(**values)

    @staticmethod
    def _coerce_numeric_strings(value):
        """兼容 PyYAML 将 ``1e-4`` 读成字符串的情况。"""
        if isinstance(value, dict):
            return {key: ControllerGo2wWMP._coerce_numeric_strings(item) for key, item in value.items()}
        if isinstance(value, list):
            return [ControllerGo2wWMP._coerce_numeric_strings(item) for item in value]
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return value
        return value

    def _load_checkpoint(self, model_path: str) -> None:
        """严格加载 Actor 和 world model，避免把错误 checkpoint 当作可用模型。"""
        path = Path(model_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"找不到 WMP checkpoint: {path}\n"
                "请确认默认 WMP checkpoint 已放入当前项目，或用 --model 指定已审查的副本。"
            )

        loaded = torch.load(path, map_location=torch.device("cpu"))
        if not isinstance(loaded, dict):
            raise ValueError(f"WMP checkpoint 格式错误: {path}")
        required = {"model_state_dict", "world_model_dict"}
        missing = required.difference(loaded)
        if missing:
            raise KeyError(f"WMP checkpoint 缺少字段: {sorted(missing)}")

        self.policy.load_state_dict(loaded["model_state_dict"], strict=True)
        self.world_model.load_state_dict(loaded["world_model_dict"], strict=True)
        self.policy.eval()
        self.world_model.eval()
        print(f"[ControllerGo2wWMP] 模型已加载: {path}")
        print(
            f"[ControllerGo2wWMP] obs_now={self.PROP_DIM + CTRL.NUM_ACTIONS}, "
            f"history={self.HISTORY_DIM}, wm_feature={self.WM_FEATURE_DIM}, action={CTRL.NUM_ACTIONS}"
        )

    def reset(self) -> None:
        """恢复与训练 runner 相同的全零历史和 world-model 初始状态。"""
        self.last_action.zero_()
        self.obs_history.zero_()
        self.wm_action_history.zero_()
        self.previous_depth = None
        self.wm_latent = None
        self.wm_feature.zero_()
        self.is_first.fill_(1.0)
        self.counter = 0

    def _build_prop(self, state: RobotState, command: np.ndarray) -> torch.Tensor:
        """按 simtosim 顺序构造 37 维本体/命令输入。"""
        jpos_dds = torch.as_tensor(state.joint_positions, dtype=torch.float32)
        jvel_dds = torch.as_tensor(state.joint_velocities, dtype=torch.float32)
        if jpos_dds.shape != (CTRL.NUM_ACTIONS,) or jvel_dds.shape != (CTRL.NUM_ACTIONS,):
            raise ValueError("WMP 需要 16 维关节位置和速度")

        jpos_ctrl = jpos_dds[CTRL_IDX_FROM_DDS]
        jvel_ctrl = jvel_dds[CTRL_IDX_FROM_DDS]
        q_w, q_x, q_y, q_z = state.imu_quat
        gravity = quat_rotate_inverse((q_x, q_y, q_z, q_w), (0.0, 0.0, -1.0))
        command_t = torch.as_tensor(command, dtype=torch.float32)
        if command_t.shape != (3,):
            raise ValueError(f"cmd_vel 必须是 [vx, vy, vyaw]，实际为 {tuple(command_t.shape)}")
        if not torch.isfinite(command_t).all():
            raise ValueError("cmd_vel 包含 NaN 或 Inf")

        prop = torch.cat(
            (
                torch.as_tensor(state.imu_gyro, dtype=torch.float32) * 0.25,
                torch.as_tensor(gravity, dtype=torch.float32),
                command_t * self.COMMAND_SCALE,
                (jpos_ctrl - self.initial_pos)[self.dof_mask],
                jvel_ctrl * 0.05,
            )
        )
        if prop.shape != (self.PROP_DIM,):
            raise RuntimeError(f"WMP 本体输入维度错误: {tuple(prop.shape)}")
        if not torch.isfinite(prop).all():
            raise ValueError("WMP 本体输入包含 NaN 或 Inf")
        return torch.clamp(prop, -CTRL.CLIP_OBS, CTRL.CLIP_OBS)

    @classmethod
    def preprocess_depth(cls, depth_m: np.ndarray) -> np.ndarray:
        """把米制深度转换为训练时使用的 ``[-0.5, 0.5]`` 图像。

        Isaac Gym 的无命中深度是 ``-Inf``，训练代码会把它裁剪为远平面。
        MuJoCo/实机输入中的所有非有限值也统一按远平面处理，避免产生虚假的
        近距离障碍。Dreamer 的 ConvEncoder 还会按 checkpoint 结构再减 0.5。
        """
        depth = np.asarray(depth_m, dtype=np.float32)
        if depth.shape != cls.IMAGE_SHAPE:
            raise ValueError(f"WMP 米制深度图必须是 {cls.IMAGE_SHAPE}，实际为 {depth.shape}")
        depth = np.nan_to_num(
            depth,
            copy=True,
            nan=cls.DEPTH_FAR_M,
            posinf=cls.DEPTH_FAR_M,
            neginf=cls.DEPTH_FAR_M,
        )
        depth = np.clip(depth, cls.DEPTH_NEAR_M, cls.DEPTH_FAR_M)
        depth = (depth - cls.DEPTH_NEAR_M) / (cls.DEPTH_FAR_M - cls.DEPTH_NEAR_M)
        return np.ascontiguousarray(depth - cls.DEPTH_CENTER, dtype=np.float32)

    def _select_delayed_depth(self, depth_m: np.ndarray) -> np.ndarray:
        """复现训练 depth buffer 的一帧（100 ms）相机延迟。"""
        current_depth = self.preprocess_depth(depth_m)
        selected_depth = current_depth if self.previous_depth is None else self.previous_depth
        # ConvEncoder.forward() 会对输入执行原地减法；这里必须断开 NumPy/Torch
        # 的共享内存，否则缓存帧会被中心化两次。
        self.previous_depth = current_depth.copy()
        return selected_depth.copy()

    def _update_world_model(self, prop: torch.Tensor, depth_m: np.ndarray) -> None:
        """每五个策略周期更新一次 world model。"""
        depth = self._select_delayed_depth(depth_m)
        image_t = torch.as_tensor(depth, dtype=torch.float32).unsqueeze(-1)
        wm_obs = {
            "prop": prop,
            "is_first": self.is_first,
            "image": image_t,
        }
        with torch.no_grad():
            wm_embed = self.world_model.encoder(wm_obs)
            wm_action = self.wm_action_history.flatten(0)
            self.wm_latent, _ = self.world_model.dynamics.obs_step(
                self.wm_latent,
                wm_action.unsqueeze(0),
                wm_embed.unsqueeze(0),
                self.is_first,
                sample=True,
            )
            self.wm_feature = self.world_model.dynamics.get_deter_feat(self.wm_latent).squeeze(0)
        self.is_first.fill_(0.0)

    def build_observation(
        self, state: RobotState, command: np.ndarray
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """构造 actor 当前输入和五帧历史；顺序与 simtosim 控制器一致。"""
        prop = self._build_prop(state, command)
        obs_without_command = torch.cat((prop[:6], prop[9:], self.last_action))
        self.obs_history = torch.cat((self.obs_history[1:], obs_without_command.unsqueeze(0)))
        obs_now = torch.cat((prop, self.last_action))
        return prop, obs_now, self.obs_history.flatten(0)

    @property
    def needs_depth_update(self) -> bool:
        """当前策略帧是否会消费一张新的深度图。"""
        return self.counter % self.UPDATE_INTERVAL == 0

    def step(
        self,
        state: RobotState,
        command: np.ndarray,
        depth_m: Optional[np.ndarray],
    ) -> tuple[np.ndarray, MotorCommand]:
        """执行一次 50 Hz WMP 推理；深度输入单位为米。"""
        command = np.asarray(command, dtype=np.float32)
        if command.shape != (3,):
            raise ValueError(f"cmd_vel 必须是 [vx, vy, vyaw]，实际为 {command.shape}")
        if not np.isfinite(command).all():
            raise ValueError("cmd_vel 包含 NaN 或 Inf")
        command = np.clip(command, -CTRL.COMMAND_LIMITS, CTRL.COMMAND_LIMITS)
        if self.needs_depth_update and depth_m is None:
            raise ValueError("当前 WMP 帧需要一张 64×64 米制深度图")
        prop, obs_now, obs_history = self.build_observation(state, command)

        if self.needs_depth_update:
            self._update_world_model(prop, depth_m)

        with torch.no_grad():
            action = self.policy.act(obs_now, obs_history, self.wm_feature).flatten()
        if action.shape != (CTRL.NUM_ACTIONS,) or not torch.isfinite(action).all():
            raise RuntimeError(f"WMP action 无效: shape={tuple(action.shape)}")
        action = torch.clamp(action, -CTRL.CLIP_ACTION, CTRL.CLIP_ACTION)

        # 训练 runner 每个 policy step 都写入动作历史，RSSM 每五步一次性消费
        # 连续的 [a0, a1, a2, a3, a4]；不能只在 world-model 更新帧写一次。
        self.wm_action_history = torch.cat(
            (self.wm_action_history[1:], action.unsqueeze(0))
        )
        self.last_action = action.clone()
        self.counter += 1
        return action.numpy(), self.action_to_motor_command(action.numpy())

    def action_to_motor_command(self, action: np.ndarray) -> MotorCommand:
        """按 simtosim 缩放动作，并转换为当前 driver 使用的 DDS 顺序。"""
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
