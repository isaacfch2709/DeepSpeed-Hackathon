#!/usr/bin/env python3
"""ROS 2 wrapper: reads /scan and /ego_racecar/odom, asks the Planner, publishes /drive.

At start-up it builds the line to follow:
  - use_raceline:=true  -> minimum-curvature racing line computed from the map (raceline.py)
  - use_raceline:=false -> the shipped centreline (the Day 2 behaviour)
If building the racing line fails for any reason, it falls back to the centreline.

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

from team_driver import racing, raceline
from team_driver.planner import Planner


def find_map_file(name):
    """/hackathon/maps/<name> in the container; otherwise walk up from this file."""
    default = Path('/hackathon/maps') / name
    if default.exists():
        return str(default)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / 'maps' / name
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(name)


class Driver(Node):

    def __init__(self):
        super().__init__('driver')
        # ---- tuning knobs: values found by tools/tune.py (Optuna TPE, ~60 trials) ----
        self.declare_parameter('use_raceline', True)
        self.declare_parameter('raceline_inflate', 0.40)  # [m] keep the line this far from walls
        self.declare_parameter('v_max', 8.19)          # [m/s] top speed on straights
        self.declare_parameter('a_lat', 7.2)           # [m/s^2] cornering grip used
        self.declare_parameter('a_accel', 9.5)         # [m/s^2]
        self.declare_parameter('a_brake', 6.0)         # [m/s^2]
        self.declare_parameter('lookahead_min', 0.38)  # [m]
        self.declare_parameter('lookahead_gain', 0.29)  # [s] lookahead grows with speed
        self.declare_parameter('safety_margin', 0.24)   # [m] LiDAR emergency brake
        p = lambda name: self.get_parameter(name).value

        centreline_csv = find_map_file('icra26_centerline.csv')
        path = racing.smooth(racing.resample(racing.load_path(centreline_csv)))
        line_name = 'centreline'
        if p('use_raceline'):
            try:
                path = raceline.build(centreline_csv, find_map_file('icra26.yaml'),
                                      inflate=p('raceline_inflate'))
                line_name = 'racing line'
            except Exception as exc:                    # never fail to start because of the line
                self.get_logger().error(f'Racing line failed ({exc}); using the centreline')

        self.planner = Planner(path, p('v_max'), p('a_lat'), p('a_accel'), p('a_brake'),
                               p('lookahead_min'), p('lookahead_gain'), p('safety_margin'))
        self.get_logger().info(
            f'Following the {line_name}: {len(path)} points, '
            f'speed {self.planner.v_profile.min():.1f}-{self.planner.v_profile.max():.1f} m/s')

        self.pose = None          # (x, y, yaw)
        self.speed = 0.0
        self.drive_pub = self.create_publisher(AckermannDriveStamped, '/drive', 10)
        self.create_subscription(LaserScan, '/scan', self.scan_callback, 10)
        self.create_subscription(Odometry, '/ego_racecar/odom', self.odom_callback, 10)

    def odom_callback(self, msg):
        q = msg.pose.pose.orientation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        self.pose = (msg.pose.pose.position.x, msg.pose.pose.position.y, yaw)
        self.speed = math.hypot(msg.twist.twist.linear.x, msg.twist.twist.linear.y)

    def scan_callback(self, scan):
        if self.pose is None:
            return
        ranges = np.nan_to_num(np.asarray(scan.ranges), nan=0.0, posinf=25.0)
        angles = scan.angle_min + np.arange(len(ranges)) * scan.angle_increment
        steer, speed = self.planner.step(*self.pose, self.speed, ranges, angles)

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
