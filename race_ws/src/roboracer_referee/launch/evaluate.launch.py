"""Run one scored evaluation: simulator (optional), driver node, referee.

    # Full run, simulator included
    ros2 launch roboracer_referee evaluate.launch.py team:=my_team

    # Against a simulator you already have open
    ros2 launch roboracer_referee evaluate.launch.py team:=my_team simulator:=false

    # A different entry point or package
    ros2 launch roboracer_referee evaluate.launch.py \
        team:=my_team driver_pkg:=team_driver driver_exec:=my_other_node

The whole launch shuts down as soon as the referee exits, so a run always ends
by itself and never leaves a driver spinning against an empty simulator.
"""

import os
import sys

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, EmitEvent, IncludeLaunchDescription, LogInfo,
    OpaqueFunction, RegisterEventHandler, TimerAction,
)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

ARGUMENTS = [
    ("team", "unnamed_team", "Team name, used in the result file name"),
    ("run_id", "", "Identifier for this run (blank = UTC timestamp)"),
    ("track", "", "Track from maps/tracks.yaml (blank = the default)"),
    ("track_config", "", "Path to an alternative tracks.yaml"),
    ("driver_pkg", "team_driver", "Package containing the driver node"),
    ("driver_exec", "driver", "Executable name of the driver node"),
    ("driver_params", "", "Optional parameter YAML passed to the driver node"),
    ("output_dir", "/hackathon/results", "Where the result JSON is written"),
    ("simulator", "true", "Also start the simulator"),
    ("rviz", "true", "Open RViz (ignored when simulator:=false)"),
    ("referee_delay_s", "5.0", "Seconds to let the simulator settle before the referee starts"),
    ("driver_delay_s", "15.0", "Seconds before the driver starts; must be after the referee has "
                               "placed the car, or the car is driven off the grid mid-placement"),
    ("timed_laps", "10", "Number of scored laps"),
    ("warmup_laps", "1", "Unscored laps before timing starts"),
    ("wall_timeout_s", "1800", "Hard wall-clock watchdog on the whole run, in seconds"),
]


def _setup(context, *_args, **_kwargs):
    def arg(name):
        return LaunchConfiguration(name).perform(context)

    driver_params = arg("driver_params").strip()
    if driver_params and not os.path.isfile(driver_params):
        print(f"\n[evaluate.launch.py] driver_params file not found: {driver_params}\n",
              file=sys.stderr)
        raise FileNotFoundError(driver_params)

    driver = Node(
        package=arg("driver_pkg"),
        executable=arg("driver_exec"),
        name="driver",
        output="screen",
        parameters=[driver_params] if driver_params else [],
    )

    referee = Node(
        package="roboracer_referee",
        executable="referee",
        name="referee",
        output="screen",
        parameters=[{
            "team": arg("team"),
            "run_id": arg("run_id"),
            "track": arg("track"),
            "track_config": arg("track_config"),
            "output_dir": arg("output_dir"),
            "timed_laps": int(arg("timed_laps")),
            "warmup_laps": int(arg("warmup_laps")),
            "wall_timeout_s": float(arg("wall_timeout_s")),
        }],
    )

    actions = []
    if arg("simulator").lower() in ("true", "1", "yes"):
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(
                get_package_share_directory("roboracer_referee"),
                "launch", "simulator.launch.py")),
            launch_arguments={"track": arg("track"),
                              "track_config": arg("track_config"),
                              "rviz": arg("rviz")}.items(),
        ))

    # Order matters. The referee teleports the car onto the grid, and a driver
    # that is already publishing will drive it straight back off again - the car
    # then spends the whole startup racing unsupervised and is usually in a wall
    # by the time the green flag drops. So: simulator settles, referee starts and
    # parks the car, and only then does the driver come up.
    referee_delay = float(arg("referee_delay_s"))
    driver_delay = float(arg("driver_delay_s"))
    if driver_delay <= referee_delay:
        raise RuntimeError(
            f"driver_delay_s ({driver_delay}) must be greater than referee_delay_s "
            f"({referee_delay}); the referee has to place the car before the driver moves it."
        )
    actions.append(TimerAction(period=referee_delay, actions=[referee]))
    actions.append(TimerAction(period=driver_delay, actions=[driver]))

    actions.append(RegisterEventHandler(OnProcessExit(
        target_action=referee,
        on_exit=[LogInfo(msg="Referee finished; shutting the run down."),
                 EmitEvent(event=Shutdown(reason="evaluation complete"))],
    )))
    actions.append(RegisterEventHandler(OnProcessExit(
        target_action=driver,
        on_exit=[LogInfo(msg="WARNING: the driver node exited before the referee did.")],
    )))
    return actions


def generate_launch_description():
    return LaunchDescription(
        [DeclareLaunchArgument(name, default_value=default, description=description)
         for name, default, description in ARGUMENTS]
        + [OpaqueFunction(function=_setup)]
    )
