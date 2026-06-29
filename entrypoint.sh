#!/bin/bash
# ASR Robot Docker Entrypoint
set -e

# Source ROS 2
source /opt/ros/humble/setup.bash
source /ros2_ws/install/setup.bash

echo "🤖 ASR Patrol Robot Starting..."
echo "ROS_DISTRO: $ROS_DISTRO"

exec "$@"
