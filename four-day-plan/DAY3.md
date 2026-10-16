# Day 3 (Sat 17 Oct): racing line + ML tuning

**Where you are:** Day 2 driver = pure pursuit on the **centreline** with a speed
profile. Official 10-lap run: **COMPLETE, 0 collisions, best lap 21.747 s,
total 229.889 s**. That stays safe on branch `day2-speed-profile`.

**Today's goal:** follow a **racing line computed from the map**, with settings
**found by machine learning**, and only keep it if `evaluate.sh` says it is
faster with **0 collisions**.

| Version | Line | Settings | Real simulator here (no delay / 100 ms delay) |
|---|---|---|---|
| Day 2 | centreline | hand-picked | 21.0 s / weaves, crashes |
| Day 3 | racing line | hand-picked (Day 2 values) | 19.5 s / crashes |
| Day 3 | racing line | **tuned by `tune.py`** | **TUNED_RESULT** |

---

## Step 1: understand the two new ideas (45 min, read first)

### 1a. Racing line (`raceline.py`)
```
   centreline (blue)                 racing line (red)
   ─────────╮                        ──────────╮
            │  sharp corner                     ╲   wide in, apex, wide out:
            │  = slow                            ╲  gentler curve = faster
```
1. **Corridor:** for every centreline point, look sideways (left and right) and
   measure how far the car may move before it gets within `raceline_inflate`
   (0.40 m) of a wall. Growing the walls by 0.40 m also **seals the gaps between
   cones**, so the line can never go between them (rule 11).
2. **Optimise:** shift every point sideways (inside its corridor) so the loop
   bends as little as possible = **minimum curvature**. Less bending means a
   higher cornering speed `v = sqrt(a_lat / curvature)`.
   Maths: curvature ≈ second difference `P[i-1] - 2P[i] + P[i+1]`, which is
   linear in the shifts, so it is a *bounded least-squares* problem; scipy's
   `lsq_linear` solves it in about 2 seconds at driver start-up.
3. **Speed profile:** same code as Day 2, on the new line.

The line is computed **from the map when the driver starts**, not typed in, which
is exactly what rule 41's bonus asks for ("own racing line generation computed
from the map at runtime"). Result: the lap is 4.6 m shorter (73.2 m vs 77.8 m).

### 1b. ML tuning (`tune.py`, Bayesian optimisation with Optuna TPE)
```
 ┌───────────────┐   settings    ┌─────────────────────────────┐
 │ Optuna (TPE)  │ ────────────▶ │ real f1tenth_gym, no ROS,    │
 │ learns which  │               │ same Planner + racing line   │
 │ settings are  │ ◀──────────── │ 2 laps, no delay AND 100 ms  │
 │ fast and safe │  score        │ delay                        │
 └───────────────┘               └─────────────────────────────┘
 score = worse of the two runs: mean lap time + 15 s per collision (+100 s if it doesn't finish)
```
- **Why "worse of the two"?** Your laptop delays commands (the weaving); the
  judges' machine doesn't. Settings must survive both.
- **Why it is ML:** TPE builds a probability model of "good" vs "bad"
  settings from every trial so far and samples the next trial where good ones
  are likely. It is the standard hyper-parameter optimiser in ML.
- **Interview line:** "We didn't guess the numbers; we ran N simulated races
  and let Bayesian optimisation find the fastest settings that never crashed,
  including with a 100 ms control delay."

### New file layout
```
race_ws/src/team_driver/
├── team_driver/
│   ├── driver.py     ROS wrapper: reads /scan + /odom, asks the Planner, publishes /drive   (REPLACED)
│   ├── planner.py    the driving decision (pure pursuit + speed + LiDAR cap), no ROS          (NEW)
│   ├── racing.py     maths: resample, curvature, speed profile, pure pursuit                  (same)
│   └── raceline.py   minimum-curvature racing line from the map                               (NEW)
└── tools/
    └── tune.py       Bayesian optimisation of the settings, offline                           (NEW)
```
`planner.py` exists so the **driver and the tuner run identical code**: whatever
the tuner measures is what the judges will see.

No new dependencies for the driver: `scipy`, `PyYAML`, `Pillow`, `numpy` are
already in the image (rule 33). Optuna is only for tuning, on your laptop.

---

## Step 2: start up and make a new branch (10 min)

1. Open **Docker Desktop**, wait for *Engine running*.
2. Green Ubuntu tab:
   ```sh
   cd ~/Recruitment_Hackathon_2627
   git status
   ```
   ✅ `On branch day2-speed-profile` and nothing modified (the `DeepSpeed-Hackathon/` folder is fine to ignore).
3. New branch for today, starting from your working Day 2 code:
   ```sh
   git checkout -b day3-raceline
   ```
   ✅ `Switched to a new branch 'day3-raceline'`.
   Your Day 2 code stays untouched on `day2-speed-profile`.

---

## Step 3: get the files (10 min, green Ubuntu tab)

```sh
git fetch origin
```
```sh
B=origin/claude/loving-hopper-wmpfir:four-day-plan/code
D=race_ws/src/team_driver
git show $B/driver.py   > $D/team_driver/driver.py
git show $B/planner.py  > $D/team_driver/planner.py
git show $B/raceline.py > $D/team_driver/raceline.py
git show $B/racing.py   > $D/team_driver/racing.py
mkdir -p $D/tools
git show $B/tune.py     > $D/tools/tune.py
```
Check:
```sh
ls race_ws/src/team_driver/team_driver/ race_ws/src/team_driver/tools/
git status
```
✅ `driver.py` modified, `planner.py`, `raceline.py` and `tools/` new.

Open them in VS Code and read along with Step 1:
```sh
code race_ws/src/team_driver/
```

---

## Step 4: build and watch one lap (20 min)

**Container tab** (`./install/windows/run.sh`, then):
```sh
cd /hackathon/race_ws
colcon build --symlink-install
source install/local_setup.bash
ros2 launch roboracer_referee simulator.launch.py
```
(`colcon build` is needed once: there are new files.)

**Second container tab** (`./install/windows/shell.sh`, then):
```sh
cd /hackathon/race_ws && source install/local_setup.bash
ros2 run team_driver driver
```
✅ The driver prints `Following the racing line: ... points, speed ...-... m/s`
and the car takes wider, smoother lines than yesterday.

| You see | Do |
|---|---|
| `Following the centreline` + `Racing line failed (...)` | Send me the error text |
| `ModuleNotFoundError: planner` / `raceline` | You skipped `colcon build`; run it and `source` again |
| Hits a wall | Note `hit something at (x, y)`, carry on to Step 5 anyway; the referee decides |

Stop: driver `Ctrl+C`, then simulator `Ctrl+C`.

---

## Step 5: score it officially (30 min)

Container tab (manual sim stopped):
```sh
cd /hackathon
./scripts/evaluate.sh --team ntu_isaac --laps 3 --headless
```
If `COMPLETE` with 0 collisions, the full race:
```sh
./scripts/evaluate.sh --team ntu_isaac --headless
```
Fill in your log:

| Run | Version | Best lap | 10-lap total | Collisions | Status |
|---|---|---|---|---|---|
| Day 2 | centreline | 21.747 | 229.889 | 0 | COMPLETE |
| Day 3 | racing line, tuned | | | | |

---

## Step 6: decide (5 min)

| Result | Decision |
|---|---|
| ✅ COMPLETE, 0 collisions, faster than 21.747 / 229.889 | Keep it: Step 8 |
| ⚠️ 1–2 collisions | Safer racing line: in `driver.py` raise `raceline_inflate` by 0.05 (e.g. 0.45) and lower `a_lat` by 0.5, re-run Step 5 |
| ❌ Not COMPLETE / many collisions | Test the centreline with the new code: `ros2 run team_driver driver --ros-args -p use_raceline:=false`. If that is worse than Day 2 too, go back: `git checkout day2-speed-profile` |

Rule: **a collision costs +10 s, more than the racing line saves.** Never keep a version that hits walls.

---

## Step 7 (optional, 1-2 h): run the ML tuner yourself

I already ran it (Step 1 table, settings now the defaults in `driver.py`), so
this is for understanding, or for re-tuning after a change.

Container tab:
```sh
pip install --break-system-packages optuna
cd /hackathon/race_ws/src/team_driver/tools
python3 tune.py --trials 40
```
- Each line is one trial: its settings, its score and its lap times / hits
  with 0 ms and 100 ms delay.
- At the end it prints `Paste into driver.py:` with the best settings. Copy
  them into the `declare_parameter(...)` lines in `driver.py`, then Step 5.
- `optuna` is lost when the container restarts; that is fine, it is a
  tuning tool, not part of the driver. Do **not** add it to `requirements.txt`.
- Delete `tune.db` if you used `--storage`; never commit it.

---

## Step 8: save to GitHub (5 min, green Ubuntu tab)

```sh
cd ~/Recruitment_Hackathon_2627
git add race_ws/src/team_driver/team_driver/driver.py \
        race_ws/src/team_driver/team_driver/planner.py \
        race_ws/src/team_driver/team_driver/raceline.py \
        race_ws/src/team_driver/team_driver/racing.py \
        race_ws/src/team_driver/tools/tune.py
git commit -m "Minimum-curvature racing line from the map + Optuna-tuned settings"
git push -u origin day3-raceline
```
✅ `day3-raceline -> day3-raceline`. Check the **Actions** tab: the Judge workflow should go green.

---

## Step 9 (evening): get ready for Day 4

1. Each teammate explains, in 2 minutes each: pure pursuit, speed profile,
   racing line (corridor + least squares), ML tuning (TPE, worst-of-two score).
2. Start `SUBMISSION.md` (template in guide §7.3). I'll draft it from what we
   built; you fill in names, matric numbers and your laptop's specs (CPU, GPU,
   RAM, the `real_time_factor` from your result files).
3. Send me your Step 5 table.

## Day 3 checklist
- [ ] On branch `day3-raceline`, Day 2 safe on `day2-speed-profile`
- [ ] New files in place, `colcon build` OK
- [ ] Driver prints "Following the racing line"
- [ ] `evaluate.sh --laps 3`: COMPLETE, 0 collisions
- [ ] Full 10 laps: COMPLETE, 0 collisions, faster than Day 2
- [ ] Pushed; Judge workflow green
- [ ] Every member can explain the racing line and the tuning
