"""Shared by the training environment and the deployed driver.

Keeping observation building and action->command mapping in ONE place is what
guarantees the policy sees the same inputs at judging time as in training.
"""
import math
import numpy as np

# ---------------------------------------------------------------- vehicle (from docs)
WHEELBASE = 0.33          # m
MAX_STEER = 0.4189        # rad, hardware limit
SCAN_DT = 0.025           # s, scans arrive at ~40 Hz

# ---------------------------------------------------------------- observation layout
N_BEAMS = 36              # LiDAR min-pooled into 36 bins over 270 deg
RANGE_CLIP = 10.0         # m, anything further is "open"
LOOKAHEADS = (1.0, 2.0, 3.5, 5.0)   # m along centreline
OBS_DIM = N_BEAMS + 4 + len(LOOKAHEADS)   # = 44
OBS_V_SCALE = 10.0        # speed normaliser (m/s)

# ---------------------------------------------------------------- steering function
STEER_LIMIT = 0.40        # rad, command clamp (hardware is 0.4189)
STEER_RATE = 2.5          # rad/s, slew limit (hardware is 3.2)

# ---------------------------------------------------------------- throttle / brake function
THROTTLE_LEAD = 3.0       # m/s above current speed at full throttle (a = +1)
BRAKE_LEAD = 5.0          # m/s below current speed at full brake    (a = -1)
V_MIN = 1.0               # m/s floor: never stall (15 s no-move = DNF)
A_LAT = 6.0               # m/s^2 lateral-acceleration cap for the speed limiter


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def steering_fn(a_steer, prev_delta, dt=SCAN_DT):
    """a_steer in [-1,1] -> steering angle (rad), clamped and slew-rate limited."""
    target = float(np.clip(a_steer, -1.0, 1.0)) * STEER_LIMIT
    max_step = STEER_RATE * dt
    return prev_delta + float(np.clip(target - prev_delta, -max_step, max_step))


def speed_cap_from_steer(delta, v_max):
    """Highest speed whose lateral accel v^2*kappa stays under A_LAT (kappa=tan(delta)/L)."""
    kappa = abs(math.tan(delta)) / WHEELBASE
    return min(v_max, math.sqrt(A_LAT / max(kappa, 1e-3)))


def throttle_brake_fn(a_tb, speed, v_cap):
    """a_tb in [-1,1]: >0 throttle, <0 brake -> speed target for /drive.

    The sim treats speed as a target for its actuator model, so throttle and
    brake become "how far above / below the current speed do I ask for".
    Braking has more authority than throttle. v_cap acts as a safety layer:
    if it is below the current speed the car is told to slow down regardless.
    """
    a_tb = float(np.clip(a_tb, -1.0, 1.0))
    lead = THROTTLE_LEAD if a_tb >= 0.0 else BRAKE_LEAD
    v_cmd = speed + a_tb * lead
    return float(np.clip(v_cmd, V_MIN, max(V_MIN, v_cap)))


def act_to_command(action, speed, prev_delta, v_max):
    """Policy action [steer, throttle/brake] -> (steering_angle, speed) for /drive."""
    delta = steering_fn(action[0], prev_delta)
    v_cap = speed_cap_from_steer(delta, v_max)
    v_cmd = throttle_brake_fn(action[1], speed, v_cap)
    return delta, v_cmd


# ---------------------------------------------------------------- centreline
def _load_xy(path):
    for delim in (",", ";", None):
        for skip in (0, 1):
            try:
                a = np.loadtxt(path, delimiter=delim, skiprows=skip, ndmin=2)
                if a.shape[1] >= 2 and a.shape[0] > 10:
                    return a[:, :2]
            except ValueError:
                continue
    raise ValueError(f"cannot parse centreline csv: {path}")


class CenterlinePath:
    """Closed centreline resampled to uniform spacing. Index i <-> arc length i*spacing."""

    def __init__(self, csv_path, spacing=0.1):
        pts = _load_xy(csv_path)
        if np.hypot(*(pts[0] - pts[-1])) < 1e-6:
            pts = pts[:-1]
        closed = np.vstack([pts, pts[:1]])
        seg = np.hypot(*np.diff(closed, axis=0).T)
        s = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(s[-1])
        self.n = int(self.length / spacing)
        ss = np.linspace(0.0, self.length, self.n, endpoint=False)
        self.x = np.interp(ss, s, closed[:, 0])
        self.y = np.interp(ss, s, closed[:, 1])
        self.spacing = self.length / self.n
        dx = np.roll(self.x, -1) - np.roll(self.x, 1)
        dy = np.roll(self.y, -1) - np.roll(self.y, 1)
        self.heading = np.arctan2(dy, dx)

    def project(self, x, y, hint=None, window=60):
        """Nearest centreline index. Local search around hint, global if no hint."""
        if hint is None:
            return int(np.argmin((self.x - x) ** 2 + (self.y - y) ** 2))
        idx = (hint + np.arange(-window, window + 1)) % self.n
        d = (self.x[idx] - x) ** 2 + (self.y[idx] - y) ** 2
        return int(idx[np.argmin(d)])

    def dist_to(self, x, y, idx):
        return math.hypot(self.x[idx] - x, self.y[idx] - y)

    def state(self, x, y, yaw, idx):
        """(signed lateral offset [left +], heading error, [lookahead heading errors])."""
        h = self.heading[idx]
        lat = -(x - self.x[idx]) * math.sin(h) + (y - self.y[idx]) * math.cos(h)
        herr = float(wrap(h - yaw))
        look = [float(wrap(self.heading[(idx + int(d / self.spacing)) % self.n] - yaw))
                for d in LOOKAHEADS]
        return lat, herr, look


# ---------------------------------------------------------------- observation
def lidar_bins(ranges):
    r = np.nan_to_num(np.asarray(ranges, dtype=np.float32),
                      nan=0.0, posinf=RANGE_CLIP, neginf=0.0)
    r = np.clip(r, 0.0, RANGE_CLIP)
    edges = np.linspace(0, len(r), N_BEAMS + 1).astype(int)[:-1]
    return np.minimum.reduceat(r, edges) / RANGE_CLIP          # [0,1], idx0 = hard right


def build_obs(ranges, speed, prev_delta, lat, herr, look):
    extra = np.array([speed / OBS_V_SCALE,
                      prev_delta / MAX_STEER,
                      np.clip(lat / 1.5, -1.0, 1.0),
                      herr / np.pi], dtype=np.float32)
    return np.concatenate([lidar_bins(ranges), extra,
                           np.asarray(look, dtype=np.float32) / np.pi]).astype(np.float32)


# ---------------------------------------------------------------- inference-only policy
class NumpyPolicy:
    """44 -> 64 -> 64 -> 2 tanh MLP, weights loaded from policy.npz (no torch needed)."""

    def __init__(self, npz_path):
        d = np.load(npz_path)
        self.W = [d["W0"], d["W1"], d["W2"]]
        self.b = [d["b0"], d["b1"], d["b2"]]
        assert self.W[0].shape[1] == OBS_DIM, "policy.npz does not match OBS_DIM"

    def __call__(self, obs):
        h = np.tanh(self.W[0] @ obs + self.b[0])
        h = np.tanh(self.W[1] @ h + self.b[1])
        return np.clip(self.W[2] @ h + self.b[2], -1.0, 1.0)

