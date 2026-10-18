"""Loading and validating track definitions from maps/tracks.yaml.

A track says where the car starts, which map to load, and where the
start/finish line is. Keeping all of that in one file means switching tracks
never involves editing the simulator's own configuration.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import yaml

from .geometry import line_from_pose_and_width, signed_side

Point = Tuple[float, float]

# Searched in order; the first hit wins. The in-image copy is what the judges
# run against, the repository copy is what teams edit during practice.
DEFAULT_SEARCH_PATHS = (
    "/hackathon/maps/tracks.yaml",
    "/opt/hackathon_maps/tracks.yaml",
)


class TrackError(ValueError):
    """Raised for anything wrong with a track definition, with a fixable message."""


@dataclass
class Track:
    name: str
    description: str
    map_path: str
    map_image_ext: str
    start_pose: Tuple[float, float, float]     # x, y, theta (rad)
    finish_line: Tuple[Point, Point]
    crossing_direction: int

    @property
    def finish_line_flat(self) -> List[float]:
        (ax, ay), (bx, by) = self.finish_line
        return [ax, ay, bx, by]


def _as_float_list(value, count: int, field: str) -> List[float]:
    try:
        items = [float(v) for v in value]
    except (TypeError, ValueError) as exc:
        raise TrackError(f"'{field}' must be a list of {count} numbers, got {value!r}") from exc
    if len(items) != count:
        raise TrackError(f"'{field}' must have exactly {count} entries, got {len(items)}")
    if not all(math.isfinite(v) for v in items):
        raise TrackError(f"'{field}' contains a non-finite value: {items}")
    return items


def infer_crossing_direction(start_pose: Tuple[float, float, float],
                             line_a: Point, line_b: Point) -> int:
    """Which way the signed side of the line flips when the car races forwards.

    Derived from the start heading rather than configured by hand, because
    getting it backwards would silently reject every lap.
    """
    x, y, theta = start_pose
    ahead = (x + math.cos(theta), y + math.sin(theta))
    delta = signed_side(line_a, line_b, ahead) - signed_side(line_a, line_b, (x, y))
    if abs(delta) < 1e-9:
        raise TrackError(
            "The start heading runs parallel to the finish line, so a crossing "
            "direction cannot be inferred. Set 'crossing_direction' explicitly."
        )
    return 1 if delta > 0 else -1


def parse_track(name: str, spec: dict) -> Track:
    if not isinstance(spec, dict):
        raise TrackError(f"Track '{name}' must be a mapping, got {type(spec).__name__}")

    for required in ("map_path", "start_pose"):
        if required not in spec:
            raise TrackError(f"Track '{name}' is missing required key '{required}'")

    start = _as_float_list(spec["start_pose"], 3, f"{name}.start_pose")
    start_pose = (start[0], start[1], start[2])

    if "finish_line" in spec:
        raw = spec["finish_line"]
        # Accept either [[x1,y1],[x2,y2]] or a flat [x1,y1,x2,y2].
        if (isinstance(raw, (list, tuple)) and len(raw) == 2
                and all(isinstance(p, (list, tuple)) for p in raw)):
            a = _as_float_list(raw[0], 2, f"{name}.finish_line[0]")
            b = _as_float_list(raw[1], 2, f"{name}.finish_line[1]")
        else:
            flat = _as_float_list(raw, 4, f"{name}.finish_line")
            a, b = flat[:2], flat[2:]
        line = ((a[0], a[1]), (b[0], b[1]))
    else:
        width = float(spec.get("finish_line_width", 6.0))
        if width <= 0:
            raise TrackError(f"Track '{name}': finish_line_width must be > 0")
        # Place the line ahead of the grid slot so the car has a short run-up
        # and its first sample is unambiguously behind the line.
        offset = float(spec.get("finish_line_offset", 2.0))
        cx = start_pose[0] + offset * math.cos(start_pose[2])
        cy = start_pose[1] + offset * math.sin(start_pose[2])
        line = line_from_pose_and_width(cx, cy, start_pose[2], width)

    if math.dist(line[0], line[1]) < 1e-3:
        raise TrackError(f"Track '{name}': the finish line has zero length")

    # The car must start clear of the line, otherwise the very first sample
    # could land on either side of it and the out lap becomes a coin flip.
    offset = abs(signed_side(line[0], line[1], (start_pose[0], start_pose[1])))
    if offset / math.dist(line[0], line[1]) < 0.10:
        raise TrackError(
            f"Track '{name}': the start pose sits on the finish line. Move it at "
            f"least 0.1 m behind the line so the out lap starts cleanly."
        )

    direction = spec.get("crossing_direction")
    if direction is None:
        direction = infer_crossing_direction(start_pose, line[0], line[1])
    elif int(direction) not in (1, -1):
        raise TrackError(f"Track '{name}': crossing_direction must be 1 or -1")

    return Track(
        name=name,
        description=str(spec.get("description", "")),
        map_path=str(spec["map_path"]),
        map_image_ext=str(spec.get("map_image_ext", ".png")),
        start_pose=start_pose,
        finish_line=line,
        crossing_direction=int(direction),
    )


def find_track_config(explicit: Optional[str] = None) -> str:
    candidates = [explicit] if explicit else list(DEFAULT_SEARCH_PATHS)
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise TrackError(
        "Could not find tracks.yaml. Looked in: "
        + ", ".join(p for p in candidates if p)
        + ". Pass track_config:=/path/to/tracks.yaml, or check that the repository "
          "is mounted at /hackathon."
    )


def load_tracks(path: Optional[str] = None) -> Tuple[Dict[str, Track], str]:
    """Return every track in the file plus the name of the default one."""
    resolved = find_track_config(path)
    try:
        with open(resolved, "r") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise TrackError(f"{resolved} is not valid YAML: {exc}") from exc
    except OSError as exc:
        raise TrackError(f"Could not read {resolved}: {exc}") from exc

    if not isinstance(data, dict) or "tracks" not in data:
        raise TrackError(f"{resolved} must contain a top-level 'tracks' mapping")

    tracks = {name: parse_track(name, spec) for name, spec in (data["tracks"] or {}).items()}
    if not tracks:
        raise TrackError(f"{resolved} defines no tracks")

    default = data.get("default") or next(iter(tracks))
    if default not in tracks:
        raise TrackError(
            f"{resolved}: default track '{default}' is not defined. "
            f"Available: {', '.join(sorted(tracks))}"
        )
    return tracks, default


def load_track(name: Optional[str] = None, path: Optional[str] = None) -> Track:
    tracks, default = load_tracks(path)
    chosen = name or default
    if chosen not in tracks:
        raise TrackError(
            f"Unknown track '{chosen}'. Available: {', '.join(sorted(tracks))}"
        )
    return tracks[chosen]
