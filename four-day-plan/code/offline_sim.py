"""Rough offline check: kinematic bicycle driving the pure-pursuit planner on icra26."""
import sys
import numpy as np
from PIL import Image
sys.path.insert(0, sys.argv[1])  # folder containing racing.py
import racing as R

T1 = sys.argv[2]
v_max, a_lat, a_brake = (float(a) for a in sys.argv[3:6])
L0, KL = 0.6, 0.15

img = np.array(Image.open(f'{T1}/maps/icra26.pgm'))
res, ox, oy = 0.05, -8.68, -1.46
occ = np.argwhere(img < 128)                       # (row, col) of walls/cones
occ_xy = np.column_stack([ox + (occ[:, 1] + 0.5) * res,
                          oy + (img.shape[0] - occ[:, 0] - 0.5) * res])

def clearance(x, y):
    d = np.hypot(occ_xy[:, 0] - x, occ_xy[:, 1] - y)
    return d.min()

path = R.smooth(R.resample(R.load_path(f'{T1}/maps/icra26_centerline.csv')))
vprof = R.speed_profile(path, v_max, a_lat, 6.0, a_brake)
s = np.linalg.norm(np.diff(np.vstack([path, path[:1]]), axis=0), axis=1).sum()
print(f'path {s:.1f} m, profile min {vprof.min():.2f} max {vprof.max():.2f} m/s')

x, y, yaw, v, delta = -1.68, -0.01, 0.0, 0.0, 0.0
dt, t, hint, cmd = 0.01, 0.0, None, (0.0, 0.0)
start_x, laps, lap_t, worst = 1.32, [], 0.0, 9.0
prev_x = x
for step in range(100 * 120):
    if step % 2 == 0:                               # ~50 Hz control (scan is ~40 Hz)
        hint = R.nearest_index(path, x, y, hint)
        la = L0 + KL * v
        steer, _ = R.pure_pursuit(path, hint, x, y, yaw, la, 0.33)
        cmd = (float(np.clip(steer, -0.4189, 0.4189)), float(vprof[hint]))
    # actuator limits
    delta += np.clip(cmd[0] - delta, -3.2 * dt, 3.2 * dt)
    v += np.clip(cmd[1] - v, -9.51 * dt, 9.51 * dt)
    x += v * np.cos(yaw) * dt
    y += v * np.sin(yaw) * dt
    yaw += v / 0.33 * np.tan(delta) * dt
    t += dt
    if step % 5 == 0 and t > 1.0:
        worst = min(worst, clearance(x, y))
    if prev_x < start_x <= x and -0.76 < y < 0.89:
        laps.append(t)
    prev_x = x
lt = np.diff(laps)
print(f'lap times {np.round(lt, 2)}  min wall clearance (centre) {worst:.2f} m'
      f'  (car half-width 0.155, half-diagonal ~0.33)')
