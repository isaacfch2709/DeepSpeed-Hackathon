"""PPO training with a speed curriculum, then export weights to policy.npz.

Run (simulator already running, e.g. `ros2 launch roboracer_referee simulator.launch.py rviz:=false`):
    pip install stable-baselines3 --break-system-packages     # training only
    python3 -m team_driver.train
    python3 -m team_driver.train --resume ppo_stage1.zip      # continue
"""
import argparse
import os
import numpy as np
import torch.nn as nn
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor

from team_driver.train_env import RoboRacerEnv

PKG_DIR = "/hackathon/race_ws/src/team_driver/team_driver"   # NOT scripts/ or maps/ (protected)
CENTERLINE = "/hackathon/maps/icra26_centerline.csv"

# (v_max in m/s, PPO timesteps). Raise v_max only once the previous stage laps cleanly.
STAGES = [(3.0, 300_000), (5.0, 500_000), (7.0, 700_000)]

HYPERPARAMS = dict(
    learning_rate=3e-4, n_steps=2048, batch_size=256, n_epochs=10,
    gamma=0.995, gae_lambda=0.95, clip_range=0.2,
    ent_coef=0.005, vf_coef=0.5, max_grad_norm=0.5, seed=0, device="cpu",
)
POLICY_KWARGS = dict(
    net_arch=dict(pi=[64, 64], vf=[64, 64]),
    activation_fn=nn.Tanh,
    log_std_init=-0.5,
)


def export(model, out_path):
    p = model.policy
    layers = [m for m in p.mlp_extractor.policy_net if isinstance(m, nn.Linear)] + [p.action_net]
    arrays, total = {}, 0
    for i, lin in enumerate(layers):
        w = lin.weight.detach().cpu().numpy().astype(np.float32)   # shape (out, in)
        b = lin.bias.detach().cpu().numpy().astype(np.float32)
        arrays[f"W{i}"], arrays[f"b{i}"] = w, b
        total += w.size + b.size
        print(f"  layer {i}: W{w.shape}  b{b.shape}   |W|mean={np.abs(w).mean():.3f}  max={np.abs(w).max():.3f}")
    np.savez(out_path, **arrays)
    print(f"  exported {total} actor parameters -> {out_path}")
    print(f"  action log_std (exploration, unused at deploy): {p.log_std.detach().cpu().numpy()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", default=None)
    ap.add_argument("--centerline", default=CENTERLINE)
    a = ap.parse_args()

    env = Monitor(RoboRacerEnv(a.centerline, v_max=STAGES[0][0]))
    if a.resume:
        model = PPO.load(a.resume, env=env, device="cpu")
    else:
        model = PPO("MlpPolicy", env, policy_kwargs=POLICY_KWARGS, verbose=1, **HYPERPARAMS)

    for k, (v_max, steps) in enumerate(STAGES):
        env.unwrapped.set_v_max(v_max)
        print(f"\n=== stage {k}: v_max={v_max} m/s, {steps} steps ===")
        model.learn(total_timesteps=steps, reset_num_timesteps=False)
        model.save(f"ppo_stage{k}.zip")
        export(model, os.path.join(PKG_DIR, "policy.npz"))     # overwritten after each stage
    env.close()


if __name__ == "__main__":
    main()
