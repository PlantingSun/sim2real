"""Go2WWMP 部署侧观测、深度和时序语义回归测试。"""

import types
import unittest

import numpy as np
import torch

from config.go2w_config import CTRL, DDS_IDX_FROM_CTRL
from driver.driver_base import RobotState
from policy.controller_go2wwmp import ControllerGo2wWMP


def standing_state() -> RobotState:
    """构造 driver 对外使用的 DDS 顺序初始站立状态。"""
    return RobotState(
        joint_positions=CTRL.INITIAL_JOINTS_POS[DDS_IDX_FROM_CTRL].copy(),
        joint_velocities=np.zeros(CTRL.NUM_ACTIONS, dtype=np.float32),
        imu_quat=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        imu_gyro=np.zeros(3, dtype=np.float32),
    )


def minimal_controller() -> ControllerGo2wWMP:
    """绕过 checkpoint，仅建立观测和动作时序测试需要的状态。"""
    controller = ControllerGo2wWMP.__new__(ControllerGo2wWMP)
    controller.initial_pos = torch.tensor(CTRL.INITIAL_JOINTS_POS, dtype=torch.float32)
    controller.wheel_indices = torch.tensor(CTRL.WHEEL_INDICES, dtype=torch.long)
    controller.dof_mask = torch.tensor(CTRL.DOF_MASK, dtype=torch.bool)
    controller.last_action = torch.zeros(CTRL.NUM_ACTIONS, dtype=torch.float32)
    controller.obs_history = torch.zeros(
        controller.HISTORY_LENGTH, controller.HISTORY_FRAME_DIM, dtype=torch.float32
    )
    controller.wm_action_history = torch.zeros(
        controller.UPDATE_INTERVAL, CTRL.NUM_ACTIONS, dtype=torch.float32
    )
    controller.previous_depth = None
    controller.wm_latent = None
    controller.wm_feature = torch.zeros(controller.WM_FEATURE_DIM, dtype=torch.float32)
    controller.is_first = torch.ones(1, dtype=torch.float32)
    controller.counter = 0
    return controller


class SequencePolicy:
    """第 n 次调用返回全 n 的动作，便于检查五帧顺序。"""

    def __init__(self):
        self.call_count = 0

    def act(self, obs_now, obs_history, wm_feature):
        self.call_count += 1
        return torch.full((CTRL.NUM_ACTIONS,), float(self.call_count))


class TestGo2wWMPPipeline(unittest.TestCase):
    def test_depth_preprocessing_matches_training_range(self):
        depth_m = np.ones((64, 64), dtype=np.float32)
        depth_m[0, :8] = [-1.0, 0.0, 0.5, 1.0, 2.0, 3.0, np.nan, np.inf]
        depth_m[1, 0] = -np.inf
        original = depth_m.copy()

        image = ControllerGo2wWMP.preprocess_depth(depth_m)

        np.testing.assert_allclose(
            image[0, :8], [-0.5, -0.5, -0.25, 0.0, 0.5, 0.5, 0.5, 0.5]
        )
        self.assertEqual(float(image[1, 0]), 0.5)
        np.testing.assert_equal(depth_m, original)
        self.assertTrue(image.flags.c_contiguous)

    def test_prop_order_and_yaw_command_scale_match_training(self):
        controller = minimal_controller()
        prop = controller._build_prop(
            standing_state(), np.array([0.2, -0.3, 0.4], dtype=np.float32)
        )

        self.assertEqual(tuple(prop.shape), (controller.PROP_DIM,))
        np.testing.assert_allclose(prop[:6].numpy(), [0.0, 0.0, 0.0, 0.0, 0.0, -1.0])
        np.testing.assert_allclose(prop[6:9].numpy(), [0.2, -0.3, 0.1])
        np.testing.assert_allclose(prop[9:].numpy(), 0.0)

    def test_reset_uses_training_zero_history(self):
        controller = minimal_controller()
        controller.obs_history.fill_(7.0)
        controller.last_action.fill_(7.0)
        controller.wm_action_history.fill_(7.0)
        controller.previous_depth = np.ones((64, 64), dtype=np.float32)
        controller.wm_feature.fill_(7.0)
        controller.is_first.zero_()
        controller.counter = 9

        controller.reset()

        self.assertEqual(torch.count_nonzero(controller.obs_history).item(), 0)
        self.assertEqual(torch.count_nonzero(controller.last_action).item(), 0)
        self.assertEqual(torch.count_nonzero(controller.wm_action_history).item(), 0)
        self.assertIsNone(controller.previous_depth)
        self.assertEqual(torch.count_nonzero(controller.wm_feature).item(), 0)
        self.assertEqual(float(controller.is_first.item()), 1.0)
        self.assertEqual(controller.counter, 0)

    def test_world_model_receives_five_consecutive_actions(self):
        controller = minimal_controller()
        controller.policy = SequencePolicy()
        captured_histories = []

        def capture_update(this, prop, depth_m):
            captured_histories.append(this.wm_action_history.clone())

        controller._update_world_model = types.MethodType(capture_update, controller)
        depth_m = np.ones((64, 64), dtype=np.float32)
        for _ in range(6):
            controller.step(standing_state(), np.zeros(3, dtype=np.float32), depth_m)

        self.assertEqual(len(captured_histories), 2)
        np.testing.assert_allclose(captured_histories[0].numpy(), 0.0)
        expected = np.repeat(
            np.arange(1.0, 6.0, dtype=np.float32)[:, None], CTRL.NUM_ACTIONS, axis=1
        )
        np.testing.assert_allclose(captured_histories[1].numpy(), expected)

    def test_depth_delay_matches_training_two_frame_buffer(self):
        controller = minimal_controller()
        near = np.zeros((64, 64), dtype=np.float32)
        far = np.full((64, 64), 2.0, dtype=np.float32)

        first = controller._select_delayed_depth(near)
        first -= 0.5  # 模拟 ConvEncoder 对返回张量底层内存的原地中心化。
        second = controller._select_delayed_depth(far)
        third = controller._select_delayed_depth(near)

        np.testing.assert_allclose(first, -1.0)
        np.testing.assert_allclose(second, -0.5)
        np.testing.assert_allclose(third, 0.5)

    def test_depth_is_required_only_on_world_model_frames(self):
        controller = minimal_controller()
        controller.policy = SequencePolicy()
        controller._update_world_model = types.MethodType(lambda *args: None, controller)

        with self.assertRaisesRegex(ValueError, "需要一张"):
            controller.step(standing_state(), np.zeros(3, dtype=np.float32), None)

        controller.step(
            standing_state(), np.zeros(3, dtype=np.float32), np.ones((64, 64), dtype=np.float32)
        )
        controller.step(standing_state(), np.zeros(3, dtype=np.float32), None)


if __name__ == "__main__":
    unittest.main()
