"""
Background task processing for async model generation.
"""
import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger("uvicorn.error")

# Store background tasks
_background_tasks: Dict[str, asyncio.Task] = {}


async def process_image_to_3d_background(task_id: str, endpoint: str):
    """
    Background task to complete image-to-3d processing.
    This includes downloading, Blender post-processing, and STL conversion.
    """
    from modelling_api import _complete_image_to_3d

    try:
        logger.info("[BackgroundTask] Starting for task_id=%s", task_id)
        result = await _complete_image_to_3d(task_id, endpoint)
        logger.info("[BackgroundTask] Completed for task_id=%s", task_id)
        return result
    except Exception as e:
        logger.error("[BackgroundTask] Failed for task_id=%s: %s", task_id, str(e))
        raise
    finally:
        # Clean up task from registry
        if task_id in _background_tasks:
            del _background_tasks[task_id]


async def process_text_to_3d_background(preview_task_id: str, endpoint: str, texture_prompt: str = None):
    """
    Background task to complete text-to-3d processing.
    """
    from modelling_api import _complete_text_to_3d_with_refine

    try:
        logger.info("[BackgroundTask] Starting text-to-3d for task_id=%s", preview_task_id)
        result = await _complete_text_to_3d_with_refine(preview_task_id, endpoint, texture_prompt)
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
