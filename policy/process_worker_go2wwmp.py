"""Go2WWMP real-machine worker: domain-42 depth + print-only inference.

The parent process owns Unitree domain 0 and LowCmd safety.  This child owns
only the depth participant and the WMP model, then returns diagnostics and a
candidate MotorCommand through a bounded Pipe.  It never writes LowCmd.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import signal
import time

import numpy as np
import torch

from depth.receiver import DepthReceiver
from driver.driver_base import RobotState
from policy.controller_go2wwmp import ControllerGo2wWMP


def file_sha256(path: str) -> str:
    """Return a checkpoint digest without loading the model a second time."""
    digest = hashlib.sha256()
    with Path(path).expanduser().open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _state_from_payload(payload) -> RobotState:
    if len(payload) != 4:
        raise ValueError("WMP worker 状态包必须包含 position/velocity/quaternion/gyro")
    arrays = tuple(np.asarray(value, dtype=np.float32) for value in payload)
    expected = ((16,), (16,), (4,), (3,))
    if any(value.shape != shape for value, shape in zip(arrays, expected)):
        raise ValueError("WMP worker 状态包 shape 错误")
    if any(not np.isfinite(value).all() for value in arrays):
        raise ValueError("WMP worker 状态包包含 NaN/Inf")
    return RobotState(
        joint_positions=arrays[0],
        joint_velocities=arrays[1],
        imu_quat=arrays[2],
        imu_gyro=arrays[3],
    )


def _depth_quality(sample, now_ns: int, min_valid_ratio: float) -> dict:
    valid_ratio = float(np.mean(sample.valid != 0))
    if valid_ratio < min_valid_ratio:
        raise RuntimeError(
            f"depth valid_ratio={valid_ratio:.4f} < min_valid_ratio={min_valid_ratio:.4f}"
        )
    local_age_ms = (now_ns - sample.received_monotonic_ns) / 1.0e6
    source_processing_ms = (
        sample.source.publish_monotonic_ns - sample.source.capture_monotonic_ns
    ) / 1.0e6
    return {
        "depth_session": int(sample.session_id),
        "depth_frame": int(sample.frame_id),
        "depth_valid_ratio": valid_ratio,
        "depth_invalid_pixels": int(np.count_nonzero(sample.valid == 0)),
        "depth_local_age_ms": float(local_age_ms),
        "depth_source_processing_ms": float(source_processing_ms),
    }


def _motor_arrays(command):
    arrays = {
        "positions": np.asarray(command.positions, dtype=np.float32),
        "velocities": np.asarray(command.velocities, dtype=np.float32),
        "kp": np.asarray(command.kp, dtype=np.float32),
        "kd": np.asarray(command.kd, dtype=np.float32),
    }
    if any(value.shape != (16,) for value in arrays.values()):
        raise RuntimeError("WMP MotorCommand 必须包含 16 路数据")
    if any(not np.isfinite(value).all() for value in arrays.values()):
        raise RuntimeError("WMP MotorCommand 包含 NaN/Inf")
    return arrays


def run_go2wwmp_policy(
    conn,
    model_path: str,
    depth_interface: str,
    depth_domain: int = 42,
    depth_topic: str = "rt/depth/image64",
    depth_max_age_ms: float = 100.0,
    min_valid_ratio: float = 0.90,
    cpus=None,
    torch_threads: int = 1,
):
    """Load WMP and serve bounded state→candidate-command requests.

    ``ready`` is sent only after model loading and a fresh depth frame.  The
    parent still must perform its own staged safety checks before any LowCmd.
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if cpus:
        os.sched_setaffinity(0, cpus)
    torch.set_num_threads(torch_threads)
    torch.set_num_interop_threads(1)

    receiver = None
    try:
        model_digest = file_sha256(model_path)
        controller = ControllerGo2wWMP(model_path)
        receiver = DepthReceiver(depth_interface, domain=depth_domain, topic=depth_topic)

        deadline = time.monotonic() + 15.0
        first_sample = None
        while time.monotonic() < deadline:
            first_sample = receiver.get_latest(max_age_ms=depth_max_age_ms)
            if first_sample is not None:
                break
            time.sleep(0.01)
        if first_sample is None:
            raise RuntimeError("没有收到新鲜深度首帧，未进入 WMP 推理")
        first_quality = _depth_quality(
            first_sample, time.monotonic_ns(), min_valid_ratio
        )
        conn.send({
            "event": "ready",
            "model_sha256": model_digest,
            "depth_domain": depth_domain,
            "depth_topic": depth_topic,
            **first_quality,
        })

        last_session = first_sample.session_id
        while True:
            request = conn.recv()
            if request is None:
                break
            if request[0] == "sync_session":
                sample = receiver.get_latest(max_age_ms=depth_max_age_ms)
                if sample is None:
                    raise RuntimeError(
                        f"固定站姿接管前没有新鲜深度（max_age_ms={depth_max_age_ms:g}）"
                    )
                quality = _depth_quality(sample, time.monotonic_ns(), min_valid_ratio)
                session_rebased = sample.session_id != last_session
                if session_rebased:
                    # Re-baselining is only allowed before LowCmd takeover.  A
                    # later change is reported by step and stops fixed hold.
                    controller.reset()
                    last_session = sample.session_id
                conn.send({"event": "session_sync", "session_rebased": session_rebased, **quality})
                continue
            if request[0] != "step":
                raise RuntimeError(f"未知 WMP worker 请求: {request[0]!r}")
            state = _state_from_payload(request[1])
            command = np.asarray(request[2], dtype=np.float32)
            if command.shape != (3,) or not np.isfinite(command).all():
                raise ValueError("WMP worker 收到非法速度命令")

            sample = receiver.get_latest(max_age_ms=depth_max_age_ms)
            if sample is None:
                raise RuntimeError(
                    f"深度过期或未收到新鲜帧（max_age_ms={depth_max_age_ms:g}）"
                )
            now_ns = time.monotonic_ns()
            quality = _depth_quality(sample, now_ns, min_valid_ratio)
            previous_session = last_session
            session_changed = sample.session_id != previous_session
            if session_changed:
                # A restarted camera must not silently continue old RSSM state.
                controller.reset()
                last_session = sample.session_id

            depth_m = sample.depth_m if controller.needs_depth_update else None
            start = time.perf_counter()
            action, motor_command = controller.step(state, command, depth_m)
            inference_ms = (time.perf_counter() - start) * 1000.0
            if not np.isfinite(action).all():
                raise RuntimeError("WMP action 包含 NaN/Inf")
            conn.send({
                "event": "step",
                "session_changed": bool(session_changed),
                "previous_depth_session": int(previous_session),
                "inference_ms": float(inference_ms),
                "needs_depth_update": bool(depth_m is not None),
                "action": np.asarray(action, dtype=np.float32),
                **_motor_arrays(motor_command),
                **quality,
            })
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            conn.send({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        except (EOFError, BrokenPipeError):
            pass
    finally:
        if receiver is not None:
            receiver.close()
        conn.close()
