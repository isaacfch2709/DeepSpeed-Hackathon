"""Gymnasium wrapper around the running RoboRacer simulator. TRAINING ONLY.

It resets the car with /initialpose, which is forbidden in a scored run, so the
deployed driver (driver.py) never imports this file.
"""
import math
import time
import numpy as np
import gymnasium as gym
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry
from std_msgs.msg import Bool
from geometry_msgs.msg import PoseWithCovarianceStamped
from ackermann_msgs.msg import AckermannDriveStamped

from team_driver import rl_common as C

# ---- reward weights ----
K_PROGRESS = 10.0       # per metre advanced along the centreline
K_LATERAL = 0.5         # * lateral_offset^2   (keeps off walls / out of cone gaps)
K_SMOOTH = 2.0          # * |change in steering| per step
K_TIME = 0.01           # per step
COLLISION_PENALTY = 30.0
SPIN_PENALTY = 20.0
STUCK_PENALTY = 20.0


class RoboRacerEnv(gym.Env):
    metadata = {}

    def __init__(self, centerline_csv, v_max=3.0, max_steps=1500):
        super().__init__()
        if not rclpy.ok():
            rclpy.init()
        self.node = Node("rl_env")
        self.path = C.CenterlinePath(centerline_csv)
        self.v_max = v_max
        self.max_steps = max_steps

        self.observation_space = gym.spaces.Box(-1.0, 1.0, (C.OBS_DIM,), np.float32)
        self.action_space = gym.spaces.Box(-1.0, 1.0, (2,), np.float32)  # [steer, throttle/brake]

        self.node.create_subscription(LaserScan, "/scan", self._on_scan, qos_profile_sensor_data)
        self.node.create_subscription(Odometry, "/ego_racecar/odom", self._on_odom, qos_profile_sensor_data)
        self.node.create_subscription(Bool, "/ego_racecar/collision", self._on_col, 10)
        self.drive_pub = self.node.create_publisher(AckermannDriveStamped, "/drive", 10)
        self.pose_pub = self.node.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)

        self.ranges = None
        self.scan_seq = 0
        self.x = self.y = self.yaw = self.speed = 0.0
        self.collided = False
        self.prev_delta = 0.0
        self.idx = 0
        self.steps = 0
        self.stuck = 0
        self.progress = 0.0

    def set_v_max(self, v):          # curriculum hook
        self.v_max = v

    # ------------------------------------------------------------ ROS plumbing
    def _on_scan(self, m):
        self.ranges = np.asarray(m.ranges, dtype=np.float32)
        self.scan_seq += 1

    def _on_odom(self, m):
        p, q = m.pose.pose.position, m.pose.pose.orientation
        self.x, self.y = p.x, p.y
        self.yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        self.speed = math.hypot(m.twist.twist.linear.x, m.twist.twist.linear.y)

    def _on_col(self, m):
        self.collided = bool(m.data)

    def _send_drive(self, v, delta):
        msg = AckermannDriveStamped()
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.drive.speed = float(v)
        msg.drive.steering_angle = float(delta)
        self.drive_pub.publish(msg)

    def _wait_scan(self, timeout):
        seq, t0 = self.scan_seq, time.time()
        while self.scan_seq == seq and time.time() - t0 < timeout:
            rclpy.spin_once(self.node, timeout_sec=0.05)
        return self.scan_seq != seq

    def _teleport(self, x, y, yaw):
        m = PoseWithCovarianceStamped()
        m.header.frame_id = "map"
        m.header.stamp = self.node.get_clock().now().to_msg()
        m.pose.pose.position.x, m.pose.pose.position.y = float(x), float(y)
        m.pose.pose.orientation.z = math.sin(yaw / 2)
        m.pose.pose.orientation.w = math.cos(yaw / 2)
        self.pose_pub.publish(m)

    # ------------------------------------------------------------ gym API
    def _obs(self):
        lat, herr, look = self.path.state(self.x, self.y, self.yaw, self.idx)
        return C.build_obs(self.ranges, self.speed, self.prev_delta, lat, herr, look), lat, herr

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._send_drive(0.0, 0.0)
        i = int(self.np_random.integers(self.path.n))
        lat0 = float(self.np_random.uniform(-0.2, 0.2))
        dyaw = float(self.np_random.uniform(-0.15, 0.15))
        h = self.path.heading[i]
        x0 = self.path.x[i] - lat0 * math.sin(h)
        y0 = self.path.y[i] + lat0 * math.cos(h)
        self._teleport(x0, y0, h + dyaw)

        t0 = time.time()                       # wait for the teleport to take effect
        while time.time() - t0 < 3.0:
            self._send_drive(0.0, 0.0)
            self._wait_scan(0.5)
            if math.hypot(self.x - x0, self.y - y0) < 0.3 and self.speed < 0.3:
                break
        self.collided = False
        self.prev_delta = 0.0
        self.steps = self.stuck = 0
        self.progress = 0.0
        self.idx = self.path.project(self.x, self.y)
        if self.ranges is None:
            self._wait_scan(2.0)
        obs, _, _ = self._obs()
        return obs, {}

    def step(self, action):
        old_delta = self.prev_delta
        delta, v_cmd = C.act_to_command(action, self.speed, self.prev_delta, self.v_max)
        self._send_drive(v_cmd, delta)
        self.prev_delta = delta
        self._wait_scan(2.0)

        new_idx = self.path.project(self.x, self.y, self.idx)
        ds = ((new_idx - self.idx + self.path.n // 2) % self.path.n - self.path.n // 2) * self.path.spacing
        self.idx = new_idx
        self.progress += ds
        obs, lat, herr = self._obs()

        reward = (K_PROGRESS * ds - K_LATERAL * lat ** 2
                  - K_SMOOTH * abs(delta - old_delta) - K_TIME)
        terminated = False
        if self.collided:
            reward -= COLLISION_PENALTY
            terminated = True
        elif abs(herr) > 2.0:                  # facing the wrong way / spun out
            reward -= SPIN_PENALTY
            terminated = True
        self.stuck = self.stuck + 1 if self.speed < 0.3 else 0
        if self.stuck > 100:                   # ~2.5 s without moving
            reward -= STUCK_PENALTY
            terminated = True

        self.steps += 1
        truncated = self.steps >= self.max_steps
        return obs, float(reward), terminated, truncated, {"progress_m": self.progress}

    def close(self):
        self._send_drive(0.0, 0.0)
        self.node.destroy_node()
