import os
from typing import Any, Optional, Literal, Dict
import logging
import asyncio
import time
import uuid

logger = logging.getLogger("uvicorn.error")

# Ensure OUTPUT_DIR is set early so that utill can create the directory
_DEFAULT_OUTPUT_DIR = "./output"
if not os.getenv("OUTPUT_DIR", "").strip():
    os.environ["OUTPUT_DIR"] = _DEFAULT_OUTPUT_DIR


def _mask(token: str | None) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"

from pydantic import BaseModel, Field, ConfigDict
from utill import (
    get_httpx_client,
    to_data_url_from_url,
    to_data_url_from_bytes,
    pick_task_id,
    pick_model_url,
    maybe_download_result,
    download_thumbnail,
)

try:
    from blender_processor import process_model_with_blender, is_blender_available
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False
    logger.warning("[BlenderIntegration] blender_processor not available")

try:
    from supabase_storage import upload_glb_to_storage, upload_stl_to_storage, upload_thumbnail_to_storage
    from supabase_db import create_ai_model_record, update_model_to_completed, update_model_to_failed
    from supabase_client import get_supabase_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("[SupabaseIntegration] Supabase modules not available")

try:
    from mqtt_notification import send_model_completion_notification, send_model_failure_notification
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger.warning("[MQTTIntegration] MQTT notification module not available")

try:
    from file_cleanup import cleanup_model_files
    CLEANUP_AVAILABLE = True
except ImportError:
    CLEANUP_AVAILABLE = False
    logger.warning("[CleanupIntegration] File cleanup module not available")


MESHY_API_BASE = os.getenv("MESHY_API_BASE", "https://api.meshy.ai").rstrip("/")
MESHY_API_KEY = os.getenv("MESHY_API_KEY", "")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "").strip()

# Image-to-3D configuration
IMAGE_TO_3D_TOPOLOGY = os.getenv("IMAGE_TO_3D_TOPOLOGY", "triangle")
IMAGE_TO_3D_TARGET_POLYCOUNT = int(os.getenv("IMAGE_TO_3D_TARGET_POLYCOUNT", "15000"))

# Text-to-3D configuration
TEXT_TO_3D_ART_STYLE = os.getenv("TEXT_TO_3D_ART_STYLE", "realistic")  # realistic or sculpture
TEXT_TO_3D_ENABLE_PBR = os.getenv("TEXT_TO_3D_ENABLE_PBR", "true").lower() == "true"
TEXT_TO_3D_TOPOLOGY = os.getenv("TEXT_TO_3D_TOPOLOGY", "quad")  # quad or triangle
TEXT_TO_3D_TARGET_POLYCOUNT = int(os.getenv("TEXT_TO_3D_TARGET_POLYCOUNT", "30000"))

logger.info(
    "[MeshyCfg] base=%s key=%s output_dir=%s img_topology=%s img_polycount=%d txt_style=%s txt_pbr=%s txt_topology=%s txt_polycount=%d",
    MESHY_API_BASE,
    _mask(MESHY_API_KEY),
    os.getenv("OUTPUT_DIR"),
    IMAGE_TO_3D_TOPOLOGY,
    IMAGE_TO_3D_TARGET_POLYCOUNT,
    TEXT_TO_3D_ART_STYLE,
    TEXT_TO_3D_ENABLE_PBR,
    TEXT_TO_3D_TOPOLOGY,
    TEXT_TO_3D_TARGET_POLYCOUNT,
)


def meshy_headers_json() -> dict:
    return {
        "Authorization": f"Bearer {MESHY_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def meshy_headers_get() -> dict:
    return {
        "Authorization": f"Bearer {MESHY_API_KEY}",
        "Accept": "application/json",
    }


async def meshy_get_task(endpoint: str, task_id: str) -> dict:
    logger.info("[MeshyReq] GET %s/%s", endpoint, task_id)
    async with get_httpx_client() as client:
        r = await client.get(f"{endpoint}/{task_id}", headers=meshy_headers_get(), timeout=30)
        logger.info("[MeshyResp] GET %s -> %s", endpoint, r.status_code)
        r.raise_for_status()
        j = r.json()
        logger.info(
            "[MeshyTask] id=%s status=%s progress=%s url=%s",
            task_id,
            j.get("status"),
            j.get("progress"),
            pick_model_url(j),
        )
        return j


async def poll_until_done(endpoint: str, task_id: str, timeout_sec: int = 20 * 60, interval: int = 6) -> Dict[str, Any]:
    start = time.monotonic()
    last_status: Optional[str] = None
    retry_count = 0
    max_retries = 5  # 최대 5번 재시도 (약 30초)

    while True:
        if time.monotonic() - start > timeout_sec:
            raise TimeoutError(f"Timeout: task {task_id} not finished within {timeout_sec}s")

        try:
            task = await meshy_get_task(endpoint, task_id)
            retry_count = 0  # 성공하면 재시도 카운트 리셋
        except Exception as e:
            # 404 에러는 task가 아직 등록되지 않은 것일 수 있음
            if "404" in str(e) and retry_count < max_retries:
                retry_count += 1
                logger.warning("[Poll] Task not found yet (404), retry %d/%d for id=%s", retry_count, max_retries, task_id)
                await asyncio.sleep(interval)
                continue
            else:
                # 다른 에러거나 최대 재시도 횟수 초과
                raise

        status = str(task.get("status", "")).upper()
        progress = task.get("progress")
        if status != last_status:
            logger.info("[Poll] id=%s status=%s progress=%s", task_id, status, progress)
            last_status = status
        if status in ("PENDING", "PROCESSING", "IN_PROGRESS"):
            await asyncio.sleep(interval)
            continue
        if status == "FAILED":
            raise RuntimeError(f"Task failed: {task.get('task_error') or task}")
        if status == "SUCCEEDED":
            return task


# ---------- Models ----------
class OutputSpec(BaseModel):
    format: Literal["glb", "gltf", "obj"] = "glb"
    unit: Literal["mm", "cm", "m"] = "mm"
    scale: float = 1.0


class PrinterSpec(BaseModel):
    device_uuid: Optional[str] = None
    auto_slice: bool = False
    print: bool = False


class MetadataSpec(BaseModel):
    session_id: Optional[str] = None
    source: Optional[str] = None
    user_id: Optional[str] = None


class ImageSpec(BaseModel):
    url: str
    mime_type: str


class BaseModellingRequest(BaseModel):
    task: Literal["text_to_3d", "image_to_3d"]
    model: str = "flux-kontext"
    quality: Literal["low", "medium", "high"] = "medium"
    output: OutputSpec
    printer: PrinterSpec
    metadata: MetadataSpec


class TextTo3DRequest(BaseModellingRequest):
    task: Literal["text_to_3d"]
    prompt: str


class ImageTo3DRequest(BaseModellingRequest):
    task: Literal["image_to_3d"]
    image: ImageSpec
    prompt: str
    should_remesh: bool = True
    should_texture: bool = False


ModellingRequest = TextTo3DRequest | ImageTo3DRequest


class TaskStatusResponse(BaseModel):
    status: str
    progress: Optional[float] = None
    result_glb_url: Optional[str] = None
    raw: Optional[Any] = None


# ---------- Services ----------
async def _complete_image_to_3d(
    task_id: str,
    endpoint: str,
    user_id: Optional[str] = None,
    prompt: Optional[str] = None,
    source_image_url: Optional[str] = None
) -> dict:
    """Complete image-to-3d task, download result, and run Blender post-processing.

    Args:
        task_id: Meshy task ID
        endpoint: Meshy API endpoint
        user_id: User ID for Supabase integration (optional)
        prompt: Prompt used for generation (optional)
        source_image_url: Source image URL (optional)

    Returns:
        dict with task_id, result_glb_url, local paths, and Supabase URLs if user_id provided
    """
    # Generate model_id for Supabase
    model_id = str(uuid.uuid4())
    supabase_client = None

    # Create Supabase DB record if user_id provided
    if user_id and SUPABASE_AVAILABLE:
        try:
            supabase_client = get_supabase_client()
            create_ai_model_record(
                user_id=user_id,
                model_id=model_id,
                generation_type="image_to_3d",
                prompt=prompt,
                source_image_url=source_image_url,
                supabase=supabase_client
            )
            logger.info("[Supabase] Created DB record: model_id=%s, user_id=%s", model_id, user_id)
        except Exception as e:
            logger.error("[Supabase] Failed to create DB record: %s", str(e))
            # Continue processing even if DB record creation fails

    try:
        task = await poll_until_done(endpoint, task_id)
        result_url = pick_model_url(task)
        logger.info("[MeshyDone] image_to_3d id=%s url=%s", task_id, result_url)

        if not result_url:
            raise RuntimeError("No result_glb_url from image-to-3d task")

        result: dict = {
            "task_id": task_id,
            "model_id": model_id,
            "result_glb_url": result_url,
            "raw": task,
        }

        # Download GLB file
        local_glb_path = None
        if OUTPUT_DIR and result_url:
            local_glb_path = await maybe_download_result(
                task_id,
                result_url,
                "SUCCEEDED",
                f"model_{task_id}.glb"
            )
            if local_glb_path:
                logger.info("[DownloadOK] id=%s saved=%s", task_id, local_glb_path)
                result["local_path"] = local_glb_path
            else:
                logger.warning("[DownloadSkip] id=%s reason=unknown (see utill.maybe_download_result)", task_id)
        else:
            if not OUTPUT_DIR:
                logger.warning("[DownloadSkip] reason=OUTPUT_DIR unset")
            elif not result_url:
                logger.warning("[DownloadSkip] reason=no result_glb_url")

        # Run Blender post-processing if GLB was downloaded
        if local_glb_path:
            blender_result = await post_process_with_blender(local_glb_path, task_id)
            if blender_result:
                result["cleaned_glb_path"] = blender_result.get("cleaned_glb_path")
                result["stl_path"] = blender_result.get("stl_path")
                logger.info("[BlenderPostProcess] Success: GLB=%s, STL=%s",
                           result.get("cleaned_glb_path"), result.get("stl_path"))
            else:
                logger.warning("[BlenderPostProcess] Skipped or failed for task_id=%s", task_id)

        # Download thumbnail if available
        thumbnail_url = task.get("thumbnail_url")
        if thumbnail_url:
            thumbnail_path = await download_thumbnail(thumbnail_url, task_id)
            if thumbnail_path:
                result["thumbnail_path"] = thumbnail_path
                logger.info("[ThumbnailDownload] Success: %s", thumbnail_path)

        # Upload to Supabase Storage if user_id provided
        if user_id and SUPABASE_AVAILABLE and supabase_client:
            try:
                glb_upload_result = None
                stl_upload_result = None
                thumbnail_upload_result = None

                # Upload cleaned GLB (preferred) or original GLB
                glb_to_upload = result.get("cleaned_glb_path") or result.get("local_path")
                if glb_to_upload:
                    glb_upload_result = upload_glb_to_storage(
                        user_id=user_id,
                        model_id=model_id,
                        glb_file_path=glb_to_upload,
                        supabase=supabase_client
                    )
                    logger.info("[Supabase] GLB uploaded: %s", glb_upload_result.get("public_url"))
                    result["supabase_glb_url"] = glb_upload_result.get("public_url")

                # Upload STL if available
                if result.get("stl_path"):
                    stl_upload_result = upload_stl_to_storage(
                        user_id=user_id,
                        model_id=model_id,
                        stl_file_path=result["stl_path"],
                        supabase=supabase_client
                    )
                    logger.info("[Supabase] STL uploaded: %s", stl_upload_result.get("public_url"))
                    result["supabase_stl_url"] = stl_upload_result.get("public_url")

                # Upload thumbnail if available
                if result.get("thumbnail_path"):
                    thumbnail_upload_result = upload_thumbnail_to_storage(
                        user_id=user_id,
                        model_id=model_id,
                        thumbnail_file_path=result["thumbnail_path"],
                        supabase=supabase_client
                    )
                    logger.info("[Supabase] Thumbnail uploaded: %s", thumbnail_upload_result.get("public_url"))
                    result["supabase_thumbnail_url"] = thumbnail_upload_result.get("public_url")

                # Update DB record to completed
                if glb_upload_result:
                    update_model_to_completed(
                        model_id=model_id,
                        storage_path=glb_upload_result.get("path"),
                        download_url=glb_upload_result.get("public_url"),
                        thumbnail_url=thumbnail_upload_result.get("public_url") if thumbnail_upload_result else None,
                        stl_storage_path=stl_upload_result.get("path") if stl_upload_result else None,
                        stl_download_url=stl_upload_result.get("public_url") if stl_upload_result else None,
                        file_size=glb_upload_result.get("size"),
                        supabase=supabase_client
                    )
                    logger.info("[Supabase] DB record updated to completed: model_id=%s", model_id)

                    # Send MQTT completion notification
                    if MQTT_AVAILABLE:
                        try:
                            send_model_completion_notification(
                                user_id=user_id,
                                model_id=model_id,
                                download_url=glb_upload_result.get("public_url"),
                                thumbnail_url=thumbnail_upload_result.get("public_url") if thumbnail_upload_result else None,
                                stl_download_url=stl_upload_result.get("public_url") if stl_upload_result else None,
                                model_name=f"AI Model {model_id[:8]}",
                                generation_type="image_to_3d"
                            )
                        except Exception as mqtt_error:
                            logger.warning("[MQTT] Failed to send completion notification: %s", mqtt_error)

                    # Cleanup local files after successful upload
                    if CLEANUP_AVAILABLE:
                        try:
                            cleanup_model_files(
                                glb_path=result.get("cleaned_glb_path"),
                                stl_path=result.get("stl_path"),
                                thumbnail_path=result.get("thumbnail_path"),
                                source_image_path=source_image_url if source_image_url and os.path.exists(str(source_image_url)) else None
                            )
                        except Exception as cleanup_error:
                            logger.warning("[Cleanup] Failed to cleanup local files: %s", cleanup_error)

            except Exception as e:
                logger.error("[Supabase] Failed to upload files or update DB: %s", str(e))
                # Update to failed status
                try:
                    if supabase_client:
                        update_model_to_failed(model_id, str(e), supabase=supabase_client)

                        # Send MQTT failure notification
                        if MQTT_AVAILABLE and user_id:
                            try:
                                send_model_failure_notification(
                                    user_id=user_id,
                                    model_id=model_id,
                                    error_message=str(e),
                                    generation_type="image_to_3d"
                                )
                            except:
                                pass
                except:
                    pass

        return result

    except Exception as e:
        # Update Supabase DB to failed if user_id provided
        if user_id and SUPABASE_AVAILABLE and supabase_client:
            try:
                update_model_to_failed(model_id, str(e), supabase=supabase_client)
                logger.error("[Supabase] DB record updated to failed: model_id=%s, error=%s", model_id, str(e))

                # Send MQTT failure notification
                if MQTT_AVAILABLE:
                    try:
                        send_model_failure_notification(
                            user_id=user_id,
                            model_id=model_id,
                            error_message=str(e),
                            generation_type="image_to_3d"
                        )
                    except Exception as mqtt_error:
                        logger.warning("[MQTT] Failed to send failure notification: %s", mqtt_error)
            except Exception as db_error:
                logger.error("[Supabase] Failed to update DB to failed status: %s", str(db_error))
        raise


async def _complete_text_to_3d_with_refine(
    preview_task_id: str,
    endpoint: str,
    texture_prompt: Optional[str] = None,
    user_id: Optional[str] = None,
    prompt: Optional[str] = None
) -> dict:
    """Complete text-to-3d preview task and download result (skip refine, go straight to Blender).

    Args:
        preview_task_id: Meshy preview task ID
        endpoint: Meshy API endpoint
        texture_prompt: Optional texture prompt (unused in current implementation)
        user_id: User ID for Supabase integration (optional)
        prompt: Original text prompt used for generation (optional)

    Returns:
        dict with task_id, result_glb_url, local paths, and Supabase URLs if user_id provided
    """
    # Generate model_id for Supabase
    model_id = str(uuid.uuid4())
    supabase_client = None

    # Create Supabase DB record if user_id provided
    if user_id and SUPABASE_AVAILABLE:
        try:
            supabase_client = get_supabase_client()
            create_ai_model_record(
                user_id=user_id,
                model_id=model_id,
                generation_type="text_to_3d",
                prompt=prompt,
                supabase=supabase_client
            )
            logger.info("[Supabase] Created DB record: model_id=%s, user_id=%s", model_id, user_id)
        except Exception as e:
            logger.error("[Supabase] Failed to create DB record: %s", str(e))
            # Continue processing even if DB record creation fails

    try:
        # 1) Preview 완료까지 대기
        preview_task = await poll_until_done(endpoint, preview_task_id)
        preview_result_url = pick_model_url(preview_task)
        logger.info("[MeshyDone] text_to_3d_preview id=%s url=%s (skipping refine)", preview_task_id, preview_result_url)

        if not preview_result_url:
            raise RuntimeError("No result_glb_url from text-to-3d preview task")

        # 2) 결과 객체 생성
        result: dict = {
            "task_id": preview_task_id,
            "model_id": model_id,
            "result_glb_url": preview_result_url,
            "raw": preview_task,
        }

        # 3) GLB 다운로드
        local_glb_path = None
        if OUTPUT_DIR and preview_result_url:
            local_glb_path = await maybe_download_result(
                preview_task_id,
                preview_result_url,
                "SUCCEEDED",
                f"preview_{preview_task_id}.glb"
            )
            if local_glb_path:
                logger.info("[DownloadOK] id=%s saved=%s", preview_task_id, local_glb_path)
                result["local_path"] = local_glb_path
            else:
                logger.warning("[DownloadSkip] id=%s reason=unknown (see utill.maybe_download_result)", preview_task_id)
        else:
            if not OUTPUT_DIR:
                logger.warning("[DownloadSkip] reason=OUTPUT_DIR unset")
            elif not preview_result_url:
                logger.warning("[DownloadSkip] reason=no result_glb_url")

        # 4) Blender 후처리 실행
        if local_glb_path:
            blender_result = await post_process_with_blender(local_glb_path, preview_task_id)
            if blender_result:
                result["cleaned_glb_path"] = blender_result.get("cleaned_glb_path")
                result["stl_path"] = blender_result.get("stl_path")
                logger.info("[BlenderPostProcess] Success: GLB=%s, STL=%s",
                           result.get("cleaned_glb_path"), result.get("stl_path"))
            else:
                logger.warning("[BlenderPostProcess] Skipped or failed for task_id=%s", preview_task_id)

        # 5) 썸네일 다운로드
        thumbnail_url = preview_task.get("thumbnail_url")
        if thumbnail_url:
            thumbnail_path = await download_thumbnail(thumbnail_url, preview_task_id)
            if thumbnail_path:
                result["thumbnail_path"] = thumbnail_path
                logger.info("[ThumbnailDownload] Success: %s", thumbnail_path)

        # 6) Upload to Supabase Storage if user_id provided
        if user_id and SUPABASE_AVAILABLE and supabase_client:
            try:
                glb_upload_result = None
                stl_upload_result = None
                thumbnail_upload_result = None

                # Upload cleaned GLB (preferred) or original GLB
                glb_to_upload = result.get("cleaned_glb_path") or result.get("local_path")
                if glb_to_upload:
                    glb_upload_result = upload_glb_to_storage(
                        user_id=user_id,
                        model_id=model_id,
                        glb_file_path=glb_to_upload,
                        supabase=supabase_client
                    )
                    logger.info("[Supabase] GLB uploaded: %s", glb_upload_result.get("public_url"))
                    result["supabase_glb_url"] = glb_upload_result.get("public_url")

                # Upload STL if available
                if result.get("stl_path"):
                    stl_upload_result = upload_stl_to_storage(
                        user_id=user_id,
                        model_id=model_id,
                        stl_file_path=result["stl_path"],
                        supabase=supabase_client
                    )
                    logger.info("[Supabase] STL uploaded: %s", stl_upload_result.get("public_url"))
                    result["supabase_stl_url"] = stl_upload_result.get("public_url")

                # Upload thumbnail if available
                if result.get("thumbnail_path"):
                    thumbnail_upload_result = upload_thumbnail_to_storage(
                        user_id=user_id,
                        model_id=model_id,
                        thumbnail_file_path=result["thumbnail_path"],
                        supabase=supabase_client
                    )
                    logger.info("[Supabase] Thumbnail uploaded: %s", thumbnail_upload_result.get("public_url"))
                    result["supabase_thumbnail_url"] = thumbnail_upload_result.get("public_url")

                # Update DB record to completed
                if glb_upload_result:
                    update_model_to_completed(
                        model_id=model_id,
                        storage_path=glb_upload_result.get("path"),
                        download_url=glb_upload_result.get("public_url"),
                        thumbnail_url=thumbnail_upload_result.get("public_url") if thumbnail_upload_result else None,
                        stl_storage_path=stl_upload_result.get("path") if stl_upload_result else None,
                        stl_download_url=stl_upload_result.get("public_url") if stl_upload_result else None,
                        file_size=glb_upload_result.get("size"),
                        supabase=supabase_client
                    )
                    logger.info("[Supabase] DB record updated to completed: model_id=%s", model_id)

                    # Send MQTT completion notification
                    if MQTT_AVAILABLE:
                        try:
                            send_model_completion_notification(
                                user_id=user_id,
                                model_id=model_id,
                                download_url=glb_upload_result.get("public_url"),
                                thumbnail_url=thumbnail_upload_result.get("public_url") if thumbnail_upload_result else None,
                                stl_download_url=stl_upload_result.get("public_url") if stl_upload_result else None,
                                model_name=f"AI Model {model_id[:8]}",
                                generation_type="image_to_3d"
                            )
                        except Exception as mqtt_error:
                            logger.warning("[MQTT] Failed to send completion notification: %s", mqtt_error)

                    # Cleanup local files after successful upload
                    if CLEANUP_AVAILABLE:
                        try:
                            cleanup_model_files(
                                glb_path=result.get("cleaned_glb_path"),
                                stl_path=result.get("stl_path"),
                                thumbnail_path=result.get("thumbnail_path"),
                                source_image_path=source_image_url if source_image_url and os.path.exists(str(source_image_url)) else None
                            )
                        except Exception as cleanup_error:
                            logger.warning("[Cleanup] Failed to cleanup local files: %s", cleanup_error)

            except Exception as e:
                logger.error("[Supabase] Failed to upload files or update DB: %s", str(e))
                # Update to failed status
                try:
                    if supabase_client:
                        update_model_to_failed(model_id, str(e), supabase=supabase_client)

                        # Send MQTT failure notification
                        if MQTT_AVAILABLE and user_id:
                            try:
                                send_model_failure_notification(
                                    user_id=user_id,
                                    model_id=model_id,
                                    error_message=str(e),
                                    generation_type="image_to_3d"
                                )
                            except:
                                pass
                except:
                    pass

        return result

    except Exception as e:
        # Update Supabase DB to failed if user_id provided
        if user_id and SUPABASE_AVAILABLE and supabase_client:
            try:
                update_model_to_failed(model_id, str(e), supabase=supabase_client)
                logger.error("[Supabase] DB record updated to failed: model_id=%s, error=%s", model_id, str(e))

                # Send MQTT failure notification
                if MQTT_AVAILABLE:
                    try:
                        send_model_failure_notification(
                            user_id=user_id,
                            model_id=model_id,
                            error_message=str(e),
                            generation_type="image_to_3d"
                        )
                    except Exception as mqtt_error:
                        logger.warning("[MQTT] Failed to send failure notification: %s", mqtt_error)
            except Exception as db_error:
                logger.error("[Supabase] Failed to update DB to failed status: %s", str(db_error))
        raise


async def start_text_to_3d_preview(prompt: str, art_style: Optional[str] = None, ai_model: Optional[str] = None) -> dict:
    """Start text-to-3d preview task (v2 API)."""
    endpoint = f"{MESHY_API_BASE}/openapi/v2/text-to-3d"
    body: Dict[str, Any] = {
        "mode": "preview",
        "prompt": prompt,
        "art_style": art_style or TEXT_TO_3D_ART_STYLE,
        "topology": TEXT_TO_3D_TOPOLOGY,
        "target_polycount": TEXT_TO_3D_TARGET_POLYCOUNT,
    }
    if ai_model:
        body["ai_model"] = ai_model

    logger.info("[MeshyReq] POST %s (preview)", endpoint)
    async with get_httpx_client() as client:
        resp = await client.post(endpoint, headers=meshy_headers_json(), json=body, timeout=60)
        logger.info("[MeshyResp] POST %s -> %s", endpoint, resp.status_code)
        resp.raise_for_status()
        j = resp.json()
        task_id = pick_task_id(j)
        logger.info("[MeshyTaskStart] preview task_id=%s", task_id)
        if not task_id:
            logger.warning("[MeshyTaskStart] task_id missing, raw=%s", j)
            raise RuntimeError(f"task_id not found: {j}")
        return {"task_id": task_id, "result": j}


async def start_text_to_3d_refine(preview_task_id: str, texture_prompt: Optional[str] = None) -> dict:
    """Start text-to-3d refine task (v2 API)."""
    endpoint = f"{MESHY_API_BASE}/openapi/v2/text-to-3d"
    body: Dict[str, Any] = {
        "mode": "refine",
        "preview_task_id": preview_task_id,
        "enable_pbr": TEXT_TO_3D_ENABLE_PBR,
    }
    if texture_prompt:
        body["texture_prompt"] = texture_prompt

    logger.info("[MeshyReq] POST %s (refine) body=%s", endpoint, body)
    async with get_httpx_client() as client:
        resp = await client.post(endpoint, headers=meshy_headers_json(), json=body, timeout=60)
        logger.info("[MeshyResp] POST %s -> %s", endpoint, resp.status_code)
        if resp.status_code >= 400:
            error_body = resp.text
            logger.error("[MeshyError] Refine request failed: status=%s, body=%s", resp.status_code, error_body)
        resp.raise_for_status()
        j = resp.json()
        task_id = pick_task_id(j)
        logger.info("[MeshyTaskStart] refine task_id=%s from_preview=%s", task_id, preview_task_id)
        if not task_id:
            logger.warning("[MeshyTaskStart] task_id missing, raw=%s", j)
            raise RuntimeError(f"task_id not found: {j}")
        return {"task_id": task_id, "result": j}


async def start_text_to_3d_task_only(payload: TextTo3DRequest) -> dict:
    """Start text-to-3d preview task and return task_id immediately without waiting."""
    endpoint = f"{MESHY_API_BASE}/openapi/v2/text-to-3d"

    # Start preview task
    preview_result = await start_text_to_3d_preview(payload.prompt)
    preview_task_id = preview_result["task_id"]

    return {
        "task_id": preview_task_id,
        "status": "PENDING",
        "endpoint": endpoint,
        "raw": preview_result
    }


async def start_text_to_3d(payload: TextTo3DRequest) -> dict:
    """Start text-to-3d workflow (preview + refine)."""
    endpoint = f"{MESHY_API_BASE}/openapi/v2/text-to-3d"

    # Start preview task
    preview_result = await start_text_to_3d_preview(payload.prompt)
    preview_task_id = preview_result["task_id"]

    # Complete preview and refine
    return await _complete_text_to_3d_with_refine(preview_task_id, endpoint)


async def start_image_to_3d_task_only(payload: ImageTo3DRequest) -> dict:
    """Start image-to-3d task and return task_id immediately without waiting."""
    endpoint = f"{MESHY_API_BASE}/openapi/v1/image-to-3d"
    img_url = payload.image.url
    data_url = img_url
    logger.info("[MeshyReqPrep] image_to_3d img_url=%s mime=%s", img_url, payload.image.mime_type)
    if img_url.startswith("http://") or img_url.startswith("https://"):
        data_url = await to_data_url_from_url(img_url, payload.image.mime_type)
    body = {
        "image_url": data_url,
        "should_remesh": payload.should_remesh,
        "should_texture": payload.should_texture,
        "topology": IMAGE_TO_3D_TOPOLOGY,
        "target_polycount": IMAGE_TO_3D_TARGET_POLYCOUNT,
    }
    logger.info("[MeshyReq] POST %s (should_remesh=%s, should_texture=%s)", endpoint, payload.should_remesh, payload.should_texture)
    async with get_httpx_client() as client:
        resp = await client.post(endpoint, headers=meshy_headers_json(), json=body, timeout=60)
        logger.info("[MeshyResp] POST %s -> %s", endpoint, resp.status_code)
        resp.raise_for_status()
        j = resp.json()
        task_id = pick_task_id(j)
        logger.info("[MeshyTaskStart] task_id=%s", task_id)
        if not task_id:
            logger.warning("[MeshyTaskStart] task_id missing, raw=%s", j)
            raise RuntimeError(f"task_id not found: {j}")
    return {
        "task_id": task_id,
        "status": "PENDING",
        "endpoint": endpoint,
        "raw": j
    }


async def start_image_to_3d(payload: ImageTo3DRequest) -> dict:
    """Start image-to-3d task and wait for completion."""
    result = await start_image_to_3d_task_only(payload)
    task_id = result["task_id"]
    endpoint = result["endpoint"]
    return await _complete_image_to_3d(task_id, endpoint)


async def start_image_to_3d_from_bytes_task_only(file_bytes: bytes, mime_type: Optional[str], extra_meta: Optional[Dict[str, Any]] = None) -> dict:
    """Start image-to-3d task from bytes and return task_id immediately without waiting."""
    endpoint = f"{MESHY_API_BASE}/openapi/v1/image-to-3d"
    logger.info("[MeshyReqPrep] image_to_3d_from_bytes size=%s mime=%s", len(file_bytes), mime_type)
    data_url = to_data_url_from_bytes(file_bytes, mime_type)

    # Get should_remesh and should_texture from extra_meta or use defaults
    should_remesh = extra_meta.get("should_remesh", True) if extra_meta else True
    should_texture = extra_meta.get("should_texture", False) if extra_meta else False

    body: Dict[str, Any] = {
        "image_url": data_url,
        "should_remesh": should_remesh,
        "should_texture": should_texture,
        "topology": IMAGE_TO_3D_TOPOLOGY,
        "target_polycount": IMAGE_TO_3D_TARGET_POLYCOUNT,
    }
    if extra_meta:
        # Only merge known or safe keys
        for k in ("prompt", "depth", "model", "quality", "output", "printer", "metadata"):
            if k in extra_meta and extra_meta[k] is not None:
                body[k] = extra_meta[k]

    logger.info("[MeshyReq] POST %s (should_remesh=%s, should_texture=%s)", endpoint, should_remesh, should_texture)
    async with get_httpx_client() as client:
        resp = await client.post(endpoint, headers=meshy_headers_json(), json=body, timeout=60)
        logger.info("[MeshyResp] POST %s -> %s", endpoint, resp.status_code)
        resp.raise_for_status()
        j = resp.json()
        task_id = pick_task_id(j)
        logger.info("[MeshyTaskStart] task_id=%s", task_id)
        if not task_id:
            logger.warning("[MeshyTaskStart] task_id missing, raw=%s", j)
            raise RuntimeError(f"task_id not found: {j}")
    return {
        "task_id": task_id,
        "status": "PENDING",
        "endpoint": endpoint,
        "raw": j
    }


async def start_image_to_3d_from_bytes(file_bytes: bytes, mime_type: Optional[str], extra_meta: Optional[Dict[str, Any]] = None) -> dict:
    """Accept raw file bytes + optional meta JSON and start an image-to-3d task.
    extra_meta can include: prompt, depth, model, quality, output, printer, metadata, should_remesh, should_texture, etc.
    """
    result = await start_image_to_3d_from_bytes_task_only(file_bytes, mime_type, extra_meta)
    task_id = result["task_id"]
    endpoint = result["endpoint"]
    return await _complete_image_to_3d(task_id, endpoint)


async def get_modelling_status(task_id: str) -> dict:
    # Try v1 API first (image-to-3d), then fall back to v2 (text-to-3d)
    # v1 is more common so we try it first to reduce unnecessary API calls
    endpoint_v1 = f"{MESHY_API_BASE}/openapi/v1/image-to-3d"
    endpoint_v2 = f"{MESHY_API_BASE}/openapi/v2/text-to-3d"

    task = None
    endpoint_used = None

    # Try v1 first (image-to-3d)
    try:
        task = await meshy_get_task(endpoint_v1, task_id)
        endpoint_used = "v1"
        logger.info("[MeshyStatus] Found task in v1 API (image-to-3d): id=%s", task_id)
    except Exception as e:
        logger.debug("[MeshyStatus] Not found in v1 API, trying v2: %s", str(e))
        # Try v2 (text-to-3d)
        try:
            task = await meshy_get_task(endpoint_v2, task_id)
            endpoint_used = "v2"
            logger.info("[MeshyStatus] Found task in v2 API (text-to-3d): id=%s", task_id)
        except Exception as e2:
            logger.error("[MeshyStatus] Task not found in both v1 and v2 APIs: id=%s", task_id)
            raise RuntimeError(f"Task not found: {task_id}")

    data = {
        "status": task.get("status"),
        "progress": task.get("progress"),
        "result_glb_url": pick_model_url(task),
        "raw": task,
    }
    logger.info(
        "[MeshyStatus] id=%s status=%s progress=%s url=%s api=%s",
        task_id,
        data["status"],
        data["progress"],
        data["result_glb_url"],
        endpoint_used,
    )

    # Check for local files (original GLB, cleaned GLB, STL) and trigger post-processing if needed
    if OUTPUT_DIR:
        from pathlib import Path

        output_path = Path(OUTPUT_DIR)

        # Original GLB - check multiple possible filenames
        # image-to-3d: model_{task_id}.glb
        # text-to-3d: refined_{task_id}.glb or preview_{task_id}.glb
        model_glb = None
        for prefix in ["model", "refined", "preview"]:
            candidate = output_path / f"{prefix}_{task_id}.glb"
            if candidate.exists():
                model_glb = candidate
                data["local_path"] = str(model_glb)
                logger.info("[LocalFile] Found original GLB: %s", model_glb)
                break

        # Cleaned GLB (from Blender)
        cleaned_glb = output_path / f"cleaned_{task_id}.glb"
        if cleaned_glb.exists():
            data["cleaned_glb_path"] = str(cleaned_glb)
            logger.info("[LocalFile] Found cleaned GLB: %s", cleaned_glb)

        # STL (from Blender)
        stl_file = output_path / f"cleaned_{task_id}.stl"
        if stl_file.exists():
            data["stl_path"] = str(stl_file)
            logger.info("[LocalFile] Found STL: %s", stl_file)

        # Thumbnail (from Meshy)
        for ext in [".png", ".jpg", ".jpeg"]:
            thumbnail_file = output_path / f"thumbnail_{task_id}{ext}"
            if thumbnail_file.exists():
                data["thumbnail_path"] = str(thumbnail_file)
                logger.info("[LocalFile] Found thumbnail: %s", thumbnail_file)
                break

        # If task is SUCCEEDED but no local GLB, download it first
        if data["status"] == "SUCCEEDED" and not model_glb and data["result_glb_url"]:
            logger.info("[AutoDownload] Downloading GLB for task_id=%s", task_id)
            # Determine filename based on API version
            if endpoint_used == "v2":
                filename = f"preview_{task_id}.glb"
            else:
                filename = f"model_{task_id}.glb"

            local_glb_path = await maybe_download_result(
                task_id,
                data["result_glb_url"],
                "SUCCEEDED",
                filename
            )
            if local_glb_path:
                model_glb = Path(local_glb_path)
                data["local_path"] = str(model_glb)
                logger.info("[AutoDownload] Success: %s", model_glb)

        # If task is SUCCEEDED but no cleaned files, trigger post-processing
        if (data["status"] == "SUCCEEDED" and
            model_glb and
            not cleaned_glb.exists() and
            not stl_file.exists()):
            logger.info("[PostProcess] Triggering Blender post-processing for task_id=%s", task_id)
            blender_result = await post_process_with_blender(str(model_glb), task_id)
            if blender_result:
                data["cleaned_glb_path"] = blender_result.get("cleaned_glb_path")
                data["stl_path"] = blender_result.get("stl_path")
                logger.info("[PostProcess] Success: GLB=%s, STL=%s",
                           data.get("cleaned_glb_path"), data.get("stl_path"))

            # Download thumbnail if not exists
            thumbnail_url = task.get("thumbnail_url")
            if thumbnail_url and not any((output_path / f"thumbnail_{task_id}{ext}").exists() for ext in [".png", ".jpg", ".jpeg"]):
                thumbnail_path = await download_thumbnail(thumbnail_url, task_id)
                if thumbnail_path:
                    data["thumbnail_path"] = thumbnail_path
                    logger.info("[ThumbnailDownload] Success: %s", thumbnail_path)

    return data


async def post_process_with_blender(glb_path: str, task_id: str) -> Optional[dict]:
    """
    Optional Blender post-processing step.
    Returns dict with cleaned_glb_path and stl_path if successful, None otherwise.
    """
    if not BLENDER_AVAILABLE:
        logger.warning("[BlenderProcess] Not available, skipping")
        return None

    try:
        if not is_blender_available():
            logger.warning("[BlenderProcess] Blender not configured, skipping")
            return None

        logger.info("[BlenderProcess] Starting post-process for task_id=%s", task_id)
        result = await process_model_with_blender(glb_path, task_id)
        logger.info("[BlenderProcess] Completed for task_id=%s", task_id)
        return result
    except Exception as e:
        logger.error("[BlenderProcess] Failed for task_id=%s: %s", task_id, str(e))
        return None
