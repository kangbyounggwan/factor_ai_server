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


class GCodeSegmentAnalysisRequest(BaseModel):
    """세그먼트 + LLM 분석 요청 (스트리밍)

    1단계: 세그먼트 데이터(Float32Array+Base64) 즉시 반환
    2단계: LLM 분석 완료 후 결과 반환
    """
    gcode_content: str
    printer_info: Optional[PrinterInfo] = None
    filament_type: Optional[str] = None
    user_id: Optional[str] = None
    analysis_id: Optional[str] = None
    language: Optional[str] = "ko"
    binary_format: bool = True  # True: Float32Array+Base64, False: JSON 배열


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


def _cleanup_temp_gcode_file(temp_file: Optional[str] = None):
    """임시 G-code 파일만 삭제 (상태 파일은 유지)"""
    if temp_file and os.path.exists(temp_file):
        try:
            os.remove(temp_file)
            logger.info(f"[GCode] Deleted temp gcode file: {temp_file}")
        except Exception as e:
            logger.warning(f"[GCode] Failed to delete temp file {temp_file}: {e}")

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
    if data is None:
        raise HTTPException(status_code=404, detail="분석 데이터를 읽을 수 없습니다.")

    if data.get("status") not in ["completed", "summary_completed"]:
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
    if data is None:
        raise HTTPException(status_code=404, detail="분석 데이터를 읽을 수 없습니다.")

    if data.get("status") not in ["completed", "summary_completed"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "분석이 아직 완료되지 않았습니다.",
                "status": data.get("status", "unknown"),
                "progress": data.get("progress", 0)
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
    if data is None:
        raise HTTPException(status_code=404, detail="분석 데이터를 읽을 수 없습니다.")

    return {
        "analysis_id": analysis_id,
        "status": data.get("status", "unknown"),
        "progress": data.get("progress", 0),
        "current_step": data.get("current_step", ""),
        "progress_message": data.get("progress_message", ""),  # 실시간 메시지
        "timeline": data.get("timeline", []),
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

        # 임시 G-code 파일 유지 (export 기능에서 원본 필요)
        # 파일 정리는 cleanup_old_analyses()에서 일괄 처리

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

        # PatchPlan 복원 (모든 필드 포함)
        patches = [
            PatchSuggestion(
                line_index=p.get("line_index") or p.get("line", 0),
                original_line=p.get("original_line") or p.get("original", ""),
                action=p.get("action", "review"),
                new_line=p.get("new_line") or p.get("modified"),
                reason=p.get("reason", ""),
                priority=i,
                issue_type=p.get("issue_type", "unknown"),
                autofix_allowed=p.get("autofix_allowed", True),
                position=p.get("position"),
                vendor_extension=p.get("vendor_extension")
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

        # 임시 G-code 파일만 삭제 (상태 파일은 클라이언트가 조회할 수 있도록 유지)
        _cleanup_temp_gcode_file(data.get("temp_file"))

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


# ============================================================
# Internal Functions for Chat API Integration
# ============================================================

class GCodeAnalysisInternalResult(BaseModel):
    """Chat API용 내부 분석 결과"""
    analysis_id: str
    status: str
    segments: Optional[Dict[str, Any]] = None
    stream_url: str
    message: str
    layer_count: int = 0


async def process_gcode_analysis_internal(
    gcode_content: str,
    user_id: Optional[str] = None,
    printer_info: Optional[Dict[str, Any]] = None,
    filament_type: Optional[str] = None,
    language: str = "ko",
    analysis_id: Optional[str] = None
) -> GCodeAnalysisInternalResult:
    """
    Chat API에서 직접 호출하는 내부 G-code 분석 함수

    1단계: 세그먼트 추출 (동기) - 즉시 반환
    2단계: LLM 분석 (백그라운드) - SSE 스트리밍

    Args:
        gcode_content: G-code 파일 내용
        user_id: 사용자 ID
        printer_info: 프린터 정보
        filament_type: 필라멘트 타입
        language: 응답 언어
        analysis_id: 분석 ID (없으면 자동 생성)

    Returns:
        GCodeAnalysisInternalResult: 세그먼트 데이터 + 스트림 URL
    """
    from gcode_analyzer.segment_extractor import extract_segments, EncodingError

    analysis_id = analysis_id or str(uuid.uuid4())

    # 임시 파일 생성
    output_dir = os.getenv("OUTPUT_DIR", "./output")
    os.makedirs(output_dir, exist_ok=True)

    temp_file_path = os.path.join(output_dir, f"gcode_chat_{analysis_id}.gcode")
    with open(temp_file_path, 'w', encoding='utf-8') as f:
        f.write(gcode_content)

    # 1단계: 세그먼트 추출 (동기)
    try:
        segments = extract_segments(temp_file_path, binary_format=True)
        layer_count = segments.get('metadata', {}).get('layerCount', 0)
    except EncodingError as e:
        logger.error(f"[GCode] Segment extraction encoding error: {e}")
        raise ValueError(f"G-code 인코딩 오류: {e}")
    except Exception as e:
        logger.error(f"[GCode] Segment extraction failed: {e}")
        raise ValueError(f"G-code 세그먼트 추출 실패: {e}")

    # 분석 상태 초기화
    initial_data = {
        "status": "segments_ready",
        "progress": 0.2,  # 세그먼트 추출 완료
        "current_step": "segments_extracted",
        "progress_message": f"세그먼트 추출 완료 ({layer_count}개 레이어)",
        "timeline": [{
            "step": 1,
            "label": f"세그먼트 추출 완료 ({layer_count}개 레이어)",
            "status": "done",
            "timestamp": datetime.now().isoformat()
        }],
        "temp_file": temp_file_path,
        "printer_info": printer_info,
        "filament_type": filament_type,
        "user_id": user_id,
        "language": language,
        "segments": segments,
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat()
    }
    set_analysis(analysis_id, initial_data)

    logger.info(f"[GCode] Chat analysis started: {analysis_id} (layers={layer_count})")

    # 2단계: LLM 분석 백그라운드 실행
    import asyncio
    asyncio.create_task(run_gcode_analysis_task(analysis_id))

    return GCodeAnalysisInternalResult(
        analysis_id=analysis_id,
        status="segments_ready",
        segments=segments,
        stream_url=f"/api/v1/gcode/analysis/{analysis_id}/stream",
        message=f"세그먼트 추출 완료. {layer_count}개 레이어를 감지했습니다. LLM 분석이 백그라운드에서 진행됩니다.",
        layer_count=layer_count
    )


# ============================================================
# Segment + LLM Streaming Analysis API
# ============================================================

@router.post("/analyze-with-segments")
async def analyze_gcode_with_segments(request: GCodeSegmentAnalysisRequest, background_tasks: BackgroundTasks):
    """
    세그먼트 추출 + LLM 분석 (스트리밍)

    **2단계 응답 방식:**
    1. 세그먼트 데이터 (Float32Array + Base64) 즉시 반환 (~1-3초)
    2. LLM 분석 백그라운드 실행, 완료 시 SSE로 전송

    **사용 방법:**
    1. 이 엔드포인트 호출 → segments 데이터 즉시 수신
    2. analysis_id로 SSE 스트림 연결 → LLM 분석 진행률 & 결과 수신

    **응답 예시:**
    ```json
    {
        "analysis_id": "xxx",
        "status": "segments_ready",
        "segments": {
            "layers": [
                {
                    "layerNum": 0,
                    "z": 0.2,
                    "extrusionData": "base64...",
                    "travelData": "base64...",
                    "extrusionCount": 1234,
                    "travelCount": 567
                },
                ...
            ],
            "metadata": { ... }
        },
        "llm_analysis_started": true,
        "stream_url": "/api/v1/gcode/analysis/{analysis_id}/stream"
    }
    ```
    """
    from gcode_analyzer.segment_extractor import extract_segments, EncodingError

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

    temp_file_path = os.path.join(output_dir, f"gcode_segment_{analysis_id}.gcode")
    with open(temp_file_path, 'w', encoding='utf-8') as f:
        f.write(request.gcode_content)

    # 1단계: 세그먼트 추출 (즉시)
    try:
        segments = extract_segments(temp_file_path, binary_format=request.binary_format)
    except EncodingError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": "encoding_error",
                "message": str(e),
                "analysis_id": analysis_id
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": "segment_extraction_failed",
                "message": str(e),
                "analysis_id": analysis_id
            }
        )

    # 분석 상태 초기화
    initial_data = {
        "status": "segments_ready",
        "progress": 0.2,  # 세그먼트 추출 완료
        "current_step": "segments_extracted",
        "timeline": [{
            "step": 1,
            "label": f"세그먼트 추출 완료 ({segments['metadata']['layerCount']}개 레이어)",
            "status": "done",
            "timestamp": datetime.now().isoformat()
        }],
        "temp_file": temp_file_path,
        "printer_info": request.printer_info.dict() if request.printer_info else None,
        "filament_type": request.filament_type,
        "user_id": request.user_id,
        "language": request.language or "ko",
        "segments": segments,  # 세그먼트 데이터 저장
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat()
    }
    set_analysis(analysis_id, initial_data)

    logger.info(f"[GCode] Segments extracted: {analysis_id} (layers={segments['metadata']['layerCount']})")

    # 2단계: LLM 분석 백그라운드 실행
    background_tasks.add_task(run_gcode_analysis_task, analysis_id)

    return {
        "analysis_id": analysis_id,
        "status": "segments_ready",
        "segments": segments,
        "llm_analysis_started": True,
        "message": "세그먼트 추출 완료. LLM 분석이 백그라운드에서 진행됩니다.",
        "stream_url": f"/api/v1/gcode/analysis/{analysis_id}/stream"
    }


@router.get("/analysis/{analysis_id}/segments")
async def get_gcode_segments(analysis_id: str):
    """
    세그먼트 데이터만 조회

    분석 완료 전에도 세그먼트 데이터를 즉시 반환합니다.
    (analyze-with-segments로 시작한 경우)
    """
    if not exists(analysis_id):
        raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")

    data = get_analysis(analysis_id)
    if data is None:
        raise HTTPException(status_code=404, detail="분석 데이터를 읽을 수 없습니다.")

    segments = data.get("segments")
    if not segments:
        raise HTTPException(status_code=400, detail="세그먼트 데이터가 없습니다. /analyze-with-segments를 사용하세요.")

    return {
        "analysis_id": analysis_id,
        "status": data.get("status", "unknown"),
        "segments": segments
    }


# ============================================================
# AI Issue Resolver API (AI 해결하기)
# ============================================================

class IssueResolveRequest(BaseModel):
    """이슈 해결 요청"""
    analysis_id: str  # 분석 ID
    conversation_id: Optional[str] = None  # 대화 세션 ID (같은 대화로 묶기 위함)
    issue: Dict[str, Any]  # 이슈 정보 (line, type, severity, title, description 등)
    gcode_context: Optional[str] = None  # 클라이언트에서 전달하는 G-code 컨텍스트 (앞뒤 50줄, 총 100줄)
    language: str = "ko"


@router.post("/analysis/{analysis_id}/resolve-issue")
async def resolve_gcode_issue(analysis_id: str, request: IssueResolveRequest):
    """
    G-code 이슈에 대한 AI 해결 방법 제공

    이슈의 원인을 분석하고 상세한 해결 방법을 제공합니다.

    ## 요청 예시
    ```json
    {
        "analysis_id": "uuid-xxx",
        "conversation_id": "conv_abc123",
        "issue": {
            "line": 137,
            "type": "cold_extrusion",
            "severity": "high",
            "title": "저온 압출",
            "description": "첫 압출 전 노즐 온도가 충분하지 않습니다.",
            "fix_proposal": "M109 S200 추가"
        },
        "gcode_context": "135: G1 X10 Y10\\n136: M104 S0\\n>>> 137: G1 E5 F300\\n138: G1 X20...",
        "language": "ko"
    }
    ```

    ## 응답 구조
    - conversation_id: 대화 세션 ID
    - problem_analysis: 문제 원인 분석
    - impact: 출력물에 미치는 영향
    - solution: 단계별 해결 방법
    - code_fix: 수정된 G-code (있는 경우)
    - prevention: 예방 방법
    """
    from gcode_analyzer.llm.issue_resolver import resolve_issue, extract_gcode_context
    import uuid as uuid_module

    # conversation_id 생성 또는 사용
    conversation_id = request.conversation_id or f"conv_{uuid_module.uuid4().hex[:12]}"

    # 분석 데이터 확인
    if not exists(analysis_id):
        raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")

    data = get_analysis(analysis_id)
    if data is None:
        raise HTTPException(status_code=404, detail="분석 데이터를 읽을 수 없습니다.")

    line_number = request.issue.get("line", 1)

    # G-code 컨텍스트: 클라이언트 전달값 우선, 없으면 서버에서 추출
    gcode_context = request.gcode_context

    if not gcode_context:
        # 서버에서 G-code 파일 읽어서 컨텍스트 추출 (fallback)
        temp_file = data.get("temp_file")
        if temp_file and os.path.exists(temp_file):
            try:
                with open(temp_file, 'r', encoding='utf-8') as f:
                    gcode_content = f.read()
                gcode_context = extract_gcode_context(gcode_content, line_number, context_lines=50)
            except Exception as e:
                logger.warning(f"[IssueResolver] Failed to read G-code file: {e}")
                gcode_context = "(G-code 컨텍스트 없음)"
        else:
            gcode_context = "(G-code 컨텍스트 없음)"

    # 요약 정보 추출
    result_data = data.get("result", {})
    summary_info = {
        "temperature": result_data.get("summary", {}).get("temperature", {}),
        "feed_rate": result_data.get("summary", {}).get("feed_rate", {}),
        "filament_type": data.get("filament_type"),
        "slicer_info": result_data.get("summary", {}).get("slicer_info", {})
    }

    try:
        result = await resolve_issue(
            issue=request.issue,
            gcode_context=gcode_context,
            summary_info=summary_info,
            language=request.language
        )

        return {
            "success": True,
            "conversation_id": conversation_id,
            "analysis_id": analysis_id,
            "issue_line": line_number,
            "resolution": result["resolution"],
            "updated_issue": result["updated_issue"]
        }

    except Exception as e:
        logger.error(f"[IssueResolver] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"이슈 분석 실패: {str(e)}")


@router.post("/resolve-issue")
async def resolve_issue_standalone(request: IssueResolveRequest):
    """
    독립 이슈 해결 API (analysis_id 없이도 사용 가능)

    클라이언트에서 G-code 컨텍스트(앞뒤 50줄)를 직접 전달하여 분석합니다.

    ## 요청 예시
    ```json
    {
        "analysis_id": "uuid-xxx",
        "conversation_id": "conv_abc123",
        "issue": {
            "line": 137,
            "type": "cold_extrusion",
            "severity": "high",
            "title": "저온 압출",
            "description": "첫 압출 전 노즐 온도가 충분하지 않습니다."
        },
        "gcode_context": "87: G28\\n88: G1 Z5\\n...\\n>>> 137: G1 E5 F300  <<< [문제 라인]\\n...\\n187: G1 X100"
    }
    ```
    """
    from gcode_analyzer.llm.issue_resolver import resolve_issue
    import uuid as uuid_module

    # conversation_id 생성 또는 사용
    conversation_id = request.conversation_id or f"conv_{uuid_module.uuid4().hex[:12]}"

    # G-code 컨텍스트: 클라이언트 전달값 사용 (없으면 없음으로 처리)
    gcode_context = request.gcode_context or "(G-code 컨텍스트 없음)"

    try:
        result = await resolve_issue(
            issue=request.issue,
            gcode_context=gcode_context,
            summary_info={},
            language=request.language
        )

        return {
            "success": True,
            "conversation_id": conversation_id,
            "analysis_id": request.analysis_id,
            "issue_line": request.issue.get("line"),
            "resolution": result["resolution"],
            "updated_issue": result["updated_issue"]
        }

    except Exception as e:
        logger.error(f"[IssueResolver] Standalone error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"이슈 분석 실패: {str(e)}")


# ============================================================
# Issue Types Management API
# ============================================================

@router.get("/issue-types")
async def get_issue_types():
    """
    등록된 모든 이슈 유형 조회

    Returns:
        List[Dict]: 이슈 유형 목록 (type_code, label, category, severity 등)
    """
    from gcode_analyzer.db.issue_types import get_all_issue_types

    try:
        issue_types = get_all_issue_types()
        return {
            "success": True,
            "count": len(issue_types),
            "issue_types": issue_types
        }
    except Exception as e:
        logger.error(f"[IssueTypes] Error getting issue types: {e}")
        raise HTTPException(status_code=500, detail=f"이슈 유형 조회 실패: {str(e)}")


@router.get("/issue-types/{type_code}")
async def get_issue_type(type_code: str):
    """
    특정 이슈 유형 조회

    Args:
        type_code: 이슈 유형 코드 (예: "cold_extrusion")

    Returns:
        Dict: 이슈 유형 정보
    """
    from gcode_analyzer.db.issue_types import get_issue_type_info

    try:
        issue_type = get_issue_type_info(type_code)
        return {
            "success": True,
            "issue_type": issue_type
        }
    except Exception as e:
        logger.error(f"[IssueTypes] Error getting issue type {type_code}: {e}")
        raise HTTPException(status_code=500, detail=f"이슈 유형 조회 실패: {str(e)}")


@router.post("/issue-types/sync")
async def sync_issue_types():
    """
    코드 정의 기반 이슈 유형 DB 동기화

    코드에서 정의된 모든 이슈 유형을 DB에 추가/업데이트합니다.
    관리자 기능으로 초기 설정 또는 업데이트 시 사용합니다.

    Returns:
        Dict: 동기화 결과 (created, updated, skipped, errors)
    """
    from gcode_analyzer.db.issue_types import sync_issue_types_from_code

    try:
        result = sync_issue_types_from_code()
        return {
            "success": True,
            "message": "이슈 유형 동기화 완료",
            "result": {
                "created": result["created"],
                "created_count": len(result["created"]),
                "updated": result["updated"],
                "updated_count": len(result["updated"]),
                "skipped_count": len(result["skipped"]),
                "errors": result["errors"]
            }
        }
    except Exception as e:
        logger.error(f"[IssueTypes] Error syncing issue types: {e}")
        raise HTTPException(status_code=500, detail=f"이슈 유형 동기화 실패: {str(e)}")

