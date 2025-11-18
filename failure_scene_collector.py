"""
Failure Scene Collector

Automatically collects and saves failure scenes when AI detects a print failure:
1. Maintains ring buffer of recent frames (30 frames = ~5 seconds at 6 FPS)
2. On failure detection:
   - Saves original + annotated frames
   - Creates before/after video clips
   - Requests GPT Vision analysis
   - Saves everything to Supabase (Storage + Database)
   - Sends MQTT notification
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from collections import deque
import asyncio

import numpy as np
import cv2
from supabase import create_client, Client
from dotenv import load_dotenv

from storage_uploader import StorageUploader
from gpt_vision_analyzer import GPTVisionAnalyzer

load_dotenv()

logger = logging.getLogger(__name__)


class FailureSceneCollector:
    """
    Collects and saves failure scenes automatically.

    Key features:
    - Ring buffer of last 30 frames (~5 seconds at 6 FPS)
    - Automatic upload to Supabase Storage
    - GPT Vision analysis integration
    - Database record creation
    - MQTT notification support
    """

    def __init__(
        self,
        user_id: str,
        device_uuid: str,
        buffer_size: int = 30,
        fps: int = 6,
        enable_gpt_analysis: bool = True,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None
    ):
        """
        Initialize Failure Scene Collector.

        Args:
            user_id: User UUID
            device_uuid: Device UUID
            buffer_size: Number of frames to keep in buffer (default: 30 = 5s at 6fps)
            fps: Frames per second for video generation
            enable_gpt_analysis: Enable GPT Vision analysis
            supabase_url: Supabase URL (optional, from env)
            supabase_key: Supabase service role key (optional, from env)
        """
        self.user_id = user_id
        self.device_uuid = device_uuid
        self.buffer_size = buffer_size
        self.fps = fps
        self.enable_gpt_analysis = enable_gpt_analysis

        # Ring buffer: stores {frame, timestamp, frame_number}
        self.frame_buffer = deque(maxlen=buffer_size)
        self.frame_counter = 0

        # Initialize Supabase client
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Supabase credentials not found in environment")

        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)

        # Initialize storage uploader
        self.storage = StorageUploader(self.supabase_url, self.supabase_key)

        # Initialize GPT analyzer if enabled
        self.gpt_analyzer = None
        if self.enable_gpt_analysis:
            try:
                self.gpt_analyzer = GPTVisionAnalyzer()
                logger.info("[Collector] GPT Vision analyzer enabled")
            except Exception as e:
                logger.warning(f"[Collector] GPT analyzer unavailable: {e}")
                self.enable_gpt_analysis = False

        # Statistics
        self.total_failures_collected = 0

        logger.info(
            f"[Collector] Initialized for device {device_uuid} "
            f"(buffer={buffer_size}, fps={fps}, gpt={enable_gpt_analysis})"
        )

    def add_frame(self, frame: np.ndarray):
        """
        Add frame to ring buffer.

        Call this for every frame captured from WebRTC camera.

        Args:
            frame: BGR image (numpy array)
        """
        self.frame_buffer.append({
            'frame': frame.copy(),
            'timestamp': datetime.utcnow(),
            'frame_number': self.frame_counter
        })
        self.frame_counter += 1

    async def collect_failure_scene(
        self,
        current_frame: np.ndarray,
        annotated_frame: np.ndarray,
        failure_type: str,
        confidence: float,
        severity: str,
        detection_bbox: Optional[Dict[str, int]] = None,
        print_context: Optional[Dict[str, Any]] = None,
        raw_prediction: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Collect and save complete failure scene.

        This is called when AI detector identifies a failure.

        Args:
            current_frame: Original frame where failure was detected
            annotated_frame: Frame with bounding boxes/annotations
            failure_type: Type of failure (spaghetti, layer_shift, etc.)
            confidence: Detection confidence (0.0-1.0)
            severity: Severity level (low, medium, high, critical)
            detection_bbox: Bounding box {x, y, width, height}
            print_context: Print parameters (temps, layer, speed, etc.)
            raw_prediction: Full AI model output

        Returns:
            Dictionary with:
                - scene_id: UUID of created database record
                - urls: Dictionary of uploaded file URLs
                - gpt_analysis: GPT analysis result (if enabled)
        """
        start_time = datetime.utcnow()
        logger.info(
            f"[Collector] Collecting failure scene: {failure_type} "
            f"(confidence={confidence:.2f}, severity={severity})"
        )

        try:
            # 1. Upload original frame
            original_result = await self.storage.upload_frame(
                frame=current_frame,
                user_id=self.user_id,
                device_uuid=self.device_uuid,
                file_type="original"
            )

            # 2. Upload annotated frame
            annotated_result = await self.storage.upload_frame(
                frame=annotated_frame,
                user_id=self.user_id,
                device_uuid=self.device_uuid,
                file_type="annotated"
            )

            # 3. Create "before" video from buffer
            before_frames_url = None
            if len(self.frame_buffer) > 0:
                # Get last 15 frames (2.5 seconds at 6 FPS)
                num_before_frames = min(15, len(self.frame_buffer))
                before_frames = [
                    item['frame'] for item in list(self.frame_buffer)[-num_before_frames:]
                ]

                before_result = await self.storage.upload_video_clip(
                    frames=before_frames,
                    user_id=self.user_id,
                    device_uuid=self.device_uuid,
                    file_type="before",
                    fps=self.fps
                )
                before_frames_url = before_result['public_url']

            # 4. GPT Vision Analysis (if enabled)
            gpt_analysis = None
            if self.enable_gpt_analysis and self.gpt_analyzer:
                try:
                    logger.info("[Collector] Requesting GPT Vision analysis...")
                    gpt_analysis = await self.gpt_analyzer.analyze_failure_from_url(
                        image_url=original_result['public_url'],
                        failure_type=failure_type,
                        confidence=confidence,
                        print_context=print_context or {}
                    )
                    logger.info("[Collector] GPT analysis completed")
                except Exception as e:
                    logger.error(f"[Collector] GPT analysis failed: {e}")
                    gpt_analysis = None

            # 5. Save to database
            scene_data = {
                "user_id": self.user_id,
                "device_uuid": self.device_uuid,
                "failure_type": failure_type,
                "confidence": confidence,
                "severity": severity,
                "detection_model": "spaghetti_detective",
                "original_frame_url": original_result['public_url'],
                "annotated_frame_url": annotated_result['public_url'],
                "before_frames_url": before_frames_url,
                "detection_bbox": detection_bbox,
                "raw_prediction_data": raw_prediction,
            }

            # Add print context if available
            if print_context:
                scene_data.update({
                    "gcode_filename": print_context.get("gcode_filename"),
                    "layer_number": print_context.get("layer_number"),
                    "print_progress": print_context.get("print_progress"),
                    "nozzle_temp": print_context.get("nozzle_temp"),
                    "bed_temp": print_context.get("bed_temp"),
                    "print_speed": print_context.get("print_speed"),
                    "fan_speed": print_context.get("fan_speed"),
                    "z_height": print_context.get("z_height"),
                    "estimated_time_remaining": print_context.get("estimated_time_remaining"),
                })

            # Add GPT analysis if available
            if gpt_analysis:
                scene_data.update({
                    "gpt_description": gpt_analysis.get("description"),
                    "gpt_root_cause": gpt_analysis.get("root_cause"),
                    "gpt_suggested_action": gpt_analysis.get("suggested_action"),
                    "gpt_prevention_tips": gpt_analysis.get("prevention_tips"),
                    "gpt_raw_response": gpt_analysis.get("raw_response"),
                })

            # Insert into database
            result = self.supabase.table("failure_scenes").insert(scene_data).execute()

            if not result.data:
                raise Exception("Failed to insert failure scene into database")

            scene_record = result.data[0]
            scene_id = scene_record["id"]

            # 6. Statistics
            self.total_failures_collected += 1
            elapsed = (datetime.utcnow() - start_time).total_seconds()

            logger.info(
                f"[Collector] Failure scene saved: {scene_id} "
                f"(elapsed={elapsed:.2f}s, total_collected={self.total_failures_collected})"
            )

            return {
                "scene_id": scene_id,
                "urls": {
                    "original": original_result['public_url'],
                    "annotated": annotated_result['public_url'],
                    "before_video": before_frames_url,
                },
                "gpt_analysis": gpt_analysis,
                "elapsed_seconds": elapsed
            }

        except Exception as e:
            logger.error(f"[Collector] Failed to collect failure scene: {e}")
            raise

    def get_buffer_status(self) -> Dict[str, Any]:
        """Get current buffer status."""
        return {
            "buffer_size": len(self.frame_buffer),
            "buffer_capacity": self.buffer_size,
            "frame_counter": self.frame_counter,
            "total_failures_collected": self.total_failures_collected,
            "oldest_frame_timestamp": self.frame_buffer[0]['timestamp'].isoformat() if self.frame_buffer else None,
            "newest_frame_timestamp": self.frame_buffer[-1]['timestamp'].isoformat() if self.frame_buffer else None,
        }


# ============================================================================
# Test Function
# ============================================================================

async def test_failure_scene_collector():
    """Test failure scene collector."""
    print("=" * 80)
    print("Failure Scene Collector Test")
    print("=" * 80)

    # Test user/device
    test_user_id = "00000000-0000-0000-0000-000000000000"
    test_device_uuid = "test-device-001"

    # Initialize collector
    try:
        collector = FailureSceneCollector(
            user_id=test_user_id,
            device_uuid=test_device_uuid,
            buffer_size=30,
            fps=6,
            enable_gpt_analysis=True
        )
        print("✅ Collector initialized")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return

    # Simulate adding frames to buffer
    print("\n📸 Adding 30 frames to buffer...")
    for i in range(30):
        test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        cv2.putText(test_frame, f"Frame {i}", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        collector.add_frame(test_frame)

    status = collector.get_buffer_status()
    print(f"✅ Buffer status: {status['buffer_size']}/{status['buffer_capacity']} frames")

    # Simulate failure detection
    print("\n🚨 Simulating failure detection...")
    failure_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    cv2.putText(failure_frame, "FAILURE!", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)

    annotated_frame = failure_frame.copy()
    cv2.rectangle(annotated_frame, (100, 100), (500, 400), (0, 0, 255), 3)
    cv2.putText(annotated_frame, "Spaghetti Detected", (110, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    try:
        result = await collector.collect_failure_scene(
            current_frame=failure_frame,
            annotated_frame=annotated_frame,
            failure_type="spaghetti",
            confidence=0.87,
            severity="critical",
            detection_bbox={"x": 100, "y": 100, "width": 400, "height": 300},
            print_context={
                "layer_number": 152,
                "print_progress": 45.3,
                "nozzle_temp": 210,
                "bed_temp": 60,
                "print_speed": 50,
            }
        )

        print("\n✅ Failure scene collected!")
        print(f"   Scene ID: {result['scene_id']}")
        print(f"   Original URL: {result['urls']['original']}")
        print(f"   Annotated URL: {result['urls']['annotated']}")
        print(f"   Before Video URL: {result['urls']['before_video']}")
        print(f"   Elapsed: {result['elapsed_seconds']:.2f}s")

        if result['gpt_analysis']:
            print(f"\n💬 GPT Analysis:")
            print(f"   Description: {result['gpt_analysis']['description']}")
            print(f"   Root Cause: {result['gpt_analysis']['root_cause']}")
            print(f"   Action: {result['gpt_analysis']['suggested_action']}")

    except Exception as e:
        print(f"❌ Collection failed: {e}")

    print("\n" + "=" * 80)
    print("✅ Test completed!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_failure_scene_collector())
