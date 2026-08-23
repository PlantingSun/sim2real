import torch.nn as nn
import torch
import numpy as np


def resolve_nn_activation(act_name: str) -> torch.nn.Module:
    if act_name == "elu":
        return torch.nn.ELU()
    elif act_name == "selu":
        return torch.nn.SELU()
    elif act_name == "relu":
        return torch.nn.ReLU()
    elif act_name == "crelu":
        return torch.nn.CELU()
    elif act_name == "lrelu":
        return torch.nn.LeakyReLU()
    elif act_name == "tanh":
        return torch.nn.Tanh()
    elif act_name == "sigmoid":
        return torch.nn.Sigmoid()
    elif act_name == "identity":
        return torch.nn.Identity()
    else:
        raise ValueError(f"Invalid activation function '{act_name}'.")


def q_conjugate(q):
    x, y, z, w = q
    return (-x, -y, -z, w)


def q_mult(q1, q2):
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
    x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
    y = w1 * y2 + y1 * w2 + z1 * x2 - x1 * z2
    z = w1 * z2 + z1 * w2 + x1 * y2 - y1 * x2
    return x, y, z, w


def quat_rotate_inverse(q1, v1):
    q2 = v1 + (0.0,)
    output = q_mult(q_mult(q_conjugate(q1), q2), q1)[:3]
    return output


def wrap_to_pi(angles):
    angles %= 2 * np.pi
    angles -= 2 * np.pi * (angles > np.pi)
    return angles


def quat_apply(q, v):
    q = np.asarray(q, dtype=np.float32)
    v = np.asarray(v, dtype=np.float32)
    xyz = q[:3]
    w = q[3]
    t = 2.0 * np.cross(xyz, v)
    return v + w * t + np.cross(xyz, t)
