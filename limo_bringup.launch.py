#!/usr/bin/env python3
"""
ASR Patrol Robot — LIMO Pro Bringup Launch File
DigitalCubeDesigns | digitalcubedesigns.com

Launches:
  - AgileX LIMO Pro base driver
  - RPLIDAR A3 LiDAR driver
  - IMU driver
  - Robot State Publisher (URDF)
  - SLAM Toolbox
  - Nav2 Navigation Stack
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():

    # ── Launch Arguments ──────────────────────────────────────────
    use_sim_time = LaunchConfiguration('use_sim_time', default='false')
    use_rviz     = LaunchConfiguration('use_rviz',     default='true')
    slam_mode    = LaunchConfiguration('slam_mode',    default='mapping')  # mapping | localization

    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='false',
        description='Use simulation clock if true')

    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz', default_value='true',
        description='Launch RViz2 visualizer')

    declare_slam_mode = DeclareLaunchArgument(
        'slam_mode', default_value='mapping',
        description='SLAM mode: mapping or localization')

    # ── Package Paths ─────────────────────────────────────────────
    asr_bringup_dir   = get_package_share_directory('asr_bringup')
    asr_nav_dir       = get_package_share_directory('asr_navigation')
    nav2_bringup_dir  = get_package_share_directory('nav2_bringup')

    # ── LIMO Pro Base Driver Node ─────────────────────────────────
    limo_base_node = Node(
        package='limo_base',
        executable='limo_base_node',
        name='limo_base',
        output='screen',
        parameters=[{
            'use_sim_time': use_sim_time,
            'port_name': '/dev/ttyTHS1',   # LIMO Pro UART port on Jetson
            'odom_frame': 'odom',
            'base_frame': 'base_link',
            'pub_odom_tf': True,
        }]
    )

    # ── RPLIDAR A3 Driver Node ────────────────────────────────────
    rplidar_node = Node(
        package='rplidar_ros',
        executable='rplidar_composition',
        name='rplidar',
        output='screen',
        parameters=[{
            'serial_port': '/dev/ttyUSB0',
            'serial_baudrate': 256000,
            'frame_id': 'laser_frame',
            'angle_compensate': True,
            'scan_mode': 'Sensitivity',
        }]
    )

    # ── IMU Driver Node (Wit-Motion WT901C) ───────────────────────
    imu_node = Node(
        package='wit_ros2_imu',
        executable='wit_ros2_imu',
        name='imu_node',
        output='screen',
        parameters=[{
            'port': '/dev/ttyUSB1',
            'baud': 115200,
            'frame_id': 'imu_link',
        }]
    )

    # ── Robot State Publisher (URDF) ──────────────────────────────
    urdf_file = os.path.join(asr_bringup_dir, 'urdf', 'limo_pro.urdf.xacro')
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'use_sim_time': use_sim_time,
            'robot_description': open(urdf_file).read() if os.path.exists(urdf_file) else '',
        }]
    )

    # ── SLAM Toolbox ──────────────────────────────────────────────
    slam_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(asr_nav_dir, 'launch', 'slam.launch.py')
        ),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'slam_mode': slam_mode,
        }.items()
    )

    # ── Nav2 Navigation Stack ─────────────────────────────────────
    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, 'launch', 'navigation_launch.py')
        ),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'params_file': os.path.join(asr_nav_dir, 'config', 'nav2_params.yaml'),
        }.items()
    )

    # ── RViz2 Visualizer ─────────────────────────────────────────
    rviz_node = Node(
        condition=IfCondition(use_rviz),
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', os.path.join(asr_bringup_dir, 'rviz', 'asr_default.rviz')],
        output='screen',
    )

    return LaunchDescription([
        declare_use_sim_time,
        declare_use_rviz,
        declare_slam_mode,
        limo_base_node,
        rplidar_node,
        imu_node,
        robot_state_publisher,
        slam_launch,
        nav2_launch,
        rviz_node,
    ])
