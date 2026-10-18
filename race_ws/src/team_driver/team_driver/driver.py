#!/usr/bin/env python3
"""YOUR DRIVER GOES HERE.

This is the node the judges run. Keep `driver` as the executable name and
`/drive` as the output topic and everything else is yours to change - rewrite
this file completely if you want to.

--------------------------------------------------------------------------
THIS TEMPLATE DOES NOT DRIVE
--------------------------------------------------------------------------
It is wiring, not a driver. It connects to the simulator, subscribes to the
sensors, and then asks for a slow constant speed with the wheels straight. It
will set off from the grid and into the first thing in front of it. That is
deliberate and it is the whole point: **there is no algorithm here and no
algorithm is shipped anywhere else in this repository.** Writing one is the
hackathon.

What the template is good for is proving your setup works. If the car moves
when you run it, then the image, the bridge, the workspace, the topics and
your commands are all correct, and every problem left is yours.

    ros2 run team_driver driver
    ros2 launch team_driver driver.launch.py

`docs/04-algorithms.md` lists the approaches worth starting from - reactive
ones that need nothing but the LiDAR, planners that follow a line, model-based
control, and learned policies - with what each needs and where each breaks.
Pick one and replace `plan()` below.

What you are allowed to read (see docs/06-rules.md):
    /scan               LiDAR, 819 beams over 270 degrees
    /ego_racecar/odom   ground-truth pose and velocity - ALLOWED and RECOMMENDED
    TF, /map            the static map
What you publish:
    /drive              AckermannDriveStamped - you ask for a SPEED, and the
                        simulator closes that loop for you
    /driver/...         anything of your own, for visualisation
"""

"""RL driver: LiDAR + ground-truth odometry -> MLP policy -> /drive.

Inference needs only numpy. Never publishes to /initialpose (forbidden in a scored run).
Launch:  ros2 run team_driver driver
Params:  --ros-args -p v_max:=6.0 -p policy_path:=/path/policy.npz
"""
import math
import os
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry
from ackermann_msgs.msg import AckermannDriveStamped

from team_driver import rl_common as C

HERE = os.path.dirname(os.path.abspath(__file__))
FALLBACK_DIR = "/hackathon/race_ws/src/team_driver/team_driver"   # repo is mounted at /hackathon


def _find(name):
    for d in (HERE, FALLBACK_DIR):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return os.path.join(HERE, name)


class Driver(Node):
    def __init__(self):
        super().__init__("driver")
        self.declare_parameter("policy_path", _find("policy.npz"))
        self.declare_parameter("centerline_csv", "/hackathon/maps/icra26_centerline.csv")
        self.declare_parameter("v_max", 6.0)

        self.v_max = float(self.get_parameter("v_max").value)
        self.path = C.CenterlinePath(self.get_parameter("centerline_csv").value)
        self.policy = None
        try:
            self.policy = C.NumpyPolicy(self.get_parameter("policy_path").value)
            self.get_logger().info("policy loaded")
        except Exception as e:                       # missing weights -> stand still, loudly
            self.get_logger().error(f"NO POLICY ({e}); car will not move")

        self.have_odom = False
        self.x = self.y = self.yaw = self.speed = 0.0
        self.prev_delta = 0.0
        self.idx = None

        self.create_subscription(Odometry, "/ego_racecar/odom", self.on_odom, qos_profile_sensor_data)
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        self.pub = self.create_publisher(AckermannDriveStamped, "/drive", 10)

    def on_odom(self, m):
        p, q = m.pose.pose.position, m.pose.pose.orientation
        self.x, self.y = p.x, p.y
        self.yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        self.speed = math.hypot(m.twist.twist.linear.x, m.twist.twist.linear.y)
        self.have_odom = True

    def on_scan(self, scan):
        if not self.have_odom:
            return
        # centreline index: local search, global re-search if the car was teleported
        idx = self.path.project(self.x, self.y, self.idx) if self.idx is not None else self.path.project(self.x, self.y)
        if self.path.dist_to(self.x, self.y, idx) > 2.0:
            idx = self.path.project(self.x, self.y)
            self.prev_delta = 0.0
        self.idx = idx

        if self.policy is None:
            delta, v = 0.0, 0.0
        else:
            lat, herr, look = self.path.state(self.x, self.y, self.yaw, idx)
            obs = C.build_obs(scan.ranges, self.speed, self.prev_delta, lat, herr, look)
            delta, v = C.act_to_command(self.policy(obs), self.speed, self.prev_delta, self.v_max)
            self.prev_delta = delta

        msg = AckermannDriveStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.drive.steering_angle = float(delta)
        msg.drive.speed = float(v)
        self.pub.publish(msg)


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


if __name__ == "__main__":
    main()
