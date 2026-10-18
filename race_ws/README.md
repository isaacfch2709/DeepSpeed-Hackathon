# `race_ws` — the racing workspace

A colcon workspace, bind-mounted into the container at `/hackathon/race_ws`.

```sh
cd /hackathon/race_ws
colcon build --symlink-install
source install/local_setup.bash
```

| Package | Yours? | What it is |
| --- | --- | --- |
| [`team_driver`](src/team_driver/) | **Yes** | Your entry. Start in [`team_driver/driver.py`](src/team_driver/team_driver/driver.py). |
| [`roboracer_referee`](src/roboracer_referee/) | **Do not modify** | The judging environment: lap timing, penalties, result files, and the simulator launch. |

The simulator itself is built into the image at `/sim_ws` and is not part of
this workspace.

`--symlink-install` means Python edits take effect without rebuilding. Rebuild
only after adding a file or changing `setup.py`.

See [docs/04-algorithms.md](../docs/04-algorithms.md) and
[docs/05-evaluation.md](../docs/05-evaluation.md).
