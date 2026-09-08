#!/usr/bin/env python3
"""Go2WWMP real-machine validation: read-only print or fixed ground stand.

Default safety model:
  --print-only  reads LowState + depth and prints candidate WMP output; no LowCmd.
  --ground-stand --arm performs the staged fixed INITIAL_JOINTS_POS ground hold,
                  while WMP output remains print-only.
  --ground-stand --arm --enable-wmp-action explicitly sends candidate actions for <=5s.
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
        help="显式发送 WMP MotorCommand；仅允许 ground-stand，duration 必须不超过 5 秒",
    )
    parser.add_argument("--interface", default=DDS.DEFAULT_NET_IF,
                        help="Unitree domain 0 网卡")
    parser.add_argument("--depth-interface", required=True,
                        help="深度 domain 42 网卡，通常与 --interface 相同但必须显式确认")
    parser.add_argument("--depth-domain", type=int, default=42)
    parser.add_argument("--depth-topic", default="rt/depth/image64")
    parser.add_argument("--depth-max-age-ms", type=float, default=100.0)
    parser.add_argument("--min-valid-ratio", type=float, default=0.90,
                        help="低于此值停止；默认允许已知 USB2 底部无效行")
    parser.add_argument("--model", default=model_path("go2wwmp/model_6000.pt"))
    parser.add_argument("--duration", type=float, default=30.0)
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
    if args.duration <= 0 or args.rate <= 0 or args.torch_threads < 1:
        parser.error("duration/rate 必须为正数，torch-threads 必须为正整数")
    if args.depth_max_age_ms <= 0:
        parser.error("depth-max-age-ms 必须为正数")
    if not 0.0 <= args.min_valid_ratio <= 1.0:
        parser.error("min-valid-ratio 必须位于 [0,1]")

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
    if args.enable_wmp_action and args.duration > 5.0:
        parser.error("--enable-wmp-action 的 duration 不能超过 5 秒")
    if args.enable_wmp_action and not args.log:
        parser.error("--enable-wmp-action 必须同时提供 --log，保留动作和状态证据")
    if not Path(args.model).is_file():
        parser.error(f"找不到 WMP checkpoint: {args.model}")

    print("=== Go2WWMP 实机数据验证 ===")
    print(f"[MODE] {'PRINT ONLY' if args.print_only else 'FIXED GROUND STAND'}")
    print(f"[DDS] motor domain=0 interface={args.interface}")
    print(f"[DEPTH] domain={args.depth_domain} interface={args.depth_interface} topic={args.depth_topic}")
    if args.enable_wmp_action:
        print("[SAFETY] WMP action ENABLED for <=5s; q/dq/velocity limits are checked before buffering")
    else:
        print(f"[SAFETY] min_valid_ratio={args.min_valid_ratio:.3f}; WMP candidate actions are never sent")
    print("[CMD] print-only/ground-stand uses cmd_vel=[0, 0, 0]; no joystick command is forwarded")

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
              args.depth_topic, args.depth_max_age_ms, args.min_valid_ratio,
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

        if args.ground_stand:
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
                print("[GROUND STAND] 500 Hz 已接管；下一响应起发送 WMP action，最长 5 秒")
            else:
                print("[GROUND STAND] 500 Hz 固定 INITIAL_JOINTS_POS 已接管；WMP action 仍只打印")

        period = 1.0 / args.rate
        deadline = time.monotonic() + args.duration
        next_deadline = time.monotonic()
        count = 0
        report_start = time.monotonic()
        report_count = 0
        while running and time.monotonic() < deadline:
            if driver.emergency:
                raise RuntimeError("DdsDriver 已进入紧急阻尼")
            state = driver.get_state()
            state_age_ms = require_fresh_state(state)
            parent_conn.send(("step", state_payload(state), np.zeros(3, dtype=np.float32)))
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
            action_sent = False
            if args.enable_wmp_action:
                driver.send_command(response_to_motor_command(response))
                action_sent = True
            if log_handle:
                record = dict(response)
                for key in ("action", "positions", "velocities", "kp", "kd"):
                    record[key] = np.asarray(record[key], dtype=np.float32).tolist()
                record["loop"] = count
                record["state_tick"] = int(state.tick)
                record["state_age_ms"] = state_age_ms
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
            if log_handle:
                log_handle.close()
            if lowcmd_started:
                driver.set_emergency_damping()
                time.sleep(0.1)
            driver.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
