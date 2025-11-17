"""
Supabase Storage Helper Functions for AI Server

Handles file uploads to Supabase Storage bucket 'ai-models'
"""
import os
import time
from supabase import Client
from supabase_client import get_supabase_client
import logging

logger = logging.getLogger("uvicorn.error")

BUCKET_NAME = "ai-models"


def upload_glb_to_storage(
    user_id: str,
    model_id: str,
    glb_file_path: str,
    supabase: Client = None
) -> dict:
    """
    Upload GLB file to Supabase Storage

    Args:
        user_id: User ID
        model_id: Model ID (UUID)
        glb_file_path: Local path to GLB file
        supabase: Supabase client (optional, will use default if not provided)

    Returns:
        dict: {
            "path": "user_id/generated-models/model_id.glb",
            "public_url": "https://...",
            "size": 123456
        }
    """
    if supabase is None:
        supabase = get_supabase_client()

    # Storage path
    storage_path = f"{user_id}/generated-models/{model_id}.glb"

    # Read file
    with open(glb_file_path, 'rb') as f:
        file_data = f.read()

    file_size = len(file_data)
    logger.info(f"[Storage] Uploading GLB: {storage_path}, size: {file_size / 1024:.2f} KB")

    # Upload to Supabase Storage
    start_time = time.time()
    try:
        response = supabase.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=file_data,
            file_options={
                "content-type": "model/gltf-binary",
                "cache-control": "3600",
                "upsert": "true"
            }
        )

        upload_duration = time.time() - start_time
        upload_speed_kbps = (file_size / 1024) / upload_duration if upload_duration > 0 else 0

        # Get public URL
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)

        logger.info(f"[Storage] ✅ GLB uploaded successfully in {upload_duration:.2f}s ({upload_speed_kbps:.2f} KB/s): {public_url}")

        return {
            "path": storage_path,
            "public_url": public_url,
            "size": file_size
        }

    except Exception as e:
        logger.error(f"[Storage] Failed to upload GLB: {e}")
        raise


def upload_stl_to_storage(
    user_id: str,
    model_id: str,
    stl_file_path: str,
    supabase: Client = None
) -> dict:
    """
    Upload STL file to Supabase Storage

    Args:
        user_id: User ID
        model_id: Model ID (UUID)
        stl_file_path: Local path to STL file
        supabase: Supabase client (optional)

    Returns:
        dict: {
            "path": "user_id/generated-models/model_id.stl",
            "public_url": "https://...",
            "size": 123456
        }
    """
    if supabase is None:
        supabase = get_supabase_client()

    # Storage path
    storage_path = f"{user_id}/generated-models/{model_id}.stl"

    # Read file
    with open(stl_file_path, 'rb') as f:
        file_data = f.read()

    file_size = len(file_data)
    logger.info(f"[Storage] Uploading STL: {storage_path}, size: {file_size / 1024:.2f} KB")

    # Upload to Supabase Storage
    start_time = time.time()
    try:
        response = supabase.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=file_data,
            file_options={
                "content-type": "application/octet-stream",
                "cache-control": "3600",
                "upsert": "true"
            }
        )

        upload_duration = time.time() - start_time
        upload_speed_kbps = (file_size / 1024) / upload_duration if upload_duration > 0 else 0

        # Get public URL
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)

        logger.info(f"[Storage] ✅ STL uploaded successfully in {upload_duration:.2f}s ({upload_speed_kbps:.2f} KB/s): {public_url}")

        return {
            "path": storage_path,
            "public_url": public_url,
            "size": file_size
        }

    except Exception as e:
        logger.error(f"[Storage] Failed to upload STL: {e}")
        raise


def upload_thumbnail_to_storage(
    user_id: str,
    model_id: str,
    thumbnail_file_path: str,
    supabase: Client = None
) -> dict:
    """
    Upload thumbnail image to Supabase Storage

    Args:
        user_id: User ID
        model_id: Model ID (UUID)
        thumbnail_file_path: Local path to thumbnail file
        supabase: Supabase client (optional)

    Returns:
        dict: {
            "path": "user_id/thumbnails/model_id.png",
            "public_url": "https://...",
            "size": 123456
        }
    """
    if supabase is None:
        supabase = get_supabase_client()

    # Storage path
    storage_path = f"{user_id}/thumbnails/{model_id}.png"

    # Read file
    with open(thumbnail_file_path, 'rb') as f:
        file_data = f.read()

    file_size = len(file_data)
    logger.info(f"[Storage] Uploading thumbnail: {storage_path}, size: {file_size / 1024:.2f} KB")

    # Upload to Supabase Storage
    start_time = time.time()
    try:
        response = supabase.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=file_data,
            file_options={
                "content-type": "image/png",
                "cache-control": "3600",
                "upsert": "true"
            }
        )

        upload_duration = time.time() - start_time
        upload_speed_kbps = (file_size / 1024) / upload_duration if upload_duration > 0 else 0

        # Get public URL
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)

        logger.info(f"[Storage] ✅ Thumbnail uploaded successfully in {upload_duration:.2f}s ({upload_speed_kbps:.2f} KB/s): {public_url}")

        return {
            "path": storage_path,
            "public_url": public_url,
            "size": file_size
        }

    except Exception as e:
        logger.error(f"[Storage] Failed to upload thumbnail: {e}")
        raise


def delete_model_files(
    user_id: str,
    model_id: str,
    supabase: Client = None
) -> bool:
    """
    Delete all files associated with a model from Storage

    Args:
        user_id: User ID
        model_id: Model ID
        supabase: Supabase client (optional)

    Returns:
        bool: True if all deletions successful
    """
    if supabase is None:
        supabase = get_supabase_client()

    paths_to_delete = [
        f"{user_id}/generated-models/{model_id}.glb",
        f"{user_id}/generated-models/{model_id}.stl",
        f"{user_id}/thumbnails/{model_id}.png"
    ]

    success = True
    for path in paths_to_delete:
        try:
            supabase.storage.from_(BUCKET_NAME).remove([path])
            logger.info(f"[Storage] Deleted: {path}")
        except Exception as e:
            logger.warning(f"[Storage] Failed to delete {path}: {e}")
            success = False

    return success


if __name__ == "__main__":
    # Test storage functions
    print("Testing Supabase Storage functions...")

    # Test with a dummy file (create a small test file)
    test_file_path = "/tmp/test_model.glb"
    with open(test_file_path, 'wb') as f:
        f.write(b"TEST_GLB_DATA")

    try:
        result = upload_glb_to_storage(
            user_id="test_user",
            model_id="test_model_123",
            glb_file_path=test_file_path
        )
        print(f"✅ Upload successful: {result['public_url']}")

        # Delete test file
        delete_model_files("test_user", "test_model_123")
        print("✅ Delete successful")

    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        os.remove(test_file_path)
