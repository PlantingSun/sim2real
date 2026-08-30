#!/usr/bin/env python3
"""离线验证 go2wcr/CRRL 模型、观测维度和四 stage 推理。"""

import argparse

import numpy as np

from config.go2w_config import CTRL, CRRL, CTRL_IDX_FROM_DDS, DDS_IDX_FROM_CTRL
from driver.driver_base import RobotState
from policy.controller_go2wcr import ControllerGo2wCR


def main() -> None:
    parser = argparse.ArgumentParser(description="go2wcr CRRL offline policy test")
    parser.add_argument("--model", default="models/go2wcr/model_1499.pt")
    args = parser.parse_args()

    print("=== Step CRRL-1: go2wcr 策略离线测试 ===")
    print(f"模型: {args.model}")
    controller = ControllerGo2wCR(args.model)

    assert controller.curriculum_embeddings.shape == (4, 4)
    assert controller.curriculum_embeddings.shape[0] == CRRL.NUM_ASSIST_STAGES
    print(f"课程嵌入维度: {tuple(controller.curriculum_embeddings.shape)}")
    print(f"课程嵌入:\n{controller.curriculum_embeddings.numpy()}")

    state = RobotState()
    state.joint_positions = CTRL.INITIAL_JOINTS_POS[DDS_IDX_FROM_CTRL]
    command = np.zeros(3, dtype=np.float32)
    obs = controller.build_obs(state, command)
    assert obs.shape == (CTRL.NUM_OBS * CTRL.HISTORY_LENGTH,)

    action = controller.compute_action(obs)
    assert action.shape == (CTRL.NUM_ACTIONS,)
    assert np.isfinite(action).all(), "动作含 NaN/Inf"

    motor_command = controller.action_to_motor_command(action)
    for name, values in (
        ("position", motor_command.positions),
        ("velocity", motor_command.velocities),
        ("kp", motor_command.kp),
        ("kd", motor_command.kd),
    ):
        assert values.shape == (CTRL.NUM_ACTIONS,), f"{name} 维度错误"
        assert np.isfinite(values).all(), f"{name} 含 NaN/Inf"

    # MotorCommand 是 DDS 顺序；用 DDS→Ctrl 映射检查轮关节位置。
    np.testing.assert_array_equal(motor_command.kp[CTRL_IDX_FROM_DDS], np.array([
        CTRL.LEG_KP, CTRL.LEG_KP, CTRL.LEG_KP, CTRL.WHEEL_KP,
        CTRL.LEG_KP, CTRL.LEG_KP, CTRL.LEG_KP, CTRL.WHEEL_KP,
        CTRL.LEG_KP, CTRL.LEG_KP, CTRL.LEG_KP, CTRL.WHEEL_KP,
        CTRL.LEG_KP, CTRL.LEG_KP, CTRL.LEG_KP, CTRL.WHEEL_KP,
    ], dtype=np.float32))
    print("\n--- 初始站立零运动状态输出 ---")
    print(f"初始站立零运动观测维度: {tuple(obs.shape)}")
    print("初始站立零运动动作输出 (16维, Ctrl顺序):")
    for index, value in enumerate(action):
        print(f"  [{index:2d}] {value:+.6f}")

    print("\n初始站立零运动 MotorCommand 数据 (DDS 顺序):")
    print(f"{'i':>3s}  {'pos':>10s}  {'vel':>10s}  {'kp':>6s}  {'kd':>6s}")
    for index in range(CTRL.NUM_ACTIONS):
        print(
            f"{index:3d}  {motor_command.positions[index]:10.4f}  "
            f"{motor_command.velocities[index]:10.4f}  "
            f"{motor_command.kp[index]:6.1f}  {motor_command.kd[index]:6.1f}"
        )
    print(f"初始站立零运动动作范围: [{action.min():+.5f}, {action.max():+.5f}]")
    print("✓ CRRL 模型、观测、动作和 MotorCommand 检查通过")


if __name__ == "__main__":
    main()
