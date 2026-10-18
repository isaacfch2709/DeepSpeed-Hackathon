# The circuit

| File | What it is |
| --- | --- |
| `icra26.pgm` | The occupancy grid. 341 x 364 px at 5 cm, so 17.0 x 18.2 m. |
| `icra26.yaml` | Map metadata: resolution and origin. Read by the simulator and by `map_server`. |
| `tracks.yaml` | Where the car starts and where the start/finish line is. |
| `icra26_centerline.csv` | A traced centreline, `x, y` in metres. Generated, not hand-drawn. |

Nothing here is loaded by path from your code: the simulator launch file and
the referee both read `tracks.yaml`, so this is the one place a track is
defined.

```sh
./scripts/track_tool.py validate      # check the numbers against the map image
./scripts/track_tool.py centerline    # regenerate icra26_centerline.csv
```

## How the simulator reads the map

`f1tenth_gym` ignores the thresholds in `icra26.yaml` and binarises the image
at 128: **darker than 128 is a wall, anything lighter is drivable.** On this
map that means the black outlines are the barriers and both the white track
surface and the grey background are open floor. The grey is fully enclosed by
black, so a car cannot reach it, but it is worth knowing when you are reasoning
about what the LiDAR will return.

`map_server`, which only draws the map in RViz, does use the thresholds.

## The lap

The start/finish line sits on the bottom straight at `x = +1.32`, spanning the
full 1.80 m width of the corridor. The car is placed 3 m before it facing `+x`,
and laps run **counter-clockwise**: east along the bottom straight, north up
the right-hand side, west across the top, south down the left.

A lap is about 78 m down the middle of the track. `track_tool.py validate`
confirms a closed lap exists for a car of real width, which is the check worth
re-running after any edit to `tracks.yaml`.

Two things decide that route, and both matter:

- **Clearance, 0.35 m.** Not the car's half width (0.155 m) but the radius its
  corners sweep when turning. Plan with less and the search threads gaps the
  car cannot take, which shows up as a car that scrapes the same places every
  lap.
- **Cone rows are sealed.** Neighbouring cones are joined into solid barriers
  before the search runs, so no path can thread between them. Cones sit 0.25 to
  0.50 m apart and the car is 0.31 m wide, so without this a shortest-path
  search goes straight through a slalom. See rule 11.

## The centreline is not a racing line

`icra26_centerline.csv` is the middle of the corridor. The fast way round is
not the middle: a racing line runs wide into a corner, clips the apex and runs
wide again, and is both shorter and faster. Turning one into the other is the
work — see [docs/04-algorithms.md](../docs/04-algorithms.md).
