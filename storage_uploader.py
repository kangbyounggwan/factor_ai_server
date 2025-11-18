"""
Supabase Storage Uploader for Failure Scene Media

This module handles uploading failure detection media to Supabase Storage:
- Original frames (failure-frames bucket)
- Annotated frames with bounding boxes (failure-frames bucket)
- Before/after video clips (failure-videos bucket)
- Segmentation masks (failure-masks bucket)
"""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import io

import cv2
import numpy as np
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class StorageUploader:
    """
    Handles uploading failure scene media to Supabase Storage.

    Bucket structure:
    - failure-frames/{user_id}/{device_uuid}/{timestamp}_original.jpg
    - failure-frames/{user_id}/{device_uuid}/{timestamp}_annotated.jpg
    - failure-videos/{user_id}/{device_uuid}/{timestamp}_before.mp4
    - failure-videos/{user_id}/{device_uuid}/{timestamp}_after.mp4
    - failure-masks/{user_id}/{device_uuid}/{timestamp}_mask.png
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None
    ):
        """
        Initialize Storage Uploader.

        Args:
            supabase_url: Supabase project URL (defaults to env SUPABASE_URL)
            supabase_key: Supabase service role key (defaults to env SUPABASE_SERVICE_ROLE_KEY)
        """
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not self.supabase_url or not self.supabase_key:
            raise ValueError(
                "Supabase credentials not found. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env"
            )

        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        logger.info("[Storage] Initialized Supabase Storage uploader")

    def _generate_file_path(
        self,
        user_id: str,
        device_uuid: str,
        file_type: str,
        extension: str = "jpg"
    ) -> str:
        """
        Generate storage file path.

        Args:
            user_id: User UUID
            device_uuid: Device UUID
            file_type: Type of file (original, annotated, before, after, mask)
            extension: File extension (jpg, mp4, png)

        Returns:
            Storage path: {user_id}/{device_uuid}/{timestamp}_{file_type}.{extension}
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{timestamp}_{file_type}.{extension}"
        return f"{user_id}/{device_uuid}/{filename}"

    async def upload_frame(
        self,
        frame: np.ndarray,
        user_id: str,
        device_uuid: str,
        file_type: str = "original",
        quality: int = 90
    ) -> Dict[str, str]:
        """
        Upload a single frame image to failure-frames bucket.

        Args:
            frame: BGR image (numpy array)
            user_id: User UUID
            device_uuid: Device UUID
            file_type: 'original' or 'annotated'
            quality: JPEG quality (1-100)

        Returns:
            Dictionary with:
                - path: Storage path
                - public_url: Public URL to access the image
        """
        try:
            # Encode frame to JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            success, encoded = cv2.imencode('.jpg', frame, encode_param)

            if not success:
                raise ValueError("Failed to encode frame to JPEG")

            # Generate file path
            file_path = self._generate_file_path(user_id, device_uuid, file_type, "jpg")

            # Upload to Supabase Storage
            result = self.client.storage.from_("failure-frames").upload(
                path=file_path,
                file=encoded.tobytes(),
                file_options={"content-type": "image/jpeg"}
            )

            # Get public URL
            public_url = self.client.storage.from_("failure-frames").get_public_url(file_path)

            logger.info(f"[Storage] Uploaded {file_type} frame: {file_path}")

            return {
                "path": file_path,
                "public_url": public_url
            }

        except Exception as e:
            logger.error(f"[Storage] Failed to upload frame: {e}")
            raise

    async def upload_video_clip(
        self,
        frames: list,
        user_id: str,
        device_uuid: str,
        file_type: str = "before",
        fps: int = 6
    ) -> Dict[str, str]:
        """
        Upload video clip from frame list to failure-videos bucket.

        Args:
            frames: List of BGR images (numpy arrays)
            user_id: User UUID
            device_uuid: Device UUID
            file_type: 'before' or 'after'
            fps: Frames per second

        Returns:
            Dictionary with path and public_url
        """
        if not frames:
            raise ValueError("No frames provided for video clip")

        try:
            # Generate file path
            file_path = self._generate_file_path(user_id, device_uuid, file_type, "mp4")

            # Create temporary video file
            temp_path = f"./temp_{file_type}.mp4"
            height, width = frames[0].shape[:2]

            # Use H.264 codec for wide compatibility
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(temp_path, fourcc, fps, (width, height))

            for frame in frames:
                out.write(frame)

            out.release()

            # Read video file
            with open(temp_path, 'rb') as f:
                video_bytes = f.read()

            # Upload to Supabase Storage
            result = self.client.storage.from_("failure-videos").upload(
                path=file_path,
                file=video_bytes,
                file_options={"content-type": "video/mp4"}
            )

            # Get public URL
            public_url = self.client.storage.from_("failure-videos").get_public_url(file_path)

            # Cleanup temp file
            os.remove(temp_path)

            logger.info(f"[Storage] Uploaded {file_type} video: {file_path} ({len(frames)} frames)")

            return {
                "path": file_path,
                "public_url": public_url
            }

        except Exception as e:
            logger.error(f"[Storage] Failed to upload video clip: {e}")
            # Cleanup on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    async def upload_mask(
        self,
        mask: np.ndarray,
        user_id: str,
        device_uuid: str
    ) -> Dict[str, str]:
        """
        Upload segmentation mask to failure-masks bucket.

        Args:
            mask: Binary mask (numpy array)
            user_id: User UUID
            device_uuid: Device UUID

        Returns:
            Dictionary with path and public_url
        """
        try:
            # Encode mask to PNG (lossless)
            success, encoded = cv2.imencode('.png', mask)

            if not success:
                raise ValueError("Failed to encode mask to PNG")

            # Generate file path
            file_path = self._generate_file_path(user_id, device_uuid, "mask", "png")

            # Upload to Supabase Storage
            result = self.client.storage.from_("failure-masks").upload(
                path=file_path,
                file=encoded.tobytes(),
                file_options={"content-type": "image/png"}
            )

            # Get public URL
            public_url = self.client.storage.from_("failure-masks").get_public_url(file_path)

            logger.info(f"[Storage] Uploaded mask: {file_path}")

            return {
                "path": file_path,
                "public_url": public_url
            }

        except Exception as e:
            logger.error(f"[Storage] Failed to upload mask: {e}")
            raise

    async def delete_file(self, bucket: str, file_path: str) -> bool:
        """
        Delete a file from storage.

        Args:
            bucket: Bucket name (failure-frames, failure-videos, failure-masks)
            file_path: Path to file in bucket

        Returns:
            True if successful
        """
        try:
            self.client.storage.from_(bucket).remove([file_path])
            logger.info(f"[Storage] Deleted {bucket}/{file_path}")
            return True

        except Exception as e:
            logger.error(f"[Storage] Failed to delete file: {e}")
            return False


# ============================================================================
# Test Function
# ============================================================================

async def test_storage_uploader():
    """Test storage uploader with sample data."""
    print("=" * 80)
    print("Storage Uploader Test")
    print("=" * 80)

    # Initialize uploader
    try:
        uploader = StorageUploader()
        print("✅ Uploader initialized")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return

    # Create test frame
    test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    cv2.putText(test_frame, "TEST FRAME", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)

    # Test user/device IDs
    test_user_id = "00000000-0000-0000-0000-000000000000"
    test_device_uuid = "test-device-001"

    print(f"\n📸 Testing frame upload...")
    try:
        result = await uploader.upload_frame(
            frame=test_frame,
            user_id=test_user_id,
            device_uuid=test_device_uuid,
            file_type="original"
        )
        print(f"✅ Frame uploaded:")
        print(f"   Path: {result['path']}")
        print(f"   URL: {result['public_url']}")

    except Exception as e:
        print(f"❌ Frame upload failed: {e}")

    print(f"\n🎬 Testing video clip upload...")
    try:
        # Create 10 test frames
        test_frames = [test_frame.copy() for _ in range(10)]
        for i, frame in enumerate(test_frames):
            cv2.putText(frame, f"Frame {i}", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        result = await uploader.upload_video_clip(
            frames=test_frames,
            user_id=test_user_id,
            device_uuid=test_device_uuid,
            file_type="before",
            fps=6
        )
        print(f"✅ Video uploaded:")
        print(f"   Path: {result['path']}")
        print(f"   URL: {result['public_url']}")

    except Exception as e:
        print(f"❌ Video upload failed: {e}")

    print("\n" + "=" * 80)
    print("✅ Test completed!")
    print("=" * 80)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_storage_uploader())
