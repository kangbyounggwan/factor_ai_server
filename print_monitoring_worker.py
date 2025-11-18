"""
Print Monitoring Worker

Integrates all components for real-time 3D print failure detection:
1. Receives frames from WebRTC camera
2. Maintains frame buffer
3. Runs AI failure detection
4. Collects failure scenes automatically
5. Sends MQTT notifications

This is the main service that runs during print monitoring.
"""

import os
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

import numpy as np
import cv2
from dotenv import load_dotenv

from ai_failure_detector import AIFailureDetector
from failure_scene_collector import FailureSceneCollector

load_dotenv()

logger = logging.getLogger(__name__)


class PrintMonitoringWorker:
    """
    Main worker for print monitoring.

    Workflow:
    1. User starts print monitoring
    2. Worker receives frames from WebRTC camera
    3. Each frame:
       - Added to buffer
       - Checked for failures with AI detector
       - If failure: auto-collect scene + notify user
    """

    def __init__(
        self,
        user_id: str,
        device_uuid: str,
        conf_threshold: float = 0.75,
        fps: int = 6,
        buffer_size: int = 30,
        enable_gpt_analysis: bool = True,
        notification_callback: Optional[callable] = None
    ):
        """
        Initialize monitoring worker.

        Args:
            user_id: User UUID
            device_uuid: Device UUID
            conf_threshold: AI detection confidence threshold
            fps: Expected frames per second
            buffer_size: Frame buffer size (default 30 = 5s at 6fps)
            enable_gpt_analysis: Enable GPT Vision analysis on failures
            notification_callback: Async function to call on failure (MQTT, etc.)
        """
        self.user_id = user_id
        self.device_uuid = device_uuid
        self.conf_threshold = conf_threshold
        self.fps = fps
        self.notification_callback = notification_callback

        # Initialize AI detector
        self.detector = AIFailureDetector(conf_threshold=conf_threshold)

        # Initialize failure scene collector
        self.collector = FailureSceneCollector(
            user_id=user_id,
            device_uuid=device_uuid,
            buffer_size=buffer_size,
            fps=fps,
            enable_gpt_analysis=enable_gpt_analysis
        )

        # State
        self.is_monitoring = False
        self.last_failure_time = None
        self.cooldown_seconds = 60  # Don't detect same failure within 60s

        # Statistics
        self.frames_processed = 0
        self.failures_detected = 0
        self.start_time = None

        logger.info(
            f"[Monitor Worker] Initialized for device {device_uuid} "
            f"(threshold={conf_threshold}, fps={fps}, buffer={buffer_size})"
        )

    async def start_monitoring(self):
        """Start monitoring."""
        self.is_monitoring = True
        self.start_time = datetime.utcnow()
        logger.info(f"[Monitor Worker] Started monitoring device {self.device_uuid}")

    async def stop_monitoring(self):
        """Stop monitoring."""
        self.is_monitoring = False
        elapsed = (datetime.utcnow() - self.start_time).total_seconds() if self.start_time else 0
        logger.info(
            f"[Monitor Worker] Stopped monitoring device {self.device_uuid} "
            f"(duration={elapsed:.0f}s, frames={self.frames_processed}, failures={self.failures_detected})"
        )

    def _is_in_cooldown(self) -> bool:
        """Check if still in cooldown period after last failure."""
        if not self.last_failure_time:
            return False

        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed < self.cooldown_seconds

    async def process_frame(
        self,
        frame: np.ndarray,
        print_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a single frame from camera.

        Call this for every frame received from WebRTC.

        Args:
            frame: BGR image (numpy array)
            print_context: Optional print state info (temps, layer, progress, etc.)

        Returns:
            Dictionary with:
                - failure_detected: bool
                - result: Detection result
                - scene_collected: bool (if failure was collected)
                - scene_id: UUID if scene was collected
        """
        if not self.is_monitoring:
            return {"failure_detected": False, "scene_collected": False}

        self.frames_processed += 1

        # 1. Add frame to buffer
        self.collector.add_frame(frame)

        # 2. Run AI detection
        result = await self.detector.detect_failure(frame)

        # 3. If failure detected and not in cooldown
        if result.has_failure and not self._is_in_cooldown():
            self.failures_detected += 1
            self.last_failure_time = datetime.utcnow()

            logger.warning(
                f"[Monitor Worker] Failure detected: {result.failure_type} "
                f"(confidence={result.confidence:.2%})"
            )

            # Create annotated frame
            annotated_frame = self.detector.annotate_frame(frame, result)

            # Collect failure scene
            try:
                collection_result = await self.collector.collect_failure_scene(
                    current_frame=frame,
                    annotated_frame=annotated_frame,
                    failure_type=result.failure_type,
                    confidence=result.confidence,
                    severity=result.severity,
                    detection_bbox=result.bbox,
                    print_context=print_context,
                    raw_prediction=result.details
                )

                logger.info(
                    f"[Monitor Worker] Scene collected: {collection_result['scene_id']}"
                )

                # Send notification
                if self.notification_callback:
                    try:
                        await self.notification_callback({
                            "type": "failure_detected",
                            "device_uuid": self.device_uuid,
                            "scene_id": collection_result['scene_id'],
                            "failure_type": result.failure_type,
                            "confidence": result.confidence,
                            "severity": result.severity,
                            "urls": collection_result['urls'],
                            "gpt_analysis": collection_result.get('gpt_analysis'),
                            "print_context": print_context,
                        })
                    except Exception as e:
                        logger.error(f"[Monitor Worker] Notification failed: {e}")

                return {
                    "failure_detected": True,
                    "result": result.to_dict(),
                    "scene_collected": True,
                    "scene_id": collection_result['scene_id'],
                    "urls": collection_result['urls']
                }

            except Exception as e:
                logger.error(f"[Monitor Worker] Failed to collect scene: {e}")
                return {
                    "failure_detected": True,
                    "result": result.to_dict(),
                    "scene_collected": False,
                    "error": str(e)
                }

        # No failure or in cooldown
        return {
            "failure_detected": result.has_failure,
            "result": result.to_dict() if result.has_failure else None,
            "scene_collected": False,
            "in_cooldown": self._is_in_cooldown()
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current monitoring status."""
        uptime = (datetime.utcnow() - self.start_time).total_seconds() if self.start_time else 0

        return {
            "is_monitoring": self.is_monitoring,
            "device_uuid": self.device_uuid,
            "uptime_seconds": uptime,
            "frames_processed": self.frames_processed,
            "failures_detected": self.failures_detected,
            "buffer_status": self.collector.get_buffer_status(),
            "detector_stats": self.detector.get_statistics(),
            "in_cooldown": self._is_in_cooldown(),
            "cooldown_remaining": max(0, self.cooldown_seconds - (
                (datetime.utcnow() - self.last_failure_time).total_seconds()
                if self.last_failure_time else 0
            ))
        }


# ============================================================================
# Test Function
# ============================================================================

async def test_monitoring_worker():
    """Test monitoring worker with simulated frames."""
    print("=" * 80)
    print("Print Monitoring Worker Test")
    print("=" * 80)

    # Test user/device
    test_user_id = "00000000-0000-0000-0000-000000000000"
    test_device_uuid = "test-device-001"

    # Mock notification callback
    async def mock_notification(data):
        print(f"\n📢 NOTIFICATION SENT:")
        print(f"   Type: {data['type']}")
        print(f"   Failure: {data['failure_type']} ({data['confidence']:.0%})")
        print(f"   Scene ID: {data['scene_id']}")
        if data.get('gpt_analysis'):
            print(f"   GPT: {data['gpt_analysis']['description'][:50]}...")

    # Initialize worker
    try:
        worker = PrintMonitoringWorker(
            user_id=test_user_id,
            device_uuid=test_device_uuid,
            conf_threshold=0.7,
            fps=6,
            enable_gpt_analysis=True,
            notification_callback=mock_notification
        )
        print("✅ Worker initialized")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return

    # Start monitoring
    await worker.start_monitoring()
    print("\n🔍 Monitoring started")

    # Simulate 20 normal frames
    print("\n📸 Processing 20 normal frames...")
    for i in range(20):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(frame, (200, 150), (440, 330), (100, 100, 100), -1)
        cv2.putText(frame, f"Frame {i}", (220, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        result = await worker.process_frame(
            frame,
            print_context={
                "layer_number": 50 + i,
                "print_progress": 25.0 + i,
                "nozzle_temp": 210,
                "bed_temp": 60,
                "print_speed": 50
            }
        )

        if result['failure_detected']:
            print(f"   ⚠️  Frame {i}: Failure detected!")

    print(f"✅ Processed 20 normal frames")

    # Simulate failure frame
    print("\n🚨 Simulating failure (spaghetti)...")
    failure_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    for _ in range(200):
        pt1 = (np.random.randint(0, 640), np.random.randint(0, 480))
        pt2 = (np.random.randint(0, 640), np.random.randint(0, 480))
        cv2.line(failure_frame, pt1, pt2, (255, 255, 255), 1)

    result = await worker.process_frame(
        failure_frame,
        print_context={
            "layer_number": 152,
            "print_progress": 45.3,
            "nozzle_temp": 210,
            "bed_temp": 60,
            "print_speed": 50
        }
    )

    if result['failure_detected']:
        print(f"✅ Failure detected and collected!")
        print(f"   Scene ID: {result.get('scene_id')}")
    else:
        print(f"❌ Failure not detected")

    # Get status
    print("\n📊 Worker Status:")
    status = worker.get_status()
    for key, value in status.items():
        if key not in ['buffer_status', 'detector_stats']:
            print(f"   {key}: {value}")

    # Stop monitoring
    await worker.stop_monitoring()

    print("\n" + "=" * 80)
    print("✅ Test completed!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_monitoring_worker())
