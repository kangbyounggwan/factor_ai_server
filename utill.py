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


