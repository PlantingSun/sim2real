"""Go2W 的 Ctrl 参数、DDS 参数和两种关节顺序映射。"""

import os
import platform
import numpy as np


class CTRL:
    """策略控制器内部使用的参数（Ctrl 关节顺序）。"""

    JOINT_NAMES = (
        "FL_hip", "FL_thigh", "FL_calf", "FL_foot",
        "FR_hip", "FR_thigh", "FR_calf", "FR_foot",
        "RL_hip", "RL_thigh", "RL_calf", "RL_foot",
        "RR_hip", "RR_thigh", "RR_calf", "RR_foot",
    )
    WHEEL_INDICES = [3, 7, 11, 15]
    DOF_MASK = np.ones(16, dtype=bool)
    DOF_MASK[WHEEL_INDICES] = False

    INITIAL_JOINTS_POS = np.array(
        [
            0.0, 0.67, -1.3, 0.0,
            0.0, 0.67, -1.3, 0.0,
            0.0, 0.67, -1.3, 0.0,
            0.0, 0.67, -1.3, 0.0,
        ],
        dtype=np.float32,
    )

    LEG_KP = 50.0
    LEG_KD = 1.0
    WHEEL_KP = 0.0
    WHEEL_KD = 0.5

    POS_SCALE = 0.25
    VEL_SCALE = 10.0

    NUM_OBS = 53
    NUM_ACTIONS = 16
    HISTORY_LENGTH = 5
    CLIP_OBS = 100.0
    CLIP_ACTION = 100.0
    ACTOR_HIDDEN_DIMS = [512, 256, 128]
    CRITIC_HIDDEN_DIMS = [512, 256, 128]

    POLICY_RATE_HZ = 50
    # [vx, vy, vyaw]。输入设备和固定速度模式都在进入策略前裁剪到该范围。
    COMMAND_LIMITS = np.array([1.0, 1.0, 0.5], dtype=np.float32)
    # simtosim 的原始训练范围是 vx=[0,1]、vy=0、vyaw=[-1,1]；当前实机
    # 手柄按用户确认放开少量倒车范围到 vx=-0.2。这个范围仍独立于
    # Go2W/Go2WCR 的通用 COMMAND_LIMITS，并在 WMP 全链路统一裁剪。
    WMP_COMMAND_MIN = np.array([-0.2, 0.0, -1.0], dtype=np.float32)
    WMP_COMMAND_MAX = np.array([1.0, 0.0, 1.0], dtype=np.float32)


class CRRL:
    """CRRL/go2wcr 策略参数；电机接口仍沿用 ``CTRL``。"""

    NUM_ASSIST_STAGES = 4
    NUM_ASSIST_PARAMS = 4  # [sin(c_k), cos(c_k), sin(c_{k-1}), cos(c_{k-1})]
    ASSIST_CURRICULUM_POWER = 1.5

    ACTOR_HIDDEN_DIMS = [256, 256, 256, 256]
    CRITIC_HIDDEN_DIMS = [512, 256, 128]
    ACTOR_OBS_DIM = (
        CTRL.NUM_OBS * CTRL.HISTORY_LENGTH
        + CTRL.NUM_ACTIONS
        + NUM_ASSIST_PARAMS
    )
    CRITIC_OBS_DIM = 119 + NUM_ASSIST_PARAMS
    CLIP_OBS = CTRL.CLIP_OBS
    CLIP_ACTION = CTRL.CLIP_ACTION


class DDS:
    """Unitree SDK2/CycloneDDS 通信和实物侧参数。"""

    DOMAIN_ID = 0
    # 当前已确认的固定有线网口。笔记本和 Orin 的默认值分开写在配置中，
    # 因此直接运行 Python 入口时也不需要手动 export 网卡环境变量。
    LAPTOP_NET_IF = "enp0s31f6"
    ORIN_NET_IF = "eth0"
    DEFAULT_NET_IF = os.environ.get(
        "SIM2REAL_NET_IF",
        ORIN_NET_IF if platform.machine() in ("aarch64", "arm64") else LAPTOP_NET_IF,
    )
    DEPTH_NET_IF = DEFAULT_NET_IF
    DEFAULT_JOYSTICK = os.environ.get(
        "SIM2REAL_JOYSTICK",
        "/dev/input/by-id/usb-BEITONG_BEITONG_A1T2_BFM_DONGLE-joystick"
        if platform.machine() in ("aarch64", "arm64") else "/dev/input/js0",
    )
    LOWCMD_TOPIC = "rt/lowcmd"
    LOWSTATE_TOPIC = "rt/lowstate"
    RATE_HZ = 500

    POS_STOP_F = 2.146e9
    VEL_STOP_F = 16000.0

    # DDS 顺序的 16 路 q/dq 参考值，数值对应 assets/go2w_description/mjcf/go2w.xml。
    # 当前 q_min/q_max 仅作为记录，不启用任何位置保护；命令侧不做 q/dq 限制，只有 LowState
    # 实测 dq 按 30 rad/s 急停。轮子的 MJCF q range 是无界占位值。
    JOINT_LIMITS = [
        {"q_min": -1.0472, "q_max": 1.0472, "dq_max": 30.0},       # DDS 0: FR hip
        {"q_min": -1.5708, "q_max": 3.4907, "dq_max": 30.0},       # DDS 1: FR thigh
        {"q_min": -2.7227, "q_max": -0.83776, "dq_max": 30.0},     # DDS 2: FR calf
        {"q_min": -1.0472, "q_max": 1.0472, "dq_max": 30.0},       # DDS 3: FL hip
        {"q_min": -1.5708, "q_max": 3.4907, "dq_max": 30.0},       # DDS 4: FL thigh
        {"q_min": -2.7227, "q_max": -0.83776, "dq_max": 30.0},     # DDS 5: FL calf
        {"q_min": -1.0472, "q_max": 1.0472, "dq_max": 30.0},       # DDS 6: RR hip
        {"q_min": -1.0236, "q_max": 4.5379, "dq_max": 30.0},       # DDS 7: RR thigh
        {"q_min": -2.7227, "q_max": -0.83776, "dq_max": 30.0},     # DDS 8: RR calf
        {"q_min": -1.0472, "q_max": 1.0472, "dq_max": 30.0},       # DDS 9: RL hip
        {"q_min": -1.0236, "q_max": 4.5379, "dq_max": 30.0},       # DDS 10: RL thigh
        {"q_min": -2.7227, "q_max": -0.83776, "dq_max": 30.0},     # DDS 11: RL calf
        {"q_min": -999999.0, "q_max": 999999.0, "dq_max": 30.0},  # DDS 12: FR wheel
        {"q_min": -999999.0, "q_max": 999999.0, "dq_max": 30.0},  # DDS 13: FL wheel
        {"q_min": -999999.0, "q_max": 999999.0, "dq_max": 30.0},  # DDS 14: RR wheel
        {"q_min": -999999.0, "q_max": 999999.0, "dq_max": 30.0},  # DDS 15: RL wheel
    ]
    WHEEL_VEL_LIMIT = 30.0
    EMERGENCY_DAMPING_KD = 8.0

    SPORT_MODE_TIMEOUT = 5.0
    SPORT_MODE_MAX_ATTEMPTS = 10


# 保留用户已确认的映射数值。
# 用法：ctrl_array = dds_array[CTRL_IDX_FROM_DDS]
CTRL_IDX_FROM_DDS = [3, 4, 5, 13, 0, 1, 2, 12, 9, 10, 11, 15, 6, 7, 8, 14]
# 用法：dds_array = ctrl_array[DDS_IDX_FROM_CTRL]
DDS_IDX_FROM_CTRL = [4, 5, 6, 0, 1, 2, 12, 13, 14, 8, 9, 10, 7, 3, 15, 11]
