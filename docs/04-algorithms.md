# 4. Algorithms to start from

**No driver ships with this repository.** There is no reference implementation
to read, race or copy: `race_ws/src/team_driver` is wiring — it connects to the
simulator, subscribes to the sensors, and drives slowly in a straight line
until it hits something. Everything that makes the car go round is yours to
write.

That is the hackathon. What this chapter gives you instead is the menu: the
approaches that actually work on a 1/10-scale car, what each one needs, what it
costs you to build, and where each breaks on `icra26`. All of them have been
made to work on a RoboRacer by somebody. Pick one, get it finishing laps, then
make it fast.

Choosing well is part of what is being assessed. **Ambition is not scored** —
ten clean laps from a well-tuned reactive driver beats a half-trained policy
that crashes out on lap three. Get something finishing first, then get clever.

| | Needs | Build cost | Ceiling |
| --- | --- | --- | --- |
| [Wall following](#41-reactive-nothing-but-the-lidar) | LiDAR | An afternoon | Low — will not finish `icra26` |
| [Follow-the-gap](#41-reactive-nothing-but-the-lidar) | LiDAR | A day | Medium |
| [Pure pursuit / Stanley](#42-planning-against-the-map) | Map + pose | A day | High |
| [Racing line + speed profile](#42-planning-against-the-map) | Map + pose | Days | Highest |
| [MPC / MPPI](#43-model-based-optimal-control) | Model + pose | Days | Highest |
| [RL / imitation](#44-learned-policies) | Time, GPU | Weeks | Unknown — yours to find out |

One thing Track 1 gives you for free, and it is worth naming before you choose:
you ask the car for a **speed**, not a throttle
([§2.1](02-simulator.md#21-running-it)). The simulator closes that loop. So
every approach below can work in the units it naturally thinks in, and the
speed controller that Track 2 teams have to write first is one problem you do
not have.

---

## 4.1 Reactive: nothing but the LiDAR

Reactive drivers decide from the current scan alone. No map, no memory, no
localisation — which makes them the fastest thing to get running and the
easiest to debug, and caps how good they can get.

### Wall following

Hold a constant distance from one wall with a PID controller. Two LiDAR beams —
one straight out to the side, one angled forwards — give you both the distance
to the wall and its angle, and steering on a point projected *ahead* of the car
rather than on the current error is the difference between tracking the wall
and oscillating about it.

**Build this first if ROS 2 is new to you.** It is about forty lines of real
logic, and if it gets the car moving then the bridge, the workspace, your
commands and the topics are all correct.

**Do not expect it to finish `icra26`.** The algorithm steers from two beams
aimed at one wall, and this circuit keeps taking that wall away: the cone rows
are gaps rather than surfaces, and the infield hairpins put the followed wall
behind the car. That is the algorithm, not the tuning — and understanding *why*
it fails here is the clearest possible argument for the next one.

### Follow-the-gap, with disparity extension

The strongest purely reactive approach, and a genuinely hard thing to beat on a
tight circuit. Three ideas stacked up:

1. **A safety bubble.** Find the closest return and blank out an arc around it,
   so the car can never aim at a point it would clip on the way to.
2. **Disparity extension.** Where the scan jumps from near to far there is a
   corner the LiDAR can see past but the car cannot fit past. Pull the far side
   of the jump in by half a car width. This is what stops it clipping
   doorframes and apexes, and it is what separates a good gap follower from a
   naive one.
3. **Aim at the widest gap, not the deepest beam.** The deepest beam makes the
   car twitch between two nearly identical directions; the middle of the widest
   run of near-maximal readings does not.

Then scale speed down with steering angle and with how short the gap ahead is.

**Two settings decide whether it finishes at all on this circuit**, and both
want to be more conservative than follow-the-gap usually needs:

- **Field of view.** The full 3.14 rad lets the deepest reading fall down a
  side opening — the mouth of the infield, the lane between two cone rows — and
  the car turns into it. Narrowing the view to roughly the width of the
  corridor ahead keeps its attention on the track.
- **Bubble radius and assumed car half-width.** Too small and it clips; too
  large and it refuses gaps it would comfortably fit through, then crawls.

**Where it breaks:** no memory and no plan. It brakes for a corner only once it
can see it, so it is always later on the brakes and earlier off the throttle
than it needs to be. On a fast, flowing circuit that costs a lot.

### Also in this family

**Potential fields** — sum a repulsion from every return and an attraction
towards the track ahead, and steer along the result. Elegant, and prone to
local minima that park the car in a corner. **Bug algorithms** — obstacle
circumnavigation; fine for getting somewhere, far too slow for racing. Worth
knowing about; neither is where the lap time is.

---

## 4.2 Planning against the map

Knowing where you are changes the problem: you can see the corner before the
LiDAR can, which means you can brake before it rather than in it. That is most
of the lap time, and **on Track 1 you have everything this needs already**.

`/ego_racecar/odom` is ground-truth pose and velocity and the rules explicitly
allow it ([§2.4](02-simulator.md#24-ground-truth-odometry--use-it), rule 31).
The occupancy grid ships with the simulator and is published on `/map`, and
`maps/icra26_centerline.csv` is a traced centreline you can follow today
([§2.7](02-simulator.md#27-the-centreline-and-making-your-own-line)).
`scripts/track_tool.py` shows one way to pull a loop out of an occupancy grid.

### Path tracking

**Pure pursuit** is the standard and the one to start with. Find the point on
your path a lookahead distance ahead of the car, and steer along the circular
arc that reaches it; the steering angle follows from the arc's curvature and
the wheelbase. Two properties make it popular: it is a few lines of geometry,
and the lookahead distance is a single intuitive knob — too short and it saws
at the wheel, too long and it cuts every apex. Scaling lookahead with speed is
the usual refinement, and it matters more once your speeds vary.

**Stanley control** steers on cross-track error measured at the front axle plus
a heading term. Sharper than pure pursuit at tracking the line exactly, less
forgiving of a line with discontinuities in it.

Either one will follow the shipped centreline. Neither is fast on its own,
because a centreline driven at one speed is not a lap.

### The two things that make it fast

1. **A speed for every point.** Compute the path's curvature, cap cornering
   speed by the lateral grip you can hold, then propagate braking and
   acceleration limits forwards and backwards around the loop so the car slows
   down *in time*. A flat cruise speed has to be slow enough for the hairpins,
   which makes it far too slow everywhere else — watch a constant-speed lap
   crawl down the main straight and you will see exactly what there is to win.
   The vehicle's real limits are in [§2.8](02-simulator.md#28-vehicle-limits).

2. **A racing line, not a centreline.** Wide in, apex, wide out — shorter and
   faster than the middle of the track. Minimum-curvature and minimum-time line
   optimisation are both well documented and both solvable from the map you
   already have. Generating your own line from the map, rather than shipping
   one as data, is explicitly worth bonus marks (rule 41); hand-typed waypoints
   from watching the car are not (rule 32).

### When the line is blocked

A path follower follows its line and nothing else — put an obstacle on that
line and it drives into it. Two answers:

- **Plan around it.** A* or Dijkstra over the occupancy grid, or a sampling
  planner (RRT\*), re-run locally when the scan says the line is blocked.
- **Switch behaviour.** Follow the line when the track is clear, fall back to
  gap following when it is not. Cruder, robust, and a genuinely good answer.

---

## 4.3 Model-based optimal control

Instead of tracking a path, optimise the controls directly against a model of
the car, every cycle.

**MPC.** Predict the car's motion over a short horizon with a kinematic or
dynamic bicycle model, solve for the steering and speed sequence that minimises
a cost — lap progress, deviation from a line, control effort — subject to the
actuator and track limits, apply the first control, repeat. The model
parameters you need are in [§2.8](02-simulator.md#28-vehicle-limits). The costs
are solve time inside the control loop's budget and a model that has to be good
enough.

**MPPI** replaces the solver with sampling: roll out several thousand random
control sequences, weight them by cost, take the weighted average. No
derivatives and no convexity needed, it parallelises onto the GPU, and it copes
with a cost function you can only evaluate. Popular on scaled racing cars for
exactly those reasons.

**LQR** around a reference trajectory is the cheap classical option — fast and
principled, but linear, so it gives up at the limit of grip.

Principled, fast, and the tuning is honest work. This is a strong choice if
somebody on the team has done control theory.

---

## 4.4 Learned policies

Allowed, encouraged, and worth bonus marks if you can explain what you built
(rule 41). Also the easiest way to spend three weeks and finish with nothing
that laps, so read §4.5 before committing.

**Reinforcement learning.** `f1tenth_gym` is a Gymnasium environment, so you
can train a policy directly against it, outside ROS and faster than real time,
then ship the weights and a thin inference node. That is a real advantage over
Track 2 and the main reason to pick this approach here. Expect the hard parts
to be reward shaping (progress, not speed; penalise contact properly), the gap
between your training setup and the judged one, and keeping inference inside
the control loop's budget.

**Imitation learning.** Drive well by some other means — teleop
([§2.5](02-simulator.md#25-driving-by-hand)), or one of the planners above —
record it, and train a policy to copy it. Cheap to get working, and it inherits
whatever your teacher does badly. Behaviour cloning is the simple version;
DAgger, which asks the expert what it would have done in the states the student
actually visits, is the standard fix for the compounding-error problem that
kills plain cloning.

**Residual and hybrid approaches.** Learn a correction on top of a classical
controller rather than replacing it. Much less likely to fail catastrophically,
much easier to explain, and it still counts as replacing the approach.

**What rule 38 asks of a learned component.** Exactly what it asks of an `if`
statement — but what it asks for is the *method*, not the weights. Nobody will
ask what a particular weight is for. Be ready to say what the network sees and
emits, how you trained it (the environment, the reward, the data and how much
of it), why that method rather than the alternatives, how you checked it works,
and where it fails. Explain how the box was built and you have explained the
box.

---

## 4.5 What to build, in what order

Roughly in order of lap time gained per hour spent:

1. **Something that finishes ten laps.** Either algorithm in §4.1 will do. A
   result you can measure beats an idea you cannot.

2. **Brake properly.** Most crashes are corner entry speed, not steering.
   Decide speed from the distance to what is ahead, not just from the steering
   angle you are already holding. A collision is +10 s and eleven of them is a
   disqualification, so this is worth more than any amount of top speed.

3. **Use your position** (§4.2). You know exactly where you are and a reactive
   planner throws that away. Even a coarse "which section of the track am I in"
   lets you pick different behaviour for a straight and a hairpin.

4. **A line and a speed profile** (§4.2). This is where the lap time is, and it
   is defensible in an interview.

5. **Then get ambitious** (§4.3, §4.4) — with something that already finishes in
   reserve.

**Measure everything.** Run `./scripts/evaluate.sh` after each change:

```sh
./scripts/evaluate.sh --team my_team --laps 10
```

An idea that sounds better and is not shows up in the lap times immediately.
Judging switches the LiDAR noise off and measures in simulated seconds, so runs
here repeat to the millisecond — which means a difference you see between two
runs is a real difference, and you should trust it.

---

## 4.6 Where to read more

Starting points, not a reading list to finish:

- **Follow-the-gap and disparity extension** — Sezer & Gokasan, *A novel
  obstacle avoidance algorithm: "Follow the Gap Method"* (2012); Otterness,
  *The "disparity extender" algorithm* (2019).
- **Pure pursuit** — Coulter, *Implementation of the Pure Pursuit Path Tracking
  Algorithm*, CMU-RI-TR-92-01.
- **Racing lines and speed profiles** — Heilmeier et al., *Minimum curvature
  trajectory planning and control for an autonomous race car* (2019).
- **MPC and MPPI on scaled cars** — Williams et al., *Information-theoretic MPC
  for model-based reinforcement learning* (2017).
- **The F1TENTH course materials**, which cover most of §4.1 and §4.2 from
  first principles and are written for exactly this vehicle — the workshop in
  [chapter 3](03-workshop.md) draws on them.

---

Whatever you build, put it behind `ros2 run team_driver driver` (rule 34) and
declare its dependencies (rule 33).

Next: **[5. Evaluation](05-evaluation.md)**
