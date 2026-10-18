# 5. Evaluation

The judging environment is in this repository. The script that scores you on
judging day is the same one you can run right now, against the same referee
with the same settings. There are no surprises on the day — only a track you
have not seen.

---

## 5.1 Score yourself

```sh
# From the host, with the container running
./scripts/evaluate.sh --team your_team_name
```

That builds the workspace, starts the simulator, starts your driver, runs the
full race format and writes a result file to `results/`.

Keep the result files from your final runs. Committing them is part of a
submission — see [§7.1](07-submission.md#71-what-to-submit).

Useful variations:

```sh
# Three runs, keep the best — this is what the judges do
./scripts/evaluate.sh --team your_team --runs 3 --headless

# A short run while you are iterating
./scripts/evaluate.sh --team your_team --laps 3

# Score an alternative executable of your own, side by side with `driver`
./scripts/evaluate.sh --team my_experiment --driver-exec my_other_node
```

`--headless` skips RViz and is much faster. `./scripts/evaluate.sh --help`
lists every option.

The script works from your host (it hops into the container for you) or from
inside the container directly.

---

## 5.2 The race format

| | |
| --- | --- |
| Out lap | From the grid slot to the start/finish line. Not timed. |
| Warm-up lap | One full lap, granted, not scored. |
| Timed laps | 10 consecutive laps. |
| Collision | +10 s added to the lap it happened on. |
| Disqualification | More than 10 collisions in a run. |

Two numbers come out:

- **Best lap** — your fastest single timed lap, including its penalties.
- **10-lap total** — the sum of all ten timed laps, including penalties.

The scoring formula that turns those into leaderboard points is in
[chapter 6](06-rules.md).

A run can also end early:

| Status | Means |
| --- | --- |
| `COMPLETE` | All 10 laps finished. This is the only status that scores. |
| `DISQUALIFIED` | More than 10 collisions. |
| `DNF_TIMEOUT` | Ran out of session time (900 simulated seconds) before 10 laps. |
| `DNF_STUCK` | The car did not move for 15 simulated seconds. |
| `ABORTED` | Interrupted, or the referee never got as far as racing. |

---

## 5.3 Everything is measured in simulated time

**This is the most important thing in this chapter.** Lap times come from the
simulator's own clock, not the wall clock.

The physics runs at 100 Hz on a ROS timer. On a machine that cannot keep up,
that timer fires late and the simulation runs at, say, 0.6× real time. Timed
against a wall clock, an identical car would appear 67% slower on a tired
laptop than on a fast desktop.

So the bridge publishes a simulated clock on `/clock`, and the referee times
against that. The consequences:

- **Your hardware does not affect your score.** An Apple Silicon Mac scores the
  same as a gaming PC.
- **Results are reproducible.** The same submission gives the same number twice.
- **`--headless` does not make you faster** in score terms, only in how long you
  wait.

The result file records `real_time_factor` so you can see how hard your machine
was working. A value below 0.8 means it was struggling; your times are still
valid.

What it does *not* protect you from: a control loop so slow that your node
misses scans. That is your code's problem, and it is a real one — keep the
per-scan work bounded.

---

## 5.4 How collisions are counted

The bridge publishes the simulator's own collision flag on
`/ego_racecar/collision`, so the referee uses ground truth rather than guessing
from "the car seems to have stopped".

The flag is raised on every physics step the car is in contact, about a
hundred times a second, which is too fine-grained to score directly. So a
collision is counted **at most once per second** of simulated time.

The important part: that clock runs from the last *counted* collision, not from
the last contact. **Staying on a barrier keeps costing you.** A car that
scrapes along a wall accrues a fresh collision, and a fresh 10-second penalty,
every second it stays there.

| What happens | Collisions counted |
| --- | --- |
| A clean tap and away | 1 (+10 s) |
| Scraping a wall for 3 seconds | 3 (+30 s) |
| Bouncing off the same wall a second apart | 1 each |
| Ending up wedged against a barrier | 1 per second until the run is disqualified |

That last row matters. At one per second against a limit of 10, a car that gets
stuck on a wall and never recovers is disqualified after about 11 seconds of
contact. It will normally hit that before the 15-second stuck timer fires, so
a car wedged on a barrier is disqualified rather than recorded as DNF; a car
that simply stops in open track is still a DNF.

Collisions during the out lap or the warm-up lap count towards the
disqualification limit but add no time penalty, because there is no scored lap
to add it to.

The interval is `collision_interval_s` in
[`config/referee.yaml`](../race_ws/src/roboracer_referee/config/referee.yaml).

---

## 5.5 Reading a result file

```jsonc
{
  "schema_version": 2,
  "team": "your_team_name",
  "run_id": "20261018T143000Z",
  "track": "icra26",
  "status": "COMPLETE",
  "scored": true,
  "laps_completed": 10,
  "laps_required": 10,
  "collisions": 1,
  "collision_limit": 10,
  "best_lap_time": 21.804,        // what you are scored on
  "best_lap_time_raw": 21.804,    // before penalties
  "best_lap_number": 7,
  "total_time": 238.912,          // what you are scored on
  "total_time_raw": 228.912,      // before penalties
  "total_penalty_s": 10.0,
  "laps": [
    { "number": 1, "raw_time": 23.441, "collisions": 0, "penalty_s": 0.0, "net_time": 23.441 },
    { "number": 2, "raw_time": 22.108, "collisions": 1, "penalty_s": 10.0, "net_time": 32.108 }
  ],
  "environment": { "real_time_factor": 0.94, "wall_duration_s": 262.1 }
}
```

`best_lap_time` and `total_time` are `null` unless `scored` is `true`.

```sh
# Summarise your recent runs
./scripts/leaderboard.py summarise results/

# Full leaderboard across teams
./scripts/leaderboard.py rank results/ --csv leaderboard.csv
```

---

## 5.6 Automated judging on every push

[`.github/workflows/judge.yml`](../.github/workflows/judge.yml) races your
entry on GitHub Actions whenever you push, and writes the result to the
workflow summary. It is the same referee with the same settings, so a green run
means your entry will at least start on judging day.

> **The workflow is for reference only. It never decides your result.**
> Your score comes from the organisers' run on the judging machine
> ([§5.8](#58-judging-day)) — three runs, best attempt, rule 23. A green
> Judge run tells you the entry builds, starts and finishes; the times it
> prints are an indication and nothing more. Nothing it reports is scored,
> and a quick time here wins nothing.

It runs in two stages:

| Stage | What it does |
| --- | --- |
| **Checks** | Referee rule tests, track validation, and `verify_judging_env.sh`. About a minute. |
| **Race** | Builds the image and races, headless. 30 to 90 minutes, mostly the build. |

**Checks failing blocks the race.** That is deliberate: the one most likely to
trip is the judging-environment check, and an entry that modifies it is not
scored (rule 27), so there is no point racing it.

### Entry or template?

Before racing, the workflow asks whether there is anything to score:

```sh
./scripts/detect_submission.sh --explain
```

It compares `race_ws/src/team_driver/` against the recorded template. Edit any
file, or add one, and it reports `submission` and your driver is raced. Leave
it untouched — as on the template repository — and it reports `template`, and
the workflow skips the race and says so. There is nothing to score: the
template does not drive, and racing it would fill the summary with a car
parked against the first wall.

> [!NOTE]
> **Organisers:** the reference is `scripts/template_manifest.sha256`. If you
> change anything under `race_ws/src/team_driver/` — even a comment — re-record
> it with `./scripts/detect_submission.sh --update`, or the template repository
> starts reporting itself as a submission and CI races the stub driver.

### Running it by hand

Use **Actions — Judge — Run workflow** to set the number of laps and runs:

| Input | Default | |
| --- | --- | --- |
| `laps` | 10 | Scored laps per run. Drop it to 3 for a quick check. |
| `runs` | 1 | Runs per driver; the best counts. |

Result JSONs are attached to the run as an artifact, so you can feed them to
`leaderboard.py` locally.

### What it is not

CI runs on a shared two-core runner with no GPU, so the simulator runs well
below real time. That does **not** change your lap times — they are measured in
simulated seconds (§5.3) — but it does mean a run takes a while, and a driver
that only just fits its control loop here may behave differently on the judging
machine. Nothing CI reports is scored: the result that counts is the
organisers' run on the machine in [§5.8](#58-judging-day).

---

## 5.7 Watching a run

With RViz open you get, live:

- the **finish line** in yellow, exactly as the referee sees it;
- a **status line** above it: laps done, collisions, best lap so far;
- `/driver/markers`, for whatever your own node draws.

The referee log prints each lap as it closes, with any penalty applied.

---

## 5.8 Judging day

### The judging machine

Every submission is scored on one machine, so nobody is advantaged by hardware:

| | |
| --- | --- |
| CPU | Intel Core i9-14900HX, 16 cores / 32 threads |
| RAM | 32 GB, of which about 16 GB is visible inside WSL by default |
| GPU | NVIDIA GeForce RTX 5060 Laptop, 8 GB, driver 616.64, compute capability 12.0 |
| OS | Windows 11 with WSL 2 (Ubuntu 24.04, kernel 6.18) |
| Docker | Docker Desktop, WSL 2 backend |

The GPU is attached to the container when one is available — `install/<os>/run.sh`
detects it and merges `docker/docker-compose.gpu.yml`, falling back to CPU-only
if Docker cannot attach it. `--gpu` forces it on, `--no-gpu` off.

**The GPU is usable.** The container is ROS 2 Jazzy on Ubuntu 24.04, so Python
3.12, and CUDA builds of PyTorch, JAX and CuPy all support a compute capability
12.0 card. Declare what you need in `requirements.txt` (rule 33) and it is
installed into the image.

The simulator itself deliberately stays on the CPU (`JAX_PLATFORMS=cpu`): it is
small, and CPU execution keeps a run reproducible. The GPU is there for your
code — a learned policy, a planner, whatever you build.

Two practical notes. The card has 8 GB, shared with the desktop, so a model
needing more will not fit. And your node still has to keep up with a ~40 Hz
control loop; a heavyweight network that misses scans costs more time than it
gains.

Because lap times are measured in simulated seconds, none of this affects
fairness — see §5.3.

For each submission the judges:

1. Check out the entry, verify the judging environment is intact
   (`./scripts/verify_judging_env.sh`), and confirm it builds from clean.
2. Build the image from this repository, which installs whatever the team
   declared in `requirements.txt` and `apt-packages.txt`. That step is the last
   layer in the Dockerfile, so it is quick per submission.
3. Run three scored attempts, headless:
   ```sh
   ./scripts/evaluate.sh --team <team> --runs 3 --headless
   ```
4. Take the **best** of the three. Anything that never completes is a DNF.
5. Feed every team's best run into `leaderboard.py rank`, which produces the
   final ranking.

No internet access during a run — anything a team needs must be declared so
it lands in the image at build time. No manual intervention once a run starts.
Identical referee settings for every team.

A run that fails to build, fails to start, or never publishes a drive command
scores zero for the timing component. Test from a clean clone before you
submit — see [chapter 7](07-submission.md).

---

## 5.9 Verifying your environment

```sh
./scripts/verify_judging_env.sh
```

It hashes every file a scored run depends on — the referee package, the
Dockerfile, the compose files, `maps/`, the evaluation scripts — compares
against a manifest, checks for files added into those directories, and confirms
the submodules are at their pinned commits.

A clean report means your entry will be judged. If it flags something you
changed by accident:

```sh
git checkout -- race_ws/src/roboracer_referee docker maps/tracks.yaml scripts install
git submodule update --init --recursive
```

`race_ws/src/team_driver/` is deliberately not protected. That is yours.

---

Next: **[6. Rules](06-rules.md)**
