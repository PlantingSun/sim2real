# ============================================================================
# driver_base.py — 抽象驱动接口
#
# 定义 RobotState、MotorCommand 数据容器和 DriverBase 抽象类。
# 所有驱动后端（DDS、MuJoCo）必须实现此接口。
# ============================================================================

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import numpy as np


@dataclass
class RobotState:
    """统一机器人状态，替代 ROS MotorReturn + IMU + Twist。"""
    # 关节数据（16 DOF，DDS 顺序）
    joint_positions: np.ndarray = field(default_factory=lambda: np.zeros(16, dtype=np.float32))
    joint_velocities: np.ndarray = field(default_factory=lambda: np.zeros(16, dtype=np.float32))
    joint_torques: np.ndarray = field(default_factory=lambda: np.zeros(16, dtype=np.float32))
    # IMU
    imu_quat: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))  # [w,x,y,z]
    imu_gyro: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))       # [x,y,z]
    imu_accel: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))      # [x,y,z]
    imu_rpy: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))        # [roll,pitch,yaw]
    # 系统
    tick: int = 0
    battery_soc: float = 0.0


@dataclass
class MotorCommand:
    """统一电机指令，替代 ROS MotorControl。"""
    positions: np.ndarray = field(default_factory=lambda: np.zeros(16, dtype=np.float32))
    velocities: np.ndarray = field(default_factory=lambda: np.zeros(16, dtype=np.float32))
    kp: np.ndarray = field(default_factory=lambda: np.zeros(16, dtype=np.float32))
    kd: np.ndarray = field(default_factory=lambda: np.zeros(16, dtype=np.float32))
    torques: np.ndarray = field(default_factory=lambda: np.zeros(16, dtype=np.float32))


class DriverBase(ABC):
    """驱动抽象基类。"""

    @abstractmethod
    def initialize(self) -> bool:
        """建立连接，返回 True 表示成功。"""
        ...

    @abstractmethod
    def get_state(self) -> RobotState:
        """读取最新机器人状态（非阻塞）。"""
        ...

    @abstractmethod
    def send_command(self, cmd: MotorCommand) -> None:
        """发送电机指令（非阻塞，写入内部缓冲区）。"""
        ...

    @abstractmethod
    def set_emergency_damping(self) -> None:
        """紧急阻尼：全部电机 kp=0, kd>0, 目标速度=0。"""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """安全关闭：停止发布、清理资源。"""
        ...
