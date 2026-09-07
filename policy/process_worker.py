"""独立 policy 进程入口；主进程通过 Pipe 发送状态和速度命令。"""

import os
import signal
import time

import numpy as np
import torch

from driver.driver_base import RobotState
from policy.controller_go2w import ControllerGo2w


def _create_onnx_session(path, threads):
    """延迟导入 ONNX Runtime，避免默认 PyTorch 路径新增依赖。"""
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(
        path, sess_options=options, providers=("CPUExecutionProvider",)
    )


def run_go2w_policy(conn, model_path, cpus=None, torch_threads=1,
                    backend="torch", onnx_model_path=""):
    """加载 go2w policy，并逐帧返回 DDS 顺序的 MotorCommand 数据。"""
    # Ctrl+C 由 DDS 主进程统一处理，避免子进程在推理中打印 traceback。
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if cpus:
        os.sched_setaffinity(0, cpus)
    torch.set_num_threads(torch_threads)
    torch.set_num_interop_threads(1)
    controller = ControllerGo2w(model_path)
    controller.reset()
    onnx_session = (
        _create_onnx_session(onnx_model_path, torch_threads)
        if backend == "onnx" else None
    )
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
            if onnx_session is None:
                action = controller.compute_action(obs)
            else:
                observation = obs.numpy().reshape(1, -1)
                action = onnx_session.run(
                    ("action",), {"observation": observation}
                )[0].reshape(-1)
                controller.last_action = torch.from_numpy(action.copy())
            p, v, kp, kd = controller.action_to_motor_command(action)
            if hold_action:
                controller.last_action.zero_()
            conn.send((p, v, kp, kd, action, obs.numpy(),
                       (time.perf_counter() - start) * 1000.0))
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        conn.close()
