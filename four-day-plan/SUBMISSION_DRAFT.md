# Team <TEAM NAME>

## Members
| Name | Matric number | Email |
| --- | --- | --- |
| <name> | <matric> | <email> |
| <name> | <matric> | <email> |
| <name> | <matric> | <email> |

## Approach
Our driver follows a **minimum-curvature racing line computed from the map at
start-up**, tracks it with **pure pursuit**, and sets the speed at every point from
a **curvature-based speed profile**; a LiDAR check caps the speed if something is
close straight ahead. The settings were chosen by **Bayesian optimisation** in the
simulator.

1. **Racing line** (`raceline.py`). We resample the shipped centreline and, at
   each point, march sideways along the normal through the occupancy grid to find
   how far the line may move before coming within 0.40 m of an obstacle. Growing
   the obstacles by 0.40 m also seals the 0.25–0.50 m gaps between cones, so the
   line can never pass through a cone row (rule 11). We then choose a lateral shift
   for every point that minimises the summed squared curvature (approximated by
   the second difference of consecutive points), which is a bounded linear
   least-squares problem solved by `scipy.optimize.lsq_linear` in about 2 s. The
   result is 4.6 m shorter than the centreline (73.2 m vs 77.8 m) and bends less.
2. **Speed profile** (`racing.py`). Corner speed limit `v = sqrt(a_lat / |κ|)`,
   capped at `v_max`, then a backward pass enforces the braking limit (so the car
   slows *before* a corner) and a forward pass the acceleration limit.
3. **Tracking** (`planner.py`). Pure pursuit towards the point `0.38 + 0.29·v`
   metres ahead on the line; steering `atan(2·L·y / d²)`, L = 0.33 m. The
   speed-scaled lookahead is what stopped the car weaving at speed.
4. **Safety**. The commanded speed is capped so the car can stop before the
   nearest return within ±10° ahead (minimum 1 m/s, so the car never stalls). If
   the car is more than 1 m from where it last was on the line (e.g. after a
   reset) it re-searches the whole line.
5. **Tuning** (`tools/tune.py`). Optuna's TPE sampler proposed settings
   (v_max, a_lat, a_brake, lookahead, LiDAR margin, line margin); each was driven
   for 2 laps in f1tenth_gym configured exactly like the ROS bridge, once with no
   delay and once with a 100 ms command delay, scored by the worse run
   (mean lap time + 15 s per collision, +100 s for a DNF). About 60 trials; the
   best settings were then checked over 10 laps at 0, 100 and 150 ms delay with
   zero collisions, and refined by hand (a_accel, a_brake, a_lat) with the same
   10-lap check.

**What we tried that did not work.** Wall following and reactive gap-following
were not attempted beyond reading: the guide shows wall following cannot finish
icra26. A pure pursuit with a short fixed lookahead weaved on straights and
crashed when commands arrived ~100 ms late. Pushing the racing line closer to the
walls (0.35 m), raising the braking limit to 6.5 m/s², or removing the LiDAR cap
were all faster in isolation but caused collisions. Looking ahead along the speed
profile to brake earlier made laps slower.

## How it uses the inputs
- **LiDAR**: only the beams within ±10° straight ahead, for the emergency speed cap.
- **Odometry**: ground truth from `/ego_racecar/odom` (pose, heading, speed). We
  did not build our own localisation.
- **Map**: `maps/icra26.yaml` + `.pgm` are read at start-up to compute the
  corridor and the racing line; `maps/icra26_centerline.csv` is the starting
  point for the optimisation.

## Results on our own machine
The runs committed in `results/submitted/`, summarised.

| Best lap | 10-lap total | Collisions | Runs attempted |
| --- | --- | --- | --- |
| <x.xxx> | <xxx.xxx> | 0 | 3 |

### The machine that produced them
| CPU | GPU | RAM | OS | Typical real-time factor |
| --- | --- | --- | --- | --- |
| <CPU> | <GPU> | <RAM> | Windows 11 + WSL 2 (Ubuntu), Docker Desktop | <from the result files> |

In the simulator without ROS we measured 17.25 s best lap / 172.6 s for 10 laps
with no command delay, 17.79 s / 178.4 s with 100 ms and 18.97 s / 190.1 s with
150 ms, all with zero collisions; it fails at 200 ms. A gap between our numbers and
yours is most likely how quickly the driver's commands reach the simulator on each
machine.

## Anything precomputed
Nothing is shipped as data. The racing line and its speed profile are computed
from the map every time the driver starts. The parameter defaults in `driver.py`
come from `tools/tune.py` (Optuna TPE, f1tenth_gym without ROS, ~60 trials of
2 laps × 2 delay conditions, about an hour on a 4-core machine); re-run with
`pip install --break-system-packages optuna && python3 tools/tune.py --trials 60`
inside the container.

## Dependencies we added
None for the driver: it uses `numpy`, `scipy`, `PyYAML` and `Pillow`, which are
already in the image. `optuna` is used only by the offline tuning script and is
not needed to run or judge the driver.

| Package | pip or apt | What we use it for |
| --- | --- | --- |
| none | | |

## Third-party code and references
- R. C. Coulter, *Implementation of the Pure Pursuit Path Tracking Algorithm*, CMU-RI-TR-92-01, 1992.
- A. Heilmeier et al., *Minimum curvature trajectory planning and control for an autonomous race car*, Vehicle System Dynamics, 2019.
- J. Bergstra et al., *Algorithms for Hyper-Parameter Optimization* (TPE), NeurIPS 2011; Optuna (Akiba et al., KDD 2019).
- The F1TENTH course material on pure pursuit and raceline optimisation.
- The hackathon guide, chapters 2, 4 and 5.

## AI assistance
We used Claude (Anthropic) and ChatGPT. ChatGPT helped us understand the
hackathon and make a learning plan. Claude helped us plan the four days, write the
driver code (pure pursuit, speed profile, racing line, tuner), debug problems we
hit (two drivers publishing at once, the car losing its place after a reset,
weaving caused by command delay) and run simulator experiments. Every member has
read the code and can explain how each part works and why.

## Known issues
- **The car does not reach the planned lap.** The speed profile plans about
  15.2 s per lap on the racing line but the car achieves about 17.3–19 s: pure
  pursuit cannot follow the line closely enough at the planned corner speeds, so
  the LiDAR cap has to slow it in some corners. With more time we would replace
  pure pursuit with model predictive control (MPC) to track the line more precisely.
- **Sensitive to command delay.** Above ~150 ms between a scan and the command
  reaching the simulator the car weaves and hits walls.
- **One fixed map.** The line is recomputed from whatever map it is given, but the
  settings were tuned for icra26 only.
