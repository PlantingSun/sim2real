#!/usr/bin/env python3
"""长期运行 Go2WWMP + 宇树原装遥控器。

正常流程：机器人先在原生 Sport Mode 下站稳，程序完成 LowState、深度和
WMP 只读自检；操作者松开再同时按下 L2+R2 后，程序释放 Sport Mode 并立即
接管 LowCmd。Select 或 Ctrl+C 退出。

本文件是正式实机入口，不导入任何 test_policy 脚本。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import multiprocessing as mp
import os
from pathlib import Path
import signal
import time

import numpy as np

from config.go2w_config import CTRL, DDS, DDS_IDX_FROM_CTRL
from config.paths import PROJECT_ROOT, model_path
from depth.opencv_display import load_cv2_for_gui
from driver.dds_driver import DdsDriver
from driver.driver_base import MotorCommand
from policy.process_worker_go2wwmp import run_go2wwmp_policy
from teleop.heading_mode import (
    HEADING_DISABLE_BUTTON,
    HEADING_ENABLE_BUTTON,
    HEADING_FORWARD_SPEED,
    HEADING_YAW_KP,
    HeadingModeController,
)
from teleop.unitree_remote import UnitreeRemoteCommandSource


# 这些是已经实机验收的运行参数，不再暴露为日常命令行开关。
DEPTH_DOMAIN = 42
DEPTH_TOPIC = "rt/depth/image64"
DEPTH_MAX_AGE_MS = 1000.0
LOWSTATE_MAX_AGE_MS = 100.0
REMOTE_TIMEOUT_S = 0.5
REMOTE_DEADZONE = 0.10
DEPTH_DISPLAY_HZ = 2.0
POLICY_RATE_HZ = CTRL.POLICY_RATE_HZ
LOWCMD_CPU = 1
TORCH_THREADS = 1


def default_log_path():
    """每次运行使用新日志，避免覆盖上一轮实机证据。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return PROJECT_ROOT / "logs" / "real" / f"go2wwmp_unitree_{stamp}.jsonl"


def parse_args(argv=None):
    """解析正式入口少量的文件与显示选项。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=model_path("go2wwmp/model_6000.pt"),
        help="WMP checkpoint；默认使用 models/go2wwmp/model_6000.pt",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="诊断日志；默认在 logs/real 下按时间自动命名",
    )
    parser.add_argument(
        "--no-depth-display",
        action="store_true",
        help="关闭默认 2 Hz 的单幅深度预览",
    )
    parser.add_argument(
        "--observation-dir",
        type=Path,
        default=None,
        help="观测归档目录；默认与 JSONL 同名加 _obs",
    )
    parser.add_argument(
        "--no-observation-log",
        action="store_true",
        help="关闭观测归档（默认保存 timestamp、obs、深度和 world-model context）",
    )
    args = parser.parse_args(argv)
    args.model = str(Path(args.model).expanduser())
    args.log = args.log or default_log_path()
    if args.no_observation_log:
        args.observation_dir = None
    elif args.observation_dir is not None:
        args.observation_dir = args.observation_dir.expanduser()
    else:
        args.observation_dir = args.log.with_name(args.log.stem + "_obs")

    if not Path(args.model).is_file():
        parser.error(f"找不到 WMP checkpoint: {args.model}")
    if not DDS.DEFAULT_NET_IF.strip() or not DDS.DEPTH_NET_IF.strip():
        parser.error("go2w_config.py 中的电机/深度网卡不能为空")
    if LOWCMD_CPU not in os.sched_getaffinity(0):
        parser.error(f"LowCmd CPU {LOWCMD_CPU} 当前不可用")
    return args


def build_initial_hold_command():
    """生成 ReleaseMode 后发送的第一条固定站姿指令（DDS 顺序）。"""
    positions = CTRL.INITIAL_JOINTS_POS.copy()
    velocities = np.zeros(16, dtype=np.float32)
    kp = np.full(16, CTRL.LEG_KP, dtype=np.float32)
    kd = np.full(16, CTRL.LEG_KD, dtype=np.float32)
    for index in CTRL.WHEEL_INDICES:
        kp[index] = CTRL.WHEEL_KP
        kd[index] = CTRL.WHEEL_KD
    return MotorCommand(
        positions=positions[DDS_IDX_FROM_CTRL],
        velocities=velocities[DDS_IDX_FROM_CTRL],
        kp=kp[DDS_IDX_FROM_CTRL],
        kd=kd[DDS_IDX_FROM_CTRL],
    )


def response_to_motor_command(response):
    """把 WMP worker 返回值转换为 DdsDriver 使用的 16 路命令。"""
    return MotorCommand(
        positions=np.asarray(response["positions"], dtype=np.float32),
        velocities=np.asarray(response["velocities"], dtype=np.float32),
        kp=np.asarray(response["kp"], dtype=np.float32),
        kd=np.asarray(response["kd"], dtype=np.float32),
        torques=np.zeros(16, dtype=np.float32),
    )


def state_payload(state):
    """只向 WMP 子进程传送策略需要的状态，避免跨进程共享 DDS 对象。"""
    return (
        state.joint_positions.copy(),
        state.joint_velocities.copy(),
        state.imu_quat.copy(),
        state.imu_gyro.copy(),
    )


def require_fresh_state(state):
    """LowState 缺失或过期时终止本轮，不复用旧状态。"""
    if not state.received_monotonic_ns:
        raise RuntimeError("LowState 尚未收到")
    age_ms = (time.perf_counter_ns() - state.received_monotonic_ns) / 1.0e6
    if age_ms > LOWSTATE_MAX_AGE_MS:
        raise RuntimeError(
            f"LowState 过期: age={age_ms:.1f}ms > {LOWSTATE_MAX_AGE_MS:.1f}ms"
        )
    return float(age_ms)


def receive_event(conn, expected, timeout, description):
    """所有 policy IPC 都使用有界等待，并核对返回事件类型。"""
    if not conn.poll(timeout):
        raise RuntimeError(f"{description}超时")
    response = conn.recv()
    if response.get("event") == "error":
        raise RuntimeError(response.get("error", f"{description}失败"))
    if response.get("event") != expected:
        raise RuntimeError(f"{description}返回异常: {response}")
    return response


def print_status(response, count):
    """每秒打印一次关键运行指标，避免终端输出影响 50 Hz 控制。"""
    if count != 1 and count % POLICY_RATE_HZ != 0 and not response["session_changed"]:
        return
    action = np.asarray(response["action"])
    command = np.asarray(response["command"])
    heading_text = ""
    if response.get("heading_mode"):
        heading_text = (
            f" heading=ON target={response['heading_target_yaw_rad']:+.3f} "
            f"error={response['heading_error_rad']:+.3f}"
        )
    print(
        "[WMP] "
        f"frame={response['depth_frame']} session={response['depth_session']} "
        f"cmd={np.array2string(command, precision=3, suppress_small=True)} "
        f"valid={response['depth_valid_ratio']:.3f} "
        f"depth_age={response['depth_local_age_ms']:.1f}ms "
        f"infer={response['inference_ms']:.2f}ms "
        f"action=[{action.min():+.3f},{action.max():+.3f}]"
        f"{heading_text}"
    )


def show_depth_preview(cv2_module, response):
    """显示 WMP 实际接收的单幅米制深度；紫色表示 valid=0。"""
    depth_m = np.asarray(response["depth_preview"], dtype=np.float32)
    valid = np.asarray(response["depth_preview_valid"], dtype=np.uint8).astype(bool)
    meters_u8 = np.rint(np.clip(depth_m, 0.0, 2.0) * 127.5).astype(np.uint8)
    view = cv2_module.cvtColor(meters_u8, cv2_module.COLOR_GRAY2BGR)
    view[~valid] = (255, 0, 255)
    view = cv2_module.resize(view, (512, 512), interpolation=cv2_module.INTER_NEAREST)
    cv2_module.putText(
        view,
        f"depth 0-2m | frame={response['depth_frame']} valid={response['depth_valid_ratio']:.3f}",
        (8, 24),
        cv2_module.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
        cv2_module.LINE_AA,
    )
    cv2_module.imshow("go2wwmp depth", view)
    key = cv2_module.waitKey(1) & 0xFF
    return key not in (27, ord("q"))


def write_log(log_handle, response, loop_count, state, state_age_ms):
    """去掉预览图后写一行 JSONL；数组显式转为普通列表。"""
    record = dict(response)
    record.pop("depth_preview", None)
    record.pop("depth_preview_valid", None)
    for key in ("command", "action", "positions", "velocities", "kp", "kd"):
        record[key] = np.asarray(record[key], dtype=np.float32).tolist()
    record.update(
        loop=loop_count,
        state_tick=int(state.tick),
        state_age_ms=state_age_ms,
        command_enabled=True,
        wmp_action_sent=True,
    )
    log_handle.write(json.dumps(record) + "\n")
    log_handle.flush()


def run(args):
    """执行唯一的正式状态机；本函数不会调用 StandUp。"""
    print("=== Go2WWMP Unitree 长期运行 ===")
    print(f"[MODEL] {args.model}")
    print(f"[LOG] {args.log}")
    print(f"[DDS] motor domain=0 interface={DDS.DEFAULT_NET_IF}")
    print(f"[DEPTH] domain={DEPTH_DOMAIN} interface={DDS.DEPTH_NET_IF} topic={DEPTH_TOPIC}")
    print("[FLOW] 原生 Sport Mode 站稳 -> L2+R2 接管 -> Select/Ctrl+C 退出")
    print("[SAFETY] 命令侧 q/dq 不限幅；保留 LowState 实测 dq>30 rad/s 急停")

    driver = DdsDriver(DDS.DEFAULT_NET_IF, lowcmd_cpu=LOWCMD_CPU)
    worker = None
    parent_conn = None
    child_conn = None
    command_source = None
    heading_controller = None
    log_handle = None
    cv2_module = None
    lowcmd_started = False
    sport_released = False
    running = [True]

    def stop_handler(_sig, _frame):
        running[0] = False
        print("\n停止中...")

    signal.signal(signal.SIGINT, stop_handler)

    try:
        # initialize() 只创建 DDS 对象；start_lowcmd_thread() 前不会 Write LowCmd。
        if not driver.initialize():
            return 1

        context = mp.get_context("spawn")
        parent_conn, child_conn = context.Pipe()
        worker = context.Process(
            target=run_go2wwmp_policy,
            args=(
                child_conn,
                args.model,
                DDS.DEPTH_NET_IF,
                DEPTH_DOMAIN,
                DEPTH_TOPIC,
                DEPTH_MAX_AGE_MS,
                None,
                TORCH_THREADS,
                str(args.observation_dir) if args.observation_dir is not None else None,
                str(args.log),
            ),
        )
        worker.start()
        child_conn.close()
        child_conn = None

        args.log.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.log.open("w")

        ready = receive_event(parent_conn, "ready", 30.0, "WMP worker 初始化")
        print(
            f"[READY] model_sha256={ready['model_sha256']} "
            f"depth_session={ready['depth_session']} frame={ready['depth_frame']} "
            f"valid={ready['depth_valid_ratio']:.3f}"
        )
        if args.observation_dir is not None:
            print(f"[OBS] chunked archive={args.observation_dir}")
        else:
            print("[OBS] observation archive disabled")

        # 接管前必须先用真实 LowState + 深度完整跑通一帧 WMP，但不发送 action。
        state_deadline = time.monotonic() + 5.0
        while not driver.get_state().received_monotonic_ns and time.monotonic() < state_deadline:
            time.sleep(0.01)
        state = driver.get_state()
        require_fresh_state(state)
        parent_conn.send(("step", state_payload(state), np.zeros(3, dtype=np.float32)))
        first = receive_event(parent_conn, "step", 5.0, "WMP 首帧只读自检")
        print_status(first, 1)
        print("[SELF CHECK] LowState + depth + WMP 已通过；尚未发送 LowCmd")

        command_source = UnitreeRemoteCommandSource(
            deadzone=REMOTE_DEADZONE,
            lowstate_timeout=REMOTE_TIMEOUT_S,
            minimum=CTRL.WMP_COMMAND_MIN,
            maximum=CTRL.WMP_COMMAND_MAX,
        )
        heading_controller = HeadingModeController(
            minimum=CTRL.WMP_COMMAND_MIN,
            maximum=CTRL.WMP_COMMAND_MAX,
            forward_speed=HEADING_FORWARD_SPEED,
            yaw_kp=HEADING_YAW_KP,
        )

        display_enabled = not args.no_depth_display
        if display_enabled:
            try:
                cv2_module = load_cv2_for_gui()
                cv2_module.namedWindow("go2wwmp depth", cv2_module.WINDOW_NORMAL)
                print(f"[DEPTH DISPLAY] 单幅预览 {DEPTH_DISPLAY_HZ:g} Hz")
            except Exception as exc:
                print(f"[DEPTH DISPLAY] 无法打开，控制继续运行: {exc}")
                display_enabled = False

        print("[UNITREE] 请先用原生 Sport Mode 站稳，并确认保护架/绳和物理急停可靠。")
        if not command_source.wait_for_takeover(lambda: not running[0]):
            return 0

        # 深度同步和初始命令缓存都在 Sport Mode 尚未释放时完成；缓存不会触发 Write。
        parent_conn.send(("sync_session",))
        sync = receive_event(parent_conn, "session_sync", 5.0, "接管前深度同步")
        print(
            f"[DEPTH SYNC] session={sync['depth_session']} frame={sync['depth_frame']} "
            f"valid={sync['depth_valid_ratio']:.3f} rebased={sync['session_rebased']}"
        )
        driver.send_command(build_initial_hold_command())

        # ReleaseMode 返回后不再执行模型/深度初始化，立即发送已缓存的固定站姿。
        if not driver.release_sport_mode():
            return 1
        sport_released = True
        if not driver.start_lowcmd_thread():
            raise RuntimeError("固定初始 LowCmd 启动失败")
        lowcmd_started = True
        print("[GROUND STAND] WMP action 已接管；持续到 Select/Ctrl+C 或故障退出")
        print(
            f"[HEADING] 按 {HEADING_ENABLE_BUTTON} 开启：锁定当前 yaw、"
            f"vx={HEADING_FORWARD_SPEED:.1f}m/s；按 {HEADING_DISABLE_BUTTON} 关闭并恢复摇杆"
        )

        period = 1.0 / POLICY_RATE_HZ
        preview_period = 1.0 / DEPTH_DISPLAY_HZ
        next_deadline = time.monotonic()
        next_preview = next_deadline
        report_start = next_deadline
        report_count = 0
        loop_count = 0

        while running[0]:
            if driver.emergency:
                raise RuntimeError("DdsDriver 已进入紧急阻尼")
            state = driver.get_state()
            state_age_ms = require_fresh_state(state)
            command_sample, remote = command_source.read_with_remote()
            if command_sample.quit_requested:
                print("[COMMAND SOURCE] Select 请求退出")
                break
            heading_command = heading_controller.update(
                current_yaw=state.imu_rpy[2],
                manual_velocity=command_sample.velocity,
                enable_pressed=remote.buttons[HEADING_ENABLE_BUTTON],
                disable_pressed=remote.buttons[HEADING_DISABLE_BUTTON],
            )
            if heading_command.event == "enabled":
                print(
                    "[HEADING ON] "
                    f"target_yaw={heading_command.target_yaw_rad:+.3f}rad "
                    f"vx={heading_command.velocity[0]:.3f}m/s"
                )
            elif heading_command.event == "disabled":
                print("[HEADING OFF] 已恢复原装遥控器 Ly/Rx 命令")

            preview_requested = display_enabled and time.monotonic() >= next_preview
            if preview_requested:
                next_preview += preview_period
            parent_conn.send(
                (
                    "step",
                    state_payload(state),
                    heading_command.velocity,
                    preview_requested,
                    args.observation_dir is not None,
                    loop_count + 1,
                    time.time_ns(),
                    time.perf_counter_ns(),
                    int(state.tick),
                    state_age_ms,
                )
            )
            response = receive_event(
                parent_conn, "step", max(0.5, 3.0 * period), "WMP worker 响应"
            )
            if response["session_changed"]:
                raise RuntimeError(
                    "深度 session 改变: "
                    f"{response['previous_depth_session']} -> {response['depth_session']} "
                    f"(frame={response['depth_frame']})"
                )

            response.update(
                heading_mode=heading_command.enabled,
                heading_event=heading_command.event,
                heading_target_yaw_rad=heading_command.target_yaw_rad,
                heading_current_yaw_rad=heading_command.current_yaw_rad,
                heading_error_rad=heading_command.error_rad,
            )

            loop_count += 1
            report_count += 1
            driver.send_command(response_to_motor_command(response))
            write_log(log_handle, response, loop_count, state, state_age_ms)
            print_status(response, loop_count)

            if preview_requested and "depth_preview" in response:
                if not show_depth_preview(cv2_module, response):
                    print("[DEPTH DISPLAY] 窗口已关闭；控制继续运行但不再显示")
                    display_enabled = False

            now = time.monotonic()
            if now - report_start >= 1.0:
                print(f"[RATE] WMP requests={report_count / (now - report_start):.2f} Hz")
                report_start = now
                report_count = 0
            next_deadline += period
            remaining = next_deadline - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            else:
                next_deadline = time.monotonic()

        print(
            f"[DONE] requests={loop_count} lowcmd_started={lowcmd_started} "
            f"writes={driver.write_count}"
        )
        return 0
    except Exception as exc:
        print(f"[FAIL CLOSED] {type(exc).__name__}: {exc}")
        return 2
    finally:
        # 一旦 ReleaseMode 成功，先让 500 Hz 路径进入阻尼，再做可能较慢的资源清理。
        if sport_released:
            driver.set_emergency_damping()
            if not lowcmd_started:
                try:
                    lowcmd_started = driver.start_lowcmd_thread()
                except Exception as exc:
                    print(f"[FAIL CLOSED] 无法启动兜底阻尼线程: {exc}")

        if worker is not None and worker.is_alive():
            if parent_conn is not None:
                try:
                    parent_conn.send(None)
                except (EOFError, BrokenPipeError, OSError):
                    pass
            worker.join(timeout=2.0)
        if worker is not None and worker.is_alive():
            worker.terminate()
            worker.join(timeout=1.0)
        if parent_conn is not None:
            parent_conn.close()
        if child_conn is not None:
            child_conn.close()
        if command_source is not None:
            command_source.close()
        if cv2_module is not None:
            try:
                cv2_module.destroyAllWindows()
            except Exception:
                pass
        if log_handle is not None:
            log_handle.close()
        if lowcmd_started:
            time.sleep(0.1)
        driver.shutdown()


def main(argv=None):
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
