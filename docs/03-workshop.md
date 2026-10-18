# 3. ROS 2 primer

If ROS 2 is new to you, start here. If you sat through the workshop, skip to
[chapter 4](04-algorithms.md).

You need surprisingly little ROS to win this. A node, a subscriber, a
publisher, and parameters — that is the whole surface area of a competitive
entry.

---

## 3.1 The five ideas

**Node** — one process doing one job. Your driver is a node. The simulator is a
node. The referee is a node.

**Topic** — a named channel carrying one message type. `/scan` carries LiDAR;
`/drive` carries steering and speed. Publishers and subscribers find each other
automatically; neither knows the other exists.

**Message** — a typed struct. `sensor_msgs/LaserScan` has `ranges`,
`angle_min`, `angle_increment`. Inspect any type with
`ros2 interface show <type>`.

**Parameter** — a named value you can set at launch without editing code. This
is how you tune without rebuilding, and it is worth using from day one.

**Workspace** — a folder of packages that `colcon build` compiles and
`source install/local_setup.bash` puts on your path. Yours is
`/hackathon/race_ws`.

---

## 3.2 The whole pattern

```python
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from ackermann_msgs.msg import AckermannDriveStamped


class Driver(Node):
    def __init__(self):
        super().__init__('driver')
        self.declare_parameter('speed', 2.0)
        self.speed = self.get_parameter('speed').value

        self.pub = self.create_publisher(AckermannDriveStamped, '/drive', 10)
        self.create_subscription(LaserScan, '/scan', self.scan_callback, 10)

    def scan_callback(self, scan):
        msg = AckermannDriveStamped()
        msg.drive.speed = self.speed
        msg.drive.steering_angle = 0.0
        self.pub.publish(msg)


def main():
    rclpy.init()
    rclpy.spin(Driver())
```

Everything else is the driving algorithm.

---

## 3.3 Commands worth knowing

```sh
ros2 topic list                       # what exists
ros2 topic echo /drive                # watch messages go by
ros2 topic hz /scan                   # publishing rate — is anything alive?
ros2 topic info /scan --verbose       # who publishes and subscribes
ros2 interface show sensor_msgs/msg/LaserScan
ros2 node list
ros2 param list /driver
ros2 param set /driver speed 3.0      # retune a running node
ros2 run <package> <executable>
ros2 launch <package> <file.launch.py>
```

When something does not work, `ros2 topic hz` is almost always the fastest way
to find out which link in the chain is dead.

---

## 3.4 Building

```sh
cd /hackathon/race_ws
colcon build --symlink-install
source install/local_setup.bash
```

`--symlink-install` makes Python edits take effect immediately. You only need
to rebuild after adding a new file or editing `setup.py`.

Build one package only:

```sh
colcon build --symlink-install --packages-select team_driver
```

---

## 3.5 Workshop material

The full workshop content is in [`workshop/`](../workshop/):

| | |
| --- | --- |
| [`workshop/slides/`](../workshop/slides/) | ROS 2 theory and practical slides, Docker, reactive navigation |
| [`workshop/ros2_ws/`](../workshop/ros2_ws/) | Teaching packages: publishers, subscribers, services, actions, custom messages, bag recording |
| [`workshop/ros2_ws/README.md`](../workshop/ros2_ws/README.md) | Walkthrough for those packages |

The workshop workspace is separate from `race_ws` on purpose — it is reference
material, and it is not built during evaluation.

---

## 3.6 Further reading

- [ROS 2 Jazzy tutorials](https://docs.ros.org/en/jazzy/Tutorials.html) — the
  official ones are good; the beginner CLI and client library sections are
  enough.
- [RoboRacer (F1TENTH) course materials](https://f1tenth-coursekit.readthedocs.io/) —
  lectures on reactive methods, pure pursuit and planning, from the people who
  built this simulator.
- [f1tenth_gym](https://github.com/f1tenth/f1tenth_gym) — the physics, if you
  want to know exactly what the car will do.

---

Next: **[4. Algorithms to start from](04-algorithms.md)**
