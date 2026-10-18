# Installation

Pick the folder for your machine and run the two scripts in it. Full
walkthroughs, including what to install first, are in
[docs/01-setup.md](../docs/01-setup.md).

| Your machine | Folder | Run the scripts from |
| --- | --- | --- |
| Windows 10/11 | [`windows/`](windows/) | a **WSL** terminal (`wsl ~`), not PowerShell |
| macOS (Intel or Apple Silicon) | [`macos/`](macos/) | Terminal.app or iTerm |
| Ubuntu / Debian Linux | [`linux/`](linux/) | any terminal |

Each folder has the same four scripts:

| Script | What it does |
| --- | --- |
| `setup.sh` | Builds the Docker image. Run once, takes 15-30 minutes. |
| `run.sh` | Starts the container and drops you into a shell. |
| `shell.sh` | Opens another shell in the running container. You will want three or four. |
| `stop.sh` | Stops everything. Your code is on a bind mount and is never touched. |

```sh
# Windows (inside WSL) - swap 'windows' for 'macos' or 'linux' as appropriate
cd ~/Recruitment_Hackathon_2627
./install/windows/setup.sh
./install/windows/run.sh
```

The scripts share their implementation in [`common.sh`](common.sh); the per-OS
files only pick the right display mode and platform checks. They are safe to
re-run, and they tell you what to fix rather than failing silently.

## Display

The simulator needs somewhere to draw its window.

- **Linux and Windows/WSL** render to the host X server (WSLg on Windows).
- **macOS** renders to a browser: open <http://localhost:8080/vnc.html> and
  click *Connect*.

If the window never appears on Linux or WSL, fall back to the browser with
`./install/<your-os>/run.sh --novnc`.
