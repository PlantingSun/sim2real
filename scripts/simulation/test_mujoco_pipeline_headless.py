#!/usr/bin/env python3
"""无窗口回归 MuJoCo → policy → MotorCommand 闭环；不初始化 DDS。"""

import argparse
import time

# Jetson 上先加载 PyTorch，避免 MuJoCo 的 OpenMP 占用 static TLS。
import torch
import mujoco
import numpy as np

from config.go2w_config import CTRL, CTRL_IDX_FROM_DDS, DDS
from config.paths import GO2W_SCENE, model_path
from driver.driver_base import MotorCommand
from driver.mujoco_driver import MujocoDriver
from policy.controller_go2w import ControllerGo2w
from policy.controller_go2wcr import ControllerGo2wCR


MIN_BASE_HEIGHT = 0.20
MAX_TILT_DEGREES = 60.0
FRAME_BUDGET_MS = 1000.0 / CTRL.POLICY_RATE_HZ


def create_controller(policy_name: str, checkpoint: str):
    if policy_name == "go2w":
        return ControllerGo2w(checkpoint)
    return ControllerGo2wCR(checkpoint)


def compute_motor_command(controller, policy_name: str, state, command):
    observation = controller.build_obs(state, command)
    action = controller.compute_action(observation)
    if policy_name == "go2w":
        position, velocity, kp, kd = controller.action_to_motor_command(action)
        motor_command = MotorCommand(
            positions=position,
            velocities=velocity,
            kp=kp,
            kd=kd,
        )
    else:
        motor_command = controller.action_to_motor_command(action)
    return action, motor_command


def require_finite(name: str, values) -> None:
    if not np.isfinite(values).all():
        raise RuntimeError(f"{name} 包含 NaN/Inf")


def base_tilt_degrees(quaternion) -> float:
    """由 MuJoCo [w,x,y,z] 四元数计算机身 z 轴相对竖直方向的夹角。"""
    _, x, y, _ = quaternion
    upright_cosine = 1.0 - 2.0 * (x * x + y * y)
    return float(np.degrees(np.arccos(np.clip(upright_cosine, -1.0, 1.0))))


def yaw_radians(quaternion) -> float:
    """由 MuJoCo [w,x,y,z] 四元数计算航向角。"""
    w, x, y, z = quaternion
    return float(np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))


def main() -> None:
    parser = argparse.ArgumentParser(description="go2w/go2wcr headless MuJoCo pipeline")
    parser.add_argument("--policy", choices=("go2w", "go2wcr"), default="go2w")
    parser.add_argument("--scene", default=str(GO2W_SCENE))
    parser.add_argument("--model")
    parser.add_argument("--frames", type=int, default=500)
    parser.add_argument("--vx", type=float, default=0.0)
    parser.add_argument("--vy", type=float, default=0.0)
    parser.add_argument("--vyaw", type=float, default=0.0)
    args = parser.parse_args()
    if args.frames < 10:
        parser.error("frames 至少为 10")

    command = np.array([args.vx, args.vy, args.vyaw], dtype=np.float32)
    if np.any(np.abs(command) > CTRL.COMMAND_LIMITS):
        parser.error(f"速度指令超过限制 {CTRL.COMMAND_LIMITS.tolist()}")
    checkpoint = args.model or model_path(
        "go2w/model_700.pt" if args.policy == "go2w" else "go2wcr/model_1499.pt"
    )

    print("=== Step 3: headless simulation pipeline ===")
    print(f"policy={args.policy}  frames={args.frames}  command={command.tolist()}")
    print(f"threads={torch.get_num_threads()}  frame_budget={FRAME_BUDGET_MS:.1f} ms")

    driver = MujocoDriver(args.scene, data_hz=DDS.RATE_HZ, show_viewer=False)
    if not driver.initialize():
        raise RuntimeError("MujocoDriver 初始化失败")
    try:
        driver.reset_to_stand()
        controller = create_controller(args.policy, checkpoint)
        controller.reset()

        physics_steps = round(driver._dt_data / driver._model.opt.timestep)
        if not np.isclose(
            physics_steps * driver._model.opt.timestep,
            driver._dt_data,
        ):
            raise RuntimeError("MuJoCo timestep 不能整除 500 Hz driver 周期")
        if DDS.RATE_HZ % CTRL.POLICY_RATE_HZ != 0:
            raise RuntimeError("500 Hz driver 频率不能整除 policy 频率")
        driver_steps = DDS.RATE_HZ // CTRL.POLICY_RATE_HZ
        control_limited = driver._model.actuator_ctrllimited.astype(bool)
        control_lower = driver._model.actuator_ctrlrange[:, 0]
        control_upper = driver._model.actuator_ctrlrange[:, 1]

        initial_position = driver._data.qpos[:3].copy()
        initial_yaw = yaw_radians(driver._data.qpos[3:7])
        minimum_height = float(initial_position[2])
        maximum_tilt = 0.0
        maximum_action = 0.0
        maximum_wheel_speed = 0.0
        maximum_model_clip = 0.0
        model_limited_frames = 0
        model_limit_counts = np.zeros(CTRL.NUM_ACTIONS, dtype=np.int64)
        model_clip_max = np.zeros(CTRL.NUM_ACTIONS, dtype=np.float64)
        maximum_control_excess = 0.0
        worst_control = None
        policy_latency_ms = np.empty(args.frames, dtype=np.float64)
        wall_start = time.perf_counter()

        for frame in range(args.frames):
            policy_start_ns = time.perf_counter_ns()
            state = driver.get_state()
            action, motor_command = compute_motor_command(
                controller,
                args.policy,
                state,
                command,
            )
            driver.send_command(motor_command)
            policy_latency_ms[frame] = (
                time.perf_counter_ns() - policy_start_ns
            ) / 1.0e6

            require_finite("RobotState position", state.joint_positions)
            require_finite("RobotState velocity", state.joint_velocities)
            require_finite("RobotState torque", state.joint_torques)
            require_finite("RobotState IMU", state.imu_quat)
            require_finite("policy action", action)
            for name, values in (
                ("MotorCommand position", motor_command.positions),
                ("MotorCommand velocity", motor_command.velocities),
                ("MotorCommand kp", motor_command.kp),
                ("MotorCommand kd", motor_command.kd),
            ):
                require_finite(name, values)

            maximum_action = max(maximum_action, float(np.max(np.abs(action))))
            wheel_velocity = motor_command.velocities[motor_command.kp == CTRL.WHEEL_KP]
            maximum_wheel_speed = max(
                maximum_wheel_speed,
                float(np.max(np.abs(wheel_velocity))),
            )

            raw_target = action * CTRL.POS_SCALE + CTRL.INITIAL_JOINTS_POS
            raw_target[CTRL.WHEEL_INDICES] = action[CTRL.WHEEL_INDICES] * CTRL.VEL_SCALE
            clipped_target = np.clip(
                raw_target,
                control_lower,
                control_upper,
            )
            model_clip_by_motor = np.abs(raw_target - clipped_target)
            model_clip = float(np.max(model_clip_by_motor))
            if model_clip > 0.0:
                model_limited_frames += 1
                maximum_model_clip = max(maximum_model_clip, model_clip)
                model_limit_counts += model_clip_by_motor > 0.0
                model_clip_max = np.maximum(model_clip_max, model_clip_by_motor)
            command_target = np.where(
                CTRL.DOF_MASK,
                motor_command.positions[CTRL_IDX_FROM_DDS],
                motor_command.velocities[CTRL_IDX_FROM_DDS],
            )
            if not np.allclose(command_target, raw_target):
                raise RuntimeError("MotorCommand 与网络动作缩放结果不一致")

            for _ in range(driver_steps):
                driver._apply_command(driver._pending_cmd)
                excess = np.maximum(
                    control_lower - driver._data.ctrl,
                    driver._data.ctrl - control_upper,
                )
                excess[~control_limited] = 0.0
                actuator_index = int(np.argmax(excess))
                frame_excess = float(excess[actuator_index])
                if frame_excess > max(maximum_control_excess, 1.0e-5):
                    maximum_control_excess = frame_excess
                    worst_control = (
                        frame,
                        driver._model.actuator(actuator_index).name,
                        float(driver._data.ctrl[actuator_index]),
                        float(control_lower[actuator_index]),
                        float(control_upper[actuator_index]),
                    )
                for _ in range(physics_steps):
                    mujoco.mj_step(driver._model, driver._data)

            require_finite("MuJoCo qpos", driver._data.qpos)
            require_finite("MuJoCo qvel", driver._data.qvel)
            require_finite("MuJoCo sensor", driver._data.sensordata)
            minimum_height = min(minimum_height, float(driver._data.qpos[2]))
            maximum_tilt = max(
                maximum_tilt,
                base_tilt_degrees(driver._data.qpos[3:7]),
            )

        wall_seconds = time.perf_counter() - wall_start
        final_position = driver._data.qpos[:3].copy()
        simulated_seconds = args.frames / CTRL.POLICY_RATE_HZ
        p99_ms = float(np.percentile(policy_latency_ms, 99))
        missed = int(np.count_nonzero(policy_latency_ms > FRAME_BUDGET_MS))
        displacement = final_position - initial_position
        yaw_change = yaw_radians(driver._data.qpos[3:7]) - initial_yaw
        yaw_change = (yaw_change + np.pi) % (2.0 * np.pi) - np.pi

        print(f"simulated={simulated_seconds:.2f} s  wall={wall_seconds:.2f} s  RTF={simulated_seconds / wall_seconds:.2f}")
        print(
            f"policy mean={policy_latency_ms.mean():.3f} ms  P99={p99_ms:.3f} ms  "
            f"max={policy_latency_ms.max():.3f} ms  missed={missed}/{args.frames}"
        )
        print(
            f"displacement=[{displacement[0]:.3f}, {displacement[1]:.3f}, "
            f"{displacement[2]:.3f}] m  min_z={minimum_height:.3f} m  "
            f"yaw_change={np.degrees(yaw_change):.2f} deg  "
            f"max_tilt={maximum_tilt:.2f} deg"
        )
        print(
            f"max_action={maximum_action:.3f}  "
            f"max_wheel_command={maximum_wheel_speed:.3f} rad/s  "
            f"model_limited={model_limited_frames}/{args.frames}  "
            f"max_model_clip={maximum_model_clip:.6f}  "
            f"max_ctrl_excess={maximum_control_excess:.6f}"
        )
        if worst_control is not None:
            frame, name, value, lower, upper = worst_control
            print(
                f"worst_control: frame={frame} actuator={name} value={value:.6f} "
                f"range=[{lower:.6f}, {upper:.6f}]"
            )
        for index in np.flatnonzero(model_limit_counts):
            print(
                f"model_limit: {CTRL.JOINT_NAMES[index]} "
                f"frames={model_limit_counts[index]} "
                f"max_clip={model_clip_max[index]:.6f}"
            )

        failures = []
        if p99_ms > FRAME_BUDGET_MS:
            failures.append("policy P99 超过 20 ms")
        if minimum_height < MIN_BASE_HEIGHT:
            failures.append(f"base 高度低于 {MIN_BASE_HEIGHT:.2f} m")
        if maximum_tilt > MAX_TILT_DEGREES:
            failures.append(f"机身倾角超过 {MAX_TILT_DEGREES:.0f}°")
        if maximum_control_excess > 1.0e-5:
            print("[WARN] MotorCommand 超出 MuJoCo ctrlrange；保留网络原始输出，不修改 controller")
        if failures:
            for failure in failures:
                print(f"[FAIL] {failure}")
            raise SystemExit(1)
        print("[PASS] simulation pipeline 无窗口回归通过")
    finally:
        driver.shutdown()


if __name__ == "__main__":
    main()
