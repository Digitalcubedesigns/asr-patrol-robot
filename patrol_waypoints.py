#!/usr/bin/env python3
"""
ASR Patrol Robot — Autonomous Patrol Waypoint Manager
DigitalCubeDesigns | digitalcubedesigns.com

Features:
  - Load patrol waypoints from YAML file
  - Send waypoints to Nav2 action server
  - Loop patrol continuously
  - Publish patrol status to /asr/patrol_status
  - Stop patrol on security alert
"""

import rclpy
import yaml
import time
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, ReliabilityPolicy

from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String, Bool
from action_msgs.msg import GoalStatus


class PatrolWaypointManager(Node):

    def __init__(self):
        super().__init__('patrol_waypoint_manager')

        # ── Parameters ────────────────────────────────────────────
        self.declare_parameter('waypoints_file',  '/home/robot/waypoints.yaml')
        self.declare_parameter('loop_patrol',     True)
        self.declare_parameter('waypoint_timeout', 60.0)  # seconds per waypoint
        self.declare_parameter('patrol_speed',    0.3)    # m/s

        self.waypoints_file   = self.get_parameter('waypoints_file').value
        self.loop_patrol      = self.get_parameter('loop_patrol').value
        self.waypoint_timeout = self.get_parameter('waypoint_timeout').value

        # ── Nav2 Action Client ────────────────────────────────────
        self._nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # ── Publishers ────────────────────────────────────────────
        self.status_pub = self.create_publisher(String, '/asr/patrol_status', 10)
        self.current_wp_pub = self.create_publisher(String, '/asr/current_waypoint', 10)

        # ── Subscribers ───────────────────────────────────────────
        self.alert_sub = self.create_subscription(
            Bool, '/asr/security_alert',
            self.alert_callback, 10)

        self.stop_sub = self.create_subscription(
            Bool, '/asr/stop_patrol',
            self.stop_callback, 10)

        # ── State ─────────────────────────────────────────────────
        self.waypoints       = []
        self.current_index   = 0
        self.is_patrolling   = False
        self.is_paused       = False
        self.alert_active    = False

        # ── Load Waypoints & Start ─────────────────────────────────
        self.load_waypoints()
        self.get_logger().info(f'✅ Loaded {len(self.waypoints)} patrol waypoints')
        self.get_logger().info('🤖 ASR Patrol Node Ready — Waiting for Nav2...')

        # Wait for Nav2 action server
        self._nav_client.wait_for_server()
        self.get_logger().info('✅ Nav2 connected. Starting patrol...')

        # Start patrol loop
        self.create_timer(1.0, self.patrol_loop)

    # ── Load Waypoints from YAML ───────────────────────────────────
    def load_waypoints(self):
        try:
            with open(self.waypoints_file, 'r') as f:
                data = yaml.safe_load(f)
                self.waypoints = data.get('waypoints', [])
        except FileNotFoundError:
            self.get_logger().warn(f'⚠️  Waypoints file not found: {self.waypoints_file}')
            self.get_logger().warn('Using default 4-corner patrol waypoints')
            # Default square patrol pattern
            self.waypoints = [
                {'name': 'Point A', 'x':  5.0, 'y':  0.0, 'yaw': 0.0},
                {'name': 'Point B', 'x':  5.0, 'y':  5.0, 'yaw': 1.57},
                {'name': 'Point C', 'x':  0.0, 'y':  5.0, 'yaw': 3.14},
                {'name': 'Point D', 'x':  0.0, 'y':  0.0, 'yaw': -1.57},
            ]

    # ── Build PoseStamped from Waypoint Dict ──────────────────────
    def build_pose(self, wp: dict) -> PoseStamped:
        import math
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp    = self.get_clock().now().to_msg()
        pose.pose.position.x = float(wp['x'])
        pose.pose.position.y = float(wp['y'])
        pose.pose.position.z = 0.0
        # Convert yaw to quaternion
        yaw = float(wp.get('yaw', 0.0))
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        return pose

    # ── Main Patrol Loop ──────────────────────────────────────────
    def patrol_loop(self):
        if not self.waypoints:
            return
        if self.is_patrolling or self.is_paused or self.alert_active:
            return

        wp = self.waypoints[self.current_index]
        self.get_logger().info(
            f'🚶 Navigating to [{wp["name"]}] '
            f'({wp["x"]:.1f}, {wp["y"]:.1f}) — '
            f'Waypoint {self.current_index + 1}/{len(self.waypoints)}'
        )

        # Publish status
        self.publish_status(f'PATROLLING → {wp["name"]}')
        self.current_wp_pub.publish(String(data=wp['name']))

        # Send goal to Nav2
        goal = NavigateToPose.Goal()
        goal.pose = self.build_pose(wp)

        self.is_patrolling = True
        send_goal_future = self._nav_client.send_goal_async(
            goal,
            feedback_callback=self.feedback_callback
        )
        send_goal_future.add_done_callback(self.goal_response_callback)

    # ── Nav2 Callbacks ─────────────────────────────────────────────
    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('❌ Goal rejected by Nav2')
            self.is_patrolling = False
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.result_callback)

    def result_callback(self, future):
        result = future.result()
        self.is_patrolling = False

        if result.status == GoalStatus.STATUS_SUCCEEDED:
            wp = self.waypoints[self.current_index]
            self.get_logger().info(f'✅ Reached: {wp["name"]}')
            self.publish_status(f'REACHED → {wp["name"]}')

            # Advance to next waypoint
            self.current_index = (self.current_index + 1) % len(self.waypoints)

            if not self.loop_patrol and self.current_index == 0:
                self.get_logger().info('✅ Patrol complete. All waypoints visited.')
                self.publish_status('PATROL_COMPLETE')
        else:
            self.get_logger().warn(f'⚠️  Navigation failed. Retrying same waypoint...')
            self.publish_status('NAV_FAILED — RETRYING')

    def feedback_callback(self, feedback_msg):
        dist = feedback_msg.feedback.distance_remaining
        if dist > 0.5:  # Only log if far from goal
            self.get_logger().debug(f'Distance remaining: {dist:.2f}m')

    # ── Alert & Stop Callbacks ────────────────────────────────────
    def alert_callback(self, msg: Bool):
        if msg.data and not self.alert_active:
            self.alert_active = True
            self.get_logger().warn('🚨 SECURITY ALERT — Patrol paused!')
            self.publish_status('SECURITY_ALERT — PATROL_PAUSED')
        elif not msg.data and self.alert_active:
            self.alert_active = False
            self.get_logger().info('✅ Alert cleared — Resuming patrol')
            self.publish_status('ALERT_CLEARED — RESUMING')

    def stop_callback(self, msg: Bool):
        if msg.data:
            self.is_paused = True
            self.get_logger().info('⏸️  Patrol stopped by operator')
            self.publish_status('PATROL_STOPPED')
        else:
            self.is_paused = False
            self.get_logger().info('▶️  Patrol resumed by operator')
            self.publish_status('PATROL_RESUMED')

    # ── Status Publisher ──────────────────────────────────────────
    def publish_status(self, status: str):
        msg = String()
        msg.data = status
        self.status_pub.publish(msg)
        self.get_logger().info(f'📡 Status: {status}')


def main(args=None):
    rclpy.init(args=args)
    node = PatrolWaypointManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('🛑 Patrol node stopped.')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
