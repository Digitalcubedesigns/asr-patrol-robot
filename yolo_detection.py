#!/usr/bin/env python3
"""
ASR Patrol Robot — YOLOv8 Detection Node
DigitalCubeDesigns | digitalcubedesigns.com

Features:
  - Real-time person & vehicle detection via YOLOv8
  - Runs on NVIDIA Jetson (CUDA accelerated)
  - Subscribes to PTZ camera RTSP stream
  - Publishes detections to /asr/detections
  - Publishes security alerts to /asr/security_alert
  - Saves detection snapshots with timestamp
"""

import rclpy
import cv2
import numpy as np
import time
import os
from datetime import datetime
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String, Bool
from cv_bridge import CvBridge

try:
    from ultralytics import YOLO
except ImportError:
    raise RuntimeError("Install ultralytics: pip install ultralytics")


# ── Classes we care about for security ────────────────────────────
SECURITY_CLASSES = {
    0:  'person',
    2:  'car',
    3:  'motorcycle',
    5:  'bus',
    7:  'truck',
    15: 'cat',    # optional
    16: 'dog',    # optional
}

ALERT_CLASSES = {0, 2, 3, 5, 7}  # Trigger alert for these classes


class YoloDetectionNode(Node):

    def __init__(self):
        super().__init__('yolo_detection_node')

        # ── Parameters ────────────────────────────────────────────
        self.declare_parameter('model_path',       'yolov8n.pt')   # nano = fastest on Jetson
        self.declare_parameter('confidence',        0.5)
        self.declare_parameter('image_topic',      '/camera/image_raw')
        self.declare_parameter('save_detections',   True)
        self.declare_parameter('save_dir',         '/home/robot/asr_detections')
        self.declare_parameter('alert_cooldown',    5.0)           # seconds between alerts

        model_path       = self.get_parameter('model_path').value
        self.confidence  = self.get_parameter('confidence').value
        image_topic      = self.get_parameter('image_topic').value
        self.save_det    = self.get_parameter('save_detections').value
        self.save_dir    = self.get_parameter('save_dir').value
        self.alert_cd    = self.get_parameter('alert_cooldown').value

        # ── Load YOLOv8 Model ─────────────────────────────────────
        self.get_logger().info(f'🔄 Loading YOLOv8 model: {model_path}')
        self.model = YOLO(model_path)
        self.get_logger().info('✅ YOLOv8 model loaded')

        # ── Bridge & State ────────────────────────────────────────
        self.bridge         = CvBridge()
        self.last_alert_time = 0.0
        self.frame_count    = 0

        # Create save directory
        if self.save_det:
            os.makedirs(self.save_dir, exist_ok=True)

        # ── Subscribers ───────────────────────────────────────────
        self.image_sub = self.create_subscription(
            Image, image_topic,
            self.image_callback, 10)

        # ── Publishers ────────────────────────────────────────────
        self.detection_pub = self.create_publisher(
            String, '/asr/detections', 10)

        self.alert_pub = self.create_publisher(
            Bool, '/asr/security_alert', 10)

        self.annotated_pub = self.create_publisher(
            Image, '/asr/annotated_image', 10)

        self.get_logger().info(f'✅ YOLOv8 Node ready — Listening on: {image_topic}')

    # ── Main Image Callback ────────────────────────────────────────
    def image_callback(self, msg: Image):
        self.frame_count += 1

        # Process every 2nd frame to reduce load on Jetson
        if self.frame_count % 2 != 0:
            return

        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f'Image conversion error: {e}')
            return

        # ── Run YOLOv8 Inference ──────────────────────────────────
        results = self.model(frame, conf=self.confidence, verbose=False)

        detections      = []
        alert_triggered = False

        for result in results:
            for box in result.boxes:
                class_id   = int(box.cls[0])
                confidence = float(box.conf[0])
                label      = SECURITY_CLASSES.get(class_id, None)

                if label is None:
                    continue  # Skip non-security classes

                x1, y1, x2, y2 = map(int, box.xyxy[0])

                det = {
                    'class':      label,
                    'confidence': round(confidence, 2),
                    'bbox':       [x1, y1, x2, y2],
                    'timestamp':  datetime.now().isoformat(),
                }
                detections.append(det)

                # Check if alert class
                if class_id in ALERT_CLASSES:
                    alert_triggered = True

                # Draw bounding box on frame
                color = (0, 0, 255) if class_id in ALERT_CLASSES else (0, 255, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    frame,
                    f'{label} {confidence:.0%}',
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2
                )

        # ── Publish Detections ─────────────────────────────────────
        if detections:
            import json
            self.detection_pub.publish(String(data=json.dumps(detections)))
            self.get_logger().info(
                f'🎯 Detected: {[d["class"] for d in detections]}'
            )

            # Save snapshot
            if self.save_det:
                ts  = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                path = os.path.join(self.save_dir, f'detection_{ts}.jpg')
                cv2.imwrite(path, frame)

        # ── Trigger Security Alert ─────────────────────────────────
        now = time.time()
        if alert_triggered and (now - self.last_alert_time) > self.alert_cd:
            self.alert_pub.publish(Bool(data=True))
            self.last_alert_time = now
            self.get_logger().warn('🚨 SECURITY ALERT TRIGGERED!')
        elif not alert_triggered:
            self.alert_pub.publish(Bool(data=False))

        # ── Publish Annotated Image ────────────────────────────────
        try:
            annotated_msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
            self.annotated_pub.publish(annotated_msg)
        except Exception as e:
            self.get_logger().error(f'Annotated image publish error: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = YoloDetectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('🛑 YOLO Detection node stopped.')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
