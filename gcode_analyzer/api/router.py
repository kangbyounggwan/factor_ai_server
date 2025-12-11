"""
G-code 분석 API 라우터
기존 main.py에 통합하여 사용
"""
import os
import json
import asyncio
import tempfile
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import uuid
import logging

from gcode_analyzer.rate_limiter import (
    get_rate_limiter,
    RateLimitError,
)

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/v1/gcode", tags=["G-code Analyzer"])

# ============================================================
# Request/Response Models
# ============================================================

class PrinterInfo(BaseModel):
    """프린터 정보"""
    name: Optional[str] = None
    model: Optional[str] = None
    nozzle_diameter: Optional[float] = 0.4  # mm
    max_temp_nozzle: Optional[float] = 300  # °C
    max_temp_bed: Optional[float] = 110     # °C
    build_volume: Optional[Dict[str, float]] = None  # {"x": 220, "y": 220, "z": 250}

class GCodeAnalysisRequest(BaseModel):
    """분석 요청 (JSON)"""
    gcode_content: str
    printer_info: Optional[PrinterInfo] = None
    filament_type: Optional[str] = None  # PLA, ABS, PETG, TPU
    user_id: Optional[str] = None
    analysis_id: Optional[str] = None
    analysis_mode: Optional[str] = "full"  # "summary_only" | "full"
    language: Optional[str] = "ko"  # "ko" | "en" | "ja" | "zh" (기본값: 한국어)


class GCodeSummaryRequest(BaseModel):
    """요약만 요청 (JSON) - LLM 분석 없이 빠르게"""
    gcode_content: str
    printer_info: Optional[PrinterInfo] = None
    filament_type: Optional[str] = None
    user_id: Optional[str] = None
    analysis_id: Optional[str] = None
    language: Optional[str] = "ko"  # "ko" | "en" | "ja" | "zh" (기본값: 한국어)


class ErrorAnalysisRequest(BaseModel):
    """에러 분석 요청 (기존 요약 기반)"""
    analysis_id: str  # 기존 요약 분석 ID


class PatchApprovalRequest(BaseModel):
    """패치 승인 요청"""
    approved: bool
    selected_patches: Optional[List[int]] = None  # 적용할 패치 인덱스 (None이면 전체)


class DashboardSummaryResponse(BaseModel):
    """대시보드 UI용 플랫 응답 모델"""
    # 기본 정보
    analysis_id: str
    status: str
    file_name: Optional[str] = None
    total_lines: int = 0
    slicer_info: Optional[str] = None
    filament_type: Optional[str] = None

    # 예상 출력 시간
    print_time_formatted: str = "00:00:00"
    print_time_seconds: int = 0

    # 필라멘트 사용량
    filament_used_meters: float = 0.0
    total_extrusion_mm: float = 0.0

    # 레이어 정보
    total_layers: int = 0
    layer_height_mm: float = 0.0
    first_layer_height_mm: float = 0.0

    # 리트랙션
    retraction_count: int = 0
    avg_retraction_mm: float = 0.0

    # 서포트
    has_support: bool = False
    support_ratio_percent: float = 0.0
    support_layers: int = 0

    # 속도 (mm/min)
    speed_min: float = 0.0
    speed_max: float = 0.0
    speed_avg: float = 0.0
    travel_speed_avg: float = 0.0
    print_speed_avg: float = 0.0

    # 온도 (°C)
    nozzle_temp_min: float = 0.0
    nozzle_temp_max: float = 0.0
    nozzle_temp_avg: float = 0.0
    nozzle_temp_changes: int = 0
    bed_temp_min: float = 0.0
    bed_temp_max: float = 0.0
    bed_temp_avg: float = 0.0

    # 구간 정보
    start_gcode_lines: int = 0
    body_lines: int = 0
    end_gcode_lines: int = 0

    # 팬
    max_fan_speed: int = 0
    fan_on_layer: int = 0


def _create_dashboard_response(analysis_id: str, data: Dict[str, Any]) -> DashboardSummaryResponse:
    """comprehensive_summary에서 대시보드 응답 생성"""
    summary = data.get("comprehensive_summary") or data.get("result", {}).get("comprehensive_summary") or {}

    # 중첩 객체 안전하게 접근
    temp = summary.get("temperature", {})
    feed = summary.get("feed_rate", {})
    ext = summary.get("extrusion", {})
    layer = summary.get("layer", {})
    support = summary.get("support", {})
    fan = summary.get("fan", {})
    print_time = summary.get("print_time", {})

    return DashboardSummaryResponse(
        analysis_id=analysis_id,
        status=data.get("status", "unknown"),
        file_name=summary.get("file_name"),
        total_lines=summary.get("total_lines", 0),
        slicer_info=summary.get("slicer_info"),
        filament_type=summary.get("filament_type"),

        # 시간
        print_time_formatted=print_time.get("formatted_time", "00:00:00"),
        print_time_seconds=print_time.get("estimated_seconds", 0),

        # 필라멘트
        filament_used_meters=ext.get("total_filament_used", 0.0),
        total_extrusion_mm=ext.get("total_extrusion", 0.0),

        # 레이어
        total_layers=layer.get("total_layers", 0),
        layer_height_mm=layer.get("avg_layer_height", 0.0),
        first_layer_height_mm=layer.get("first_layer_height", 0.0),

        # 리트랙션
        retraction_count=ext.get("retraction_count", 0),
        avg_retraction_mm=ext.get("avg_retraction", 0.0),

        # 서포트
        has_support=support.get("has_support", False),
        support_ratio_percent=support.get("support_ratio", 0.0),
        support_layers=support.get("support_layers", 0),

        # 속도
        speed_min=feed.get("min_speed", 0.0),
        speed_max=feed.get("max_speed", 0.0),
        speed_avg=feed.get("avg_speed", 0.0),
        travel_speed_avg=feed.get("travel_speed_avg", 0.0),
        print_speed_avg=feed.get("print_speed_avg", 0.0),

        # 온도
        nozzle_temp_min=temp.get("nozzle_min", 0.0),
        nozzle_temp_max=temp.get("nozzle_max", 0.0),
        nozzle_temp_avg=temp.get("nozzle_avg", 0.0),
        nozzle_temp_changes=temp.get("nozzle_changes", 0),
        bed_temp_min=temp.get("bed_min", 0.0),
        bed_temp_max=temp.get("bed_max", 0.0),
        bed_temp_avg=temp.get("bed_avg", 0.0),

        # 구간
        start_gcode_lines=summary.get("start_gcode_lines", 0),
        body_lines=summary.get("body_lines", 0),
        end_gcode_lines=summary.get("end_gcode_lines", 0),

        # 팬
        max_fan_speed=fan.get("max_fan_speed", 0),
        fan_on_layer=fan.get("fan_on_layer", 0)
    )

# ============================================================
# File-Based Storage (멀티 워커 환경에서 상태 공유)
# ============================================================

from gcode_analyzer.api.file_store import gcode_analysis_store, get_analysis, set_analysis, update_analysis, exists, delete_analysis


def _cleanup_temp_files(analysis_id: str, temp_file: Optional[str] = None):
    """분석 완료 후 임시 파일 및 상태 파일 정리"""
    # 임시 G-code 파일 삭제
    if temp_file and os.path.exists(temp_file):
        try:
            os.remove(temp_file)
            logger.info(f"[GCode] Deleted temp file: {temp_file}")
        except Exception as e:
            logger.warning(f"[GCode] Failed to delete temp file {temp_file}: {e}")

    # 상태 JSON 파일 삭제
    if delete_analysis(analysis_id):
        logger.info(f"[GCode] Deleted analysis state: {analysis_id}")
    else:
        logger.warning(f"[GCode] Failed to delete analysis state: {analysis_id}")

# ============================================================
# API Endpoints
# ============================================================

@router.get("/")
async def gcode_analyzer_info():
    """G-code 분석기 정보"""
    return {
        "service": "G-code Analyzer",
        "version": "2.1.0",
        "description": "G-code 종합 요약 및 에러 분석 API (Rate Limiting 포함)",
        "endpoints": {
            "analyze": "POST /api/v1/gcode/analyze - 전체 분석 (요약 + 에러)",
            "summary": "POST /api/v1/gcode/summary - 요약만 (빠름, LLM 없음)",
            "error_analysis": "POST /api/v1/gcode/analysis/{analysis_id}/error-analysis - 에러 분석 실행",
            "status": "GET /api/v1/gcode/analysis/{analysis_id}",
            "summary_result": "GET /api/v1/gcode/analysis/{analysis_id}/summary - 요약 결과 (중첩 구조)",
            "dashboard": "GET /api/v1/gcode/analysis/{analysis_id}/dashboard - 대시보드용 플랫 데이터",
            "stream": "GET /api/v1/gcode/analysis/{analysis_id}/stream",
            "approve_patch": "POST /api/v1/gcode/analysis/{analysis_id}/approve",
            "download_patched": "GET /api/v1/gcode/analysis/{analysis_id}/download",
            "rate_limit_status": "GET /api/v1/gcode/rate-limit/status - 사용자 Rate Limit 상태",
            "rate_limit_stats": "GET /api/v1/gcode/rate-limit/stats - 서버 Rate Limit 통계"
        },
        "analysis_modes": {
            "summary_only": "요약만 수행 (LLM 분석 없음, 빠름)",
            "full": "전체 분석 (요약 + 에러 분석 + 패치 제안)"
        },
        "rate_limits": {
            "user_rpm": "사용자당 분당 10회",
            "user_daily": "사용자당 일일 100회",
            "server_rpm": "서버 전체 분당 4000회 (80% 사용)"
        }
    }


@router.get("/rate-limit/status")
async def get_rate_limit_status(user_id: Optional[str] = None):
    """
    사용자 Rate Limit 상태 확인

    Args:
        user_id: 사용자 ID (query parameter)

    Returns:
        - can_request: 요청 가능 여부
        - remaining_rpm: 남은 분당 요청 수
        - remaining_daily: 남은 일일 요청 수
        - retry_after: 다음 요청까지 대기 시간 (초)
    """
    limiter = get_rate_limiter()
    status = limiter.check_user_limit(user_id)

    return {
        "user_id": user_id or "anonymous",
        **status
    }


@router.get("/rate-limit/stats")
async def get_rate_limit_stats():
    """
    서버 Rate Limit 통계 (관리자용)

    Returns:
        - total_requests: 총 요청 수
        - rate_limited: Rate limit으로 거부된 요청 수
        - total_tokens_used: 총 사용 토큰
        - active_users: 활성 사용자 수 (최근 1분)
    """
    limiter = get_rate_limiter()
    return limiter.get_stats()

@router.post("/analyze")
async def analyze_gcode_json(request: GCodeAnalysisRequest, background_tasks: BackgroundTasks):
    """
    G-code 분석 시작 (JSON 요청)

    - gcode_content: G-code 문자열
    - printer_info: 프린터 정보 (선택)
    - filament_type: 필라멘트 타입 (선택)

    Returns: analysis_id (SSE 스트리밍에 사용)

    Rate Limit:
    - 사용자당 분당 10회, 일일 100회 제한
    - 서버 전체 RPM 4000 제한 (안전 마진 80%)
    """
    # Rate Limit 체크
    limiter = get_rate_limiter()
    estimated_tokens = limiter.estimate_tokens(request.gcode_content)

    try:
        await limiter.acquire(
            user_id=request.user_id,
            estimated_tokens=estimated_tokens,
            timeout=30.0
        )
    except RateLimitError as e:
        logger.warning(f"[GCode] Rate limit exceeded for user {request.user_id}: {e}")
        return JSONResponse(
            status_code=429,
            content={
                "error": e.error_code,
                "message": str(e),
                "retry_after": e.retry_after
            },
            headers={"Retry-After": str(int(e.retry_after))}
        )

    analysis_id = request.analysis_id or str(uuid.uuid4())

    # 임시 파일 생성
    output_dir = os.getenv("OUTPUT_DIR", "./output")
    os.makedirs(output_dir, exist_ok=True)

    temp_file_path = os.path.join(output_dir, f"gcode_analysis_{analysis_id}.gcode")
    with open(temp_file_path, 'w', encoding='utf-8') as f:
        f.write(request.gcode_content)

    # 분석 상태 초기화 (파일 저장소에 저장)
    initial_data = {
        "status": "pending",
        "progress": 0.0,
        "current_step": "initializing",
        "timeline": [],
        "temp_file": temp_file_path,
        "printer_info": request.printer_info.dict() if request.printer_info else None,
        "filament_type": request.filament_type,
        "user_id": request.user_id,
        "language": request.language or "ko",  # 언어 설정 저장
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat()
    }
    set_analysis(analysis_id, initial_data)

    logger.info(f"[GCode] Analysis started: {analysis_id} (lang={request.language}, tokens={estimated_tokens})")

    # 백그라운드에서 분석 실행
    background_tasks.add_task(run_gcode_analysis_task, analysis_id)

    return {
        "analysis_id": analysis_id,
        "status": "pending",
        "message": "G-code 분석이 시작되었습니다.",
        "stream_url": f"/api/v1/gcode/analysis/{analysis_id}/stream"
    }


@router.post("/summary")
async def analyze_gcode_summary_only(request: GCodeSummaryRequest, background_tasks: BackgroundTasks):
    """
    G-code 요약만 분석 (LLM 분석 없음 - 빠름)

    온도, 피드, 서포트 비율, 예상 출력 시간 등의 요약 정보만 추출합니다.
    에러 분석은 수행하지 않습니다.

    - gcode_content: G-code 문자열
    - printer_info: 프린터 정보 (선택)
    - filament_type: 필라멘트 타입 (선택)

    Returns: analysis_id (요약 결과 조회에 사용)

    Rate Limit:
    - 사용자당 분당 10회, 일일 100회 제한
    - 요약은 LLM을 사용하지 않으므로 토큰 제한은 느슨하게 적용
    """
    # Rate Limit 체크 (요약은 LLM 없으므로 토큰은 최소로)
    limiter = get_rate_limiter()

    try:
        await limiter.acquire(
            user_id=request.user_id,
            estimated_tokens=100,  # 요약은 LLM 없으므로 최소 토큰
            timeout=10.0
        )
    except RateLimitError as e:
        logger.warning(f"[GCode] Rate limit exceeded for user {request.user_id}: {e}")
        return JSONResponse(
            status_code=429,
            content={
                "error": e.error_code,
                "message": str(e),
                "retry_after": e.retry_after
            },
            headers={"Retry-After": str(int(e.retry_after))}
        )

    analysis_id = request.analysis_id or str(uuid.uuid4())

    # 임시 파일 생성
    output_dir = os.getenv("OUTPUT_DIR", "./output")
    os.makedirs(output_dir, exist_ok=True)

    temp_file_path = os.path.join(output_dir, f"gcode_summary_{analysis_id}.gcode")
    with open(temp_file_path, 'w', encoding='utf-8') as f:
        f.write(request.gcode_content)

    # 분석 상태 초기화 (파일 저장소에 저장)
    initial_data = {
        "status": "pending",
        "progress": 0.0,
        "current_step": "initializing",
        "analysis_mode": "summary_only",
        "timeline": [],
        "temp_file": temp_file_path,
        "printer_info": request.printer_info.dict() if request.printer_info else None,
        "filament_type": request.filament_type,
        "user_id": request.user_id,
        "language": request.language or "ko",  # 언어 설정 저장
        "result": None,
        "comprehensive_summary": None,
        "error": None,
        "created_at": datetime.now().isoformat()
    }
    set_analysis(analysis_id, initial_data)

    logger.info(f"[GCode] Summary analysis started: {analysis_id} (lang={request.language})")

    # 백그라운드에서 요약 분석 실행
    background_tasks.add_task(run_gcode_summary_task, analysis_id)

    return {
        "analysis_id": analysis_id,
        "status": "pending",
        "analysis_mode": "summary_only",
        "message": "G-code 요약 분석이 시작되었습니다. (LLM 분석 없음)",
        "summary_url": f"/api/v1/gcode/analysis/{analysis_id}/summary"
    }


@router.get("/analysis/{analysis_id}/summary")
async def get_gcode_summary(analysis_id: str):
    """
    종합 요약 결과 조회 (중첩 구조)

    온도, 피드, 서포트 비율, 예상 출력 시간 등의 요약 정보 반환
    """
    if not exists(analysis_id):
        raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")

    data = get_analysis(analysis_id)

    if data["status"] not in ["completed", "summary_completed"]:
        return {
            "analysis_id": analysis_id,
            "status": data["status"],
            "progress": data["progress"],
            "message": "분석이 아직 완료되지 않았습니다."
        }

    comprehensive_summary = data.get("comprehensive_summary") or data.get("result", {}).get("comprehensive_summary")

    return {
        "analysis_id": analysis_id,
        "status": data["status"],
        "analysis_mode": data.get("analysis_mode", "full"),
        "comprehensive_summary": comprehensive_summary,
        "timeline": data.get("timeline", [])
    }


@router.get("/analysis/{analysis_id}/dashboard", response_model=DashboardSummaryResponse)
async def get_gcode_dashboard(analysis_id: str):
    """
    대시보드 UI용 플랫 요약 데이터 조회

    모든 필드가 중첩 없이 플랫한 구조로 반환됩니다.
    UI에서 바로 사용할 수 있는 형태입니다.

    응답 예시:
    ```json
    {
        "analysis_id": "xxx",
        "status": "summary_completed",
        "file_name": "model.gcode",
        "print_time_formatted": "01:51:06",
        "filament_used_meters": 77.78,
        "total_layers": 698,
        "layer_height_mm": 0.10,
        "retraction_count": 10552,
        "support_ratio_percent": 56.8,
        "speed_avg": 4546,
        "nozzle_temp_max": 205.0,
        ...
    }
    ```
    """
    if not exists(analysis_id):
        raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")

    data = get_analysis(analysis_id)

    if data["status"] not in ["completed", "summary_completed"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "분석이 아직 완료되지 않았습니다.",
                "status": data["status"],
                "progress": data["progress"]
            }
        )

    return _create_dashboard_response(analysis_id, data)


@router.post("/analysis/{analysis_id}/error-analysis")
async def run_error_analysis(analysis_id: str, background_tasks: BackgroundTasks):
    """
    기존 요약 기반으로 에러 분석 실행

    이미 요약 분석이 완료된 경우, 추가로 에러 분석을 실행합니다.
    LLM을 사용하여 문제를 분석하고 패치를 제안합니다.
    """
    if not exists(analysis_id):
        raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")

    data = get_analysis(analysis_id)

    if data["status"] not in ["completed", "summary_completed"]:
        raise HTTPException(status_code=400, detail="요약 분석이 완료되지 않았습니다. 먼저 요약 분석을 실행하세요.")

    if data.get("analysis_mode") == "full" and data["status"] == "completed":
        return {
            "analysis_id": analysis_id,
            "status": "already_analyzed",
            "message": "이미 전체 분석이 완료되었습니다.",
            "result": data.get("result")
        }

    # 에러 분석 모드로 전환
    update_analysis(analysis_id, {
        "status": "running_error_analysis",
        "analysis_mode": "error_analysis"
    })

    logger.info(f"[GCode] Error analysis started: {analysis_id}")
    
    # 백그라운드에서 에러 분석 실행
    background_tasks.add_task(run_gcode_error_analysis_task, analysis_id)
    
    return {
        "analysis_id": analysis_id,
        "status": "running_error_analysis",
        "message": "에러 분석이 시작되었습니다. (LLM 사용)",
        "stream_url": f"/api/v1/gcode/analysis/{analysis_id}/stream"
    }


@router.get("/analysis/{analysis_id}")
async def get_gcode_analysis_status(analysis_id: str):
    """분석 상태 조회"""
    if not exists(analysis_id):
        raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")

    data = get_analysis(analysis_id)
    return {
        "analysis_id": analysis_id,
        "status": data["status"],
        "progress": data["progress"],
        "current_step": data["current_step"],
        "progress_message": data.get("progress_message", ""),  # 실시간 메시지
        "timeline": data["timeline"],
        "result": data.get("result"),
        "error": data.get("error")
    }

@router.get("/analysis/{analysis_id}/stream")
async def stream_gcode_analysis(analysis_id: str):
    """
    SSE 스트리밍으로 분석 진행 상황 전송

    EventSource로 연결하여 실시간 진행 상황 수신
    """
    if not exists(analysis_id):
        raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")

    async def event_generator():
        last_step = 0
        while True:
            if not exists(analysis_id):
                break

            data = get_analysis(analysis_id)
            if data is None:
                break
            timeline = data.get("timeline", [])
            
            # 새로운 타임라인 이벤트 전송
            while last_step < len(timeline):
                event = timeline[last_step]
                yield f"event: timeline\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                last_step += 1
            
            # 진행률 전송 (메시지 포함)
            progress_data = {
                'progress': data['progress'],
                'step': data['current_step'],
                'message': data.get('progress_message', '')
            }
            yield f"event: progress\ndata: {json.dumps(progress_data, ensure_ascii=False)}\n\n"
            
            # 완료 또는 에러 시 종료
            if data["status"] in ["completed", "summary_completed", "error"]:
                if data["status"] in ["completed", "summary_completed"]:
                    yield f"event: complete\ndata: {json.dumps(data.get('result', {}), ensure_ascii=False)}\n\n"
                else:
                    yield f"event: error\ndata: {json.dumps({'error': data.get('error', 'Unknown error')}, ensure_ascii=False)}\n\n"
                break
            
            await asyncio.sleep(0.5)  # 500ms 간격
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.post("/analysis/{analysis_id}/approve")
async def approve_gcode_patch(analysis_id: str, request: PatchApprovalRequest, background_tasks: BackgroundTasks):
    """
    패치 승인/거부

    - approved: True면 패치 적용, False면 거부
    - selected_patches: 적용할 패치 인덱스 목록 (선택적)
    """
    if not exists(analysis_id):
        raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")

    data = get_analysis(analysis_id)

    if data["status"] != "completed":
        raise HTTPException(status_code=400, detail="분석이 완료되지 않았습니다.")

    if not request.approved:
        update_analysis(analysis_id, {"patch_status": "rejected"})
        logger.info(f"[GCode] Patch rejected: {analysis_id}")
        return {"status": "rejected", "message": "패치가 거부되었습니다."}

    # 패치 적용
    background_tasks.add_task(apply_gcode_patches_task, analysis_id, request.selected_patches)

    update_analysis(analysis_id, {"patch_status": "applying"})
    logger.info(f"[GCode] Patch applying: {analysis_id}")
    return {"status": "applying", "message": "패치를 적용하고 있습니다."}

@router.get("/analysis/{analysis_id}/download")
async def download_patched_gcode(analysis_id: str):
    """수정된 G-code 다운로드"""
    if not exists(analysis_id):
        raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")

    data = get_analysis(analysis_id)

    if data.get("patch_status") != "applied":
        raise HTTPException(status_code=400, detail="패치가 적용되지 않았습니다.")
    
    patched_content = data.get("patched_gcode", "")
    original_filename = data.get("original_filename", "output")
    
    # 파일명 생성
    base_name = os.path.splitext(original_filename)[0] if original_filename else "gcode"
    patched_filename = f"{base_name}_patched.gcode"
    
    return StreamingResponse(
        iter([patched_content]),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{patched_filename}"'
        }
    )

# ============================================================
# Background Tasks
# ============================================================

def create_progress_callback(analysis_id: str):
    """
    분석 ID에 대한 progress 콜백 생성

    콜백이 호출되면 파일 저장소가 실시간으로 업데이트됨
    """
    from gcode_analyzer.workflow.callback import ProgressUpdate

    def callback(update: ProgressUpdate):
        if exists(analysis_id):
            update_analysis(analysis_id, {
                "progress": update.progress,
                "current_step": update.step,
                "progress_message": update.message
            })
            logger.debug(f"[GCode] {analysis_id}: {update.progress:.0%} - {update.message}")

    return callback


async def run_gcode_analysis_task(analysis_id: str):
    """백그라운드에서 G-code 분석 실행"""
    from gcode_analyzer.analyzer import run_analysis

    data = get_analysis(analysis_id)
    if data is None:
        logger.error(f"[GCode] Analysis not found: {analysis_id}")
        return

    update_analysis(analysis_id, {"status": "running"})

    # Progress 콜백 생성
    progress_callback = create_progress_callback(analysis_id)

    try:
        logger.info(f"[GCode] Running analysis: {analysis_id}")

        # 분석 실행 (콜백 전달)
        result = await run_analysis(
            file_path=data["temp_file"],
            filament_type=data.get("filament_type"),
            printer_info=data.get("printer_info"),
            auto_approve=False,  # 사용자 승인 필요
            progress_callback=progress_callback,
            language=data.get("language", "ko")  # 언어 설정 전달
        )

        # 결과 저장
        update_analysis(analysis_id, {
            "status": "completed",
            "progress": 1.0,
            "current_step": "completed",
            "progress_message": "분석 완료",
            "result": {
                "final_summary": result.get("final_summary", {}),
                "issues_found": result.get("issues_found", []),
                "patch_plan": result.get("patch_plan"),
                "timeline": result.get("timeline", []),
                "token_usage": result.get("token_usage", {}),
                "comprehensive_summary": result.get("comprehensive_summary"),
                "printing_info": result.get("printing_info", {})  # LLM 프린팅 요약 추가
            },
            "comprehensive_summary": result.get("comprehensive_summary"),
            "printing_info": result.get("printing_info", {}),  # 별도 저장
            "timeline": result.get("timeline", [])
        })

        logger.info(f"[GCode] Analysis completed: {analysis_id}")

        # 임시 파일 삭제
        _cleanup_temp_files(analysis_id, data.get("temp_file"))

    except Exception as e:
        import traceback
        update_analysis(analysis_id, {
            "status": "error",
            "error": str(e),
            "progress_message": f"오류: {str(e)}",
            "error_trace": traceback.format_exc()
        })
        logger.error(f"[GCode] Analysis failed: {analysis_id} - {e}")

async def apply_gcode_patches_task(analysis_id: str, selected_patches: Optional[List[int]] = None):
    """백그라운드에서 패치 적용"""
    from gcode_analyzer.patcher import apply_patches, PatchPlan, PatchSuggestion

    data = get_analysis(analysis_id)
    if data is None:
        logger.error(f"[GCode] Analysis not found for patch: {analysis_id}")
        return

    try:
        patch_plan_dict = data["result"].get("patch_plan")
        if not patch_plan_dict:
            update_analysis(analysis_id, {"patch_status": "no_patches"})
            return

        # 원본 파일 읽기
        with open(data["temp_file"], "r", encoding="utf-8") as f:
            original_lines = f.readlines()

        # 선택된 패치만 또는 전체
        patches_data = patch_plan_dict.get("patches", [])
        if selected_patches is not None:
            patches_data = [p for i, p in enumerate(patches_data) if i in selected_patches]

        # PatchPlan 복원
        patches = [
            PatchSuggestion(
                line_index=p["line_index"],
                original_line=p["original_line"],
                action=p["action"],
                new_line=p.get("new_line"),
                reason=p["reason"],
                priority=i,
                issue_type=p["issue_type"]
            )
            for i, p in enumerate(patches_data)
        ]

        patch_plan = PatchPlan(
            file_path=data["temp_file"],
            total_patches=len(patches),
            patches=patches,
            estimated_quality_improvement=patch_plan_dict.get("estimated_improvement", 0)
        )

        # 패치 적용
        new_lines, applied_log = apply_patches(original_lines, patch_plan)

        # 결과 저장
        update_analysis(analysis_id, {
            "patched_gcode": "".join(new_lines),
            "patch_status": "applied",
            "applied_patches": applied_log
        })

        logger.info(f"[GCode] Patches applied: {analysis_id} ({len(applied_log)} patches)")

    except Exception as e:
        update_analysis(analysis_id, {
            "patch_status": "error",
            "patch_error": str(e)
        })
        logger.error(f"[GCode] Patch failed: {analysis_id} - {e}")

async def run_gcode_summary_task(analysis_id: str):
    """백그라운드에서 G-code 요약만 실행 (LLM 없음)"""
    from gcode_analyzer.analyzer import run_analysis

    data = get_analysis(analysis_id)
    if data is None:
        logger.error(f"[GCode] Analysis not found: {analysis_id}")
        return

    update_analysis(analysis_id, {"status": "running"})

    # Progress 콜백 생성
    progress_callback = create_progress_callback(analysis_id)

    try:
        logger.info(f"[GCode] Running summary analysis: {analysis_id}")

        # 요약만 분석 실행 (콜백 전달)
        result = await run_analysis(
            file_path=data["temp_file"],
            filament_type=data.get("filament_type"),
            printer_info=data.get("printer_info"),
            auto_approve=False,
            analysis_mode="summary_only",  # 요약만 모드
            progress_callback=progress_callback,
            language=data.get("language", "ko")  # 언어 설정 전달
        )

        # 결과 저장
        update_analysis(analysis_id, {
            "status": "summary_completed",
            "progress": 1.0,
            "current_step": "summary_completed",
            "progress_message": "요약 분석 완료",
            "comprehensive_summary": result.get("comprehensive_summary"),
            "printing_info": result.get("printing_info", {}),  # LLM 프린팅 요약
            "result": {
                "comprehensive_summary": result.get("comprehensive_summary"),
                "printing_info": result.get("printing_info", {}),  # LLM 프린팅 요약 추가
                "summary": result.get("summary"),
                "timeline": result.get("timeline", []),
                "token_usage": result.get("token_usage", {})
            },
            "timeline": result.get("timeline", [])
        })

        logger.info(f"[GCode] Summary analysis completed: {analysis_id}")

        # 임시 파일 삭제
        _cleanup_temp_files(analysis_id, data.get("temp_file"))

    except Exception as e:
        import traceback
        update_analysis(analysis_id, {
            "status": "error",
            "error": str(e),
            "progress_message": f"오류: {str(e)}",
            "error_trace": traceback.format_exc()
        })
        logger.error(f"[GCode] Summary analysis failed: {analysis_id} - {e}")


async def run_gcode_error_analysis_task(analysis_id: str):
    """백그라운드에서 에러 분석 실행 (기존 요약 기반)"""
    from gcode_analyzer.analyzer import run_error_analysis_only

    data = get_analysis(analysis_id)
    if data is None:
        logger.error(f"[GCode] Analysis not found: {analysis_id}")
        return

    # Progress 콜백 생성
    progress_callback = create_progress_callback(analysis_id)

    try:
        logger.info(f"[GCode] Running error analysis: {analysis_id}")

        # 에러 분석 실행 (기존 파싱 결과 활용, 콜백 전달)
        result = await run_error_analysis_only(
            file_path=data["temp_file"],
            filament_type=data.get("filament_type"),
            printer_info=data.get("printer_info"),
            existing_summary=data.get("comprehensive_summary"),
            progress_callback=progress_callback,
            language=data.get("language", "ko")  # 언어 설정 전달
        )

        # 타임라인 병합
        existing_timeline = data.get("timeline", [])
        new_timeline = result.get("timeline", [])

        # 결과 저장
        update_analysis(analysis_id, {
            "status": "completed",
            "progress": 1.0,
            "current_step": "completed",
            "progress_message": "에러 분석 완료",
            "result": {
                "comprehensive_summary": data.get("comprehensive_summary"),
                "printing_info": data.get("printing_info", {}),  # 기존 요약의 프린팅 정보 유지
                "final_summary": result.get("final_summary", {}),
                "issues_found": result.get("issues_found", []),
                "patch_plan": result.get("patch_plan"),
                "timeline": result.get("timeline", []),
                "token_usage": result.get("token_usage", {})
            },
            "timeline": existing_timeline + new_timeline
        })

        logger.info(f"[GCode] Error analysis completed: {analysis_id}")

    except Exception as e:
        import traceback
        update_analysis(analysis_id, {
            "status": "error",
            "error": str(e),
            "progress_message": f"오류: {str(e)}",
            "error_trace": traceback.format_exc()
        })
        logger.error(f"[GCode] Error analysis failed: {analysis_id} - {e}")
