# 6. Rules

These rules govern Track 1 of the NTU DeepSpeed Recruitment Hackathon 26/27.
Where this page and any other document disagree, this page wins.

---

## 6.1 Teams

1. A team has **3 to 5 members**.
2. Each person may be on **one team only**.
3. The roster is fixed at submission. Name every member in your `SUBMISSION.md`
   (see [chapter 7](07-submission.md)).
4. One entry per team.

---

## 6.2 Deadline

5. **Submissions close 18 October 2026, 23:59 (SGT).**
6. The commit timestamp on your submitted branch is what counts. Anything
   pushed after the deadline is not scored.
7. Late entries are not accepted. Submit early and push again if you improve —
   the last commit before the deadline is the one judged.

---

## 6.3 The race

8. Every run is driven on the official circuit, `icra26`, in the official
   Docker image built from this repository, on a single judging machine whose
   specification is published in
   [§5.8](05-evaluation.md#58-judging-day). The map is in `maps/`, so you can
   practise on exactly what you will be scored on. If the organisers revise the
   circuit before the deadline it is announced in the team channel and updated
   here.
9. A run consists of:
   - an **out lap** from the grid slot to the start/finish line — not timed;
   - **one warm-up lap** — granted, not scored;
   - **10 timed laps**, run consecutively.
10. A lap counts when the car crosses the start/finish line in the racing
    direction. Crossing it backwards does not count.
11. **Cone rows are barriers. Do not drive between the cones.** A line of cones
    marks the edge of the course exactly as a wall does; the gaps between them
    are not a route, they are a consequence of the cones being separate
    objects. Go around the end of a row, never through it.

    The gaps are wide enough to squeeze a car through — 0.25 to 0.50 m
    against a 0.31 m car — which is why this is written down rather than left
    to the geometry. A run that threads a cone row is not scored, and the
    shipped centreline is generated with those gaps sealed so it cannot suggest
    one (`scripts/track_tool.py --link-cones`).
12. The car is placed on the grid by the referee at the start of every run.
    Once a run starts there is no manual intervention.
13. A run that does not complete all 10 timed laps within **900 seconds of
    simulated time** is recorded as DNF and scores zero for both components.
14. A car that does not move for **15 seconds of simulated time** is recorded as
    DNF.

---

## 6.4 Collisions

15. Every collision adds a **10-second penalty** to the lap on which it
    happened. Penalties are included in both your fastest lap and your 10-lap
    total.
16. **More than 10 collisions in a run is a disqualification** for that run.
17. A collision is counted at most once per second of simulated time, and
    **continuous contact keeps counting**: a car scraping along a barrier
    accrues a fresh collision, and a fresh 10-second penalty, every second
    it stays there. A car that ends up wedged against a wall is therefore
    disqualified after about eleven seconds of contact. See
    [§5.4](05-evaluation.md#54-how-collisions-are-counted).
18. Collisions during the out lap or the warm-up lap count towards the limit in
    rule 16, but carry no time penalty, because there is no scored lap to apply
    it to.

---

## 6.5 Scoring

19. Two components, 50 points each, scored **relative to the best team**:

    | Component | Points | Formula |
    | --- | --- | --- |
    | **Fastest single lap** | 50 | `50 × (fastest lap of any team ÷ your fastest lap)` |
    | **10-lap total** | 50 | `50 × (fastest 10-lap total of any team ÷ your 10-lap total)` |

    The fastest team in each component gets the full 50. Everyone else is scaled
    by the ratio of times.

20. **Leaderboard score = fastest-lap points + 10-lap points**, out of 100,
    ranked highest first.

21. Both components use times **after** collision penalties.

22. Only a run with status `COMPLETE` scores. A disqualified or DNF run scores
    **zero for both components**.

23. The judges run each submission **three times** and take the best attempt.
    The simulator is not perfectly deterministic, and nobody should lose on a
    single unlucky run.

    **That run, on the judging machine, is the only one that scores.** The
    GitHub Actions **Judge** workflow races your entry too, but it is for
    reference — it tells you the entry builds and runs, on hardware that is
    neither yours nor ours. Nothing it reports counts towards the leaderboard.
    See [§5.6](05-evaluation.md#56-automated-judging-on-every-push).

24. Results are computed by
    [`scripts/leaderboard.py`](../scripts/leaderboard.py), which is in this
    repository. You can run it yourself.

### Worked example

Three teams finish. The fastest single lap of anyone is 20.50 s; the fastest
10-lap total is 228.90 s.

| Team | Best lap | 10 laps | Lap points | Endurance points | **Total** |
| --- | --- | --- | --- | --- | --- |
| Alpha | 21.80 | 228.90 | 50 × 20.50/21.80 = **47.02** | 50 × 228.90/228.90 = **50.00** | **97.02** |
| Bravo | 20.50 | 245.00 | 50 × 20.50/20.50 = **50.00** | 50 × 228.90/245.00 = **46.71** | **96.71** |
| Charlie | 25.00 | 260.00 | **41.00** | **44.02** | **85.02** |

Bravo has the fastest single lap and still finishes second. Consistency over
ten laps is worth exactly as much as one quick one.

---

## 6.6 The judging environment

25. **Do not modify the judging environment.** That means:
    - `race_ws/src/roboracer_referee/`
    - `docker/` and `.dockerignore` — everything that defines the image
    - `maps/` — the circuit, its metadata and `tracks.yaml`
    - `scripts/` and `install/`
    - `.github/workflows/`
    - `external/` — the pinned simulator submodules

    Adding a file to one of those directories counts as modifying it.

    Editing the map to move a wall is the clearest possible case of this, and
    it is checked.

26. Verify before you submit:
    ```sh
    ./scripts/verify_judging_env.sh
    ```
    It checks file hashes, looks for files added into protected directories, and
    confirms the submodule pins. The **Judge** workflow runs the same check on
    every push and, when it fails, reports it in the run summary with the list
    of files that differ — a disqualification is a ruling, so it is shown as
    one rather than left as a failed build.

    The manifest it compares against is committed in your own branch, so it
    tells you what *you* changed. It is not what decides the ruling: the
    workflow also diffs the protected paths against the official branch, and
    the judges repeat that from an official checkout
    (`./scripts/verify_judging_env.sh --against <your-branch>`). Re-signing the
    manifest changes nothing except how much explaining there is to do.

27. An entry that modifies the judging environment is **not scored**. If you
    genuinely believe something in it is broken, raise it with the organisers
    before the deadline rather than patching around it.

28. Your code must not publish to, or otherwise interfere with, the referee's
    topics: `/initialpose`, `/referee/*`, `/clock`,
    `/ego_racecar/collision`.

---

## 6.7 What your code may use

29. **Inputs you may read:**

    | Topic | |
    | --- | --- |
    | `/scan` | LiDAR |
    | `/ego_racecar/odom` | **Ground-truth pose and velocity — allowed and recommended** |
    | `/map` | The static occupancy grid |
    | `/tf`, `/tf_static` | Transforms |

30. **Output:** `/drive`, plus any topics of your own under `/driver/...` for
    visualisation and debugging.

31. **Ground-truth odometry is explicitly permitted.** Building your own
    localisation is not required and is genuinely difficult. If you do build
    one, and can explain it thoroughly at the interview, it earns **bonus marks**
    — see rule 41.

32. **Offline precomputation is allowed.** Optimising a racing line before the
    run is real racing practice. But it must be produced by code you submit, and
    it must be reproducible from the map alone. Hand-tuned waypoints typed in
    from watching the car are not in the spirit of this and will not survive the
    interview.

33. **Extra packages are allowed, but you must declare them.** Anything you
    declare is installed into the image when it is built, so it is there during
    judging. Anything you do not declare will not be:

    | What you need | Where to declare it |
    | --- | --- |
    | Python packages | `race_ws/src/team_driver/requirements.txt` |
    | System packages | `race_ws/src/team_driver/apt-packages.txt` |

    List them in your `SUBMISSION.md` as well, with a line on what each is for.
    An undeclared dependency means your entry does not start, and **there is no
    network access during a judged run** to rescue it.

    Already installed, so nothing to declare: `rclpy`, `numpy`, `scipy`,
    `jax`, `gymnasium`, `numba`, `Pillow`, `opencv-python`, `scikit-image`,
    `PyYAML`.

    The image is ROS 2 Jazzy on Python 3.12, and the judging machine has an
    8 GB NVIDIA GPU, so CUDA builds of PyTorch, JAX and CuPy are all usable —
    see [§5.8](05-evaluation.md#58-judging-day). Rebuild from clean after
    adding anything, and check the simulator still starts: the build fails
    loudly if a package breaks it.

34. Your driver must remain a ROS 2 node launched as
    `ros2 run team_driver driver`. You may add files, modules and extra
    executables inside `team_driver`, but keep that entry point working.

35. Keep your control loop real-time capable. The simulator publishes scans at
    roughly 40 Hz; a callback that takes longer than that will miss data. Timing
    is in simulated seconds, so a slow machine costs you nothing — but slow code
    still costs you lap time.

---

## 6.8 AI assistance

36. **Using AI assistants is permitted.** ChatGPT, Claude, Copilot,
    Cursor — all fine.

37. You are responsible for everything you submit. At the interview, any member
    may be asked to explain any part of the code: why it is written that way,
    what happens if a parameter changes, why the alternative approach was
    rejected.

38. Code you cannot explain will not count in your favour, however fast it is.
    This is a recruitment hackathon; we are hiring for understanding, not for
    prompt output. "Explain" means generally, not line by line: what it does,
    why it is built that way, what you rejected, where it breaks.

    This applies to learned components exactly as it does to hand-written ones,
    and it is satisfied the same way. Nobody is asked to account for an
    individual weight. If you can explain the method that produced them — what
    the model takes in and puts out, how it was trained, on what data or in
    what environment, under what reward or loss, how you validated it, and
    where it fails — then the model is explained, and it counts in full.

39. Third-party code and open-source algorithms are fine, with attribution in
    your `SUBMISSION.md`. Copying another team's entry is not.

---

## 6.9 Interview and bonus marks

40. Every team is interviewed after the race. The leaderboard decides the
    ranking; the interview decides recruitment.

41. Bonus marks, awarded at the interview and separate from the leaderboard:
    - **An ambitious algorithm.** Reinforcement learning, MPC, imitation
      learning, or anything else beyond a solid implementation of a standard
      reactive or path-following method
      ([chapter 4](04-algorithms.md)). The bar is that you can explain what it
      does, why you chose it, how you produced it — the training setup
      included, if it was trained — and what its failure modes are; not that
      it wins.
    - **Own localisation.** A particle filter, scan matching or similar,
      replacing `/ego_racecar/odom`, that you can explain thoroughly.
    - **Own racing line generation** computed from the map at runtime rather
      than shipped as data.
    - **Clear engineering.** Readable code, sensible structure, evidence you
      measured rather than guessed.

---

## 6.10 Conduct

42. Do not interfere with another team's work, machines or submissions.
43. Do not attack, overload or attempt to gain access to the organisers'
    infrastructure.
44. Do not attempt to make the referee report a result other than what the car
    actually did. Exploiting a bug in the judging environment is the same as
    modifying it.
45. If you find a bug in the judging environment, report it. Teams that report a
    genuine bug before the deadline are credited, not penalised.

---

## 6.11 Judges' discretion

46. The organisers may adjust or clarify these rules before the deadline. Any
    change is announced in the team channel and reflected here.
47. In a situation these rules do not cover, the organisers decide, and will
    explain the reasoning.
48. The organisers' decisions on scoring and disqualification are final.

---

Next: **[7. Submission](07-submission.md)**
