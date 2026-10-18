# 1. Setup

Everything runs inside one Docker container: ROS 2 Jazzy, the RoboRacer simulator,
the reference algorithms and the judging environment. You install Docker, build
the image once, and from then on you work inside it.

Your code lives on your own machine and is mounted into the container at
`/hackathon`, so you edit files in your normal editor and nothing is lost when
the container stops.

---

## 1.1 Get the repository

```sh
git clone --branch track1 --recurse-submodules \
    https://github.com/NTUDeepSpeed/Recruitment_Hackathon_2627.git ~/Recruitment_Hackathon_2627
cd ~/Recruitment_Hackathon_2627
```

`--branch track1` matters as much as `--recurse-submodules`. The submodules are
declared on `track1`, not on the default branch, so cloning first and switching
afterwards fetches nothing — `git checkout` does not initialise submodules that
appeared in the branch you switched to. If you did it that way, or `external/`
is empty for any other reason:

```sh
git submodule update --init --recursive
```

The setup script checks this before it builds and runs that command for you, so
an empty `external/` is a delay rather than a dead end.

**Do not download the repository as a ZIP.** GitHub's ZIP export leaves the
submodule folders empty and there is no way to fill them in afterwards.

---

## 1.2 Install Docker

### Windows 10/11

1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
2. Install WSL 2. Open **PowerShell as Administrator**:
   ```powershell
   wsl --install
   ```
   Reboot when it asks.
3. In Docker Desktop, go to **Settings → Resources → WSL integration**, enable
   your Ubuntu distro, and click **Apply & Restart**.
4. From then on, work in a WSL terminal:
   ```powershell
   wsl --set-default Ubuntu
   wsl ~
   ```

> Everything after this point happens **inside WSL**, not in PowerShell. If you
> run the scripts from PowerShell they will tell you so and stop.

> Cannot paste into the terminal? Right-click the window title → *Properties* →
> tick *Use Ctrl+Shift+C/V as Copy/Paste*.

### macOS

1. Install the Xcode command line tools if you have not already:
   ```sh
   xcode-select --install
   ```
2. Install [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
   — pick the Apple Silicon or Intel build to match your machine.
3. Launch Docker Desktop and wait for the whale icon to stop animating.

Apple Silicon works. The simulator runs under emulation for a few components
and is slower than on an Intel Mac or a PC, but lap times are measured in
simulated time, so **a slow machine does not cost you points**. See
[chapter 5](05-evaluation.md).

### Ubuntu / Debian Linux

1. Install [Docker Engine](https://docs.docker.com/engine/install/ubuntu/).
2. Add yourself to the `docker` group so you do not need `sudo`:
   ```sh
   sudo usermod -aG docker "$USER"
   newgrp docker
   ```
   (Full instructions: [post-install steps](https://docs.docker.com/engine/install/linux-postinstall/).)
3. Check it works:
   ```sh
   docker run --rm hello-world
   ```

---

## 1.3 Build the image

Pick the folder for your platform. The commands below use Linux; swap in
`macos` or `windows` as appropriate.

```sh
cd ~/Recruitment_Hackathon_2627
./install/linux/setup.sh
```

This takes **15 to 30 minutes** the first time: it pulls the ROS 2 Jazzy base
image and installs the simulator's stack, which includes JAX, OpenCV and Qt.
Later builds are cached and take seconds.

If a build step fails, read the last few lines of output — the Dockerfile
checks its own work and says which step broke and why. `./install/linux/setup.sh
--no-cache` forces a clean rebuild.

---

## 1.4 Start the container

```sh
./install/linux/run.sh
```

You land in a shell inside the container, at `/hackathon`. ROS is already
sourced.

For more terminals — and you will want three or four — open new host terminals
and run:

```sh
./install/linux/shell.sh
```

To shut everything down:

```sh
./install/linux/stop.sh
```

### Where the simulator window appears

| Platform | Where |
| --- | --- |
| Linux | Directly on your desktop, via the host X server |
| Windows / WSL | Directly on your desktop, via WSLg |
| macOS | In a browser: <http://localhost:8080/vnc.html> → click **Connect** |

If nothing appears on Linux or WSL, fall back to the browser:

```sh
./install/linux/run.sh --novnc
```

### GPU

If an NVIDIA GPU is visible, `run.sh` attaches it automatically and falls back
to CPU-only if Docker cannot. Force it either way with `--gpu` or `--no-gpu`.

The container is Python 3.12, so CUDA builds of PyTorch, JAX and CuPy do
install and run. The simulator itself stays on the CPU by design
(`JAX_PLATFORMS=cpu`) so that a judged run is reproducible; the GPU is there
for your code. See [chapter 5](05-evaluation.md#58-judging-day).

---

## 1.5 Build the workspace and drive

Inside the container:

```sh
cd /hackathon/race_ws
colcon build --symlink-install
source install/local_setup.bash
```

`--symlink-install` means Python edits take effect without rebuilding. You only
need to re-run `colcon build` after adding a new file or changing `setup.py`.

Now, in two separate container shells:

```sh
# Terminal 1 — simulator
ros2 launch roboracer_referee simulator.launch.py

# Terminal 2 — your car
ros2 run team_driver driver
```

The car should set off — slowly, in a straight line, and into the first wall.
**That is correct.** The template in
[`race_ws/src/team_driver/team_driver/driver.py`](../race_ws/src/team_driver/team_driver/driver.py)
is wiring, not a driver: it has no steering logic at all. Seeing it move is how
you know the image, the simulator, the workspace and the topics are all
working, and everything after that is yours to write — start with
[chapter 4](04-algorithms.md).

---

## 1.6 Check your environment is sane

```sh
./scripts/verify_judging_env.sh
```

This confirms the judging environment matches the official one. Run it before
you submit; an entry with a modified referee or Dockerfile is not scored.

---

## 1.7 Troubleshooting

**`docker: command not found`, or "cannot connect to the Docker daemon"**
Docker Desktop is not running, or on Linux your user is not in the `docker`
group. On Windows, check Settings → Resources → WSL integration.

**`external/f1tenth_gym is empty`**
Submodules are not checked out: `git submodule update --init --recursive`. If
that does nothing, you downloaded a ZIP — clone properly instead.

**The build fails at `apt-get` or `pip`**
Force a clean rebuild: `./install/linux/setup.sh --no-cache`. A half-cached
layer from an interrupted attempt is the usual cause.

**No simulator window**
Use `--novnc` and open <http://localhost:8080/vnc.html>. On Linux also check
`echo $DISPLAY` is set and try `xhost +local:root`.

**RViz is black, or the window is blank**
Give it a few seconds on the first launch. If it stays black, software
rendering usually fixes it:
```sh
LIBGL_ALWAYS_SOFTWARE=1 ./install/linux/run.sh
```

**The car does not move**
Check something is publishing:
```sh
ros2 topic hz /drive
ros2 topic echo /drive --once
```
No output means your driver node is not running or crashed — look at its
terminal. The simulator does not step its physics until it receives the first
drive command, so a frozen car usually means nothing is publishing.

**`ros2: command not found` inside the container**
You are in a shell that did not source ROS. Exit and use
`./install/<os>/shell.sh`, or run `source /opt/ros/jazzy/setup.bash` by hand.

**`Package 'team_driver' not found`**
The workspace is not built or not sourced:
```sh
cd /hackathon/race_ws && colcon build --symlink-install && source install/local_setup.bash
```

**Everything is very slow**
The simulator steps physics at 100 Hz and can fall behind on a laptop. This
does **not** affect your score — timing uses simulated time. Close RViz
(`ros2 launch roboracer_referee simulator.launch.py rviz:=false`) or run
evaluations with `--headless` to claw back speed.

**Port 8080 is already in use**
```sh
NOVNC_PORT=8081 ./install/macos/run.sh
```

---

Next: **[2. The simulator](02-simulator.md)**
