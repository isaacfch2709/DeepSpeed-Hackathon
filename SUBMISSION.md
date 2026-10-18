---
spec: submission.md/v1          # required marker
problem: ../../PROBLEM.md       # the problem this entry answers (relative path, or a URL if it lives in another repository)
title: Reinforcement Learning
authors: [cch0410,chezhong05,isaacfch2709]   # or: authors: [handle-one, handle-two]
date: 2026-10-18

results:                        # one line per track you entered; ids come from PROBLEM.md
  - track: main
    value: 16.4066
    notes:   # optional

agent:                          # who actually did the work; omit the block if it was all by hand
  model: Claude Sonnet 5.5
  harness: Claude Code
  role: author                  # author (the agent produced it) | assisted (a human led, the agent helped)

code: race_ws/src/team_driver/team_driver                       # where the entry lives: a path in this repository or a URL
---

# Approach

What you did and why it works, in a few paragraphs. What changed relative to the baseline
or to the previous best entry.

We did both Pure Pursuit and Reinforcement Learning, which respectively gave 17.9s and 16.5s (best time when tested locally).

Pure Pursuit does not work as well as the driver wobbles a few times before the last turn, which we intended to use RL to solve. By creating RL model and its environment, the model was trained for 1.5M timesteps to obtain the desired parameters. 

During training, there are 3 Stages (Stage 0,1,2) which corresponds to 3 speed cap (3,5,7 m/s). The speed caps are for the model to find a safer path first before increasing the speed.

After the training, the parameters were obtained and stored in policy.npz file. The result driver test (using RL model) gives average of 16.5 laptime as compared to Pure Pursuit model (17.9s).

## Reproduce

```bash
python score.py --submission submissions/v1
```

## Notes

Anything a reviewer should know: hardware, seeds, run-to-run variance, known caveats.

The code "driver.py" must be downloaded along with "policy.npz", which exists in the same path "race_ws/src/team_driver/team_driver".

Team name: niubi
Team member: CHAN CHEE HAO, ISAAC FRANCIS CHEANG HAOMIN, OOI CHE ZHONG, TAN DYLAN, MASON BONG NENG HAO
