# ============================================================
# ASR Patrol Robot — Jetson Docker Image
# Base: NVIDIA L4T (JetPack 5.x) + ROS 2 Humble
# DigitalCubeDesigns | digitalcubedesigns.com
# ============================================================

FROM nvcr.io/nvidia/l4t-pytorch:r35.2.1-pth2.0-py3

LABEL maintainer="DigitalCubeDesigns <digitalcubedesigns.com>"
LABEL description="ASR Patrol Robot — ROS 2 Humble on NVIDIA Jetson"
LABEL version="1.0"

# ── Environment ───────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=humble
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# ── System Dependencies ───────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
    curl \
    gnupg2 \
    lsb-release \
    software-properties-common \
    build-essential \
    cmake \
    git \
    wget \
    nano \
    python3-pip \
    python3-dev \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    can-utils \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# ── ROS 2 Humble ─────────────────────────────────────────────
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) \
    signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
    http://packages.ros.org/ros2/ubuntu \
    $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
    > /etc/apt/sources.list.d/ros2.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-humble-ros-base \
    ros-humble-nav2-bringup \
    ros-humble-nav2-msgs \
    ros-humble-slam-toolbox \
    ros-humble-rplidar-ros \
    ros-humble-cv-bridge \
    ros-humble-image-transport \
    ros-humble-sensor-msgs \
    ros-humble-geometry-msgs \
    ros-humble-tf2-ros \
    ros-humble-robot-state-publisher \
    ros-humble-rviz2 \
    && rm -rf /var/lib/apt/lists/*

# ── Python AI Dependencies ────────────────────────────────────
RUN pip3 install --no-cache-dir \
    ultralytics \
    opencv-python-headless \
    numpy \
    pyyaml \
    requests \
    paho-mqtt \
    Pillow

# ── Create Workspace ──────────────────────────────────────────
RUN mkdir -p /ros2_ws/src
WORKDIR /ros2_ws

# ── Copy ASR Source Code ──────────────────────────────────────
COPY . /ros2_ws/src/asr_robot/

# ── Build Workspace ───────────────────────────────────────────
RUN /bin/bash -c "source /opt/ros/humble/setup.bash && \
    rosdep init || true && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y && \
    colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release"

# ── Setup Entrypoint ──────────────────────────────────────────
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "asr_bringup", "limo_bringup.launch.py"]
