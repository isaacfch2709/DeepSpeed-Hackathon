"""Pure-pursuit + speed-profile maths, kept free of ROS so it can be tested offline."""

import numpy as np


def load_path(csv_path):
    """Read the `x, y` centreline CSV (lines starting with # are comments)."""
    pts = np.loadtxt(csv_path, delimiter=',', comments='#')
    return pts[:, :2]


def resample(path, step=0.10):
    """Evenly space the closed loop every `step` metres."""
    loop = np.vstack([path, path[:1]])
    seg = np.linalg.norm(np.diff(loop, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    s_new = np.arange(0.0, s[-1], step)
    return np.column_stack([np.interp(s_new, s, loop[:, 0]),
                            np.interp(s_new, s, loop[:, 1])])


def smooth(path, passes=20):
    """Simple moving-average smoothing on a closed loop (removes jaggies)."""
    for _ in range(passes):
        path = (np.roll(path, 1, axis=0) + 2 * path + np.roll(path, -1, axis=0)) / 4.0
    return path


def curvature(path, gap=5):
    """Curvature (1/m) of a closed loop from three points `gap` samples apart."""
    a, b, c = np.roll(path, gap, axis=0), path, np.roll(path, -gap, axis=0)
    ab, bc, ca = (np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1),
                  np.linalg.norm(a - c, axis=1))
    cross = (b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0]
    return 2.0 * cross / np.maximum(ab * bc * ca, 1e-9)   # signed: + is left


def speed_profile(path, v_max, a_lat, a_accel, a_brake):
    """A target speed for every point: corner limit, then accel/brake passes."""
    k = np.abs(curvature(path))
    v = np.minimum(v_max, np.sqrt(a_lat / np.maximum(k, 1e-6)))
    ds = np.linalg.norm(np.roll(path, -1, axis=0) - path, axis=1)
    n = len(v)
    for _ in range(2):                         # twice, so the loop wraps round
        for i in range(n):                     # forwards: can't accelerate harder than a_accel
            j = (i + 1) % n
            v[j] = min(v[j], np.sqrt(v[i] ** 2 + 2 * a_accel * ds[i]))
        for i in range(n - 1, -1, -1):         # backwards: must brake before corners
            j = (i + 1) % n
            v[i] = min(v[i], np.sqrt(v[j] ** 2 + 2 * a_brake * ds[i]))
    return v


def nearest_index(path, x, y, hint=None, window=60):
    """Index of the path point closest to (x, y); search near `hint` when given."""
    if hint is None:
        idx = np.arange(len(path))
    else:
        idx = (hint + np.arange(-10, window)) % len(path)
    d = np.hypot(path[idx, 0] - x, path[idx, 1] - y)
    return int(idx[np.argmin(d)])


def pure_pursuit(path, i_near, x, y, yaw, lookahead, wheelbase):
    """Steering angle that drives an arc through the point `lookahead` metres ahead."""
    n = len(path)
    j = i_near
    for _ in range(n):                         # walk forward until far enough away
        if np.hypot(path[j, 0] - x, path[j, 1] - y) >= lookahead:
            break
        j = (j + 1) % n
    dx, dy = path[j, 0] - x, path[j, 1] - y
    # target point in the car's frame (x forward, y left)
    lx = np.cos(yaw) * dx + np.sin(yaw) * dy
    ly = -np.sin(yaw) * dx + np.cos(yaw) * dy
    ld2 = max(lx * lx + ly * ly, 1e-6)
    return float(np.arctan(2.0 * wheelbase * ly / ld2)), j
