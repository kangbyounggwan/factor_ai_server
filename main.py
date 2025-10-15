import os
import logging
import json
from typing import Any, Optional
import time

from dotenv import load_dotenv

# Load .env BEFORE importing modules that use environment variables
load_dotenv()

from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, TypeAdapter
import httpx
from modelling_api import (
    ModellingRequest,
    TaskStatusResponse,
    start_text_to_3d,
    start_text_to_3d_task_only,
    start_image_to_3d,
    start_image_to_3d_from_bytes,
    start_image_to_3d_task_only,
    start_image_to_3d_from_bytes_task_only,
    get_modelling_status,
)
from blender_processor import process_model_with_blender, is_blender_available
from background_tasks import start_background_task, process_image_to_3d_background

ALLOWED_ORIGINS_RAW = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",")] if ALLOWED_ORIGINS_RAW else ["*"]
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:7000").rstrip("/")

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Factor AI Proxy API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/files", StaticFiles(directory=os.getenv("OUTPUT_DIR", "./output")), name="files")


class ApiResponse(BaseModel):
    status: str
    data: Optional[Any] = None
    error: Optional[str] = None


class TextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "error": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "error": "Internal server error"},
    )


@app.get("/health", response_model=ApiResponse)
async def health():
    return ApiResponse(status="ok", data={"service": "alive"})


@app.post("/v1/process/modelling", response_model=ApiResponse)
async def process_modelling(request: Request, async_mode: bool = False):
    """
    Process 3D modelling request.

    Query Parameters:
        async_mode: If True, return task_id immediately without waiting for completion.
                   Client should poll GET /v1/process/modelling/{task_id} for progress.
    """
    try:
        content_type = (request.headers.get("content-type") or "").lower()
        # multipart/form-data: task, image_file, json
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            task = str(form.get("task") or "")
            if task != "image_to_3d":
                raise HTTPException(status_code=400, detail="multipart only supports task=image_to_3d")
            upload = form.get("image_file")
            if not upload:
                raise HTTPException(status_code=400, detail="image_file is required")
            json_str = form.get("json") or "{}"
            try:
                extra_meta = json.loads(json_str)
            except Exception:
                raise HTTPException(status_code=400, detail="json field must be a valid JSON string")
            file_bytes = await upload.read()
            # save uploaded image to OUTPUT_DIR
            output_dir = os.getenv("OUTPUT_DIR", "./output")
            os.makedirs(output_dir, exist_ok=True)
            safe_name = os.path.basename(getattr(upload, "filename", "") or "upload.bin")
            name_root, name_ext = os.path.splitext(safe_name)
            stamped = f"{name_root}_{int(time.time())}{name_ext or '.bin'}"
            save_path = os.path.join(output_dir, stamped)
            try:
                with open(save_path, "wb") as f:
                    f.write(file_bytes)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"failed to save uploaded file: {e}")

            payload_log = {
                "task": "image_to_3d",
                "meta": extra_meta,
                "filename": safe_name,
                "content_type": getattr(upload, "content_type", None),
                "size": len(file_bytes),
                "async_mode": async_mode,
            }
            logger.info("modelling multipart payload: %s", payload_log)

            # Async mode: return task_id immediately
            if async_mode:
                result = await start_image_to_3d_from_bytes_task_only(file_bytes, getattr(upload, "content_type", None), extra_meta)
                response_data = {
                    "task_id": result["task_id"],
                    "status": result["status"],
                    "progress": 0,
                    "message": f"Task started. Use GET /v1/process/modelling/{result['task_id']} to check progress",
                    "uploaded_local_path": save_path,
                    "request_payload": payload_log,
                }

                # Start background processing
                task_id = result["task_id"]
                endpoint = result["endpoint"]
                start_background_task(task_id, process_image_to_3d_background(task_id, endpoint))

                logger.info("[Modelling] Async task started: task_id=%s", task_id)
                logger.info("[Modelling] Full Response (async multipart): %s", response_data)
                return ApiResponse(status="ok", data=response_data)

            # Sync mode: wait for completion
            result = await start_image_to_3d_from_bytes(file_bytes, getattr(upload, "content_type", None), extra_meta)

            # 다운로드 URL 구성 (로컬 경로가 있으면 파일명 기준)
            download_url = None
            file_size = None
            local_path = result.get("local_path")
            if local_path:
                download_url = f"{PUBLIC_BASE_URL}/files/{os.path.basename(local_path)}"
                if os.path.exists(local_path):
                    file_size = os.path.getsize(local_path)

            # GLB 및 STL 다운로드 URL 추가
            glb_download_url = None
            stl_download_url = None
            glb_file_size = None
            stl_file_size = None

            cleaned_glb_path = result.get("cleaned_glb_path")
            if cleaned_glb_path and os.path.exists(cleaned_glb_path):
                glb_download_url = f"{PUBLIC_BASE_URL}/files/{os.path.basename(cleaned_glb_path)}"
                glb_file_size = os.path.getsize(cleaned_glb_path)

            stl_path = result.get("stl_path")
            if stl_path and os.path.exists(stl_path):
                stl_download_url = f"{PUBLIC_BASE_URL}/files/{os.path.basename(stl_path)}"
                stl_file_size = os.path.getsize(stl_path)

            # Thumbnail URL
            thumbnail_download_url = None
            thumbnail_file_size = None
            thumbnail_path = result.get("thumbnail_path")
            if thumbnail_path and os.path.exists(thumbnail_path):
                thumbnail_download_url = f"{PUBLIC_BASE_URL}/files/{os.path.basename(thumbnail_path)}"
                thumbnail_file_size = os.path.getsize(thumbnail_path)

            response_data = {
                **result,
                "uploaded_local_path": save_path,
                "request_payload": payload_log,
                "download_url": download_url,
                "file_size": file_size,
                "glb_download_url": glb_download_url,
                "glb_file_size": glb_file_size,
                "stl_download_url": stl_download_url,
                "stl_file_size": stl_file_size,
                "thumbnail_download_url": thumbnail_download_url,
                "thumbnail_file_size": thumbnail_file_size
            }
            # 로그 출력 (전체 응답)
            logger.info("[Modelling] Response (multipart): task_id=%s, glb_url=%s, stl_url=%s, thumbnail_url=%s",
                       response_data.get('task_id'), glb_download_url, stl_download_url, thumbnail_download_url)
            logger.info("[Modelling] Full Response (multipart): %s", response_data)
            return ApiResponse(status="ok", data=response_data)

        # application/json: legacy JSON body using ModellingRequest (Union)
        body = await request.json()
        payload = TypeAdapter(ModellingRequest).validate_python(body)
        print(payload)
        payload_dict = payload.model_dump(mode="json")
        payload_dict["async_mode"] = async_mode
        logger.info("modelling json payload: %s", payload_dict)

        # Async mode for both text_to_3d and image_to_3d
        if async_mode:
            if payload.task == "text_to_3d":
                result = await start_text_to_3d_task_only(payload)
                response_data = {
                    "task_id": result["task_id"],
                    "status": result["status"],
                    "progress": 0,
                    "message": f"Task started. Use GET /v1/process/modelling/{result['task_id']} to check progress",
                    "request_payload": payload_dict,
                }

                # Start background processing
                task_id = result["task_id"]
                endpoint = result["endpoint"]
                from background_tasks import process_text_to_3d_background
                start_background_task(task_id, process_text_to_3d_background(task_id, endpoint))

                logger.info("[Modelling] Async text_to_3d task started: task_id=%s", task_id)
                logger.info("[Modelling] Full Response (async json): %s", response_data)
                return ApiResponse(status="ok", data=response_data)

            elif payload.task == "image_to_3d":
                result = await start_image_to_3d_task_only(payload)
                response_data = {
                    "task_id": result["task_id"],
                    "status": result["status"],
                    "progress": 0,
                    "message": f"Task started. Use GET /v1/process/modelling/{result['task_id']} to check progress",
                    "request_payload": payload_dict,
                }

                # Start background processing
                task_id = result["task_id"]
                endpoint = result["endpoint"]
                start_background_task(task_id, process_image_to_3d_background(task_id, endpoint))

                logger.info("[Modelling] Async image_to_3d task started: task_id=%s", task_id)
                logger.info("[Modelling] Full Response (async json): %s", response_data)
                return ApiResponse(status="ok", data=response_data)

        # Sync mode
        if payload.task == "text_to_3d":
            result = await start_text_to_3d(payload)
        elif payload.task == "image_to_3d":
            result = await start_image_to_3d(payload)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported task: {payload.task}")

        download_url = None
        file_size = None
        local_path = result.get("local_path")
        if local_path:
            download_url = f"{PUBLIC_BASE_URL}/files/{os.path.basename(local_path)}"
            if os.path.exists(local_path):
                file_size = os.path.getsize(local_path)

        # GLB 및 STL 다운로드 URL 추가
        glb_download_url = None
        stl_download_url = None
        glb_file_size = None
        stl_file_size = None

        cleaned_glb_path = result.get("cleaned_glb_path")
        if cleaned_glb_path and os.path.exists(cleaned_glb_path):
            glb_download_url = f"{PUBLIC_BASE_URL}/files/{os.path.basename(cleaned_glb_path)}"
            glb_file_size = os.path.getsize(cleaned_glb_path)

        stl_path = result.get("stl_path")
        if stl_path and os.path.exists(stl_path):
            stl_download_url = f"{PUBLIC_BASE_URL}/files/{os.path.basename(stl_path)}"
            stl_file_size = os.path.getsize(stl_path)

        # Thumbnail URL
        thumbnail_download_url = None
        thumbnail_file_size = None
        thumbnail_path = result.get("thumbnail_path")
        if thumbnail_path and os.path.exists(thumbnail_path):
            thumbnail_download_url = f"{PUBLIC_BASE_URL}/files/{os.path.basename(thumbnail_path)}"
            thumbnail_file_size = os.path.getsize(thumbnail_path)

        response_data = {
            **result,
            "request_payload": payload_dict,
            "download_url": download_url,
            "file_size": file_size,
            "glb_download_url": glb_download_url,
            "glb_file_size": glb_file_size,
            "stl_download_url": stl_download_url,
            "stl_file_size": stl_file_size,
            "thumbnail_download_url": thumbnail_download_url,
            "thumbnail_file_size": thumbnail_file_size
        }
        # 로그 출력 (전체 응답)
        logger.info("[Modelling] Response (json): task_id=%s, glb_url=%s, stl_url=%s, thumbnail_url=%s",
                   response_data.get('task_id'), glb_download_url, stl_download_url, thumbnail_download_url)
        logger.info("[Modelling] Full Response (json): %s", response_data)
        return ApiResponse(status="ok", data=response_data)
    except TimeoutError as e:
        logger.warning("Task timeout: %s", str(e))
        raise HTTPException(status_code=504, detail=f"Task timeout: {str(e)}")
    except RuntimeError as e:
        logger.warning("Task failed: %s", str(e))
        raise HTTPException(status_code=502, detail=f"Task failed: {str(e)}")
    except httpx.HTTPStatusError as e:
        msg = f"Meshy API error {e.response.status_code}"
        logger.warning("%s: %s", msg, e.response.text)
        raise HTTPException(status_code=502, detail=msg)
    except httpx.RequestError as e:
        logger.warning("Meshy request failed: %s", str(e))
        raise HTTPException(status_code=504, detail="Meshy timeout or network error")

@app.get("/v1/process/modelling/{task_id}", response_model=ApiResponse)
async def get_modelling(task_id: str):
    data = await get_modelling_status(task_id)
    resp = TaskStatusResponse(**data).model_dump()

    # 상태 조회에서도 로컬 경로가 있으면 다운로드 URL 제공
    if data.get("local_path"):
        resp["download_url"] = f"{PUBLIC_BASE_URL}/files/{os.path.basename(data['local_path'])}"

    # GLB 및 STL 다운로드 URL 추가
    if data.get("cleaned_glb_path"):
        resp["glb_download_url"] = f"{PUBLIC_BASE_URL}/files/{os.path.basename(data['cleaned_glb_path'])}"
        if os.path.exists(data["cleaned_glb_path"]):
            resp["glb_file_size"] = os.path.getsize(data["cleaned_glb_path"])

    if data.get("stl_path"):
        resp["stl_download_url"] = f"{PUBLIC_BASE_URL}/files/{os.path.basename(data['stl_path'])}"
        if os.path.exists(data["stl_path"]):
            resp["stl_file_size"] = os.path.getsize(data["stl_path"])

    # 로컬 썸네일 다운로드 URL 추가
    if data.get("thumbnail_path"):
        resp["thumbnail_download_url"] = f"{PUBLIC_BASE_URL}/files/{os.path.basename(data['thumbnail_path'])}"
        if os.path.exists(data["thumbnail_path"]):
            resp["thumbnail_file_size"] = os.path.getsize(data["thumbnail_path"])

    # Meshy 원본 썸네일 URL 추가 (백업용)
    if data.get("raw", {}).get("thumbnail_url"):
        resp["thumbnail_url"] = data["raw"]["thumbnail_url"]

    return ApiResponse(status="ok", data=resp)


class CleanModelRequest(BaseModel):
    glb_path: Optional[str] = None
    task_id: Optional[str] = None


class GenerateGCodeRequest(BaseModel):
    stl_path: Optional[str] = None
    task_id: Optional[str] = None
    cura_settings: Optional[dict] = None


@app.post("/v1/process/clean-model", response_model=ApiResponse)
async def clean_model(payload: CleanModelRequest):
    """
    Clean and optimize GLB model using Blender, then convert to STL.

    Provide either:
    - glb_path: Direct path to GLB file
    - task_id: Task ID from previous modelling operation
    """
    try:
        if not is_blender_available():
            raise HTTPException(
                status_code=503,
                detail="Blender post-processing is not available (not configured or not installed)"
            )

        # Determine input GLB path
        glb_path = None
        task_id = None

        if payload.glb_path:
            glb_path = payload.glb_path
            # Extract task_id from filename if possible
            import re
            match = re.search(r'(?:model_|refined_|preview_)([a-f0-9\-]+)', os.path.basename(glb_path))
            task_id = match.group(1) if match else "custom"
        elif payload.task_id:
            task_id = payload.task_id
            # Try to find the GLB file for this task
            output_dir = os.getenv("OUTPUT_DIR", "./output")
            candidates = [
                os.path.join(output_dir, f"model_{task_id}.glb"),
                os.path.join(output_dir, f"refined_{task_id}.glb"),
                os.path.join(output_dir, f"preview_{task_id}.glb"),
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    glb_path = candidate
                    break
        else:
            raise HTTPException(
                status_code=400,
                detail="Either glb_path or task_id must be provided"
            )

        if not glb_path or not os.path.exists(glb_path):
            raise HTTPException(
                status_code=404,
                detail=f"GLB file not found: {glb_path or 'unknown'}"
            )

        logger.info("[CleanModel] Processing: %s (task_id=%s)", glb_path, task_id)

        # Run Blender processing
        result = await process_model_with_blender(glb_path, task_id)

        # Add download URLs
        cleaned_glb_url = f"/files/{os.path.basename(result['cleaned_glb_path'])}"
        stl_url = f"/files/{os.path.basename(result['stl_path'])}"

        response_data = {
            "task_id": task_id,
            "input_glb": glb_path,
            "cleaned_glb_path": result["cleaned_glb_path"],
            "stl_path": result["stl_path"],
            "cleaned_glb_url": cleaned_glb_url,
            "stl_url": stl_url,
        }

        logger.info("[CleanModel] Success: task_id=%s", task_id)
        return ApiResponse(status="ok", data=response_data)

    except HTTPException:
        raise
    except RuntimeError as e:
        logger.warning("[CleanModel] Failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("[CleanModel] Unexpected error: %s", e)
        raise HTTPException(status_code=500, detail="Blender processing failed")


@app.post("/v1/process/generate-gcode", response_model=ApiResponse)
async def generate_gcode(payload: GenerateGCodeRequest):
    """
    Convert STL file to G-code using CuraEngine.

    Provide either:
    - stl_path: Direct path to STL file
    - task_id: Task ID from previous clean-model operation

    Optional:
    - cura_settings: Custom Cura settings dict (e.g., {"layer_height": "0.2", "infill_sparse_density": "20"})
    """
    try:
        from cura_processor import convert_stl_to_gcode, is_curaengine_available

        if not is_curaengine_available():
            raise HTTPException(
                status_code=503,
                detail="CuraEngine is not available (not configured or not installed)"
            )

        # Determine input STL path
        stl_path = None
        task_id = None

        if payload.stl_path:
            stl_path = payload.stl_path
            # Extract task_id from filename if possible
            import re
            match = re.search(r'cleaned_([a-f0-9\-]+)', os.path.basename(stl_path))
            task_id = match.group(1) if match else "custom"
        elif payload.task_id:
            task_id = payload.task_id
            # Try to find the STL file for this task
            output_dir = os.getenv("OUTPUT_DIR", "./output")
            stl_path = os.path.join(output_dir, f"cleaned_{task_id}.stl")
        else:
            raise HTTPException(
                status_code=400,
                detail="Either stl_path or task_id must be provided"
            )

        if not stl_path or not os.path.exists(stl_path):
            raise HTTPException(
                status_code=404,
                detail=f"STL file not found: {stl_path or 'unknown'}"
            )

        logger.info("[GenerateGCode] Processing: %s (task_id=%s)", stl_path, task_id)

        # Prepare output path
        output_dir = os.getenv("OUTPUT_DIR", "./output")
        gcode_path = os.path.join(output_dir, f"cleaned_{task_id}.gcode")

        # Run CuraEngine
        success = await convert_stl_to_gcode(
            stl_path=os.path.abspath(stl_path),
            gcode_path=os.path.abspath(gcode_path),
            custom_settings=payload.cura_settings,
        )

        if not success:
            raise RuntimeError("G-code generation failed")

        # Add download URL
        gcode_url = f"/files/{os.path.basename(gcode_path)}"

        response_data = {
            "task_id": task_id,
            "input_stl": stl_path,
            "gcode_path": gcode_path,
            "gcode_url": gcode_url,
        }

        if payload.cura_settings:
            response_data["cura_settings"] = payload.cura_settings

        logger.info("[GenerateGCode] Success: task_id=%s", task_id)
        return ApiResponse(status="ok", data=response_data)

    except HTTPException:
        raise
    except RuntimeError as e:
        logger.warning("[GenerateGCode] Failed: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("[GenerateGCode] Unexpected error: %s", e)
        raise HTTPException(status_code=500, detail="G-code generation failed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=7000, reload=True)


