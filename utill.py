import os
import base64
from typing import Optional, Any
from pathlib import Path
from urllib.parse import urlparse

import httpx


# ---- OUTPUT DIR ---------------------------------------------------
OUTPUT_DIR_RAW = os.getenv("OUTPUT_DIR", "").strip()
OUTPUT_DIR: Optional[Path] = Path(OUTPUT_DIR_RAW) if OUTPUT_DIR_RAW else None
if OUTPUT_DIR:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- MODEL SCALING ------------------------------------------------
DEFAULT_MODEL_SIZE_MM = float(os.getenv("DEFAULT_MODEL_SIZE_MM", "100.0"))
MIN_MODEL_X_MM = float(os.getenv("MIN_MODEL_X_MM", "10.0"))


# ---- HTTP Client --------------------------------------------------
def get_httpx_client() -> httpx.AsyncClient:
    # httpx.Timeout은 default 또는 4개 인자를 모두 요구하므로, 단일 기본값으로 설정
    timeout = httpx.Timeout(60.0)
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True)


# ---- Data URL helpers --------------------------------------------
async def to_data_url_from_url(url: str, mime_type: Optional[str] = None) -> str:
    async with get_httpx_client() as client:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        content = r.content
    b64 = base64.b64encode(content).decode("utf-8")
    mt = mime_type or "image/png"
    return f"data:{mt};base64,{b64}"


def to_data_url_from_bytes(content: bytes, mime_type: Optional[str] = None) -> str:
    b64 = base64.b64encode(content).decode("utf-8")
    mt = mime_type or "image/png"
    return f"data:{mt};base64,{b64}"


# ---- Result parsing -----------------------------------------------
def pick_task_id(j: dict) -> Optional[str]:
    for k in ("result", "task_id", "id"):
        v = j.get(k)
        if v:
            return v
    return None


def pick_model_url(task: dict) -> Optional[str]:
    model_urls = task.get("model_urls") or {}
    if isinstance(model_urls, dict) and model_urls.get("glb"):
        return model_urls["glb"]
    return task.get("result_glb_url") or task.get("model_url")


def sanitize_filename(name: str) -> str:
    """Sanitize filename to be safe across Windows and POSIX systems."""
    allowed = "-. _()abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    sanitized = "".join(ch if ch in allowed else "_" for ch in name)
    return sanitized or "model.glb"


# ---- Download helpers ---------------------------------------------
async def download_file(url: str, out_path: Path) -> Path:
    async with get_httpx_client() as client:
        async with client.stream("GET", url, timeout=180) as resp:
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
    return out_path


async def convert_yup_to_zup(glb_path: Path, target_size_mm: float = 100.0, min_x_mm: float = 10.0) -> bool:
    """
    Convert Y-up GLB file to Z-up (standard for 3D printing) and scale to target size.

    Meshy API 등에서 다운로드한 GLB는 Y-up 좌표계를 사용하지만,
    3D 프린팅(Cura, Prusa 등)은 Z-up 좌표계를 사용합니다.

    변환 후 모델을 적절한 크기로 스케일링합니다.
    - 가장 긴 축을 target_size_mm로 스케일
    - X축이 min_x_mm보다 작으면 추가 스케일링

    변환 방법: X축 기준 +90도 회전
    - Y-up: Y가 위쪽
    - Z-up: Z가 위쪽

    Args:
        glb_path: GLB 파일 경로 (in-place 변환)
        target_size_mm: 목표 크기 (가장 긴 축 기준, mm 단위, 기본값: 100mm)
        min_x_mm: 최소 X축 크기 (mm 단위, 기본값: 10mm)

    Returns:
        bool: 성공 여부
    """
    import logging
    logger = logging.getLogger("uvicorn.error")

    try:
        import trimesh
        import numpy as np

        logger.info("[YupToZup] Converting %s from Y-up to Z-up...", glb_path.name)

        # GLB 로드
        scene = trimesh.load(str(glb_path), file_type='glb')

        # 모든 geometry 추출 및 병합
        if hasattr(scene, "geometry"):
            meshes = list(scene.geometry.values())
            if len(meshes) > 1:
                combined_mesh = trimesh.util.concatenate(meshes)
            else:
                combined_mesh = meshes[0]
        else:
            combined_mesh = scene

        # 원본 크기 확인
        original_bounds = combined_mesh.bounds
        original_size = original_bounds[1] - original_bounds[0]
        original_max_dim = max(original_size)

        logger.info("[YupToZup] Original size: X=%.2f, Y=%.2f, Z=%.2f mm (max: %.2f mm)",
                   original_size[0], original_size[1], original_size[2], original_max_dim)

        # 1. X축 기준 +90도 회전 (Y-up → Z-up)
        rotation_matrix = trimesh.transformations.rotation_matrix(
            np.pi / 2,  # +90 degrees
            [1, 0, 0],  # X axis
        )
        combined_mesh.apply_transform(rotation_matrix)

        # 2. 크기 조정 (가장 긴 축을 target_size_mm로 스케일)
        current_bounds = combined_mesh.bounds
        current_size = current_bounds[1] - current_bounds[0]
        current_max_dim = max(current_size)

        if current_max_dim > 0:
            scale_factor = target_size_mm / current_max_dim
            scale_matrix = trimesh.transformations.scale_matrix(scale_factor)
            combined_mesh.apply_transform(scale_matrix)

            # 중간 크기 확인
            temp_bounds = combined_mesh.bounds
            temp_size = temp_bounds[1] - temp_bounds[0]

            logger.info("[YupToZup] Initial scale: %.2fx (max: %.2f mm → %.2f mm)",
                       scale_factor, current_max_dim, max(temp_size))

            # 3. X축 최소 크기 보장 (3D 프린팅 출력 용이성)
            if temp_size[0] < min_x_mm:
                additional_scale = min_x_mm / temp_size[0]
                additional_scale_matrix = trimesh.transformations.scale_matrix(additional_scale)
                combined_mesh.apply_transform(additional_scale_matrix)

                logger.info("[YupToZup] Additional X-scale: %.2fx (X: %.2f mm → %.2f mm)",
                           additional_scale, temp_size[0], min_x_mm)

            # 최종 크기 확인
            final_bounds = combined_mesh.bounds
            final_size = final_bounds[1] - final_bounds[0]
            final_max_dim = max(final_size)

            logger.info("[YupToZup] ✅ Final size: X=%.2f, Y=%.2f, Z=%.2f mm (max: %.2f mm)",
                       final_size[0], final_size[1], final_size[2], final_max_dim)

        # GLB로 다시 저장 (in-place)
        if hasattr(scene, "geometry"):
            # Scene 객체인 경우 - geometry를 교체
            # 원본 scene의 첫 번째 geometry를 업데이트된 mesh로 교체
            geometry_name = list(scene.geometry.keys())[0] if scene.geometry else 'mesh_0'
            scene.geometry.clear()
            scene.geometry[geometry_name] = combined_mesh
            scene.export(str(glb_path), file_type='glb')
        else:
            # 단일 mesh인 경우
            combined_mesh.export(str(glb_path), file_type='glb')

        logger.info("[YupToZup] ✅ Converted successfully: %s", glb_path.name)
        return True

    except ImportError:
        logger.warning("[YupToZup] Trimesh not available, skipping conversion")
        return False
    except Exception as e:
        logger.error("[YupToZup] Failed to convert %s: %s", glb_path.name, str(e))
        import traceback
        traceback.print_exc()
        return False


async def maybe_download_result(task_id: str, result_url: Optional[str], status: Optional[str], default_filename: str) -> Optional[str]:
    if not OUTPUT_DIR or not result_url:
        return None

    try:
        # 기본 파일명이 제공되면 우선 사용
        filename = (default_filename or "").strip()
        if not filename:
            parsed = urlparse(result_url)
            base = os.path.basename(parsed.path) or "model.glb"
            filename = base
        filename = sanitize_filename(filename)

        out_path = OUTPUT_DIR / filename
        if not out_path.exists() and status and str(status).upper() == "SUCCEEDED":
            await download_file(result_url, out_path)

        # GLB 파일이면 Y-up → Z-up 변환 + 스케일링 (3D 프린팅 표준)
        if out_path.exists() and out_path.suffix.lower() == ".glb":
            await convert_yup_to_zup(out_path, target_size_mm=DEFAULT_MODEL_SIZE_MM, min_x_mm=MIN_MODEL_X_MM)

        if out_path.exists():
            return str(out_path)
    except Exception:
        return None
    return None


async def download_thumbnail(thumbnail_url: str, task_id: str) -> Optional[str]:
    """Download thumbnail image from Meshy API and save locally."""
    if not OUTPUT_DIR or not thumbnail_url:
        return None

    try:
        # Determine file extension from URL
        parsed = urlparse(thumbnail_url)
        path_lower = parsed.path.lower()
        if ".png" in path_lower:
            ext = ".png"
        elif ".jpg" in path_lower or ".jpeg" in path_lower:
            ext = ".jpg"
        else:
            ext = ".png"  # default

        filename = f"thumbnail_{task_id}{ext}"
        out_path = OUTPUT_DIR / filename

        # Download if not exists
        if not out_path.exists():
            await download_file(thumbnail_url, out_path)

        if out_path.exists():
            return str(out_path)
    except Exception as e:
        import logging
        logger = logging.getLogger("uvicorn.error")
        logger.warning("[ThumbnailDownload] Failed for task_id=%s: %s", task_id, str(e))
        return None
    return None


