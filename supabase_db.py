"""
Supabase Database Helper Functions for AI Server

Handles database operations for ai_generated_models table
"""
from supabase import Client
from supabase_client import get_supabase_client
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger("uvicorn.error")


def create_ai_model_record(
    user_id: str,
    model_id: str,
    generation_type: str,
    prompt: Optional[str] = None,
    source_image_url: Optional[str] = None,
    model_name: Optional[str] = None,
    supabase: Client = None
) -> dict:
    """
    Create initial AI model record in database

    Args:
        user_id: User ID
        model_id: Model ID (UUID)
        generation_type: 'text_to_3d' or 'image_to_3d'
        prompt: Text prompt (for text_to_3d)
        source_image_url: Source image URL (for image_to_3d)
        model_name: Optional model name
        supabase: Supabase client (optional)

    Returns:
        dict: Created record
    """
    if supabase is None:
        supabase = get_supabase_client()

    if model_name is None:
        model_name = f"AI Model {model_id[:8]}"

    data = {
        "id": model_id,
        "user_id": user_id,
        "generation_type": generation_type,
        "prompt": prompt,
        "source_image_url": source_image_url,
        "model_name": model_name,
        "file_format": "glb",
        "storage_path": "",  # Will be updated after upload
        "status": "processing",
        "is_favorite": False,
        "is_public": False,
        "printed_count": 0
    }

    logger.info(f"[DB] Creating ai_generated_models record: {model_id}")

    try:
        response = supabase.table("ai_generated_models").insert(data).execute()
        logger.info(f"[DB] Record created successfully: {model_id}")
        return response.data[0] if response.data else {}
    except Exception as e:
        logger.error(f"[DB] Failed to create record: {e}")
        raise


def update_ai_model_record(
    model_id: str,
    updates: Dict[str, Any],
    supabase: Client = None
) -> dict:
    """
    Update AI model record

    Args:
        model_id: Model ID
        updates: Dictionary of fields to update
        supabase: Supabase client (optional)

    Returns:
        dict: Updated record
    """
    if supabase is None:
        supabase = get_supabase_client()

    # Add updated_at timestamp
    updates["updated_at"] = datetime.utcnow().isoformat()

    logger.info(f"[DB] Updating ai_generated_models: {model_id}, fields: {list(updates.keys())}")

    try:
        response = supabase.table("ai_generated_models")\
            .update(updates)\
            .eq("id", model_id)\
            .execute()

        logger.info(f"[DB] Record updated successfully: {model_id}")
        return response.data[0] if response.data else {}
    except Exception as e:
        logger.error(f"[DB] Failed to update record: {e}")
        raise


def update_model_to_completed(
    model_id: str,
    storage_path: str,
    download_url: str,
    thumbnail_url: Optional[str] = None,
    stl_storage_path: Optional[str] = None,
    stl_download_url: Optional[str] = None,
    file_size: Optional[int] = None,
    model_dimensions: Optional[dict] = None,
    supabase: Client = None
) -> dict:
    """
    Update model status to completed with file URLs

    Args:
        model_id: Model ID
        storage_path: Storage path for GLB file
        download_url: Public download URL for GLB
        thumbnail_url: Thumbnail URL (optional)
        stl_storage_path: STL storage path (optional)
        stl_download_url: STL download URL (optional)
        file_size: File size in bytes (optional)
        model_dimensions: 3D dimensions {x, y, z} (optional)
        supabase: Supabase client (optional)

    Returns:
        dict: Updated record
    """
    updates = {
        "status": "completed",
        "storage_path": storage_path,
        "download_url": download_url,
    }

    if thumbnail_url:
        updates["thumbnail_url"] = thumbnail_url

    if stl_storage_path:
        updates["stl_storage_path"] = stl_storage_path

    if stl_download_url:
        updates["stl_download_url"] = stl_download_url

    if file_size:
        updates["file_size"] = file_size

    if model_dimensions:
        updates["model_dimensions"] = model_dimensions

    return update_ai_model_record(model_id, updates, supabase)


def update_model_to_failed(
    model_id: str,
    error_message: str,
    supabase: Client = None
) -> dict:
    """
    Update model status to failed

    Args:
        model_id: Model ID
        error_message: Error message
        supabase: Supabase client (optional)

    Returns:
        dict: Updated record
    """
    updates = {
        "status": "failed",
        # Note: There's no error_message field in ai_generated_models table
        # We'll need to add this field or store it elsewhere
    }

    logger.warning(f"[DB] Marking model as failed: {model_id}, error: {error_message}")

    return update_ai_model_record(model_id, updates, supabase)


def get_ai_model(
    model_id: str,
    supabase: Client = None
) -> Optional[dict]:
    """
    Get AI model record

    Args:
        model_id: Model ID
        supabase: Supabase client (optional)

    Returns:
        dict or None: Model record
    """
    if supabase is None:
        supabase = get_supabase_client()

    try:
        response = supabase.table("ai_generated_models")\
            .select("*")\
            .eq("id", model_id)\
            .single()\
            .execute()

        return response.data if response.data else None
    except Exception as e:
        logger.error(f"[DB] Failed to get model: {e}")
        return None


def list_user_models(
    user_id: str,
    limit: int = 20,
    offset: int = 0,
    supabase: Client = None
) -> list:
    """
    List user's AI models

    Args:
        user_id: User ID
        limit: Number of records to return
        offset: Offset for pagination
        supabase: Supabase client (optional)

    Returns:
        list: List of model records
    """
    if supabase is None:
        supabase = get_supabase_client()

    try:
        response = supabase.table("ai_generated_models")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .range(offset, offset + limit - 1)\
            .execute()

        return response.data if response.data else []
    except Exception as e:
        logger.error(f"[DB] Failed to list models: {e}")
        return []


if __name__ == "__main__":
    # Test database functions
    import uuid
    print("Testing Supabase Database functions...")

    test_model_id = str(uuid.uuid4())

    try:
        # Use proper UUID for user_id (create a test user ID)
        test_user_id = str(uuid.uuid4())

        # Create record
        record = create_ai_model_record(
            user_id=test_user_id,
            model_id=test_model_id,
            generation_type="text_to_3d",
            prompt="A cute robot",
            model_name="Test Robot Model"
        )
        print(f"✅ Created record: {record.get('id')}")

        # Update to completed
        updated = update_model_to_completed(
            model_id=test_model_id,
            storage_path=f"test_user_123/generated-models/{test_model_id}.glb",
            download_url=f"https://example.com/{test_model_id}.glb",
            thumbnail_url=f"https://example.com/{test_model_id}.png"
        )
        print(f"✅ Updated to completed: status={updated.get('status')}")

        # Get record
        fetched = get_ai_model(test_model_id)
        print(f"✅ Fetched record: {fetched.get('model_name')}")

        # List models
        models = list_user_models(test_user_id, limit=5)
        print(f"✅ Listed {len(models)} models")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
