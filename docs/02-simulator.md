# 2. The simulator

The simulator is [f1tenth_gym](https://github.com/f1tenth/f1tenth_gym) behind a
ROS 2 bridge. It models a single-track (bicycle) vehicle with slip, simulates a
819-beam LiDAR by ray-casting against the map, and detects collisions against
the car's actual footprint. The physics runs on JAX.

Both upstream repositories are vendored in `external/` as pinned git
submodules. The bridge publishes collisions and a simulated clock itself, so
nothing here is patched; see [chapter 5](05-evaluation.md) for why both matter
to judging.

> **A note on names.** The competition is now called RoboRacer; it was F1TENTH
> until 2025. The upstream simulator repositories are still published under the
> old name, so `f1tenth_gym` and `f1tenth_gym_ros` appear throughout the code
> and are correct. Anything written by us is `roboracer_*`.

---

## 2.1 Running it

```sh
ros2 launch roboracer_referee simulator.launch.py

# without RViz — noticeably faster
ros2 launch roboracer_referee simulator.launch.py rviz:=false
```

The launch file reads [`maps/tracks.yaml`](../maps/tracks.yaml) and passes the
map path and grid position straight to the bridge, so you never edit the
simulator's own configuration and never rebuild it.

### The circuit

There is one circuit — `icra26`, the official hackathon track — and it is in
this repository.

| | |
| --- | --- |
| Map | [`maps/icra26.pgm`](../maps/icra26.pgm) + [`maps/icra26.yaml`](../maps/icra26.yaml) |
| Size | 17.0 × 18.2 m at 5 cm per pixel |
| Lap | about 78 m down the middle of the track |
| Start/finish | 1.80 m wide straight, the line at `x = +1.32` |
| Grid slot | `(-1.68, -0.01)` facing `+x`, 3 m before the line |
| Direction | Counter-clockwise: east along the bottom straight, north up the right-hand side, west across the top, south down the left |
| Features | Two cone slaloms on the right-hand side, a hairpin complex in the infield, a tight left-hander at the top |

A traced centreline ships in
[`maps/icra26_centerline.csv`](../maps/icra26_centerline.csv) — see §2.7.

---

## 2.2 Topics

```sh
ros2 topic list
ros2 topic info /scan
ros2 interface show ackermann_msgs/msg/AckermannDriveStamped
```

### What you read

| Topic | Type | What it is |
| --- | --- | --- |
| `/scan` | `sensor_msgs/LaserScan` | 819 beams over 270°, range 0.05–25 m |
| `/ego_racecar/odom` | `nav_msgs/Odometry` | **Ground-truth** pose and velocity in the `map` frame |
| `/map` | `nav_msgs/OccupancyGrid` | The static track map |
| `/tf`, `/tf_static` | `tf2_msgs/TFMessage` | `map` → `ego_racecar/base_link` → `ego_racecar/laser` |

### What you write

| Topic | Type | What it does |
| --- | --- | --- |
| `/drive` | `ackermann_msgs/AckermannDriveStamped` | Steering angle (rad) and speed (m/s) |

### What the referee uses

| Topic | Type | Notes |
| --- | --- | --- |
| `/ego_racecar/collision` | `std_msgs/Bool` | True while the car is in contact |
| `/clock` | `rosgraph_msgs/Clock` | Simulated time, the only clock judging trusts |
| `/initialpose` | `geometry_msgs/PoseWithCovarianceStamped` | Teleports the car. **Off limits during a scored run.** |

The bridge also publishes `/ego_racecar/lap_count` and `/ego_racecar/lap_time`.
The referee ignores both: it counts laps against the finish line defined in
`maps/tracks.yaml`, in the racing direction, with its own minimum-lap-time
guard. Those are the numbers the rules describe, so do not use the bridge's
counter to predict your score.

---

## 2.3 The LiDAR scan

```python
angles = scan.angle_min + np.arange(len(scan.ranges)) * scan.angle_increment
```

- `angle_min` is about −2.35 rad (−135°), `angle_max` about +2.35 rad.
- Index 0 is hard right, the middle index is straight ahead, the last is hard
  left. Take the count from `len(scan.ranges)` rather than hard-coding it.
- Positive angles are to the **left**, matching the steering sign convention.
- Beams that hit nothing come back as `inf`. Always clean the array:

```python
ranges = np.nan_to_num(np.asarray(scan.ranges), nan=0.0, posinf=25.0, neginf=0.0)
```

The scanner sits 0.275 m ahead of `base_link`, so a range of 0.3 m in front is
already a scrape, not 0.3 m of clearance.

---

## 2.4 Ground-truth odometry — use it

`/ego_racecar/odom` gives you the car's exact pose and velocity, with no noise
and no drift. **The rules allow this and we recommend it.**

```python
from nav_msgs.msg import Odometry

def odom_callback(self, msg):
    self.x = msg.pose.pose.position.x
    self.y = msg.pose.pose.position.y
    q = msg.pose.pose.orientation
    self.yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                          1.0 - 2.0 * (q.y * q.y + q.z * q.z))
    self.speed = math.hypot(msg.twist.twist.linear.x, msg.twist.twist.linear.y)
```

Why it matters: a purely reactive driver sees only the next few metres, so it
has to slow down for a corner it has not yet reached. Knowing where you are on
the track lets you brake for a corner you already know is coming, and pick up
the throttle before you can see the exit. That is most of the lap time.

Writing your own localisation — a particle filter against `/map`, or scan
matching — is **not required**, and it is genuinely hard. If you do build one
and can explain it properly, it is worth bonus marks at the interview. The easy
way to try: publish your estimate on your own topic and have your driver read
that instead of `/ego_racecar/odom`, so you can switch between the two with a
parameter and compare them.

---

## 2.5 Driving by hand

Useful for feeling out a track or checking a corner.

```sh
# One-off command
ros2 topic pub --once /drive ackermann_msgs/msg/AckermannDriveStamped \
  "{drive: {speed: 2.0, steering_angle: 0.2}}"

# Keyboard teleoperation
ros2 run teleop_twist_keyboard teleop_twist_keyboard

# Watch the odometry (--no-arr hides the covariance matrices)
ros2 topic echo /ego_racecar/odom --no-arr
```

Reset the car to the start line at any time by clicking **2D Pose Estimate** in
RViz, or:

```sh
ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: 0.0, y: 0.0}, orientation: {w: 1.0}}}}"
```

---

## 2.6 RViz

The bundled layout already shows the map, the LiDAR, the car, the referee's
finish line and live status, plus `/driver/markers` for anything your own node
publishes.

To draw your own debug geometry, publish a `visualization_msgs/MarkerArray` on
`/driver/markers` — the template driver shows how. Seeing where your algorithm
thinks it is aiming is by far the fastest way to work out why it just hit a
wall.

To add a topic by hand: **Add → By topic →** pick it → **OK**.

---

## 2.7 The centreline, and making your own line

```sh
# On the host
./scripts/track_tool.py validate      # check the track against the map image
./scripts/track_tool.py centerline    # (re)write maps/icra26_centerline.csv
```

`validate` is worth running if you touch `maps/`. It checks that the grid slot
is in open track, that the finish line spans the corridor wall to wall — a line
that stops short lets a car slip past an end and never complete a lap — and
that a closed lap actually exists through it for a car of real width.

`centerline` traces the cheapest closed lap through the finish line, smooths
it, pushes it back off the walls and writes a CSV of `x, y` points. That file
is the **middle of the track**, which is not the fast way round. A racing line
runs wide into a corner, clips the apex and runs wide again; it is usually
shorter and always faster. Turning the centreline into a racing line is exactly
the work this hackathon is about.

Keep any line you generate here too and load it from your driver by path:

```sh
ros2 run team_driver driver --ros-args \
    -p raceline_csv:=/hackathon/maps/my_line.csv
```

The conventional format carries a speed per point as well as the geometry, in
the `s; x; y; psi; kappa; vx; ax` layout — worth adopting, because a line
without a speed profile leaves most of the lap time on the table
([§4.2](04-algorithms.md#42-planning-against-the-map)).

Track definitions in [`maps/tracks.yaml`](../maps/tracks.yaml) look like this:

```yaml
icra26:
  map_path: /hackathon/maps/icra26          # /hackathon is this repository
  map_image_ext: .pgm
  start_pose: [-1.68, -0.01, 0.0]              # x, y, theta — behind the line
  finish_line: [[1.32, -0.76], [1.32, 0.89]]
  crossing_direction: -1
```

---

## 2.8 Vehicle limits

| Quantity | Value |
| --- | --- |
| Wheelbase | 0.33 m |
| Width | 0.31 m |
| Length | 0.58 m |
| Max steering angle | ±0.4189 rad (±24°) |
| Max steering rate | 3.2 rad/s |
| Max speed | 20 m/s (you will not get near this) |
| Max acceleration | 9.51 m/s² |
| Physics step | 0.01 s (100 Hz) |

The templates all clamp steering to ±0.34 rad, which is a deliberately
conservative default, not the car's limit. You can go to ±0.4189 rad and the
simulator will honour it — but a sharper angle at speed is also how you spin.
Beyond that it is clamped, and a speed the car cannot reach in time will not
arrive any sooner; drive commands are targets for the actuator model, not
teleports.

---

Next: **[3. ROS 2 primer](03-workshop.md)**
