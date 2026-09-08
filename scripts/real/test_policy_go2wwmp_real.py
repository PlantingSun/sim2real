#!/usr/bin/env python3
"""Go2WWMP real-machine validation: read-only print or bounded ground stand.

Default safety model:
  --print-only  reads LowState + depth and prints candidate WMP output; no LowCmd.
  --ground-stand --arm performs the staged fixed INITIAL_JOINTS_POS ground hold,
                  while WMP output remains print-only.
  --ground-stand --arm --enable-wmp-action explicitly sends candidate actions;
                  omit --duration for Xbox/Unitree operation until the controller
                  requests exit or Ctrl+C.

The optional Xbox/Unitree sources are command-only inputs; they do not change the
WMP/depth pipeline and are clipped to the WMP training envelope plus the field cap.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
from pathlib import Path
import signal
import sys
import termios
import time
import tty
import numpy as np

from config.go2w_config import CTRL, DDS, DDS_IDX_FROM_CTRL
from config.paths import model_path
from driver.dds_driver import DdsDriver
from driver.driver_base import MotorCommand
from policy.process_worker_go2wwmp import run_go2wwmp_policy
from teleop.unitree_remote import UnitreeRemoteCommandSource
from teleop.command_source import FixedCommandSource, XboxCommandSource


def build_initial_hold_command() -> MotorCommand:
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


def response_to_motor_command(response) -> MotorCommand:
    """Convert one worker candidate to a checked Driver command."""
    return MotorCommand(
        positions=np.asarray(response["positions"], dtype=np.float32),
        velocities=np.asarray(response["velocities"], dtype=np.float32),
        kp=np.asarray(response["kp"], dtype=np.float32),
        kd=np.asarray(response["kd"], dtype=np.float32),
        torques=np.zeros(16, dtype=np.float32),
    )


def wait_for_key(expected: str, message: str) -> bool:
    if not sys.stdin.isatty():
        raise RuntimeError("ground-stand requires an interactive terminal")
    print(f"\n{message}")
    print(f"按 {expected} 继续，按 q 或 Esc 取消。")
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            key = sys.stdin.read(1)
            if key == expected:
                print(expected)
                return True
            if key in ("q", "\x1b"):
                print("取消。")
                return False
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def state_payload(state):
    return (
        state.joint_positions.copy(),
        state.joint_velocities.copy(),
        state.imu_quat.copy(),
        state.imu_gyro.copy(),
    )


def require_fresh_state(state, max_age_ms=100.0):
    if not state.received_monotonic_ns:
        raise RuntimeError("LowState 尚未收到")
    age_ms = (time.perf_counter_ns() - state.received_monotonic_ns) / 1.0e6
    if age_ms > max_age_ms:
        raise RuntimeError(f"LowState 过期: age={age_ms:.1f}ms > {max_age_ms:.1f}ms")
    return float(age_ms)


def print_candidate(response, count):
    if count == 1 or count % 50 == 0 or response.get("session_changed"):
        action = np.asarray(response["action"])
        positions = np.asarray(response["positions"])
        velocities = np.asarray(response["velocities"])
        print(
            "[WMP PRINT] "
            f"frame={response['depth_frame']} session={response['depth_session']} "
            f"cmd={np.array2string(np.asarray(response['command']), precision=3, suppress_small=True)} "
            f"valid={response['depth_valid_ratio']:.3f} "
            f"local_age={response['depth_local_age_ms']:.1f}ms "
            f"infer={response['inference_ms']:.2f}ms "
            f"depth_update={response['needs_depth_update']} "
            f"action_range=[{action.min():+.3f},{action.max():+.3f}]"
        )
        print(
            "  candidate DDS positions="
            f"{np.array2string(positions, precision=3, suppress_small=True)}"
        )
        print(
            "  candidate DDS velocities="
            f"{np.array2string(velocities, precision=3, suppress_small=True)}"
        )


def create_wmp_command_source(args):
    """Create a bounded WMP command source; this function never touches DDS."""
    minimum = np.array([CTRL.WMP_COMMAND_MIN[0], 0.0, -args.max_vyaw], dtype=np.float32)
    maximum = np.array([args.max_vx, 0.0, args.max_vyaw], dtype=np.float32)
    if args.control == "xbox":
        return XboxCommandSource(args.joystick, minimum=minimum, maximum=maximum)
    if args.control == "unitree":
        return UnitreeRemoteCommandSource(
            deadzone=args.deadzone,
            lowstate_timeout=args.lowstate_timeout,
            minimum=minimum,
            maximum=maximum,
        )
    return FixedCommandSource(
        [args.vx, args.vy, args.vyaw], minimum=minimum, maximum=maximum
    )


def show_depth_preview(cv2_module, response):
    """Display one worker-provided depth frame; this never affects commands."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print-only", action="store_true")
    mode.add_argument("--ground-stand", dest="ground_stand", action="store_true",
                      help="显式进入落地承重的固定 INITIAL_JOINTS_POS 站姿")
    # Backward-compatible spelling for already reviewed commands. Keep it hidden
    # so new instructions use the physically accurate name.
    mode.add_argument("--hold-stand", dest="ground_stand", action="store_true",
                      help=argparse.SUPPRESS)
    parser.add_argument("--arm", action="store_true",
                        help="仅允许与 --ground-stand 一起使用；显式授权固定站姿 LowCmd")
    parser.add_argument(
        "--enable-wmp-action",
        action="store_true",
        help="显式发送 WMP MotorCommand；仅允许 ground-stand，Xbox Back/Unitree Select/Ctrl+C 停止",
    )
    parser.add_argument("--interface", default=DDS.DEFAULT_NET_IF,
                        help="Unitree domain 0 网卡")
    parser.add_argument("--depth-interface", default=DDS.DEPTH_NET_IF,
                        help="深度 domain 42 网卡；默认读取 go2w_config.DDS.DEPTH_NET_IF")
    parser.add_argument("--depth-domain", type=int, default=42)
    parser.add_argument("--depth-topic", default="rt/depth/image64")
    parser.add_argument("--depth-max-age-ms", type=float, default=100.0)
    parser.add_argument("--control", choices=("fixed", "xbox", "unitree"), default="fixed",
                        help="WMP cmd_vel 来源；xbox 按住 A，unitree 使用 L2+R2 接管/Select 退出")
    parser.add_argument("--joystick", default=DDS.DEFAULT_JOYSTICK,
                        help="Xbox Linux joystick 路径")
    parser.add_argument("--deadzone", type=float, default=0.10,
                        help="Unitree 手柄摇杆 deadzone")
    parser.add_argument("--lowstate-timeout", type=float, default=0.50,
                        help="Unitree 手柄 LowState 超时（秒）")
    parser.add_argument("--vx", type=float, default=0.0, help="固定模式 vx (m/s)")
    parser.add_argument("--vy", type=float, default=0.0, help="固定模式 vy；WMP 必须为 0")
    parser.add_argument("--vyaw", type=float, default=0.0, help="固定模式 vyaw (rad/s)")
    parser.add_argument("--max-vx", type=float, default=1.0,
                        help="实机输入上限 vx；默认 1.0 m/s")
    parser.add_argument("--max-vyaw", type=float, default=1.0,
                        help="实机输入上限 |vyaw|；默认 1.0 rad/s")
    parser.add_argument("--model", default=model_path("go2wwmp/model_6000.pt"))
    parser.add_argument("--duration", type=float, default=None,
                        help="运行秒数；省略则持续运行到 Ctrl+C、手柄退出或输入故障")
    parser.add_argument("--depth-display-hz", type=float, default=2.0,
                        help="Xbox/Unitree 模式单张深度预览刷新频率，默认 2 Hz")
    parser.add_argument("--no-depth-display", action="store_true",
                        help="关闭 Xbox 模式深度窗口")
    parser.add_argument("--rate", type=float, default=CTRL.POLICY_RATE_HZ)
    parser.add_argument("--policy-cpus", default="",
                        help="WMP 子进程 CPU 列表；留空不绑定")
    parser.add_argument("--torch-threads", type=int, default=1)
    parser.add_argument("--lowcmd-cpu", type=int, default=1)
    parser.add_argument("--log", default="", help="JSONL diagnostics path")
    args = parser.parse_args()

    if args.arm and not args.ground_stand:
        parser.error("--arm 只能与 --ground-stand 一起使用")
    if args.ground_stand and not args.arm:
        parser.error("--ground-stand 必须同时提供 --arm；默认不会接管 LowCmd")
    if not args.interface.strip():
        parser.error("--interface 不能为空；请填写实际电机网卡名")
    if not args.depth_interface.strip():
        parser.error("--depth-interface 不能为空；请填写实际深度网卡名")
    if args.duration is not None and args.duration <= 0:
        parser.error("duration 必须为正数")
    if args.rate <= 0 or args.torch_threads < 1 or args.depth_display_hz <= 0:
        parser.error("rate/depth-display-hz 必须为正数，torch-threads 必须为正整数")
    if args.depth_max_age_ms <= 0:
        parser.error("depth-max-age-ms 必须为正数")
    if not 0.0 <= args.deadzone < 1.0:
        parser.error("deadzone 必须在 [0, 1) 内")
    if args.lowstate_timeout <= 0.0:
        parser.error("lowstate-timeout 必须为正数")
    if not (0.0 < args.max_vx <= float(CTRL.WMP_COMMAND_MAX[0])):
        parser.error("max-vx 必须在 (0, 1.0] 内")
    if not (0.0 < args.max_vyaw <= float(CTRL.WMP_COMMAND_MAX[2])):
        parser.error("max-vyaw 必须在 (0, 1.0] 内")
    fixed_command = np.array([args.vx, args.vy, args.vyaw], dtype=np.float32)
    real_command_min = np.array([CTRL.WMP_COMMAND_MIN[0], 0.0, -args.max_vyaw], dtype=np.float32)
    real_command_max = np.array([args.max_vx, 0.0, args.max_vyaw], dtype=np.float32)
    if args.control == "fixed" and (
        not np.isfinite(fixed_command).all()
        or np.any(fixed_command < real_command_min)
        or np.any(fixed_command > real_command_max)
    ):
        parser.error(
            "固定实机 cmd_vel 超出当前现场上限: "
            f"min={real_command_min.tolist()} max={real_command_max.tolist()}"
        )

    try:
        policy_cpus = ({int(value) for value in args.policy_cpus.split(",")}
                       if args.policy_cpus else None)
    except ValueError:
        parser.error("policy-cpus 必须是逗号分隔的整数，例如 2 或 2,3")
    if policy_cpus and any(cpu < 0 for cpu in policy_cpus):
        parser.error("policy-cpus 不能包含负数")
    allowed_cpus = os.sched_getaffinity(0)
    if policy_cpus and not policy_cpus.issubset(allowed_cpus):
        parser.error(f"policy CPU 不可用: {sorted(policy_cpus)}")
    if args.ground_stand and args.lowcmd_cpu not in allowed_cpus:
        parser.error(f"LowCmd CPU 不可用: {args.lowcmd_cpu}")
    if args.enable_wmp_action and not args.ground_stand:
        parser.error("--enable-wmp-action 只能与 --ground-stand --arm 一起使用")
    if args.enable_wmp_action and not args.log:
        parser.error("--enable-wmp-action 必须同时提供 --log，保留动作和状态证据")
    if args.enable_wmp_action and args.duration is None and args.control not in ("xbox", "unitree"):
        parser.error("无限时长 action 必须使用 --control xbox 或 unitree，并用手柄退出或 Ctrl+C 停止")
    if not Path(args.model).is_file():
        parser.error(f"找不到 WMP checkpoint: {args.model}")

    print("=== Go2WWMP 实机数据验证 ===")
    print(f"[MODE] {'PRINT ONLY' if args.print_only else 'FIXED GROUND STAND'}")
    print(f"[DDS] motor domain=0 interface={args.interface}")
    print(f"[DEPTH] domain={args.depth_domain} interface={args.depth_interface} topic={args.depth_topic}")
    print(
        f"[CMD] control={args.control} bounds="
        f"min={real_command_min.tolist()} max={real_command_max.tolist()} "
        f"(training min={CTRL.WMP_COMMAND_MIN.tolist()} max={CTRL.WMP_COMMAND_MAX.tolist()})"
    )
    if args.enable_wmp_action:
        print("[SAFETY] WMP action ENABLED; command q/dq limits are disabled; LowState measured dq protection remains")
    else:
        print("[SAFETY] valid_ratio is diagnostic only; WMP candidate actions are never sent")
    if args.control == "xbox":
        print("[CMD] WMP lateral velocity is disabled; Xbox A/deadman must be held for non-zero input")
    elif args.control == "unitree":
        print("[CMD] WMP lateral velocity is disabled; Unitree remote uses L2+R2 handoff and Select exit")

    driver = DdsDriver(args.interface, lowcmd_cpu=args.lowcmd_cpu)
    try:
        initialized = driver.initialize()
    except Exception as exc:
        print(f"[FAIL CLOSED] domain 0 初始化失败: {type(exc).__name__}: {exc}")
        driver.shutdown()
        return 2
    if not initialized:
        driver.shutdown()
        return 1

    context = mp.get_context("spawn")
    parent_conn, child_conn = context.Pipe()
    worker = context.Process(
        target=run_go2wwmp_policy,
        args=(child_conn, args.model, args.depth_interface, args.depth_domain,
              args.depth_topic, args.depth_max_age_ms,
              policy_cpus, args.torch_threads),
    )
    try:
        worker.start()
    except Exception as exc:
        child_conn.close()
        print(f"[FAIL CLOSED] WMP worker 启动失败: {type(exc).__name__}: {exc}")
        driver.shutdown()
        return 2
    child_conn.close()
    log_handle = None
    lowcmd_started = False
    command_source = None
    cv2_module = None
    display_enabled = args.control in ("xbox", "unitree") and not args.no_depth_display
    next_depth_preview = time.monotonic()
    preview_period = 1.0 / args.depth_display_hz
    running = True

    def stop_handler(_sig, _frame):
        nonlocal running
        running = False
        print("\n停止中...")

    signal.signal(signal.SIGINT, stop_handler)
    try:
        if args.log:
            log_path = Path(args.log)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handle = log_path.open("w")
        if not parent_conn.poll(30.0):
            raise RuntimeError("WMP worker 初始化超时")
        ready = parent_conn.recv()
        if ready.get("event") != "ready":
            raise RuntimeError(ready.get("error", "WMP worker 初始化失败"))
        print(
            f"[READY] model_sha256={ready['model_sha256']} "
            f"depth_session={ready['depth_session']} frame={ready['depth_frame']} "
            f"valid={ready['depth_valid_ratio']:.3f}"
        )

        # A read-only self-check must pass before any optional staged handover.
        state_deadline = time.monotonic() + 5.0
        while not driver.get_state().received_monotonic_ns and time.monotonic() < state_deadline:
            time.sleep(0.01)
        state = driver.get_state()
        require_fresh_state(state)
        parent_conn.send(("step", state_payload(state), np.zeros(3, dtype=np.float32)))
        if not parent_conn.poll(5.0):
            raise RuntimeError("WMP 首帧只读自检超时")
        first = parent_conn.recv()
        if first.get("event") == "error":
            raise RuntimeError(first["error"])
        if first.get("event") != "step":
            raise RuntimeError(f"WMP 首帧自检返回异常: {first}")
        print_candidate(first, 1)
        print("[SELF CHECK] domain 0 state + domain 42 depth + WMP pipeline passed; no LowCmd write")

        command_source = create_wmp_command_source(args)
        print("[COMMAND SOURCE] ready; input is clipped to the configured field cap and WMP envelope")
        if display_enabled:
            try:
                import cv2
                cv2_module = cv2
                cv2_module.namedWindow("go2wwmp depth", cv2_module.WINDOW_NORMAL)
                print(f"[DEPTH DISPLAY] enabled at {args.depth_display_hz:g} Hz; q/Esc closes the window")
            except Exception as exc:
                print(f"[DEPTH DISPLAY] unavailable, continuing without window: {exc}")
                display_enabled = False

        if args.ground_stand and args.control == "unitree":
            print(
                "[UNITREE] 机器人必须先由原生 Sport Mode 站稳并保持保护架/急停可靠；"
                "程序不猜测原生 StandUp 按键。"
            )
            if not command_source.wait_for_takeover(lambda: not running):
                return 0
            if not driver.release_sport_mode():
                return 1
            parent_conn.send(("sync_session",))
            if not parent_conn.poll(5.0):
                raise RuntimeError("固定站姿接管前深度 session 同步超时")
            sync = parent_conn.recv()
            if sync.get("event") == "error":
                raise RuntimeError(sync["error"])
            if sync.get("event") != "session_sync":
                raise RuntimeError(f"固定站姿接管前深度同步返回异常: {sync}")
            print(
                f"[DEPTH SYNC] session={sync['depth_session']} frame={sync['depth_frame']} "
                f"valid={sync['depth_valid_ratio']:.3f} rebased={sync['session_rebased']}; "
                "fixed hold may now start"
            )
            driver.send_command(build_initial_hold_command())
            if not driver.start_lowcmd_thread():
                return 1
            lowcmd_started = True
            duration_text = "持续到 Select/Ctrl+C" if args.duration is None else f"最长 {args.duration:g} 秒"
            print(f"[GROUND STAND] Unitree 手柄已接管；下一响应起发送 WMP action，{duration_text}")
        elif args.ground_stand:
            if not wait_for_key("1", "阶段 1：确认机器人在地面，执行 StandUp"):
                return 0
            if not driver.stand_up():
                return 1
            if not wait_for_key("2", "阶段 2：确认四足/轮已承重，保护架/绳和急停可靠；释放 Sport Mode 并固定站姿"):
                return 0
            if not driver.release_sport_mode():
                return 1
            # StandUp/manual confirmation can take long enough for the camera
            # service to restart.  Rebaseline its session before any LowCmd;
            # changes after takeover remain fail-closed.
            parent_conn.send(("sync_session",))
            if not parent_conn.poll(5.0):
                raise RuntimeError("固定站姿接管前深度 session 同步超时")
            sync = parent_conn.recv()
            if sync.get("event") == "error":
                raise RuntimeError(sync["error"])
            if sync.get("event") != "session_sync":
                raise RuntimeError(f"固定站姿接管前深度同步返回异常: {sync}")
            print(
                f"[DEPTH SYNC] session={sync['depth_session']} frame={sync['depth_frame']} "
                f"valid={sync['depth_valid_ratio']:.3f} rebased={sync['session_rebased']}; "
                "fixed hold may now start"
            )
            driver.send_command(build_initial_hold_command())
            if not driver.start_lowcmd_thread():
                return 1
            lowcmd_started = True
            if args.enable_wmp_action:
                duration_text = "持续到 Back/Ctrl+C" if args.duration is None else f"最长 {args.duration:g} 秒"
                print(f"[GROUND STAND] 500 Hz 已接管；下一响应起发送 WMP action，{duration_text}")
            else:
                print("[GROUND STAND] 500 Hz 固定 INITIAL_JOINTS_POS 已接管；WMP action 仍只打印")

        period = 1.0 / args.rate
        deadline = None if args.duration is None else time.monotonic() + args.duration
        next_deadline = time.monotonic()
        count = 0
        report_start = time.monotonic()
        report_count = 0
        while running and (deadline is None or time.monotonic() < deadline):
            if driver.emergency:
                raise RuntimeError("DdsDriver 已进入紧急阻尼")
            state = driver.get_state()
            state_age_ms = require_fresh_state(state)
            command_sample = command_source.read()
            if command_sample.quit_requested:
                print("[COMMAND SOURCE] 请求退出")
                break
            command = np.asarray(command_sample.velocity, dtype=np.float32)
            preview_requested = display_enabled and time.monotonic() >= next_depth_preview
            if preview_requested:
                next_depth_preview += preview_period
            parent_conn.send(("step", state_payload(state), command, preview_requested))
            if not parent_conn.poll(max(0.5, 3.0 * period)):
                raise RuntimeError("WMP worker 响应超时")
            response = parent_conn.recv()
            if response.get("event") == "error":
                raise RuntimeError(response["error"])
            if response.get("event") != "step":
                raise RuntimeError(f"WMP worker 返回异常: {response}")
            if response.get("session_changed") and args.ground_stand:
                raise RuntimeError(
                    "深度 session 改变，固定站立测试停止并进入阻尼: "
                    f"{response.get('previous_depth_session')} -> {response.get('depth_session')} "
                    f"(frame={response.get('depth_frame')})"
                )
            count += 1
            report_count += 1
            print_candidate(response, count)
            if preview_requested and "depth_preview" in response:
                if not show_depth_preview(cv2_module, response):
                    print("[DEPTH DISPLAY] window closed; continuing without preview")
                    display_enabled = False
            action_sent = False
            if args.enable_wmp_action:
                driver.send_command(response_to_motor_command(response))
                action_sent = True
            if log_handle:
                record = dict(response)
                record.pop("depth_preview", None)
                record.pop("depth_preview_valid", None)
                for key in ("command", "action", "positions", "velocities", "kp", "kd"):
                    record[key] = np.asarray(record[key], dtype=np.float32).tolist()
                record["loop"] = count
                record["state_tick"] = int(state.tick)
                record["state_age_ms"] = state_age_ms
                record["command_enabled"] = bool(command_sample.enabled)
                record["wmp_action_sent"] = action_sent
                log_handle.write(json.dumps(record) + "\n")
                log_handle.flush()
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
        print(f"[DONE] requests={count} lowcmd_started={lowcmd_started} writes={driver.write_count}")
        return 0
    except (RuntimeError, EOFError, BrokenPipeError) as exc:
        print(f"[FAIL CLOSED] {exc}")
        return 2
    finally:
        try:
            if worker.is_alive():
                try:
                    parent_conn.send(None)
                except (EOFError, BrokenPipeError):
                    pass
                worker.join(timeout=2.0)
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=1.0)
        finally:
            parent_conn.close()
            if command_source is not None:
                command_source.close()
            if cv2_module is not None:
                cv2_module.destroyAllWindows()
            if log_handle:
                log_handle.close()
            if lowcmd_started:
                driver.set_emergency_damping()
                time.sleep(0.1)
            driver.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
