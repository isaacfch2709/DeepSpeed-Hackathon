# Track 1 — 4-day plan (15 → 18 Oct 2026, deadline 23:59 SGT)

**Strategy:** skip the 6-week learning path. Use the method the official guide
rates *"a day to build, high ceiling"*: **pure pursuit on the shipped
centreline + a speed profile**, with a LiDAR emergency brake. Learn each
concept *only* when the step needs it.

**What you get scored on:** 50% best lap + 50% 10-lap total. Each crash adds
+10 s, and more than 10 crashes means disqualification. Scraping a wall counts
again every second. **Finishing beats speed.**

> ⚠️ **Do this first.** Your fork (`isaacfch2709/DeepSpeed-Hackathon`) only has
> the `main` branch, which holds the docs site. The hackathon code lives on the
> official **`track1`** branch, so you must submit from a copy of `track1`
> (Day 1, Step 2).

---

## Day 1 (Thu 15 Oct): get the simulator running

**Learn (about 1 h, only if new to you):** basic terminal (`cd`, `ls`, `pwd`) and
the Git basics `clone / add / commit / push`.

| # | Do | Done when |
|---|---|---|
| 1 | Install Docker. **Windows:** WSL 2 + Ubuntu + Docker Desktop with WSL integration on, then run everything below *inside the Ubuntu terminal*. **macOS:** Docker Desktop. **Linux:** Docker Engine. | `docker run hello-world` works |
| 2 | Get the `track1` code into your own repo (below) | `git branch` shows `track1` |
| 3 | Build the image: `./install/linux/setup.sh` (or `install/macos`, `install/windows`). **Takes 15–30 min**, so start it early. | finishes without error |
| 4 | Start the container: `./install/linux/run.sh` | prompt inside `/hackathon` |
| 5 | Build the workspace (below) | no red errors |
| 6 | Run the sim + template driver (below) | car drives straight into a wall ✅ (that's expected) |

```sh
# Step 2: clone the OFFICIAL repo with the track1 branch and submodules (never a ZIP)
git clone --branch track1 --recurse-submodules \
  https://github.com/NTUDeepSpeed/Recruitment_Hackathon_2627.git
cd Recruitment_Hackathon_2627
# point it at YOUR GitHub repo so you can push your entry there
git remote rename origin upstream
git remote add origin https://github.com/isaacfch2709/DeepSpeed-Hackathon.git
git push -u origin track1
```

```sh
# Step 5, inside the container
cd /hackathon/race_ws
colcon build --symlink-install
source install/local_setup.bash

# Step 6, terminal 1 (inside container)
ros2 launch roboracer_referee simulator.launch.py
# Step 6, terminal 2: open a 2nd container shell (run ./install/linux/run.sh again)
cd /hackathon/race_ws && source install/local_setup.bash
ros2 run team_driver driver
```

**Learn tonight (about 1.5 h):** ROS 2 = programs (*nodes*) talking over named
channels (*topics*). Your driver **reads** `/scan` (LiDAR) and
`/ego_racecar/odom` (exact position) and **writes** `/drive` (speed + steering).
That's all the ROS you need. Try `ros2 topic list` and
`ros2 topic echo /ego_racecar/odom --once` while the sim runs.
Optional reading: guide chapter 3 (ROS 2 primer).

If you get stuck: guide §1.7 Troubleshooting → team channel → `ntu-deepspeed@e.ntu.edu.sg`.

---

## Day 2 (Fri 16 Oct): a driver that finishes 10 laps

**Learn (about 1 h):** two ideas.
1. **Pure pursuit:** pick a point on the line ~1 m ahead and steer along the
   arc that reaches it: `steer = atan(2 · wheelbase · y_left / distance²)`.
2. **Speed profile:** tight corner means slow, `v = sqrt(a_lat / curvature)`.
   Then a backwards pass makes the car brake *before* the corner, not in it.

| # | Do | Done when |
|---|---|---|
| 1 | Copy [`code/racing.py`](code/racing.py) → `race_ws/src/team_driver/team_driver/racing.py` | file exists |
| 2 | Replace `race_ws/src/team_driver/team_driver/driver.py` with [`code/driver.py`](code/driver.py) | |
| 3 | Rebuild once (new file): `colcon build --symlink-install && source install/local_setup.bash` | |
| 4 | Run sim + `ros2 run team_driver driver`. Watch a lap. | log says `Loaded ... points` and car follows the track |
| 5 | Score it: `./scripts/evaluate.sh --team <team> --laps 3 --headless` | `COMPLETE`, 0 collisions |
| 6 | Full race: `./scripts/evaluate.sh --team <team> --headless` | `COMPLETE` |
| 7 | **Commit + push** this working version. It's your safety net. | pushed |

```sh
git add race_ws/src/team_driver
git commit -m "Pure pursuit on centreline with speed profile"
git push
```

How the code works (you must be able to explain this at the interview):

```
odom → nearest point on centreline → point `lookahead` ahead → pure-pursuit steering
                                   → v_profile[that point]  → speed
LiDAR beams within ±10° ahead → cap speed to what can stop before the obstacle
```

The driver loads `maps/icra26_centerline.csv` (shipped, allowed), resamples it
every 10 cm, smooths it, and computes the speed for every point once at
start-up. No new packages are needed (numpy only), so there's nothing to
declare in `requirements.txt`.

**Offline sanity check I ran** (simple kinematic car on the real map, not the
real simulator): it completes laps at every setting with ≥0.28 m centre-to-wall
clearance. Lap times: about 25.6 s at `v_max=4, a_lat=3` (the shipped defaults)
and about 18 s at `v_max=8, a_lat=6`. The real sim models tyre slip, so expect
to be a little slower and to find the grip limit earlier.

---

## Day 3 (Sat 17 Oct): make it fast, without crashing

Tune with command-line parameters. No rebuild is needed:

```sh
ros2 run team_driver driver --ros-args -p v_max:=5.0 -p a_lat:=4.0
```

For a scored run with parameters, put them in `config/driver_params.yaml` and run
`ros2 launch roboracer_referee evaluate.launch.py team:=<team> driver_params:=/hackathon/race_ws/src/team_driver/config/driver_params.yaml`,
or simply edit the defaults in `driver.py`.

**Raise one knob at a time** and keep a log:

| Run | v_max | a_lat | a_brake | lookahead_min | Best lap | 10-lap | Collisions |
|---|---|---|---|---|---|---|---|
| 1 | 4 | 3 | 4 | 0.6 | | | |
| 2 | 5 | 3.5 | 4.5 | 0.6 | | | |
| 3 | 6 | 4 | 5 | 0.6 | | | |

Rules of thumb:
- **Crash in a corner** → lower `a_lat` (slower corners) or lower `a_brake` (starts braking earlier).
- **Car zig-zags / wobbles** → raise `lookahead_min` (0.6 → 0.8).
- **Car cuts corners and clips the inside** → lower `lookahead_min` or `lookahead_gain`.
- **Slow in the hairpin even though the line is clear** → the LiDAR brake is
  triggering; lower `safety_margin` (0.5 → 0.3).
- Stop raising things the moment you see **one** collision, then go back one
  step. Pick the fastest setting that gives **3/3 clean runs**.

⚠️ **Final step of Day 3:** write your chosen numbers into the
`declare_parameter(...)` **defaults in `driver.py`**. The judges run
`ros2 run team_driver driver` **without** a params file. Commit + push.

**Stretch (only if Day 3 is done by lunch):** build your own racing line. Shift
each centreline point toward the inside of corners (minimum-curvature idea),
re-check clearance against `/map`, and save it via `path_csv`. Generating it
from the map at runtime earns interview bonus marks (rule 41). Hand-typed
waypoints are forbidden (rule 32).

---

## Day 4 (Sun 18 Oct): submit. Finish by ~20:00, not 23:59.

```sh
./scripts/verify_judging_env.sh                     # must say intact
mkdir -p results/submitted
./scripts/evaluate.sh --team <team> --runs 3 --headless
cp results/<team>__*.json results/submitted/        # unedited!
git add results/submitted SUBMISSION.md race_ws/src/team_driver
git commit -m "Submission" && git push
```

| # | Checklist (guide §7.5) |
|---|---|
| ☐ | Only changed `race_ws/src/team_driver/`, `SUBMISSION.md`, `results/submitted/`. **Never touch** `maps/`, `scripts/`, `docker/`, `install/`, `external/`, `.github/`, `roboracer_referee/` |
| ☐ | `package.xml` description/maintainer updated to your team |
| ☐ | `SUBMISSION.md` at repo root: members (3–5), approach, results table, **your machine specs** (CPU, GPU, RAM, OS, real-time factor), "precomputed: none — centreline shipped", deps: none, references (Coulter 1992 pure pursuit), **AI use: say you used ChatGPT/Claude and for what** |
| ☐ | Clean-clone test (guide §7.2) gives `COMPLETE` |
| ☐ | GitHub Actions **Judge** workflow green on your branch |
| ☐ | Pushed + repo URL **and branch name (`track1`)** sent to organisers before 23:59 SGT |

**Interview prep (30 min, any member may be asked anything):** each member
should be able to answer these.
- Why pure pursuit and not follow-the-gap? *(It uses the map and position, so
  it brakes before corners rather than when it first sees them.)*
- What happens if `lookahead_min` doubles? *(Smoother, but cuts corners and can
  clip the inside.)* If it halves? *(Oscillates.)*
- How is speed decided? *(Curvature gives the cornering speed limit; forward and
  backward passes apply the accel and brake limits; the LiDAR cap is a safety net.)*
- What would you do with more time? *(A racing line from the map, then MPC.)*

---

## Team split (3–5 people)

| Person | Day 1 | Day 2 | Day 3 | Day 4 |
|---|---|---|---|---|
| A (Git / setup lead) | fork + push `track1` | install code | log results | verify + push |
| B (driver) | sim running | run + debug driver | tune params | interview Q&A |
| C (docs) | read guide ch. 4–7 | explain the code | SUBMISSION.md draft | final SUBMISSION.md |
| D/E | same setup on own laptop | understand pure pursuit | parallel tuning sweeps | clean-clone test |

Everyone must get the simulator running on their own machine on Day 1, so
nobody is blocked.

## Files here

- `code/racing.py`: the maths (no ROS; easy to read and test).
- `code/driver.py`: the ROS node that the judges run.
- `code/offline_sim.py`: the rough offline check I used. Run it as
  `python3 offline_sim.py <folder with racing.py> <track1 repo> 4 3 4`.
  It needs numpy + Pillow and runs outside Docker.
