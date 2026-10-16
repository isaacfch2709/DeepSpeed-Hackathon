#!/usr/bin/env python3
"""Find the fastest settings that never crash, with Bayesian optimisation (Optuna TPE).

How it works
------------
Each *trial* proposes a set of settings (v_max, a_lat, ...). The trial drives
the car in the real f1tenth_gym simulator - the same physics model the ROS
bridge uses, but without ROS, so it runs faster than real time - using the very
same Planner and racing line code as the driver. It drives each setting twice:

  * with no delay                     (a fast machine, like the judges')
  * with steering/speed commands delayed by --delay-ms (a slow laptop)

and scores it by the WORSE of the two:  mean lap time + 15 s per collision
(+ 100 s if it fails to finish). Optuna's TPE sampler learns from every trial
which regions of the settings space give low scores and samples there more
often - that is the "machine learning" part. After --trials trials it prints
the best settings, ready to paste into driver.py.

Run it inside the container (pip-install Optuna once - it is only needed for
tuning, not by the driver, so it is not a judging dependency):

    pip install --break-system-packages optuna
    cd /hackathon/race_ws/src/team_driver/tools
    python3 tune.py --trials 60
"""

import argparse
import json
import math
import pathlib
import sys
import warnings

import numpy as np
import yaml

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))           # .../src/team_driver, so `import team_driver` works

from team_driver import racing, raceline            # noqa: E402
from team_driver.planner import Planner              # noqa: E402

FINISH_X, FINISH_Y = 1.32, (-0.76, 0.89)             # maps/tracks.yaml finish line
START = (-1.68, -0.01, 0.0)                          # maps/tracks.yaml start_pose


def find_repo():
    for parent in HERE.parents:
        if (parent / 'maps' / 'icra26.yaml').exists():
            return parent
    return pathlib.Path('/hackathon')


def make_env(repo):
    """Build the simulator exactly as the ROS bridge does (gym_bridge.py)."""
    from f1tenth_gym.envs import F110Env
    from f1tenth_gym.envs.action import LongitudinalActionType, SteerActionType
    from f1tenth_gym.envs.dynamic_models import DynamicModel, get_f1tenth_vehicle_parameters
    from f1tenth_gym.envs.env_config import (ControlConfig, EnvConfig, LoopCounterMode,
                                             ObservationConfig, ResetConfig, SimulationConfig)
    from f1tenth_gym.envs.integrators import IntegratorType
    from f1tenth_gym.envs.lidar import LiDARConfig
    from f1tenth_gym.envs.observation import ObservationType
    from f1tenth_gym.envs.reset import ResetStrategy

    # Reuse the bridge's own map loader rather than re-implementing it.
    bridge = repo / 'external/f1tenth_gym_ros/f1tenth_gym_ros/gym_bridge.py'
    src = bridge.read_text().splitlines()
    first = next(i for i, l in enumerate(src) if l.startswith('_IGNORED_MAP_KEY_WARNING'))
    last = next(i for i, l in enumerate(src) if l.startswith('class Opponent'))
    from PIL import Image                                        # noqa: F401  (used by the helpers)
    from f1tenth_gym.envs.track import Raceline, Track          # noqa: F401
    helpers = {'np': np, 'yaml': yaml, 'pathlib': pathlib, 'warnings': warnings,
               'Image': Image, 'Track': Track, 'Raceline': Raceline}
    exec('\n'.join(src[first:last]), helpers)
    track, _ = helpers['_load_track_from_yaml'](repo / 'maps/icra26.yaml', 1.0)

    cfg = yaml.safe_load(open(repo / 'external/f1tenth_gym_ros/config/sim.yaml'))
    p = next(iter(cfg.values()))['ros__parameters']
    lidar = LiDARConfig(enabled=True, num_beams=p['scan_num_beams'], range_min=p['scan_range_min'],
                        range_max=p['scan_range_max'], angle_min=np.deg2rad(p['scan_angle_min']),
                        angle_max=np.deg2rad(p['scan_angle_max']), noise_std=0.0,
                        base_link_to_lidar_tf=p['lidar_base_link_to_lidar_tf'])
    params = get_f1tenth_vehicle_parameters()
    env = F110Env(config=EnvConfig(
        map_name=track, map_scale=1.0, params=params, num_agents=1,
        control_config=ControlConfig(longitudinal_mode=LongitudinalActionType.SPEED,
                                     steering_mode=SteerActionType.STEERING_ANGLE),
        simulation_config=SimulationConfig(
            timestep=0.01, integrator_timestep=0.01, integrator=IntegratorType.RK4,
            dynamics_model=DynamicModel.ST, loop_counter=LoopCounterMode.FRENET_BASED,
            compute_frenet_frame=True, max_laps=None, count_partial_first_lap=False),
        observation_config=ObservationConfig(type=ObservationType.DEFAULT),
        reset_config=ResetConfig(strategy=ResetStrategy.MAP_RANDOM_STATIC),
        lidar_config=lidar, render_enabled=False), render_mode=None)
    angles = lidar.angle_min + np.arange(lidar.num_beams) * lidar.angle_increment
    return env, float(params.lr), angles


def drive(env, lr, angles, path, s, laps=2, delay_steps=0, limit_s=70.0):
    """Drive `laps` timed laps; return (lap_times, collisions)."""
    x, y, yaw = START
    env.reset(options={'poses': np.array([[x + lr * math.cos(yaw), y + lr * math.sin(yaw), yaw]])})
    planner = Planner(path, s['v_max'], s['a_lat'], s['a_accel'], s['a_brake'],
                      s['lookahead_min'], s['lookahead_gain'], s['safety_margin'])
    queue = [(0.0, 0.0)] * delay_steps
    cmd, crossings, hits, was_hit, prev_x, t = (0.0, 0.0), [], 0, False, x, 0.0
    for step in range(int(limit_s / 0.01)):
        st = env.unwrapped.sim.state
        cx, cy, yaw = (float(v) for v in st.poses[0, :3])
        x, y = cx - lr * math.cos(yaw), cy - lr * math.sin(yaw)        # base_link, as /odom reports
        if step % 5 in (0, 2):                                         # the scan arrives at ~40 Hz
            queue.append(planner.step(x, y, yaw, float(st.standard_state[0, 3]),
                                      np.asarray(st.scans[0]), angles))
            cmd = queue.pop(0)
        env.step(np.array([[cmd[0], cmd[1]]]))
        t += 0.01
        hit = bool(env.unwrapped.sim.state.collisions[0])
        hits += hit and not was_hit
        was_hit = hit
        if prev_x < FINISH_X <= x and FINISH_Y[0] < y < FINISH_Y[1]:
            crossings.append(t)
            if len(crossings) > laps:
                break
        prev_x = x
        if hits > 10:
            break
    return list(np.diff(crossings)), hits


def score(lap_times, hits, laps):
    if len(lap_times) < laps:
        return 100.0 + 15.0 * hits                   # did not finish: very bad
    return float(np.mean(lap_times)) + 15.0 * hits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--trials', type=int, default=60)
    ap.add_argument('--laps', type=int, default=2)
    ap.add_argument('--delay-ms', type=int, default=100, help='slow-laptop command delay to stay robust to')
    ap.add_argument('--storage', default=None, help='optional optuna storage, e.g. sqlite:///tune.db')
    ap.add_argument('--study', default='icra26')
    args = ap.parse_args()

    import optuna
    repo = find_repo()
    env, lr, angles = make_env(repo)
    centreline = str(repo / 'maps/icra26_centerline.csv')
    lines = {}                                       # cache: racing line per wall margin

    def objective(trial):
        s = {
            'v_max': trial.suggest_float('v_max', 6.0, 10.0),
            'a_lat': trial.suggest_float('a_lat', 3.0, 7.0),
            'a_accel': 6.0,
            'a_brake': trial.suggest_float('a_brake', 3.0, 8.0),
            'lookahead_min': trial.suggest_float('lookahead_min', 0.30, 0.70),
            'lookahead_gain': trial.suggest_float('lookahead_gain', 0.05, 0.35),
            'safety_margin': trial.suggest_float('safety_margin', 0.15, 0.60),
        }
        inflate = trial.suggest_categorical('raceline_inflate', [0.35, 0.40, 0.45, 0.50])
        if inflate not in lines:
            lines[inflate] = raceline.build(centreline, str(repo / 'maps/icra26.yaml'), inflate=inflate)
        results = {}
        worst = 0.0
        for delay_ms in (0, args.delay_ms):
            laps, hits = drive(env, lr, angles, lines[inflate], s, args.laps, delay_ms // 25)
            results[delay_ms] = {'laps': [round(float(v), 2) for v in laps], 'hits': hits}
            worst = max(worst, score(laps, hits, args.laps))
            if worst >= 100:                         # already failed: no need to try the other delay
                break
        trial.set_user_attr('results', results)
        return worst

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(study_name=args.study, storage=args.storage, load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=None), direction='minimize')
    # Start from the settings that already work, so the search has a safe reference point.
    study.enqueue_trial({'v_max': 10.0, 'a_lat': 5.0, 'a_brake': 6.0, 'lookahead_min': 0.45,
                         'lookahead_gain': 0.10, 'raceline_inflate': 0.40,
                         'safety_margin': 0.5}, skip_if_exists=True)

    def report(study, trial):
        print(f'trial {trial.number:3d}  score {trial.value:7.2f}  {trial.params}  '
              f'{trial.user_attrs.get("results")}', flush=True)
    study.optimize(objective, n_trials=args.trials, callbacks=[report])

    best = study.best_trial
    print('\nBEST score', round(best.value, 3), json.dumps(best.user_attrs.get('results')))
    print('Paste into driver.py:')
    for k, v in best.params.items():
        print(f"    self.declare_parameter('{k}', {v:.2f})")


if __name__ == '__main__':
    main()
