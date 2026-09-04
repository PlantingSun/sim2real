#!/usr/bin/env python3
# ============================================================================
# test_policy_real.py — Step 5: 双进程 policy 实机控制
#
# Usage:
#   source setup.sh robot
#   python scripts/real/test_policy_real.py --control keyboard
#   python scripts/real/test_policy_real.py --control xbox
# ============================================================================

import argparse
import csv
import multiprocessing as mp
import os
from pathlib import Path
import signal
import sys
import termios
import time
import tty

import numpy as np

from driver.dds_driver import DdsDriver
from driver.driver_base import MotorCommand
from policy.process_worker import run_go2w_policy
from config.go2w_config import CTRL, DDS, DDS_IDX_FROM_CTRL
from config.paths import model_path
from teleop.command_source import (
    FixedCommandSource,
    KeyboardCommandSource,
    XboxCommandSource,
)


def create_command_source(args):
    if args.control == "keyboard":
        return KeyboardCommandSource()
    if args.control == "xbox":
        return XboxCommandSource(args.joystick)
    return FixedCommandSource([args.vx, args.vy, args.vyaw])


def wait_for_stage_key(expected_key: str, message: str) -> bool:
    """等待单个阶段按键；q 或 Esc 表示退出。"""
    if not sys.stdin.isatty():
        raise RuntimeError("staged robot control requires an interactive terminal")

    print(f"\n{message}")
    print(f"按 {expected_key} 继续，按 q 退出。")
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            key = sys.stdin.read(1)
            if key == expected_key:
                print(expected_key)
                return True
            if key in ("q", "\x1b"):
                print("取消。")
                return False
            print(f"忽略按键 {key!r}，当前只接受 {expected_key} 或 q。")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def build_initial_hold_command() -> MotorCommand:
    """构造与零 action 相同的固定初始站姿指令（DDS 顺序）。"""
    positions_ctrl = CTRL.INITIAL_JOINTS_POS.copy()
    velocities_ctrl = np.zeros(16, dtype=np.float32)
    kp_ctrl = np.full(16, CTRL.LEG_KP, dtype=np.float32)
    kd_ctrl = np.full(16, CTRL.LEG_KD, dtype=np.float32)

    for index in CTRL.WHEEL_INDICES:
        kp_ctrl[index] = CTRL.WHEEL_KP
        kd_ctrl[index] = CTRL.WHEEL_KD

    return MotorCommand(
        positions=positions_ctrl[DDS_IDX_FROM_CTRL],
        velocities=velocities_ctrl[DDS_IDX_FROM_CTRL],
        kp=kp_ctrl[DDS_IDX_FROM_CTRL],
        kd=kd_ctrl[DDS_IDX_FROM_CTRL],
    )


def print_motor_command(title, positions, velocities, kp, kd) -> None:
    """以统一格式打印一条 MotorCommand。"""
    print(f"\n{title}")
    print("  position:", np.array2string(positions, precision=4, suppress_small=True))
    print("  velocity:", np.array2string(velocities, precision=4, suppress_small=True))
    print("  kp      :", np.array2string(kp, precision=2, suppress_small=True))
    print("  kd      :", np.array2string(kd, precision=2, suppress_small=True))


def open_log(path: str):
    """打开完整状态日志和 observation 日志；未指定路径时不记录。"""
    if not path:
        return None, None, None, None
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["time_s", "loop", "loop_dt_ms", "inference_ms", "ipc_ms", "state_age_ms",
              "action_state_age_ms", "state_tick", "enabled", "warmup",
              "cmd_vx", "cmd_vy", "cmd_vyaw"]
    fields += [f"q_{i}" for i in range(16)]
    fields += [f"dq_{i}" for i in range(16)]
    fields += [f"tau_{i}" for i in range(16)]
    fields += [f"imu_quat_{axis}" for axis in ("w", "x", "y", "z")]
    fields += [f"imu_gyro_{axis}" for axis in ("x", "y", "z")]
    fields += [f"imu_accel_{axis}" for axis in ("x", "y", "z")]
    fields += [f"imu_rpy_{axis}" for axis in ("r", "p", "y")]
    fields += ["battery_voltage", "battery_current"]
    fields += [f"action_{i}" for i in range(16)]
    fields += [f"p_{i}" for i in range(16)]
    fields += [f"v_{i}" for i in range(16)]
    fields += [f"kp_{i}" for i in range(16)]
    fields += [f"kd_{i}" for i in range(16)]
    handle = log_path.open("w", newline="")
    writer = csv.writer(handle)
    writer.writerow(fields)
    handle.flush()
    observation_path = log_path.with_name(f"{log_path.stem}_observation{log_path.suffix}")
    observation_handle = observation_path.open("w", newline="")
    observation_writer = csv.writer(observation_handle)
    observation_fields = ["time_s", "loop", "warmup"]
    observation_fields += [f"obs_{i}" for i in range(CTRL.NUM_OBS * CTRL.HISTORY_LENGTH)]
    observation_fields += [f"action_{i}" for i in range(CTRL.NUM_ACTIONS)]
    observation_writer.writerow(observation_fields)
    observation_handle.flush()
    print(f"[Log] 实时 CSV: {log_path}")
    print(f"[Log] Observation CSV: {observation_path}")
    return handle, writer, observation_handle, observation_writer


def main():
    parser = argparse.ArgumentParser(description="Go2W 实物策略部署")
    parser.add_argument(
        "--control",
        choices=("fixed", "keyboard", "xbox"),
        default="fixed",
        help="速度命令来源（默认保留原 fixed 行为）",
    )
    parser.add_argument("--vx", type=float, default=0.0, help="前进速度 m/s")
    parser.add_argument("--vy", type=float, default=0.0, help="侧向速度 m/s")
    parser.add_argument("--vyaw", type=float, default=0.0, help="转向速度 rad/s")
    parser.add_argument("--model", type=str, default=model_path("go2w/model_700.pt"))
    parser.add_argument("--interface", type=str, default=DDS.DEFAULT_NET_IF)
    parser.add_argument("--policy-cpus", type=str, default="2", help="policy 子进程 CPU 列表")
    parser.add_argument("--lowcmd-cpu", type=int, default=1, help="500Hz LowCmd 线程绑定的 CPU")
    parser.add_argument("--torch-threads", type=int, default=1, help="PyTorch intra-op 线程数")
    parser.add_argument("--warmup", type=float, default=3.0, help="policy 预热秒数")
    parser.add_argument("--rate", type=float, default=CTRL.POLICY_RATE_HZ, help="policy 频率")
    parser.add_argument("--joystick", type=str, default=DDS.DEFAULT_JOYSTICK)
    parser.add_argument("--no-release", action="store_true", help="跳过 Sport Mode 释放")
    parser.add_argument("--print-only", action="store_true", help="policy 只打印，不发送其 MotorCommand")
    parser.add_argument("--log", type=str, default="", help="实时 CSV 路径（留空则不记录）")
    args = parser.parse_args()
    if args.torch_threads < 1 or args.warmup < 0 or args.rate <= 0:
        parser.error("torch-threads/rate 必须为正数，warmup 不能为负数")
    policy_cpus = {int(value) for value in args.policy_cpus.split(",")} if args.policy_cpus else None
    if policy_cpus and not policy_cpus.issubset(os.sched_getaffinity(0)):
        parser.error(f"policy CPU 不可用: {sorted(policy_cpus)}")

    print(f"=== Go2W 实物部署 === control={args.control}")

    # 1. 初始化 DDS 通信；此时不会发布任何 LowCmd。
    driver = DdsDriver(args.interface, lowcmd_cpu=args.lowcmd_cpu)
    if not driver.initialize():
        print("✗ 驱动初始化失败")
        return

    command_source = None
    policy_process = None
    policy_conn = None
    log_handle, log_writer, observation_handle, observation_writer = open_log(args.log)
    lowcmd_started = False
    running = [True]

    def on_sigint(sig, frame):
        running[0] = False
        print("\n停止中...")

    signal.signal(signal.SIGINT, on_sigint)

    try:
        if not args.no_release:
            if not wait_for_stage_key("1", "阶段 1：确认机器人在地面，执行 StandUp"):
                return
            if not driver.stand_up():
                return

            # 提前构造固定指令；这里只准备数据，不发送 LowCmd。
            initial_command = build_initial_hold_command()
            if not wait_for_stage_key(
                "2",
                "阶段 2：确认机器人已站稳并吊好；释放 Sport Mode 后立即启动固定 LowCmd",
            ):
                return
            if not driver.release_sport_mode():
                return
        else:
            initial_command = build_initial_hold_command()

        # ReleaseMode 成功返回后，不再等待人工按键或 CheckMode 轮询。
        handoff_start = time.perf_counter()
        driver.send_command(initial_command)
        if not driver.start_lowcmd_thread():
            return
        lowcmd_started = True
        handoff_ms = (time.perf_counter() - handoff_start) * 1000.0
        print(f"[Handoff] ReleaseMode 返回后到首条 LowCmd Write 调用完成: {handoff_ms:.3f} ms")

        print_motor_command(
            "[LOWCMD ACTIVE] 固定 INITIAL_JOINTS_POS 指令（DDS 顺序，正在发送）",
            initial_command.positions,
            initial_command.velocities,
            initial_command.kp,
            initial_command.kd,
        )

        # policy 使用独立 Python 进程，避免与 500 Hz LowCmd 线程竞争 GIL。
        context = mp.get_context("spawn")
        policy_conn, child_conn = context.Pipe()
        policy_process = context.Process(
            target=run_go2w_policy,
            args=(child_conn, args.model, policy_cpus, args.torch_threads),
        )
        policy_process.start()
        child_conn.close()
        if not policy_conn.poll(30.0):
            raise RuntimeError("policy 子进程初始化超时")
        if policy_conn.recv() != "ready":
            raise RuntimeError("policy 子进程初始化失败")
        command_source = create_command_source(args)

        period = 1.0 / args.rate
        print_every = max(1, int(args.rate // 2))
        loop_count = 0
        active_count = 0
        next_deadline = time.perf_counter()
        warmup_end = next_deadline + args.warmup
        rate_start = warmup_end
        print(f"[WARMUP] {args.warmup:.1f}s，保持 INITIAL_JOINTS_POS，不发送 policy action")
        print(f"\n{args.rate:g}Hz 双进程 policy 实机控制（Ctrl+C 退出）...")

        while running[0]:
            t0 = time.perf_counter()
            if driver.emergency:
                print("[!!] 紧急阻尼中，结束控制循环")
                break

            command = command_source.read()
            if command.quit_requested:
                break
            state = driver.get_state()
            warmup = time.perf_counter() < warmup_end
            command_velocity = np.zeros(3, dtype=np.float32) if warmup else command.velocity
            state_age_ms = (
                (time.perf_counter_ns() - state.received_monotonic_ns) / 1.0e6
                if state.received_monotonic_ns else -1.0
            )
            ipc_start = time.perf_counter()
            policy_conn.send((state.joint_positions, state.joint_velocities,
                              state.imu_quat, state.imu_gyro, command_velocity,
                              warmup or args.print_only))
            p, v, kp, kd, action, observation, inference_ms = policy_conn.recv()
            ipc_ms = (time.perf_counter() - ipc_start) * 1000.0
            action_state_age_ms = (
                (time.perf_counter_ns() - state.received_monotonic_ns) / 1.0e6
                if state.received_monotonic_ns else -1.0
            )
            if not warmup and not args.print_only:
                driver.send_command(MotorCommand(positions=p, velocities=v, kp=kp, kd=kd))
            loop_count += 1
            if not warmup:
                active_count += 1
            if log_writer is not None and log_handle is not None:
                timestamp = time.time()
                log_writer.writerow(
                    [timestamp, loop_count, (time.perf_counter() - t0) * 1000.0,
                     inference_ms, ipc_ms, state_age_ms, action_state_age_ms, state.tick,
                     int(command.enabled), int(warmup), *command_velocity, *state.joint_positions,
                     *state.joint_velocities, *state.joint_torques, *state.imu_quat,
                     *state.imu_gyro, *state.imu_accel, *state.imu_rpy,
                     state.battery_voltage, state.battery_current, *action, *p, *v, *kp, *kd]
                )
                log_handle.flush()
                if observation_writer is not None and observation_handle is not None:
                    observation_writer.writerow(
                        [timestamp, loop_count, int(warmup), *observation, *action]
                    )
                    observation_handle.flush()
            if not warmup and active_count % print_every == 0:
                rate_elapsed = time.perf_counter() - rate_start
                rate_hz = print_every / rate_elapsed if rate_elapsed > 0 else 0.0
                rate_start = time.perf_counter()
                print(f"[RATE] policy={rate_hz:.2f} Hz")
                print(
                    "\n[COMMAND SOURCE] "
                    f"enabled={command.enabled}  "
                    f"vx={command.velocity[0]:+.3f}  "
                    f"vy={command.velocity[1]:+.3f}  "
                    f"vyaw={command.velocity[2]:+.3f}"
                )
                if args.print_only:
                    print(f"[PRINT ONLY] policy action 未发送，inference={inference_ms:.3f} ms")
                action_status = "未发送" if args.print_only else "正在发送"
                print_motor_command(
                    f"[POLICY ACTIVE] 预测 MotorCommand（{action_status}）",
                    p,
                    v,
                    kp,
                    kd,
                )
            next_deadline += period
            remaining = next_deadline - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
            else:
                # 超期后从当前时刻重新计时，禁止连续补跑旧周期。
                next_deadline = time.perf_counter()
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        print(f"\n✗ 控制输入中断: {exc}")
    except (EOFError, BrokenPipeError) as exc:
        print(f"\n✗ policy 子进程通信中断: {exc}")
    finally:
        if command_source is not None:
            command_source.close()
        if log_handle is not None:
            log_handle.close()
        if observation_handle is not None:
            observation_handle.close()
        if policy_process is not None:
            if policy_process.is_alive() and policy_conn is not None:
                try:
                    policy_conn.send(None)
                except (BrokenPipeError, EOFError):
                    pass
                policy_process.join(timeout=1.0)
            if policy_process.is_alive():
                policy_process.terminate()
                policy_process.join(timeout=1.0)
        if policy_conn is not None:
            policy_conn.close()
        if lowcmd_started:
            driver.set_emergency_damping()
            time.sleep(0.1)
        driver.shutdown()
        print("退出。")


if __name__ == "__main__":
    main()
