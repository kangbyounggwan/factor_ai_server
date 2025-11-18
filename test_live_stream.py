"""
Live Stream Monitoring Test

Tests the print monitoring system with a real HTTP MJPEG stream.
Connects to: http://192.168.200.101:8080/stream
"""

import os
import logging
import asyncio
import time
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from dotenv import load_dotenv

from print_monitoring_worker import PrintMonitoringWorker

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


class LiveStreamMonitor:
    """
    Monitors a live MJPEG stream for print failures.
    """

    def __init__(
        self,
        stream_url: str,
        user_id: str,
        device_uuid: str,
        conf_threshold: float = 0.75,
        enable_gpt: bool = False,  # Disabled by default to save costs
        display_video: bool = True
    ):
        """
        Initialize live stream monitor.

        Args:
            stream_url: HTTP MJPEG stream URL
            user_id: User UUID
            device_uuid: Device UUID
            conf_threshold: Detection confidence threshold
            enable_gpt: Enable GPT analysis (costs money!)
            display_video: Show video window with annotations
        """
        self.stream_url = stream_url
        self.display_video = display_video

        # Mock notification callback
        async def notification_callback(data):
            logger.warning("=" * 80)
            logger.warning("🚨 FAILURE ALERT!")
            logger.warning("=" * 80)
            logger.warning(f"Type: {data['failure_type']}")
            logger.warning(f"Confidence: {data['confidence']:.1%}")
            logger.warning(f"Severity: {data['severity']}")
            logger.warning(f"Scene ID: {data['scene_id']}")
            logger.warning(f"Original Frame: {data['urls']['original']}")
            logger.warning(f"Annotated Frame: {data['urls']['annotated']}")

            if data.get('gpt_analysis'):
                gpt = data['gpt_analysis']
                logger.warning(f"\n💬 GPT Analysis:")
                logger.warning(f"   {gpt.get('description', 'N/A')}")
                logger.warning(f"\n🔧 Suggested Action: {gpt.get('suggested_action', 'N/A')}")

            logger.warning("=" * 80)

        # Initialize monitoring worker
        self.worker = PrintMonitoringWorker(
            user_id=user_id,
            device_uuid=device_uuid,
            conf_threshold=conf_threshold,
            fps=6,
            buffer_size=30,
            enable_gpt_analysis=enable_gpt,
            notification_callback=notification_callback
        )

        self.is_running = False
        self.frame_count = 0
        self.start_time = None

    async def start(self):
        """Start monitoring the live stream."""
        logger.info("=" * 80)
        logger.info("🎥 Live Stream Monitoring Test")
        logger.info("=" * 80)
        logger.info(f"Stream URL: {self.stream_url}")
        logger.info(f"Device: {self.worker.device_uuid}")
        logger.info(f"Detection Threshold: {self.worker.conf_threshold:.0%}")
        logger.info(f"GPT Analysis: {'✅ Enabled' if self.worker.collector.enable_gpt_analysis else '❌ Disabled'}")
        logger.info("=" * 80)
        logger.info("\nPress 'q' to quit\n")

        # Open video stream
        logger.info(f"📡 Connecting to stream...")
        cap = cv2.VideoCapture(self.stream_url)

        if not cap.isOpened():
            logger.error(f"❌ Failed to open stream: {self.stream_url}")
            logger.error("   Make sure the camera is streaming and the URL is correct")
            return

        logger.info("✅ Connected to stream")

        # Start monitoring
        await self.worker.start_monitoring()
        self.is_running = True
        self.start_time = time.time()

        try:
            while self.is_running:
                # Read frame
                ret, frame = cap.read()

                if not ret:
                    logger.warning("⚠️  Failed to read frame, reconnecting...")
                    await asyncio.sleep(1)
                    cap.release()
                    cap = cv2.VideoCapture(self.stream_url)
                    continue

                self.frame_count += 1

                # Mock print context (replace with real data in production)
                print_context = {
                    "layer_number": self.frame_count // 10,
                    "print_progress": min(100, self.frame_count / 10),
                    "nozzle_temp": 210.0,
                    "bed_temp": 60.0,
                    "print_speed": 50.0,
                }

                # Process frame
                result = await self.worker.process_frame(frame, print_context)

                # Create display frame
                display_frame = frame.copy()

                # Draw status overlay
                status_text = f"Frame: {self.frame_count}"
                cv2.putText(display_frame, status_text, (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                if result['failure_detected']:
                    # Draw failure indicator
                    failure_type = result['result']['failure_type']
                    confidence = result['result']['confidence']
                    severity = result['result']['severity']
                    bbox = result['result'].get('bbox')

                    # Get color based on severity
                    severity_colors = {
                        "low": (0, 255, 255),      # Yellow
                        "medium": (0, 165, 255),   # Orange
                        "high": (0, 69, 255),      # Red-Orange
                        "critical": (0, 0, 255)    # Red
                    }
                    color = severity_colors.get(severity, (0, 0, 255))

                    # Draw bounding box if available
                    if bbox:
                        x = bbox["x"]
                        y = bbox["y"]
                        w = bbox["width"]
                        h = bbox["height"]

                        logger.info(f"[Display] Drawing bbox: x={x}, y={y}, w={w}, h={h}")

                        # Draw rectangle
                        cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, 3)

                        # Draw label above bbox
                        label = f"{failure_type.upper()} ({confidence:.0%})"
                        cv2.putText(
                            display_frame,
                            label,
                            (x, max(y - 10, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2
                        )
                    else:
                        # No bbox - draw text in corner
                        cv2.putText(
                            display_frame,
                            f"FAILURE: {failure_type.upper()} ({confidence:.0%})",
                            (10, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2
                        )

                    if result.get('in_cooldown'):
                        cv2.putText(
                            display_frame,
                            "COOLDOWN",
                            (10, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2
                        )
                else:
                    cv2.putText(
                        display_frame,
                        "Status: OK",
                        (10, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
                    )

                # Display statistics every 30 frames
                if self.frame_count % 30 == 0:
                    status = self.worker.get_status()
                    elapsed = time.time() - self.start_time
                    fps = self.frame_count / elapsed

                    logger.info(
                        f"📊 Stats: {self.frame_count} frames | "
                        f"{fps:.1f} FPS | "
                        f"{status['failures_detected']} failures | "
                        f"Buffer: {status['buffer_status']['buffer_size']}/30"
                    )

                # Show video window
                if self.display_video:
                    cv2.imshow('Print Monitor', display_frame)

                    # Check for 'q' key
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        logger.info("\n👋 Quit requested")
                        break

                # Small delay to match target FPS (~6 FPS)
                await asyncio.sleep(0.16)  # ~6 FPS

        except KeyboardInterrupt:
            logger.info("\n👋 Interrupted by user")

        finally:
            # Cleanup
            cap.release()
            if self.display_video:
                cv2.destroyAllWindows()

            await self.worker.stop_monitoring()

            # Final statistics
            logger.info("\n" + "=" * 80)
            logger.info("📊 FINAL STATISTICS")
            logger.info("=" * 80)

            status = self.worker.get_status()
            elapsed = time.time() - self.start_time

            logger.info(f"Duration: {elapsed:.1f}s")
            logger.info(f"Frames Processed: {self.frame_count}")
            logger.info(f"Average FPS: {self.frame_count / elapsed:.2f}")
            logger.info(f"Failures Detected: {status['failures_detected']}")
            logger.info(f"Failure Rate: {status['failures_detected'] / max(1, self.frame_count) * 100:.2f}%")
            logger.info("=" * 80)


async def main():
    """Main function."""
    # Configuration
    STREAM_URL = "http://192.168.200.101:8080/stream"

    # Test credentials (replace with real user/device)
    TEST_USER_ID = "00000000-0000-0000-0000-000000000000"
    TEST_DEVICE_UUID = "test-device-live-stream"

    # Detection threshold (0.7 = 70% confidence required for testing)
    CONF_THRESHOLD = 0.70

    # GPT Analysis (WARNING: costs money on each detection!)
    ENABLE_GPT = False  # Set to True to enable GPT Vision analysis

    # Display video window
    DISPLAY_VIDEO = True

    # Create monitor
    monitor = LiveStreamMonitor(
        stream_url=STREAM_URL,
        user_id=TEST_USER_ID,
        device_uuid=TEST_DEVICE_UUID,
        conf_threshold=CONF_THRESHOLD,
        enable_gpt=ENABLE_GPT,
        display_video=DISPLAY_VIDEO
    )

    # Start monitoring
    await monitor.start()


if __name__ == "__main__":
    asyncio.run(main())
