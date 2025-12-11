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
from auth import extract_user_id_from_token

# G-code 분석 라우터 import
from gcode_analyzer.api.router import router as gcode_router

ALLOWED_ORIGINS_RAW = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",")] if ALLOWED_ORIGINS_RAW else ["*"]
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:7000").rstrip("/")

logger = logging.getLogger("uvicorn.error")
logger.info(f"[CORS] ALLOWED_ORIGINS loaded: {ALLOWED_ORIGINS}")

app = FastAPI(title="Factor AI Proxy API", version="0.1.0")

# G-code 분석 API 라우터 등록
app.include_router(gcode_router)

# CORS 설정 (개발 환경용 - 프로덕션에서는 NGINX에서 처리)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Note: /files endpoint is now handled by custom download_file_with_tracking()
# to support auto-deletion after download
# app.mount("/files", StaticFiles(directory=os.getenv("OUTPUT_DIR", "./output")), name="files")


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


@app.options("/v1/process/modelling")
async def options_process_modelling():
    """Handle CORS preflight for process_modelling endpoint"""
    return JSONResponse(content={}, status_code=200)


@app.post("/v1/process/modelling", response_model=ApiResponse)
async def process_modelling(request: Request, async_mode: bool = False):
    """
    Process 3D modelling request.

    Query Parameters:
        async_mode: If True, return task_id immediately without waiting for completion.
                   Client should poll GET /v1/process/modelling/{task_id} for progress.
    """
    # Extract user_id from JWT token in Authorization header
    authorization = request.headers.get("authorization")
    user_id_from_jwt = extract_user_id_from_token(authorization)

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

                # Start background processing with Supabase integration
                task_id = result["task_id"]
                endpoint = result["endpoint"]
                # Extract user_id: prefer JWT, fallback to metadata
                user_id = user_id_from_jwt
                if not user_id and extra_meta:
                    metadata = extra_meta.get("metadata", {}) if extra_meta else {}
                    user_id = metadata.get("user_id")
                prompt = extra_meta.get("prompt") if extra_meta else None
                source_image_url = save_path  # Use local path as source reference
                start_background_task(
                    task_id,
                    process_image_to_3d_background(
                        task_id=task_id,
                        endpoint=endpoint,
                        user_id=user_id,
                        prompt=prompt,
                        source_image_url=source_image_url
                    )
                )

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

                # Start background processing with Supabase integration
                task_id = result["task_id"]
                endpoint = result["endpoint"]
                # Extract user_id: prefer JWT, fallback to metadata
                user_id = user_id_from_jwt
                if not user_id and payload.metadata:
                    user_id = payload.metadata.user_id
                prompt = payload.prompt
                from background_tasks import process_text_to_3d_background
                start_background_task(
                    task_id,
                    process_text_to_3d_background(
                        preview_task_id=task_id,
                        endpoint=endpoint,
                        user_id=user_id,
                        prompt=prompt
                    )
                )

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

                # Start background processing with Supabase integration
                task_id = result["task_id"]
                endpoint = result["endpoint"]
                # Extract user_id: prefer JWT, fallback to metadata
                user_id = user_id_from_jwt
                if not user_id and payload.metadata:
                    user_id = payload.metadata.user_id
                prompt = payload.prompt if hasattr(payload, 'prompt') else None
                source_image_url = payload.image.url if hasattr(payload, 'image') else None
                start_background_task(
                    task_id,
                    process_image_to_3d_background(
                        task_id=task_id,
                        endpoint=endpoint,
                        user_id=user_id,
                        prompt=prompt,
                        source_image_url=source_image_url
                    )
                )

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
    printer_definition: Optional[dict] = None  # 프린터 정의 JSON (클라이언트가 전송)


# 파일 다운로드 추적용
downloaded_files = set()  # 다운로드 완료된 파일 경로 저장


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
    - printer_definition: Printer definition JSON (entire .def.json content sent by client)
                         If not provided, uses default from CURA_DEFINITION_JSON env variable
    """
    try:
        from cura_processor import convert_stl_to_gcode, convert_stl_to_gcode_with_definition, is_curaengine_available

        # printer_definition이 없으면 기본 체크, 있으면 CuraEngine만 체크
        if not payload.printer_definition and not is_curaengine_available():
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
        if payload.printer_definition:
            logger.info("[GenerateGCode] Using client-provided printer definition")

        # Prepare output path
        output_dir = os.getenv("OUTPUT_DIR", "./output")
        gcode_path = os.path.join(output_dir, f"cleaned_{task_id}.gcode")

        # Run CuraEngine with printer definition from client or default
        if payload.printer_definition:
            # 클라이언트가 프린터 정의를 보낸 경우
            success = await convert_stl_to_gcode_with_definition(
                stl_path=os.path.abspath(stl_path),
                gcode_path=os.path.abspath(gcode_path),
                printer_definition=payload.printer_definition,
                custom_settings=payload.cura_settings,
            )
        else:
            # 기본 환경 변수 프린터 정의 사용
            success = await convert_stl_to_gcode(
                stl_path=os.path.abspath(stl_path),
                gcode_path=os.path.abspath(gcode_path),
                custom_settings=payload.cura_settings,
            )

        if not success:
            raise RuntimeError("G-code generation failed")

        # Add download URL
        gcode_url = f"/files/{os.path.basename(gcode_path)}"

        # G-code 메타데이터 추출
        from cura_processor import parse_gcode_metadata
        gcode_metadata = parse_gcode_metadata(gcode_path)

        response_data = {
            "task_id": task_id,
            "input_stl": stl_path,
            "gcode_path": gcode_path,
            "gcode_url": gcode_url,
            "gcode_metadata": gcode_metadata,
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


@app.post("/v1/process/upload-stl-and-slice", response_model=ApiResponse)
async def upload_stl_and_slice(
    file: UploadFile = File(...),  # 3D 모델 파일 (STL, GLB, GLTF, OBJ)
    cura_settings_json: str = Form("{}"),
    printer_name: str = Form(None),
    printer_definition_json: str = Form(None),
):
    """
    3D 모델 파일을 업로드하고 즉시 G-code로 슬라이싱합니다.

    지원 파일 형식: STL, GLB, GLTF, OBJ
    - GLB/GLTF/OBJ 파일은 자동으로 STL로 변환됩니다.

    Form-data 필드:
    - file: 3D 모델 파일 (필수) - STL, GLB, GLTF, OBJ
    - cura_settings_json: Cura 설정 JSON 문자열 (선택)
    - printer_name: 프린터 이름 (선택, 권장) - DB의 filename에서 .def.json 제거한 값
                   예: "elegoo_neptune_x", "creality_ender3pro"
    - printer_definition_json: 프린터 정의 JSON 문자열 (선택, 고급)

    우선순위: printer_name > printer_definition_json > 기본 프린터
    """
    try:
        logger.info("="*80)
        logger.info("[UploadSTL] ===== NEW REQUEST =====")
        logger.info("[UploadSTL] Received upload-stl-and-slice request")

        from cura_processor import (
            convert_stl_to_gcode,
            convert_stl_to_gcode_with_definition,
            convert_stl_to_gcode_with_printer_name
        )

        # 출력 디렉토리 준비
        output_dir = os.getenv("OUTPUT_DIR", "./output")
        os.makedirs(output_dir, exist_ok=True)

        # 파일명 및 확장자 추출
        timestamp = int(time.time())
        original_filename = getattr(file, "filename", "model.stl")
        name_root, file_ext = os.path.splitext(original_filename)
        file_ext = file_ext.lower()

        # 요청 파라미터 로깅
        logger.info("[UploadSTL] Request Parameters:")
        logger.info("[UploadSTL]   - file: %s (extension: %s)", original_filename, file_ext)
        logger.info("[UploadSTL]   - printer_name: %s", printer_name if printer_name else "None")
        logger.info("[UploadSTL]   - printer_definition_json: %s",
                   "Provided" if printer_definition_json else "None")
        logger.info("[UploadSTL]   - cura_settings_json: %s", cura_settings_json[:100] if cura_settings_json else "{}")

        # 파일 저장
        file_bytes = await file.read()
        temp_filename = f"uploaded_{name_root}_{timestamp}{file_ext}"
        temp_path = os.path.join(output_dir, temp_filename)

        with open(temp_path, "wb") as f:
            f.write(file_bytes)

        logger.info("[Upload] Saved: %s (%d bytes)", temp_path, len(file_bytes))

        # STL 변환 (필요한 경우)
        stl_filename = f"uploaded_{name_root}_{timestamp}.stl"
        stl_path = os.path.join(output_dir, stl_filename)

        if file_ext == ".stl":
            # 이미 STL이면 그대로 사용
            if temp_path != stl_path:
                import shutil
                shutil.move(temp_path, stl_path)
            logger.info("[Upload] STL file, no conversion needed")

        elif file_ext in [".glb", ".gltf", ".obj"]:
            # GLB/GLTF/OBJ → STL 변환
            logger.info("[Upload] Converting %s to STL...", file_ext)

            try:
                import trimesh

                # 파일 로드
                if file_ext == ".glb":
                    mesh = trimesh.load(temp_path, file_type='glb')
                elif file_ext == ".gltf":
                    mesh = trimesh.load(temp_path, file_type='gltf')
                elif file_ext == ".obj":
                    mesh = trimesh.load(temp_path, file_type='obj')

                # 여러 메시가 있으면 병합
                if hasattr(mesh, "geometry"):
                    mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))

                logger.info("[Upload] Loaded mesh: %d vertices, %d faces",
                           len(mesh.vertices), len(mesh.faces))

                # 원본 GLB 크기 측정
                original_bounds = mesh.bounds
                original_size_x = original_bounds[1, 0] - original_bounds[0, 0]
                original_size_y = original_bounds[1, 1] - original_bounds[0, 1]
                original_size_z = original_bounds[1, 2] - original_bounds[0, 2]

                logger.info("="*80)
                logger.info("[Upload] 📦 ORIGINAL GLB SIZE:")
                logger.info("[Upload]   X: %.2f mm", original_size_x)
                logger.info("[Upload]   Y: %.2f mm", original_size_y)
                logger.info("[Upload]   Z: %.2f mm", original_size_z)
                logger.info("[Upload]   Volume: %.2f mm³", mesh.volume if hasattr(mesh, 'volume') else 0)
                logger.info("="*80)

                # 기본 수리
                trimesh.repair.fix_inversion(mesh)
                trimesh.repair.fill_holes(mesh)
                mesh.remove_degenerate_faces()
                mesh.remove_duplicate_faces()
                mesh.remove_unreferenced_vertices()

                # 3D 프린팅을 위한 위치 조정
                # 1. 바닥으로 이동 (Z축 최소값을 0으로)
                minz = mesh.bounds[0, 2]
                if minz < 0:
                    mesh.apply_translation((0, 0, -minz))
                    logger.info("[Upload] Moved model to Z=0 (shifted by %.2f mm)", -minz)

                # 2. XY 평면 중심 정렬 (베드 중앙)
                center_xy = mesh.bounds.mean(axis=0)
                center_xy[2] = 0  # Z축은 유지
                mesh.apply_translation(-center_xy)
                logger.info("[Upload] Centered model on build plate (XY offset: %.2f, %.2f)",
                           -center_xy[0], -center_xy[1])

                # STL로 내보내기
                mesh.export(stl_path, file_type='stl')

                # STL 크기 재확인 (변환 후)
                stl_bounds = mesh.bounds
                stl_size_x = stl_bounds[1, 0] - stl_bounds[0, 0]
                stl_size_y = stl_bounds[1, 1] - stl_bounds[0, 1]
                stl_size_z = stl_bounds[1, 2] - stl_bounds[0, 2]

                logger.info("="*80)
                logger.info("[Upload] 📏 CONVERTED STL SIZE:")
                logger.info("[Upload]   X: %.2f mm", stl_size_x)
                logger.info("[Upload]   Y: %.2f mm", stl_size_y)
                logger.info("[Upload]   Z: %.2f mm", stl_size_z)
                logger.info("[Upload]   Volume: %.2f mm³", mesh.volume if hasattr(mesh, 'volume') else 0)

                # 크기 변화 확인
                size_diff_x = abs(stl_size_x - original_size_x)
                size_diff_y = abs(stl_size_y - original_size_y)
                size_diff_z = abs(stl_size_z - original_size_z)

                if size_diff_x < 0.01 and size_diff_y < 0.01 and size_diff_z < 0.01:
                    logger.info("[Upload] ✅ Size preserved: GLB and STL are identical")
                else:
                    logger.warning("[Upload] ⚠️  Size changed: ΔX=%.2fmm, ΔY=%.2fmm, ΔZ=%.2fmm",
                                 size_diff_x, size_diff_y, size_diff_z)
                logger.info("="*80)

                # 원본 파일 삭제
                os.remove(temp_path)

                logger.info("[Upload] Converted to STL: %s", stl_path)

            except ImportError as e:
                logger.error("[Upload] ImportError: %s", str(e), exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Trimesh library not available for file conversion: {str(e)}"
                )
            except Exception as e:
                logger.error("[Upload] Conversion failed: %s", str(e), exc_info=True)
                # 원본 파일 삭제 (에러 시에도)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to convert {file_ext} to STL: {str(e)}"
                )
        else:
            # 지원하지 않는 형식
            os.remove(temp_path)
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format: {file_ext}. Supported: .stl, .glb, .gltf, .obj"
            )

        # STL 파일 크기 확인
        stl_size = os.path.getsize(stl_path)
        logger.info("[Upload] Final STL: %s (%d bytes)", stl_path, stl_size)

        # G-code 출력 경로
        gcode_filename = f"uploaded_{name_root}_{timestamp}.gcode"
        gcode_path = os.path.join(output_dir, gcode_filename)

        # Cura 설정 파싱
        try:
            cura_settings = json.loads(cura_settings_json) if cura_settings_json else {}
            logger.info("[UploadSTL] Parsed Cura settings: %d parameters", len(cura_settings))
            if cura_settings:
                for key, value in list(cura_settings.items())[:5]:  # 처음 5개만 로깅
                    logger.info("[UploadSTL]   - %s: %s", key, value)
                if len(cura_settings) > 5:
                    logger.info("[UploadSTL]   - ... and %d more settings", len(cura_settings) - 5)
        except json.JSONDecodeError as e:
            logger.error("[UploadSTL] Invalid cura_settings_json: %s", str(e))
            raise HTTPException(status_code=400, detail="Invalid cura_settings_json format")

        # 슬라이싱 실행 (우선순위: printer_name > printer_definition_json > 기본)
        logger.info("[UploadSTL] Starting slicing process...")
        if printer_name:
            # 방법 1: printer_name 사용 (권장)
            logger.info("[UploadSTL] Using printer name: %s", printer_name)
            success = await convert_stl_to_gcode_with_printer_name(
                stl_path=os.path.abspath(stl_path),
                gcode_path=os.path.abspath(gcode_path),
                printer_name=printer_name,
                custom_settings=cura_settings,
            )

        elif printer_definition_json:
            # 방법 2: printer_definition JSON 사용 (고급)
            try:
                printer_definition = json.loads(printer_definition_json)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid printer_definition_json format")

            logger.info("[UploadSTL] Using client-provided printer definition JSON")

            # 먼저 커스텀 정의로 시도
            try:
                success = await convert_stl_to_gcode_with_definition(
                    stl_path=os.path.abspath(stl_path),
                    gcode_path=os.path.abspath(gcode_path),
                    printer_definition=printer_definition,
                    custom_settings=cura_settings,
                )
            except Exception as e:
                # 커스텀 정의 실패 시 fallback: fdmprinter + bed size만 사용
                logger.warning("[UploadSTL] Custom printer definition failed: %s", str(e))
                logger.info("[UploadSTL] Falling back to fdmprinter with bed size only")

                # printer_definition에서 bed size 추출
                bed_size_settings = {}
                if 'overrides' in printer_definition:
                    for key in ['machine_width', 'machine_depth', 'machine_height']:
                        if key in printer_definition['overrides']:
                            value = printer_definition['overrides'][key]
                            if isinstance(value, dict) and 'default_value' in value:
                                bed_size_settings[key] = str(value['default_value'])
                            else:
                                bed_size_settings[key] = str(value)

                logger.info("[UploadSTL] Extracted bed size: %s", bed_size_settings)

                # cura_settings와 bed_size_settings 병합
                fallback_settings = {**cura_settings, **bed_size_settings}

                # .env에서 설정한 기본 프린터로 재시도
                from cura_processor import get_default_printer_name
                default_printer = get_default_printer_name()
                logger.info("[UploadSTL] Fallback to default printer: %s", default_printer)

                success = await convert_stl_to_gcode_with_printer_name(
                    stl_path=os.path.abspath(stl_path),
                    gcode_path=os.path.abspath(gcode_path),
                    printer_name=default_printer,
                    custom_settings=fallback_settings,
                )

        else:
            # 방법 3: 기본 프린터 사용 (.env의 CURA_DEFINITION_JSON)
            from cura_processor import is_curaengine_available
            if not is_curaengine_available():
                raise HTTPException(status_code=503, detail="CuraEngine not available")

            logger.info("[UploadSTL] Using default printer from .env")
            success = await convert_stl_to_gcode(
                stl_path=os.path.abspath(stl_path),
                gcode_path=os.path.abspath(gcode_path),
                custom_settings=cura_settings,
            )

        if not success:
            logger.error("[UploadSTL] Slicing failed!")
            raise RuntimeError("Slicing failed")

        logger.info("[UploadSTL] Slicing completed successfully")

        # G-code 메타데이터 추출
        logger.info("[UploadSTL] Extracting G-code metadata...")
        from cura_processor import parse_gcode_metadata
        gcode_metadata = parse_gcode_metadata(gcode_path)

        # 파일 정리 (최신 50개만 유지)
        cleanup_old_files(output_dir, max_files=50)

        # 응답 데이터
        logger.info("[UploadSTL] Preparing response data...")
        response_data = {
            "original_filename": original_filename,
            "original_format": file_ext,
            "converted_to_stl": file_ext != ".stl",
            "stl_filename": stl_filename,
            "stl_path": stl_path,
            "stl_url": f"{PUBLIC_BASE_URL}/files/{stl_filename}",
            "gcode_filename": gcode_filename,
            "gcode_path": gcode_path,
            "gcode_url": f"{PUBLIC_BASE_URL}/files/{gcode_filename}",
            "file_size": {
                "stl_bytes": stl_size,
                "gcode_bytes": os.path.getsize(gcode_path) if os.path.exists(gcode_path) else 0,
            },
            "gcode_metadata": gcode_metadata,  # G-code 메타데이터 추가
        }

        # 사용된 프린터 정보 추가
        if printer_name:
            response_data["printer_name"] = printer_name
            response_data["printer_source"] = "client_name"
        elif printer_definition_json:
            response_data["printer_source"] = "client_definition"
        else:
            response_data["printer_source"] = "default"

        if cura_settings:
            response_data["cura_settings"] = cura_settings

        logger.info("[UploadSTL] ===== REQUEST COMPLETED SUCCESSFULLY =====")
        logger.info("[UploadSTL] Response Summary:")
        logger.info("[UploadSTL]   - G-code file: %s", gcode_filename)
        logger.info("[UploadSTL]   - G-code size: %s bytes",
                   response_data['file_size']['gcode_bytes'])
        logger.info("[UploadSTL]   - G-code URL: %s", response_data['gcode_url'])
        logger.info("[UploadSTL]   - Printer source: %s", response_data['printer_source'])
        if printer_name:
            logger.info("[UploadSTL]   - Printer name: %s", printer_name)
        logger.info("="*80)

        return ApiResponse(status="ok", data=response_data)

    except HTTPException as e:
        logger.error("[UploadSTL] HTTP Exception: %s - %s", e.status_code, e.detail)
        logger.info("="*80)
        raise
    except Exception as e:
        logger.exception("[UploadSTL] Unexpected error: %s", e)
        logger.info("="*80)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/files/{filename}")
async def download_file_with_tracking(filename: str):
    """
    파일 다운로드 (다운로드 완료 시 자동 삭제)

    파일을 전송한 후 downloaded_files에 추가하여 추적합니다.
    """
    from fastapi.responses import FileResponse

    output_dir = os.getenv("OUTPUT_DIR", "./output")
    file_path = os.path.join(output_dir, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # 파일 전송 후 삭제 마킹
    logger.info("[Download] File requested: %s", filename)

    # 파일 응답 (다운로드 완료 후 background task로 삭제)
    from fastapi import BackgroundTasks

    async def mark_for_deletion():
        """다운로드 완료 후 파일 삭제 (썸네일은 제외)"""
        import asyncio
        await asyncio.sleep(2)  # 다운로드 완료 대기
        try:
            # 썸네일 파일은 삭제하지 않음 (브라우저에서 재사용 가능하도록)
            if filename.startswith("thumbnail_"):
                logger.info("[Download] Thumbnail file preserved: %s", filename)
                return

            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info("[Download] Deleted after download: %s", filename)
        except Exception as e:
            logger.warning("[Download] Failed to delete: %s - %s", filename, e)

    background_tasks = BackgroundTasks()
    background_tasks.add_task(mark_for_deletion)

    return FileResponse(
        path=file_path,
        filename=filename,
        background=background_tasks,
    )


def cleanup_old_files(directory: str, max_files: int = 50):
    """
    디렉토리에서 오래된 파일을 삭제하여 최신 N개만 유지합니다.

    Args:
        directory: 정리할 디렉토리
        max_files: 유지할 최대 파일 개수
    """
    try:
        import glob
        from pathlib import Path

        # 모든 파일 목록 (숨김 파일 제외)
        all_files = []
        for pattern in ["*.stl", "*.gcode", "*.glb", "*.jpg", "*.png"]:
            all_files.extend(glob.glob(os.path.join(directory, pattern)))

        # 파일이 max_files 이하면 정리 불필요
        if len(all_files) <= max_files:
            return

        # 수정 시간 기준 정렬 (오래된 것부터)
        all_files.sort(key=lambda f: os.path.getmtime(f))

        # 삭제할 파일 개수
        files_to_delete = len(all_files) - max_files

        if files_to_delete > 0:
            logger.info("[Cleanup] Total files: %d, deleting oldest %d files", len(all_files), files_to_delete)

            for file_path in all_files[:files_to_delete]:
                try:
                    os.remove(file_path)
                    logger.info("[Cleanup] Deleted: %s", os.path.basename(file_path))
                except Exception as e:
                    logger.warning("[Cleanup] Failed to delete %s: %s", file_path, e)

            logger.info("[Cleanup] Completed. Remaining files: %d", max_files)

    except Exception as e:
        logger.error("[Cleanup] Error during cleanup: %s", e)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=7000, reload=True)


