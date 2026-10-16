# Day 4 (Sun 18 Oct): submit. Deadline 23:59 SGT, aim to be done by 20:00

**Where you are:** branch `day3-raceline` = racing line + tuned settings, official
10-lap run **COMPLETE, 0 collisions**. Day 2 is safe on `day2-speed-profile`.

**Today:** no new features. Put the tested code on `track1`, add the paperwork,
check everything, push, tell the organisers.

| # | Step | Time | Where |
|---|---|---|---|
| 1 | Put Day 3 onto `track1` | 10 min | Ubuntu |
| 2 | Update `package.xml` | 5 min | Ubuntu |
| 3 | Record 3 official runs into `results/submitted/` | 30-40 min | Container |
| 4 | Write `SUBMISSION.md` | 45 min | Ubuntu / VS Code |
| 5 | Check the judging environment | 2 min | Ubuntu |
| 6 | Commit and push `track1` | 5 min | Ubuntu |
| 7 | Check GitHub: files + Judge workflow | 5 min (+ 30-90 min waiting) | Browser |
| 8 | Give the organisers access and send the link | 10 min | Browser / email |
| 9 | Interview prep | 1 h | Team |

---

## Step 1: put Day 3 onto `track1` (green Ubuntu tab)

`track1` is the branch you submit. It still has the official empty template,
so bring your work onto it.

```sh
cd ~/Recruitment_Hackathon_2627
git status
```
✅ `On branch day3-raceline`, nothing modified (the old `DeepSpeed-Hackathon/` folder is fine).

```sh
git checkout track1
git pull origin track1
git merge --ff-only day3-raceline
git log --oneline -3
```
✅ The top line is `d9d9eb9 Day 3: racing line from the map + Optuna-tuned settings`
(plus `(HEAD -> track1, day3-raceline)`).

If `--ff-only` refuses, stop and send me the message; don't force anything.

---

## Step 2: update `package.xml` (5 min)

The template asks for your team name and approach here.
```sh
nano race_ws/src/team_driver/package.xml
```
Change only these two lines:
```xml
<description>Team <TEAM NAME>: minimum-curvature racing line from the map, pure pursuit, Optuna-tuned speed profile.</description>
<maintainer email="imcfcheang@gmail.com"><YOUR NAME></maintainer>
```
Save: `Ctrl+O`, `Enter`, `Ctrl+X`. Do **not** rename the package.

---

## Step 3: record 3 official runs (container tab, 30-40 min)

Start the container if needed (`./install/windows/run.sh`), stop any manual
simulator/driver, then:
```sh
cd /hackathon/race_ws && colcon build --symlink-install && source install/local_setup.bash
cd /hackathon
./scripts/evaluate.sh --team <team_name> --runs 3 --headless
```
Use your real team name from now on (the name in `SUBMISSION.md`).

✅ All 3 runs `COMPLETE`, 0 collisions. Then copy **only these 3 new files**:
```sh
mkdir -p results/submitted
ls -t results/<team_name>__*.json | head -3
cp $(ls -t results/<team_name>__*.json | head -3) results/submitted/
ls results/submitted/
```
- Do **not** copy old `ntu_isaac__...` files from Day 2 or earlier today: they came from older code.
- Do **not** edit the JSON files (rule 44).

Note the numbers for `SUBMISSION.md`:
```sh
./scripts/leaderboard.py summarise results/submitted/
grep -h real_time_factor results/submitted/*.json
```

---

## Step 4: write `SUBMISSION.md` (45 min)

I wrote a full draft: `four-day-plan/SUBMISSION_DRAFT.md` on the plan branch.
Copy it to the repo root:
```sh
cd ~/Recruitment_Hackathon_2627
git fetch origin
git show origin/claude/loving-hopper-wmpfir:four-day-plan/SUBMISSION_DRAFT.md > SUBMISSION.md
code SUBMISSION.md
```
Fill in every `<...>`:
- Team name; every member's name, matric number, email (3 to 5 members, rule 1-3).
- Results table: best lap, 10-lap total from Step 3.
- Machine: CPU and RAM (Windows: Settings → System → About), GPU (Task
  Manager → Performance), and the `real_time_factor` from Step 3.

Then **read the whole file**. Every member must agree with every sentence;
change anything that is not true for your team, especially "AI assistance"
and "what we tried".

---

## Step 5: check the judging environment (Ubuntu tab)

```sh
cd ~/Recruitment_Hackathon_2627
./scripts/verify_judging_env.sh
```
✅ It must report the environment intact. If it lists a file, send it to me:
you must not have changed anything in `maps/`, `scripts/`, `docker/`,
`install/`, `external/`, `.github/` or `race_ws/src/roboracer_referee/`.

---

## Step 6: commit and push `track1`

```sh
git status
```
✅ Only `SUBMISSION.md`, `race_ws/src/team_driver/package.xml` and
`results/submitted/...` should be listed (plus the ignorable `DeepSpeed-Hackathon/`).

```sh
git add SUBMISSION.md race_ws/src/team_driver/package.xml results/submitted
git commit -m "Submission: SUBMISSION.md, package.xml, our own judged runs"
git push origin track1
```
✅ `track1 -> track1`. Note the time: it must be before 18 Oct 23:59 SGT.

---

## Step 7: check on GitHub

1. https://github.com/isaacfch2709/DeepSpeed-Hackathon → switch the branch
   dropdown to **track1**. Check `SUBMISSION.md`, `results/submitted/` (3 files),
   `race_ws/src/team_driver/team_driver/raceline.py` are there.
2. **Actions** tab → the **Judge** run for your `track1` push.
   - *Checks* must pass (~1 min).
   - *Race* takes 30-90 min; it should end COMPLETE. Its times don't count.
   - If Actions is disabled for the repo: Settings → Actions → General → allow.
   - If it fails, send me a screenshot of the failed step.

---

## Step 8: access + send the link

Your repository is **Private**, so the organisers can't see it yet. Ask in the
team channel which they prefer, then either:
- **Make it public**: Settings → General → Danger Zone → Change visibility, or
- **Add them**: Settings → Collaborators → Add people (the GitHub usernames
  they give you).

Then send (team channel or `ntu-deepspeed@e.ntu.edu.sg`):
```
Team <TEAM NAME> - Track 1 submission
Repository: https://github.com/isaacfch2709/DeepSpeed-Hackathon
Branch: track1
Members: <names>
```

---

## Step 9: interview prep (whole team, 1 h)

Each member explains each part in ~2 minutes, then swap:

| Part | File | Key points |
|---|---|---|
| Pure pursuit | `planner.py`, `racing.py` | aim at a point ahead; `atan(2·L·y/d²)`; lookahead `0.38 + 0.29·v`; short = weave, long = cut corners |
| Speed profile | `racing.py` | `v = sqrt(a_lat/κ)`; backward pass = brake before corners; forward pass = acceleration limit |
| Racing line | `raceline.py` | corridor from the map, walls grown 0.40 m (seals cone gaps); minimise squared curvature = bounded least squares; 4.6 m shorter |
| ML tuning | `tools/tune.py` | Optuna TPE; each trial = 2 laps at 0 ms and 100 ms delay; score = worse run + 15 s per hit; ~60 trials; verified over 10 laps |
| Safety | `planner.py` | LiDAR cap within ±10°; never below 1 m/s; global re-search after a reset |

Practise these questions (guide §7.4):
- *Why this approach?* We know our position (odometry) and the map, so we can brake before corners and take a shorter line; reactive methods only see the corner when they reach it.
- *What if `a_lat` doubles?* Planned corner speeds rise ~1.4×; pure pursuit can't follow the line, so the LiDAR cap brakes hard and some corners end in collisions.
- *What didn't work?* Fixed short lookahead weaved; line at 0.35 m from walls, `a_brake` 6.5 and no LiDAR cap all crashed; braking earlier was slower.
- *Something learned: how was it trained / validated?* (see ML tuning row).
- *With more time?* MPC: the plan says 15.2 s per lap but we achieve ~17-19 s, because pure pursuit can't track the line precisely at speed.

## Day 4 checklist (guide §7.5)
- [ ] `track1` contains the Day 3 code (`git log` top = Day 3 commit + submission commit)
- [ ] `package.xml` description + maintainer updated
- [ ] 3 runs from the final code in `results/submitted/`, unedited, all COMPLETE
- [ ] `SUBMISSION.md` complete: 3-5 members, results, machine, AI use, references
- [ ] `verify_judging_env.sh` intact
- [ ] Pushed before 23:59 SGT; files visible on GitHub on `track1`
- [ ] Judge workflow: Checks green, Race COMPLETE
- [ ] Organisers have access; URL + branch `track1` sent
- [ ] Every member can explain every part
