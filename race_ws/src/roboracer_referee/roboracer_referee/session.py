"""Lap timing, penalties and scoring for a single evaluation run.

This module deliberately contains no ROS code. The referee node feeds it
positions and collision events; everything about *what a lap is worth* lives
here, so the rules can be unit tested without standing up a simulator.

All times are simulated seconds, never wall-clock. See docs/05-evaluation.md
for why that distinction decides whether a result is reproducible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from enum import Enum
from typing import List, Optional, Tuple

from .geometry import segment_crossing_fraction, signed_side

Point = Tuple[float, float]


class Status(str, Enum):
    """Terminal state of a run. The string values go straight into the result file."""

    PENDING = "PENDING"                # waiting for the car to start moving
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"              # all timed laps finished
    DISQUALIFIED = "DISQUALIFIED"      # collision limit exceeded
    DNF_TIMEOUT = "DNF_TIMEOUT"        # ran out of session time
    DNF_STUCK = "DNF_STUCK"            # car stopped moving
    ABORTED = "ABORTED"                # operator interrupt or crashed driver


@dataclass
class Rules:
    """The scoring rules. Defaults are the official Track 1 settings."""

    warmup_laps: int = 1
    timed_laps: int = 10
    collision_penalty_s: float = 10.0
    max_collisions: int = 10           # strictly more than this disqualifies
    collision_interval_s: float = 1.0  # sustained contact counts again this often
    min_lap_time_s: float = 2.0        # guards against double-counting one crossing
    session_timeout_s: float = 900.0
    stuck_speed_mps: float = 0.05
    stuck_timeout_s: float = 15.0

    def validate(self) -> None:
        problems = []
        if self.warmup_laps < 0:
            problems.append("warmup_laps must be >= 0")
        if self.timed_laps < 1:
            problems.append("timed_laps must be >= 1")
        if self.collision_penalty_s < 0:
            problems.append("collision_penalty_s must be >= 0")
        if self.max_collisions < 0:
            problems.append("max_collisions must be >= 0")
        if self.collision_interval_s <= 0:
            problems.append("collision_interval_s must be > 0")
        if self.min_lap_time_s < 0:
            problems.append("min_lap_time_s must be >= 0")
        if self.session_timeout_s <= 0:
            problems.append("session_timeout_s must be > 0")
        if self.stuck_timeout_s <= 0:
            problems.append("stuck_timeout_s must be > 0")
        if problems:
            raise ValueError("Invalid referee rules: " + "; ".join(problems))


@dataclass
class Lap:
    number: int                  # 1-based within its own kind
    kind: str                    # "warmup" or "timed"
    start_time: float
    end_time: float
    raw_time: float              # as driven
    collisions: int = 0
    penalty_s: float = 0.0

    @property
    def net_time(self) -> float:
        """Lap time as scored: what was driven, plus the collision penalties."""
        return self.raw_time + self.penalty_s


class RaceSession:
    """Drives one evaluation run from odometry samples and collision pulses."""

    def __init__(self, rules: Rules, line_a: Point, line_b: Point,
                 crossing_direction: int = 1):
        rules.validate()
        if crossing_direction not in (1, -1):
            raise ValueError("crossing_direction must be +1 or -1")
        if math.dist(line_a, line_b) < 1e-6:
            raise ValueError("Finish line endpoints are identical; check the track configuration")

        self.rules = rules
        self.line_a = line_a
        self.line_b = line_b
        self.crossing_direction = crossing_direction

        self.status = Status.PENDING
        self.laps: List[Lap] = []
        self.collision_events: int = 0

        self._start_time: Optional[float] = None
        self._prev_point: Optional[Point] = None
        self._prev_side: Optional[float] = None
        self._prev_time: Optional[float] = None
        self._crossings: int = 0
        self._last_crossing_time: Optional[float] = None
        self._current_lap_start: Optional[float] = None
        self._current_lap_collisions: int = 0
        self._last_collision_time: Optional[float] = None
        self._moving_since: Optional[float] = None
        self._below_speed_since: Optional[float] = None
        self._finish_reason: str = ""

    # -- lifecycle ---------------------------------------------------------

    @property
    def finished(self) -> bool:
        return self.status not in (Status.PENDING, Status.RUNNING)

    @property
    def untimed_crossings(self) -> int:
        """Crossings consumed before the first timed lap begins.

        One to leave the grid and reach the line, plus one per warm-up lap.
        """
        return 1 + self.rules.warmup_laps

    @property
    def timed_laps_done(self) -> int:
        return sum(1 for lap in self.laps if lap.kind == "timed")

    def _finish(self, status: Status, reason: str) -> None:
        if self.finished:
            return
        self.status = status
        self._finish_reason = reason

    def abort(self, reason: str = "operator interrupt") -> None:
        self._finish(Status.ABORTED, reason)

    # -- inputs ------------------------------------------------------------

    def register_collision(self, time_s: float) -> bool:
        """Record a collision pulse. Returns True if it counted as a new collision.

        The simulator raises its collision flag on every physics step the car is
        in contact, about a hundred times a second, which is too fine-grained to
        score directly. Collisions are therefore counted at most once per
        collision_interval_s - but the clock runs from the last *counted*
        collision, not from the last pulse, so a car that stays against a wall
        keeps accruing one collision per interval for as long as it stays there.
        Sitting on a barrier is not cheaper than hitting it once.
        """
        if self.finished:
            return False

        if (self._last_collision_time is not None
                and time_s - self._last_collision_time < self.rules.collision_interval_s):
            return False

        self._last_collision_time = time_s
        self.collision_events += 1
        self._current_lap_collisions += 1

        if self.collision_events > self.rules.max_collisions:
            self._finish(
                Status.DISQUALIFIED,
                f"{self.collision_events} collisions exceeds the limit of {self.rules.max_collisions}",
            )
        return True

    def update(self, time_s: float, x: float, y: float, speed_mps: float) -> List[str]:
        """Feed one odometry sample. Returns human-readable events for logging."""
        events: List[str] = []
        if self.finished:
            return events

        point = (x, y)
        side = signed_side(self.line_a, self.line_b, point)

        if self._start_time is None:
            self._start_time = time_s
            self._prev_point, self._prev_side, self._prev_time = point, side, time_s
            return events

        # Non-monotonic time means the simulator was reset underneath us. Re-seed
        # rather than emitting a nonsensical negative lap time.
        if time_s < self._prev_time:
            self._prev_point, self._prev_side, self._prev_time = point, side, time_s
            return events

        if self.status is Status.PENDING and abs(speed_mps) > self.rules.stuck_speed_mps:
            self.status = Status.RUNNING
            self._moving_since = time_s
            events.append("Car is moving; session started.")

        if self.status is Status.RUNNING:
            events.extend(self._check_crossing(time_s, point, side))

        # Rules 13 and 14 apply from the green flag, not from the first metre.
        # The referee only feeds samples once the driver is publishing, so a car
        # that has still not moved is a car that is not moving - it must DNF on
        # the stuck rule like any other, rather than sit in PENDING until the
        # wall-clock watchdog aborts the run half an hour later.
        self._check_stuck(time_s, speed_mps)
        self._check_timeout(time_s)

        self._prev_point, self._prev_side, self._prev_time = point, side, time_s
        return events

    # -- internals ---------------------------------------------------------

    def _check_crossing(self, time_s: float, point: Point, side: float) -> List[str]:
        events: List[str] = []
        assert self._prev_point is not None and self._prev_side is not None

        # The car must pass through the line in the racing direction. Checking
        # the sign change as well as the segment intersection rejects a car
        # that reverses back over the line to farm laps.
        going_the_right_way = (
            self._prev_side * self.crossing_direction < 0 <= side * self.crossing_direction
        )
        if not going_the_right_way:
            return events

        fraction = segment_crossing_fraction(self._prev_point, point, self.line_a, self.line_b)
        if fraction is None:
            return events

        # Interpolate the instant of the cut instead of using the sample time.
        assert self._prev_time is not None
        crossing_time = self._prev_time + fraction * (time_s - self._prev_time)

        if (self._last_crossing_time is not None
                and crossing_time - self._last_crossing_time < self.rules.min_lap_time_s):
            events.append(
                f"Ignored a line crossing {crossing_time - self._last_crossing_time:.2f}s "
                f"after the previous one (below min_lap_time_s)."
            )
            return events

        self._crossings += 1
        previous_crossing = self._last_crossing_time
        self._last_crossing_time = crossing_time

        if self._crossings < self.untimed_crossings:
            # Still on the out lap or a warm-up lap: no timed lap closes here.
            if self._crossings > 1 and previous_crossing is not None:
                events.append(
                    f"Warm-up lap {self._crossings - 1} complete "
                    f"({crossing_time - previous_crossing:.3f}s, not scored)."
                )
            else:
                events.append("Crossed the start/finish line; warm-up begins.")
            self._current_lap_collisions = 0
            return events

        if self._crossings == self.untimed_crossings:
            if previous_crossing is not None:
                events.append(
                    f"Warm-up lap {self.rules.warmup_laps} complete "
                    f"({crossing_time - previous_crossing:.3f}s, not scored). Timing starts now."
                )
            else:
                events.append("Timing starts now.")
            self._current_lap_start = crossing_time
            self._current_lap_collisions = 0
            return events

        # A timed lap just closed.
        assert self._current_lap_start is not None
        lap_number = self.timed_laps_done + 1
        raw = crossing_time - self._current_lap_start
        penalty = self._current_lap_collisions * self.rules.collision_penalty_s
        lap = Lap(
            number=lap_number,
            kind="timed",
            start_time=self._current_lap_start,
            end_time=crossing_time,
            raw_time=raw,
            collisions=self._current_lap_collisions,
            penalty_s=penalty,
        )
        self.laps.append(lap)

        suffix = f" (+{penalty:.0f}s from {lap.collisions} collision(s))" if penalty else ""
        events.append(f"Lap {lap_number}/{self.rules.timed_laps}: {raw:.3f}s -> {lap.net_time:.3f}s{suffix}")

        self._current_lap_start = crossing_time
        self._current_lap_collisions = 0

        if self.timed_laps_done >= self.rules.timed_laps:
            self._finish(Status.COMPLETE, "all timed laps completed")
            events.append("Run complete.")
        return events

    def _check_stuck(self, time_s: float, speed_mps: float) -> None:
        if abs(speed_mps) > self.rules.stuck_speed_mps:
            self._below_speed_since = None
            return
        if self._below_speed_since is None:
            self._below_speed_since = time_s
        elif time_s - self._below_speed_since >= self.rules.stuck_timeout_s:
            self._finish(
                Status.DNF_STUCK,
                f"car did not move for {self.rules.stuck_timeout_s:.0f}s of simulated time",
            )

    def _check_timeout(self, time_s: float) -> None:
        assert self._start_time is not None
        if time_s - self._start_time >= self.rules.session_timeout_s:
            self._finish(
                Status.DNF_TIMEOUT,
                f"session time limit of {self.rules.session_timeout_s:.0f}s reached "
                f"after {self.timed_laps_done}/{self.rules.timed_laps} timed laps",
            )

    # -- results -----------------------------------------------------------

    @property
    def scored(self) -> bool:
        """Whether this run produces leaderboard times at all."""
        return self.status is Status.COMPLETE

    def best_lap(self) -> Optional[Lap]:
        timed = [lap for lap in self.laps if lap.kind == "timed"]
        return min(timed, key=lambda lap: lap.net_time) if timed else None

    def total_time(self) -> Optional[float]:
        """Net time for the full set of timed laps, or None if it was not completed."""
        if not self.scored:
            return None
        return sum(lap.net_time for lap in self.laps if lap.kind == "timed")

    def result(self) -> dict:
        best = self.best_lap()
        timed = [lap for lap in self.laps if lap.kind == "timed"]
        return {
            "status": self.status.value,
            "reason": self._finish_reason,
            "scored": self.scored,
            "rules": asdict(self.rules),
            "laps_completed": len(timed),
            "laps_required": self.rules.timed_laps,
            "collisions": self.collision_events,
            "collision_limit": self.rules.max_collisions,
            "best_lap_time": round(best.net_time, 4) if best and self.scored else None,
            "best_lap_time_raw": round(best.raw_time, 4) if best and self.scored else None,
            "best_lap_number": best.number if best and self.scored else None,
            "total_time": round(self.total_time(), 4) if self.total_time() is not None else None,
            "total_time_raw": (round(sum(lap.raw_time for lap in timed), 4) if self.scored else None),
            "total_penalty_s": round(sum(lap.penalty_s for lap in timed), 4),
            "laps": [
                {
                    "number": lap.number,
                    "raw_time": round(lap.raw_time, 4),
                    "collisions": lap.collisions,
                    "penalty_s": round(lap.penalty_s, 4),
                    "net_time": round(lap.net_time, 4),
                }
                for lap in timed
            ],
        }
