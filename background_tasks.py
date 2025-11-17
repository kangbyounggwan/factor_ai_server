"""
Background task processing for async model generation.
"""
import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger("uvicorn.error")

# Store background tasks
_background_tasks: Dict[str, asyncio.Task] = {}


async def process_image_to_3d_background(
    task_id: str,
    endpoint: str,
    user_id: str = None,
    prompt: str = None,
    source_image_url: str = None
):
    """
    Background task to complete image-to-3d processing.
    This includes downloading, Blender post-processing, STL conversion, and Supabase upload.

    Args:
        task_id: Meshy task ID
        endpoint: Meshy API endpoint
        user_id: User ID for Supabase integration (optional)
        prompt: Prompt used for generation (optional)
        source_image_url: Source image URL (optional)
    """
    from modelling_api import _complete_image_to_3d

    try:
        logger.info("[BackgroundTask] Starting for task_id=%s, user_id=%s", task_id, user_id)
        result = await _complete_image_to_3d(
            task_id=task_id,
            endpoint=endpoint,
            user_id=user_id,
            prompt=prompt,
            source_image_url=source_image_url
        )
        logger.info("[BackgroundTask] Completed for task_id=%s", task_id)
        return result
    except Exception as e:
        logger.error("[BackgroundTask] Failed for task_id=%s: %s", task_id, str(e))
        raise
    finally:
        # Clean up task from registry
        if task_id in _background_tasks:
            del _background_tasks[task_id]


async def process_text_to_3d_background(
    preview_task_id: str,
    endpoint: str,
    texture_prompt: str = None,
    user_id: str = None,
    prompt: str = None
):
    """
    Background task to complete text-to-3d processing.
    This includes downloading, Blender post-processing, STL conversion, and Supabase upload.

    Args:
        preview_task_id: Meshy preview task ID
        endpoint: Meshy API endpoint
        texture_prompt: Optional texture prompt (unused in current implementation)
        user_id: User ID for Supabase integration (optional)
        prompt: Original text prompt used for generation (optional)
    """
    from modelling_api import _complete_text_to_3d_with_refine

    try:
        logger.info("[BackgroundTask] Starting text-to-3d for task_id=%s, user_id=%s", preview_task_id, user_id)
        result = await _complete_text_to_3d_with_refine(
            preview_task_id=preview_task_id,
            endpoint=endpoint,
            texture_prompt=texture_prompt,
            user_id=user_id,
            prompt=prompt
        )
        logger.info("[BackgroundTask] Completed text-to-3d for task_id=%s", preview_task_id)
        return result
    except Exception as e:
        import traceback
        logger.error("[BackgroundTask] Failed for task_id=%s: %s", preview_task_id, str(e))
        logger.error("[BackgroundTask] Full traceback:\n%s", traceback.format_exc())
        raise
    finally:
        # Clean up task from registry
        if preview_task_id in _background_tasks:
            del _background_tasks[preview_task_id]


def start_background_task(task_id: str, coro):
    """
    Start a background task and register it.

    Args:
        task_id: Unique task identifier
        coro: Coroutine to run in background
    """
    task = asyncio.create_task(coro)
    _background_tasks[task_id] = task
    logger.info("[BackgroundTask] Registered task_id=%s", task_id)
    return task


def get_background_task(task_id: str) -> asyncio.Task:
    """Get a background task by task_id."""
    return _background_tasks.get(task_id)


def is_task_running(task_id: str) -> bool:
    """Check if a task is still running in background."""
    task = _background_tasks.get(task_id)
    return task is not None and not task.done()
