#!/usr/bin/env python3
r"""Pure pursuit on the icra26 centreline, with a curvature-based speed profile.

  odom (where am I?) --> nearest point on the line --> look ahead --> steering
                                                  \--> speed for this point --> speed
  LiDAR (what's in front?) ------------------------------> emergency speed cap

The judges run `ros2 run team_driver driver` WITHOUT a params file, so the
defaults below must be the tuned values.
"""

import math
from pathlib import Path

import numpy as np
import rclpy
from ackermann_msgs.msg import AckermannDriveStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

from team_driver import racing

WHEELBASE = 0.33        # [m]   docs §2.8
MAX_STEER = 0.4189      # [rad] docs §2.8


def find_centreline():
    """/hackathon/maps/... in the container; otherwise walk up from this file."""
    default = Path('/hackathon/maps/icra26_centerline.csv')
    if default.exists():
        return str(default)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / 'maps' / 'icra26_centerline.csv'
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError('icra26_centerline.csv not found')


class Driver(Node):

    def __init__(self):
        super().__init__('driver')
        # ---- tuning knobs (Day 3 is spent changing these) -------------
        self.declare_parameter('path_csv', '')
        self.declare_parameter('v_max', 4.0)        # [m/s] top speed on straights
        self.declare_parameter('a_lat', 3.0)        # [m/s^2] cornering grip used
        self.declare_parameter('a_accel', 6.0)      # [m/s^2]
        self.declare_parameter('a_brake', 4.0)      # [m/s^2]
        self.declare_parameter('lookahead_min', 0.6)   # [m]
        self.declare_parameter('lookahead_gain', 0.15)  # [s] lookahead grows with speed
        self.declare_parameter('safety_margin', 0.5)    # [m] LiDAR emergency brake
        p = lambda name: self.get_parameter(name).value

        csv = p('path_csv') or find_centreline()
        self.path = racing.smooth(racing.resample(racing.load_path(csv)))
        self.v_profile = racing.speed_profile(
            self.path, p('v_max'), p('a_lat'), p('a_accel'), p('a_brake'))
        self.L0, self.KL = p('lookahead_min'), p('lookahead_gain')
        self.a_brake, self.margin = p('a_brake'), p('safety_margin')
        self.get_logger().info(
            f'Loaded {csv}: {len(self.path)} points, '
            f'speed {self.v_profile.min():.1f}-{self.v_profile.max():.1f} m/s')

        self.pose = None          # (x, y, yaw)
        self.speed = 0.0
        self.hint = None          # last nearest index, so the search stays local
        self.oriented = False

        self.drive_pub = self.create_publisher(AckermannDriveStamped, '/drive', 10)
        self.create_subscription(LaserScan, '/scan', self.scan_callback, 10)
        self.create_subscription(Odometry, '/ego_racecar/odom', self.odom_callback, 10)

    def odom_callback(self, msg):
        q = msg.pose.pose.orientation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        self.pose = (msg.pose.pose.position.x, msg.pose.pose.position.y, yaw)
        self.speed = math.hypot(msg.twist.twist.linear.x, msg.twist.twist.linear.y)
        if not self.oriented:
            self.orient_path(*self.pose)

    def orient_path(self, x, y, yaw):
        """Make sure the line runs the way the car is facing (racing direction)."""
        i = racing.nearest_index(self.path, x, y)
        tangent = self.path[(i + 5) % len(self.path)] - self.path[i]
        if tangent[0] * math.cos(yaw) + tangent[1] * math.sin(yaw) < 0:
            self.path = self.path[::-1].copy()
            self.v_profile = self.v_profile[::-1].copy()
            self.get_logger().info('Reversed the path to match the racing direction')
        self.oriented = True

    def scan_callback(self, scan):
        if self.pose is None:
            return
        x, y, yaw = self.pose
        self.hint = racing.nearest_index(self.path, x, y, self.hint)
        lookahead = self.L0 + self.KL * self.speed
        steer, _ = racing.pure_pursuit(self.path, self.hint, x, y, yaw, lookahead, WHEELBASE)
        steer = float(np.clip(steer, -MAX_STEER, MAX_STEER))
        speed = float(self.v_profile[self.hint])

        # Emergency cap: never go faster than we can stop in the free space straight ahead.
        ranges = np.nan_to_num(np.asarray(scan.ranges), nan=0.0, posinf=25.0)
        angles = scan.angle_min + np.arange(len(ranges)) * scan.angle_increment
        ahead = ranges[np.abs(angles) < math.radians(10)]
        if ahead.size:
            free = max(float(ahead.min()) - self.margin, 0.0)
            speed = min(speed, max(math.sqrt(2.0 * self.a_brake * free), 1.0))

        msg = AckermannDriveStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.drive.steering_angle = steer
        msg.drive.speed = speed
        self.drive_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = Driver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
