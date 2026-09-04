"""独立 policy 进程入口；主进程通过 Pipe 发送状态和速度命令。"""

import os
import signal
import time

import numpy as np
import torch

from driver.driver_base import RobotState
from policy.controller_go2w import ControllerGo2w


def run_go2w_policy(conn, model_path, cpus=None, torch_threads=1):
    """加载 go2w policy，并逐帧返回 DDS 顺序的 MotorCommand 数据。"""
    # Ctrl+C 由 DDS 主进程统一处理，避免子进程在推理中打印 traceback。
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if cpus:
        os.sched_setaffinity(0, cpus)
    torch.set_num_threads(torch_threads)
    torch.set_num_interop_threads(1)
    controller = ControllerGo2w(model_path)
    controller.reset()
    conn.send("ready")

    try:
        while True:
            data = conn.recv()
            if data is None:
                break
            state = RobotState(
                joint_positions=np.asarray(data[0], dtype=np.float32),
                joint_velocities=np.asarray(data[1], dtype=np.float32),
                imu_quat=np.asarray(data[2], dtype=np.float32),
                imu_gyro=np.asarray(data[3], dtype=np.float32),
            )
            command = np.asarray(data[4], dtype=np.float32)
            hold_action = bool(data[5])
            if hold_action:
                # 固定站姿对应零 action；未发送的 action 不能进入下一帧观测。
                controller.last_action.zero_()
            start = time.perf_counter()
            obs = controller.build_obs(state, command)
            action = controller.compute_action(obs)
            p, v, kp, kd = controller.action_to_motor_command(action)
            if hold_action:
                controller.last_action.zero_()
            conn.send((p, v, kp, kd, action, obs.numpy(),
                       (time.perf_counter() - start) * 1000.0))
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        conn.close()
