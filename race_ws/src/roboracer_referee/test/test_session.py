"""Rule tests for the referee's scoring logic.

Run inside the container with:  colcon test --packages-select roboracer_referee
or directly with:               python3 -m pytest race_ws/src/roboracer_referee/test
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from roboracer_referee.geometry import (          # noqa: E402
    line_from_pose_and_width, segment_crossing_fraction, signed_side,
)
from roboracer_referee.session import (           # noqa: E402
    RaceSession, Rules, Status,
)

# A straight 100 m loop: the car runs from x=-50 to x=+50 and teleports back.
# Lap distance is therefore 100 m and the finish line sits at x=0.
LINE_A, LINE_B = (0.0, -2.0), (0.0, 2.0)
LOOP_HALF = 50.0
DT = 0.02


def direction_for_positive_x_travel():
    """signed_side decreases as x grows for this line, so crossings are -1."""
    return -1


def drive(session, laps, speed, dt=DT, start_x=-45.0, collide_at=()):
    """Run the car around the loop, optionally colliding at given distances travelled."""
    x = start_x
    t = 0.0
    collide_at = sorted(collide_at)
    next_collision = 0
    distance = 0.0
    total_distance = laps * 2 * LOOP_HALF
    while distance < total_distance and not session.finished:
        x += speed * dt
        distance += speed * dt
        t += dt
        if x > LOOP_HALF:
            x -= 2 * LOOP_HALF
            # Teleport: reseed so the wrap is not mistaken for a crossing.
            session.update(t, x, 0.0, speed)
            continue
        while next_collision < len(collide_at) and distance >= collide_at[next_collision]:
            session.register_collision(t)
            next_collision += 1
        session.update(t, x, 0.0, speed)
    return t


def make_session(**kwargs):
    rules = Rules(**kwargs)
    return RaceSession(rules, LINE_A, LINE_B, direction_for_positive_x_travel())


def test_geometry_basics():
    assert signed_side((0, -1), (0, 1), (-1, 0)) > 0
    assert signed_side((0, -1), (0, 1), (1, 0)) < 0
    assert segment_crossing_fraction((-1, 0), (1, 0), (0, -1), (0, 1)) == 0.5
    assert segment_crossing_fraction((-2, 0), (-1, 0), (0, -1), (0, 1)) is None
    # Misses the finite segment even though the infinite lines cross.
    assert segment_crossing_fraction((-1, 9), (1, 9), (0, -1), (0, 1)) is None
    a, b = line_from_pose_and_width(3.0, 4.0, 0.0, 2.0)
    assert math.isclose(math.dist(a, b), 2.0)


def test_clean_run_scores_ten_laps():
    s = make_session(warmup_laps=1, timed_laps=10)
    drive(s, laps=13, speed=10.0)
    assert s.status is Status.COMPLETE, s.result()
    r = s.result()
    assert r["laps_completed"] == 10
    assert r["collisions"] == 0
    # 100 m at 10 m/s = 10 s per lap.
    assert math.isclose(r["best_lap_time"], 10.0, abs_tol=0.05), r["best_lap_time"]
    assert math.isclose(r["total_time"], 100.0, abs_tol=0.5), r["total_time"]
    assert r["total_time_raw"] == r["total_time"]


def test_warmup_lap_is_not_scored():
    s = make_session(warmup_laps=1, timed_laps=2)
    drive(s, laps=5, speed=10.0)
    assert s.timed_laps_done == 2
    # 2 timed laps only, even though 4+ line crossings happened.
    assert len(s.result()["laps"]) == 2


def test_collision_adds_ten_seconds_to_that_lap():
    s = make_session(warmup_laps=1, timed_laps=3)
    # First collision lands inside timed lap 1: after the out lap (5 m to the
    # line) plus one warm-up lap (100 m), i.e. around 150 m travelled.
    drive(s, laps=6, speed=10.0, collide_at=[150.0])
    r = s.result()
    assert r["collisions"] == 1
    penalised = [lap for lap in r["laps"] if lap["collisions"] == 1]
    assert len(penalised) == 1
    assert penalised[0]["penalty_s"] == 10.0
    assert math.isclose(penalised[0]["net_time"], penalised[0]["raw_time"] + 10.0)
    assert math.isclose(r["total_time"], r["total_time_raw"] + 10.0, abs_tol=1e-6)


def test_pulses_are_rate_limited_not_collapsed():
    """One hit is one collision, but the rate limit does not reset on contact."""
    s = make_session(collision_interval_s=1.0)
    s.update(0.0, -45.0, 0.0, 5.0)
    s.update(0.1, -44.5, 0.0, 5.0)
    # 50 pulses over half a second is a single impact, not 50 collisions.
    for i in range(50):
        s.register_collision(0.2 + i * 0.01)
    assert s.collision_events == 1


def test_continuous_contact_keeps_counting():
    """A car that stays on the barrier pays again every interval."""
    s = make_session(collision_interval_s=1.0, max_collisions=100)
    s.update(0.0, -45.0, 0.0, 5.0)
    s.update(0.1, -44.5, 0.0, 5.0)
    # Five seconds of unbroken contact at the simulator's ~100 Hz report rate.
    for i in range(500):
        s.register_collision(1.0 + i * 0.01)
    # t=1.0, 2.0, 3.0, 4.0, 5.0 -> five collisions, not one.
    assert s.collision_events == 5, s.collision_events


def test_sitting_on_a_barrier_disqualifies():
    """Never getting off the wall runs through the limit and ends the run."""
    s = make_session(collision_interval_s=1.0, max_collisions=10)
    s.update(0.0, -45.0, 0.0, 5.0)
    s.update(0.1, -44.5, 0.0, 5.0)
    for i in range(3000):                      # 30 s of contact, if it got that far
        s.register_collision(1.0 + i * 0.01)
    assert s.status is Status.DISQUALIFIED
    assert s.collision_events == 11            # stops counting once the run ends


def test_sustained_contact_penalises_the_lap_it_happened_on():
    s = make_session(warmup_laps=0, timed_laps=2, collision_interval_s=1.0,
                     max_collisions=100, min_lap_time_s=0.0)
    t = 0.0
    for x in (-3.0, -1.0, 1.0, 3.0):           # cross the line, timing starts
        t += 0.1
        s.update(t, x, 0.0, 10.0)
    for i in range(300):                       # 3 s of grinding inside lap 1
        s.register_collision(1.0 + i * 0.01)
    assert s._current_lap_collisions == 3
    assert s.collision_events == 3


def test_exceeding_the_collision_limit_disqualifies():
    s = make_session(max_collisions=10, collision_interval_s=0.001)
    s.update(0.0, -45.0, 0.0, 5.0)
    s.update(0.1, -44.5, 0.0, 5.0)
    for i in range(10):
        s.register_collision(float(i))
    assert s.status is not Status.DISQUALIFIED, "exactly 10 is still legal"
    s.register_collision(10.0)
    assert s.status is Status.DISQUALIFIED
    r = s.result()
    assert r["scored"] is False
    assert r["best_lap_time"] is None and r["total_time"] is None


def test_reverse_crossings_do_not_count():
    s = make_session(warmup_laps=0, timed_laps=1, min_lap_time_s=0.0)
    t = 0.0
    # Approach and cross forwards to start timing.
    for x in (-3.0, -1.0, 1.0, 3.0):
        t += 0.1
        s.update(t, x, 0.0, 10.0)
    assert s._crossings == 1
    # Now shuffle back and forth over the line. Starting from x=3 the moves are
    # 3->1 (back), 1->-1 (back), -1->1 (forward), 1->-1 (back): exactly one of
    # them is a crossing in the racing direction.
    for x in (1.0, -1.0, 1.0, -1.0):
        t += 0.1
        s.update(t, x, 0.0, 10.0)
    assert s._crossings == 2, s._crossings


def test_min_lap_time_rejects_double_counting():
    s = make_session(warmup_laps=0, timed_laps=5, min_lap_time_s=5.0)
    t = 0.0
    for x in (-3.0, -1.0, 1.0, 3.0):
        t += 0.1
        s.update(t, x, 0.0, 10.0)
    first = s._crossings
    # Loop back round and cross again well inside the minimum lap time.
    s.update(t + 0.1, -3.0, 0.0, 10.0)
    s.update(t + 0.2, 3.0, 0.0, 10.0)
    assert s._crossings == first, "crossing inside min_lap_time_s must be ignored"


def test_stuck_car_is_dnf():
    s = make_session(stuck_timeout_s=5.0)
    s.update(0.0, -45.0, 0.0, 5.0)
    s.update(0.1, -44.5, 0.0, 5.0)
    assert s.status is Status.RUNNING
    t = 0.2
    while t < 12.0 and not s.finished:
        s.update(t, -44.5, 0.0, 0.0)
        t += 0.1
    assert s.status is Status.DNF_STUCK


def test_session_timeout_is_dnf():
    s = make_session(session_timeout_s=30.0, timed_laps=10)
    drive(s, laps=50, speed=2.0)
    assert s.status is Status.DNF_TIMEOUT
    assert s.result()["total_time"] is None
    assert s.result()["laps_completed"] < 10


def test_car_that_never_moves_dnfs_on_the_stuck_rule():
    """Rule 14 counts a car that never moved at all, not just one that stopped.

    The referee only feeds samples once the driver is publishing, so "still on
    the grid" is a car that is not moving. Left in PENDING it would sit there
    until the wall-clock watchdog ended the run half an hour later.
    """
    s = make_session(stuck_timeout_s=15.0)
    for i in range(100):                      # 10 s: still inside the grace period
        s.update(i * 0.1, -45.0, 0.0, 0.0)
    assert s.status is Status.PENDING

    t = 10.0
    while t < 40.0 and not s.finished:
        s.update(t, -45.0, 0.0, 0.0)
        t += 0.1
    assert s.status is Status.DNF_STUCK
    assert s.result()["scored"] is False


def test_invalid_rules_are_rejected():
    for bad in (dict(timed_laps=0), dict(warmup_laps=-1), dict(session_timeout_s=0)):
        try:
            Rules(**bad).validate()
        except ValueError:
            continue
        raise AssertionError(f"{bad} should have been rejected")


def test_degenerate_finish_line_is_rejected():
    try:
        RaceSession(Rules(), (1.0, 1.0), (1.0, 1.0), 1)
    except ValueError:
        return
    raise AssertionError("identical finish line endpoints should be rejected")


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:                      # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
