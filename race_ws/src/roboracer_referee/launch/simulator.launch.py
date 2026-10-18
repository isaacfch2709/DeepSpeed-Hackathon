"""Launch the RoboRacer simulator on the circuit from maps/tracks.yaml.

    ros2 launch roboracer_referee simulator.launch.py
    ros2 launch roboracer_referee simulator.launch.py rviz:=false

This does not reimplement the upstream bridge launch. It writes a sim config
derived from the track definition and hands it to f1tenth_gym_ros's own
gym_bridge_launch.py, which owns the bridge, map server, URDFs and Foxglove.
Anything upstream changes there we inherit rather than having to chase.

What it does set, and why:

  use_sim_time      the bridge publishes /clock, which is the only time base
                    judging trusts - see docs/05-evaluation.md
  lidar_noise_std   zero, so a run is reproducible. The default adds Gaussian
                    noise, which would make the same submission score
                    differently on every attempt.
  open_foxglove     false, so a scored run never tries to open a browser.
"""

import os
import sys
import tempfile
from dataclasses import replace

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from roboracer_referee.tracks import TrackError, load_track

# Written over the upstream defaults. Everything not named here keeps whatever
# the bridge's own sim.yaml says, so upstream stays the source of truth.
# Where the Dockerfile puts the circuit, used when the repository is not mounted.
IMAGE_MAPS = "/opt/hackathon_maps"

JUDGING_OVERRIDES = {
    "num_agents": 1,
    "use_sim_time": True,          # bridge publishes /clock
    "lidar_noise_std": 0.0,        # reproducibility beats realism when scoring
    "kb_teleop": True,
    "async_mode": True,
    "vehicle_params": "f1tenth",
    "scale": 1.0,
}


def _write_sim_config(track, noise: float) -> str:
    """Merge the track into the bridge's own sim.yaml and write it somewhere readable."""
    sim_share = get_package_share_directory("f1tenth_gym_ros")
    base_path = os.path.join(sim_share, "config", "sim.yaml")
    if not os.path.isfile(base_path):
        raise FileNotFoundError(
            f"The simulator's sim.yaml is missing at {base_path}. "
            "Is the image built? Try install/<your-os>/setup.sh"
        )
    with open(base_path, "r") as handle:
        config = yaml.safe_load(handle)

    params = config["bridge"]["ros__parameters"]
    params.update(JUDGING_OVERRIDES)
    params["lidar_noise_std"] = float(noise)
    params["map_path"] = track.map_path
    params["map_img_ext"] = track.map_image_ext
    params["sx"], params["sy"], params["stheta"] = (float(v) for v in track.start_pose)

    if "foxglove" in config:
        config["foxglove"]["ros__parameters"]["open_foxglove"] = False

    # A real file on disk, because the bridge launch reads it by path. Kept in
    # a stable location so it can be inspected after a confusing run.
    out_dir = os.path.join(tempfile.gettempdir(), "roboracer_sim_config")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "sim.yaml")
    with open(out_path, "w") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)
    return out_path


def _setup(context, *_args, **_kwargs):
    track_name = LaunchConfiguration("track").perform(context).strip() or None
    track_config = LaunchConfiguration("track_config").perform(context).strip() or None
    noise = float(LaunchConfiguration("lidar_noise_std").perform(context))

    try:
        track = load_track(track_name, track_config)
    except TrackError as exc:
        print(f"\n[simulator.launch.py] {exc}\n", file=sys.stderr)
        raise

    map_yaml = track.map_path + ".yaml"
    if not os.path.isfile(map_yaml):
        # Normally the circuit comes from the bind mount at /hackathon. Without
        # it - a bare `docker run` with no volume - fall back to the copy baked
        # into the image rather than failing on a map that is right there.
        fallback = os.path.join(IMAGE_MAPS, os.path.basename(track.map_path))
        if os.path.isfile(fallback + ".yaml"):
            print(f"[simulator.launch.py] {map_yaml} is missing; "
                  f"using the image's copy at {fallback}")
            track = replace(track, map_path=fallback)
            map_yaml = fallback + ".yaml"
        else:
            print(f"\n[simulator.launch.py] Map file not found: {map_yaml}\n"
                  f"Check 'map_path' for track '{track.name}' in maps/tracks.yaml.\n",
                  file=sys.stderr)
            raise FileNotFoundError(map_yaml)

    config_path = _write_sim_config(track, noise)
    print(f"[simulator.launch.py] Track '{track.name}' -> {track.map_path}")
    print(f"[simulator.launch.py] Sim config written to {config_path}")

    sim_share = get_package_share_directory("f1tenth_gym_ros")
    referee_share = get_package_share_directory("roboracer_referee")

    rviz_config = os.path.join(referee_share, "rviz", "race.rviz")
    if not os.path.isfile(rviz_config):
        rviz_config = os.path.join(sim_share, "config", "rviz", "gym_bridge.rviz")

    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(sim_share, "launch", "gym_bridge_launch.py")),
            launch_arguments={
                "config": config_path,
                "num_agents": "1",
                "open_foxglove": "false",
            }.items(),
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz",
            output="log",
            # RViz draws on the wall clock; /clock belongs to the race, and
            # making the display wait for it just freezes the view on a pause.
            parameters=[{"use_sim_time": False}],
            arguments=["-d", rviz_config],
            condition=IfCondition(LaunchConfiguration("rviz")),
        ),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("track", default_value="",
                              description="Track name from maps/tracks.yaml (blank = the default)"),
        DeclareLaunchArgument("track_config", default_value="",
                              description="Path to an alternative tracks.yaml"),
        DeclareLaunchArgument("rviz", default_value="true",
                              description="Open RViz alongside the simulator"),
        DeclareLaunchArgument("lidar_noise_std", default_value="0.0",
                              description="LiDAR noise in metres. Judging uses 0.0; "
                                          "raise it to test robustness."),
        OpaqueFunction(function=_setup),
    ])
