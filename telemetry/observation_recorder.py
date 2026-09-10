"""Chunked on-disk recorder for Go2WWMP observations.

The recorder deliberately stores observations and policy context, not the
network action or MotorCommand.  Chunks use uncompressed ``npz`` containers:
writing is cheap enough for the laptop control process and completed chunks
remain readable if a later run is interrupted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import threading
from typing import Optional

import numpy as np


class ObservationRecorder:
    """Write fixed-size observation chunks and a small manifest."""

    FORMAT_VERSION = 1
    DEFAULT_CHUNK_FRAMES = 250  # about five seconds at the 50 Hz policy rate

    def __init__(
        self,
        directory: Path,
        *,
        source_log: Path,
        model_path: str,
        model_sha256: str,
        chunk_frames: int = DEFAULT_CHUNK_FRAMES,
    ) -> None:
        if chunk_frames <= 0:
            raise ValueError("observation chunk_frames 必须为正数")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        existing_chunks = sorted(self.directory.glob("chunk_*.npz"))
        if existing_chunks:
            raise FileExistsError(
                f"观测归档目录已有 chunk，避免混合两次实验: {self.directory}"
            )
        self.chunk_frames = int(chunk_frames)
        self._chunk_index = 0
        self._rows = []
        self._depth_rows = []
        self._total_frames = 0
        self._writer_error = None
        self._queue = queue.Queue(maxsize=2)
        self._closed = False
        self._write_manifest(
            source_log=source_log,
            model_path=model_path,
            model_sha256=model_sha256,
        )
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="go2wwmp-observation-writer",
            daemon=True,
        )
        self._writer_thread.start()

    def _write_manifest(self, *, source_log: Path, model_path: str, model_sha256: str) -> None:
        manifest = {
            "format": "go2wwmp_observations",
            "format_version": self.FORMAT_VERSION,
            "source_log": str(source_log),
            "model_path": str(model_path),
            "model_sha256": model_sha256,
            "policy_rate_hz": 50,
            "depth_shape": [64, 64],
            "depth_saved_on": "needs_depth_update=true rows only",
            "arrays": {
                "timestamp_wall_ns": "[N] int64",
                "timestamp_monotonic_ns": "[N] int64",
                "loop": "[N] int64",
                "state_tick": "[N] int64",
                "state_age_ms": "[N] float32",
                "command": "[N,3] float32; WMP input [vx, vy, vyaw]",
                "joint_positions_dds": "[N,16] float32",
                "joint_velocities_dds": "[N,16] float32",
                "imu_quat_wxyz": "[N,4] float32",
                "imu_gyro_xyz": "[N,3] float32",
                "prop": "[N,37] float32",
                "obs_now": "[N,53] float32",
                "obs_history": "[N,250] float32",
                "wm_feature": "[N,512] float32; actor world-model context",
                "depth_session": "[N] int64",
                "depth_frame": "[N] int64",
                "depth_valid_ratio": "[N] float32",
                "depth_invalid_pixels": "[N] int32",
                "depth_local_age_ms": "[N] float32",
                "depth_source_processing_ms": "[N] float32",
                "needs_depth_update": "[N] bool",
                "depth_update_rows": "[M] int64; row indices within this chunk",
                "depth_image_m": "[M,64,64] float32; raw meter depth",
                "depth_valid": "[M,64,64] uint8; valid mask",
            },
            "not_saved": ["action", "positions", "velocities", "kp", "kd", "torques"],
        }
        path = self.directory / "manifest.json"
        with path.open("w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")

    @staticmethod
    def _array(value, shape, dtype=np.float32):
        array = np.asarray(value, dtype=dtype)
        if array.shape != shape:
            raise ValueError(f"观测归档 shape 错误: expected={shape}, actual={array.shape}")
        if np.issubdtype(array.dtype, np.floating) and not np.isfinite(array).all():
            raise ValueError("观测归档包含 NaN/Inf")
        return array.copy()

    def append(
        self,
        *,
        timestamp_wall_ns: int,
        timestamp_monotonic_ns: int,
        loop: int,
        state_tick: int,
        state_age_ms: float,
        command,
        state,
        snapshot: dict,
        depth_session: int,
        depth_frame: int,
        depth_valid_ratio: float,
        depth_invalid_pixels: int,
        depth_local_age_ms: float,
        depth_source_processing_ms: float,
        needs_depth_update: bool,
        depth_m: Optional[np.ndarray],
        depth_valid: Optional[np.ndarray],
    ) -> None:
        """Append one policy observation; queue a complete chunk for disk I/O."""
        self._raise_writer_error()
        if self._closed:
            raise RuntimeError("观测归档已经关闭")
        row_index = len(self._rows)
        row = {
            "timestamp_wall_ns": int(timestamp_wall_ns),
            "timestamp_monotonic_ns": int(timestamp_monotonic_ns),
            "loop": int(loop),
            "state_tick": int(state_tick),
            "state_age_ms": float(state_age_ms),
            "command": self._array(command, (3,)),
            "joint_positions_dds": self._array(state.joint_positions, (16,)),
            "joint_velocities_dds": self._array(state.joint_velocities, (16,)),
            "imu_quat_wxyz": self._array(state.imu_quat, (4,)),
            "imu_gyro_xyz": self._array(state.imu_gyro, (3,)),
            "prop": self._array(snapshot["prop"], (37,)),
            "obs_now": self._array(snapshot["obs_now"], (53,)),
            "obs_history": self._array(snapshot["obs_history"], (250,)),
            "wm_feature": self._array(snapshot["wm_feature"], (512,)),
            "depth_session": int(depth_session),
            "depth_frame": int(depth_frame),
            "depth_valid_ratio": float(depth_valid_ratio),
            "depth_invalid_pixels": int(depth_invalid_pixels),
            "depth_local_age_ms": float(depth_local_age_ms),
            "depth_source_processing_ms": float(depth_source_processing_ms),
            "needs_depth_update": bool(needs_depth_update),
        }
        self._rows.append(row)

        if needs_depth_update:
            if depth_m is None or depth_valid is None:
                raise ValueError("需要深度更新时，观测归档缺少深度图或 valid mask")
            image = self._array(depth_m, (64, 64))
            valid = self._array(depth_valid, (64, 64), dtype=np.uint8)
            self._depth_rows.append((row_index, image, valid))

        if len(self._rows) >= self.chunk_frames:
            self.flush()

    def flush(self) -> None:
        """Queue the current chunk; disk I/O is performed by a background thread."""
        self._raise_writer_error()
        if not self._rows:
            return
        arrays = {}
        keys = (
            "timestamp_wall_ns", "timestamp_monotonic_ns", "loop", "state_tick",
            "state_age_ms", "command", "joint_positions_dds", "joint_velocities_dds",
            "imu_quat_wxyz", "imu_gyro_xyz", "prop", "obs_now", "obs_history",
            "wm_feature", "depth_session", "depth_frame", "depth_valid_ratio",
            "depth_invalid_pixels", "depth_local_age_ms", "depth_source_processing_ms",
            "needs_depth_update",
        )
        for key in keys:
            arrays[key] = np.asarray([row[key] for row in self._rows])
        for key in (
            "state_age_ms", "depth_valid_ratio", "depth_local_age_ms",
            "depth_source_processing_ms",
        ):
            arrays[key] = arrays[key].astype(np.float32, copy=False)
        arrays["depth_invalid_pixels"] = arrays["depth_invalid_pixels"].astype(
            np.int32, copy=False
        )

        if self._depth_rows:
            arrays["depth_update_rows"] = np.asarray(
                [row_index for row_index, _, _ in self._depth_rows], dtype=np.int64
            )
            arrays["depth_image_m"] = np.stack(
                [image for _, image, _ in self._depth_rows], axis=0
            ).astype(np.float32, copy=False)
            arrays["depth_valid"] = np.stack(
                [valid for _, _, valid in self._depth_rows], axis=0
            ).astype(np.uint8, copy=False)
        else:
            arrays["depth_update_rows"] = np.empty((0,), dtype=np.int64)
            arrays["depth_image_m"] = np.empty((0, 64, 64), dtype=np.float32)
            arrays["depth_valid"] = np.empty((0, 64, 64), dtype=np.uint8)

        index = self._chunk_index
        self._chunk_index += 1
        self._total_frames += len(self._rows)
        self._queue.put((index, arrays))
        self._rows.clear()
        self._depth_rows.clear()

    def _writer_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            index, arrays = item
            try:
                self._write_chunk(index, arrays)
            except Exception as exc:  # propagate on the next append/close
                self._writer_error = exc
                return

    def _write_chunk(self, index: int, arrays: dict) -> None:
        temporary = self.directory / f".chunk_{index:06d}.npz.tmp"
        target = self.directory / f"chunk_{index:06d}.npz"
        with temporary.open("wb") as stream:
            np.savez(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)

    def _raise_writer_error(self) -> None:
        if self._writer_error is not None:
            raise RuntimeError(f"观测归档写盘失败: {self._writer_error}") from self._writer_error

    def close(self) -> None:
        if self._closed:
            return
        flush_error = None
        try:
            self.flush()
        except Exception as exc:
            flush_error = exc
        if self._writer_error is None:
            while self._writer_thread.is_alive():
                try:
                    self._queue.put(None, timeout=0.1)
                    break
                except queue.Full:
                    if self._writer_error is not None:
                        break
        self._writer_thread.join()
        if flush_error is not None:
            raise flush_error
        self._raise_writer_error()
        self._closed = True
        summary = {
            "format_version": self.FORMAT_VERSION,
            "complete_chunks": self._chunk_index,
            "frames_written": self._total_frames,
        }
        with (self.directory / "summary.json").open("w", encoding="utf-8") as stream:
            json.dump(summary, stream, indent=2)
            stream.write("\n")
