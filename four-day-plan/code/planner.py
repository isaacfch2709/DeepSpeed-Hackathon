"""The driving decision, kept free of ROS so the tuner can run the exact same code.

    pose + speed --> nearest point on the line --> point `lookahead` ahead --> steering
                                               \\-> speed planned for that point --> speed
    LiDAR beams straight ahead -----------------------------------------> emergency speed cap
"""

import math

import numpy as np

from team_driver import racing

WHEELBASE = 0.33        # [m]   docs §2.8
MAX_STEER = 0.4189      # [rad] docs §2.8


class Planner:

    def __init__(self, path, v_max, a_lat, a_accel, a_brake,
                 lookahead_min, lookahead_gain, safety_margin):
        self.path = path
        self.v_profile = racing.speed_profile(path, v_max, a_lat, a_accel, a_brake)
        self.L0, self.KL = lookahead_min, lookahead_gain
        self.a_brake, self.margin = a_brake, safety_margin
        self.hint = None          # index of the last nearest point, so the search stays local
        self.oriented = False

    def orient(self, x, y, yaw):
        """Make sure the line runs the way the car is facing (the racing direction)."""
        i = racing.nearest_index(self.path, x, y)
        tangent = self.path[(i + 5) % len(self.path)] - self.path[i]
        if tangent[0] * math.cos(yaw) + tangent[1] * math.sin(yaw) < 0:
            self.path = self.path[::-1].copy()
            self.v_profile = self.v_profile[::-1].copy()
        self.oriented = True

    def step(self, x, y, yaw, speed, ranges=None, angles=None):
        """Return (steering [rad], speed [m/s]) for the car at (x, y, yaw) going `speed`."""
        if not self.oriented:
            self.orient(x, y, yaw)
        self.hint = racing.nearest_index(self.path, x, y, self.hint)
        lookahead = self.L0 + self.KL * speed
        steer, _ = racing.pure_pursuit(self.path, self.hint, x, y, yaw, lookahead, WHEELBASE)
        steer = float(np.clip(steer, -MAX_STEER, MAX_STEER))
        target = float(self.v_profile[self.hint])

        # Emergency cap: never faster than we can stop in the free space straight ahead.
        if ranges is not None:
            ahead = ranges[np.abs(angles) < math.radians(10)]
            if ahead.size:
                free = max(float(ahead.min()) - self.margin, 0.0)
                target = min(target, max(math.sqrt(2.0 * self.a_brake * free), 1.0))
        return steer, target
