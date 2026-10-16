"""Minimum-curvature racing line, computed from the map when the driver starts.

The idea (Heilmeier et al. 2019, "Minimum curvature trajectory planning"):
  1. Start from the centreline and, at every point, look sideways (along the
     normal) to find how far the car may move left or right before it gets too
     close to a wall.
  2. Choose a sideways shift for every point so that the whole loop bends as
     little as possible - the sum of squared curvature is minimal. Less bending
     means a higher cornering speed for the same grip, which is where lap time is.
  3. That is a least-squares problem with bounds (each shift must stay inside
     the corridor), which scipy solves directly: no hand-placed waypoints.

Everything comes from the map image, so the line is regenerated at start-up and
always matches the track the driver is given (rules 32 and 41).
"""

import numpy as np
import yaml
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.optimize import lsq_linear

from team_driver import racing


def load_map(yaml_path):
    """Return (free, resolution, origin_xy): free[row, col] is True where the car may be.

    Row 0 of the returned grid is the bottom of the map (y = origin_y), so a world
    point (x, y) sits at col = (x - ox) / res, row = (y - oy) / res.
    """
    with open(yaml_path) as f:
        meta = yaml.safe_load(f)
    image_path = str(yaml_path).rsplit('/', 1)[0] + '/' + meta['image']
    img = np.array(Image.open(image_path))[::-1]           # flip so row 0 = bottom
    free = img > 250                                        # white = free; walls, cones, unknown = not
    return free, float(meta['resolution']), (float(meta['origin'][0]), float(meta['origin'][1]))


def corridor_widths(path, free, res, origin, inflate):
    """For every path point, how far the line may move left (+) and right (-).

    Obstacles are first grown by `inflate` metres (car half-width plus a safety
    margin). That also seals the 0.25-0.50 m gaps between cones, so the line can
    never be pushed through a cone row (rule 11).
    """
    clearance = distance_transform_edt(free) * res          # metres to the nearest obstacle
    allowed = clearance > inflate
    tangent = np.roll(path, -1, axis=0) - np.roll(path, 1, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1, keepdims=True)
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])    # points to the left

    def inside(points):
        cols = ((points[:, 0] - origin[0]) / res).astype(int)
        rows = ((points[:, 1] - origin[1]) / res).astype(int)
        ok = (rows >= 0) & (rows < free.shape[0]) & (cols >= 0) & (cols < free.shape[1])
        out = np.zeros(len(points), dtype=bool)
        out[ok] = allowed[rows[ok], cols[ok]]
        return out

    step = res / 2
    left = np.zeros(len(path))
    right = np.zeros(len(path))
    for side, width in ((1.0, left), (-1.0, right)):
        still_in = inside(path)                              # a point already too close gets 0
        d = 0.0
        while still_in.any() and d < 3.0:                    # march outwards until we hit the inflated wall
            d += step
            still_in &= inside(path + side * d * normal)
            width[still_in] = d
    return normal, left, right


def min_curvature_line(path, normal, left, right):
    """Shift each point along its normal to minimise the summed squared curvature.

    Curvature is approximated by the second difference of consecutive points,
    P[i-1] - 2 P[i] + P[i+1], which is linear in the shifts - so this is a
    bounded linear least-squares problem.
    """
    n = len(path)
    eye = np.eye(n)
    d2 = np.roll(eye, -1, axis=1) - 2 * eye + np.roll(eye, 1, axis=1)   # closed loop
    a = np.vstack([d2 * normal[:, 0], d2 * normal[:, 1]])
    b = -np.concatenate([d2 @ path[:, 0], d2 @ path[:, 1]])
    eps = 1e-3                     # scipy needs lower < upper even where the corridor is only the line itself
    shift = lsq_linear(a, b, bounds=(-right - eps, left + eps), method='bvls').x
    return path + shift[:, None] * normal


def build(centreline_csv, map_yaml, inflate=0.30, spacing=0.25):
    """Racing line for the map, as an (N, 2) array spaced every 0.10 m."""
    free, res, origin = load_map(map_yaml)
    coarse = racing.resample(racing.smooth(racing.resample(racing.load_path(centreline_csv))), spacing)
    normal, left, right = corridor_widths(coarse, free, res, origin, inflate)
    line = min_curvature_line(coarse, normal, left, right)
    return racing.smooth(racing.resample(line, 0.10), passes=5)
