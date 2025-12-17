"""
트러블슈팅 API 라우터

POST /api/v1/troubleshoot/diagnose - 3D 프린터 문제 진단
GET /api/v1/troubleshoot/manufacturers - 지원 제조사 목록
GET /api/v1/troubleshoot/models/{manufacturer} - 제조사별 모델 목록
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .models import (
    DiagnoseRequest, DiagnoseResponse,
    Problem, Solution, Reference, ExpertOpinion, TokenUsage
)
from .printer_database import (
    get_all_manufacturers, get_manufacturer,
    get_series_for_manufacturer, get_search_context
)
from .image_analyzer import ImageAnalyzer
from .web_searcher import WebSearcher
from .solution_generator import SolutionGenerator


router = APIRouter(prefix="/api/v1/troubleshoot", tags=["troubleshoot"])


# ============================================================
# Response Models for endpoints
# ============================================================
class ManufacturerListResponse(BaseModel):
    """제조사 목록 응답"""
    manufacturers: List[str]


class ManufacturerDetailResponse(BaseModel):
    """제조사 상세 정보 응답"""
    name: str
    series: List[dict]
    official_url: str
    community_urls: List[str]
    firmware_type: str


# ============================================================
# Endpoints
# ============================================================
@router.get("/manufacturers", response_model=ManufacturerListResponse)
async def list_manufacturers():
    """
    지원하는 3D 프린터 제조사 목록 조회

    Returns:
        제조사 이름 목록
    """
    manufacturers = get_all_manufacturers()
    return ManufacturerListResponse(manufacturers=manufacturers)


@router.get("/manufacturers/{manufacturer}", response_model=ManufacturerDetailResponse)
async def get_manufacturer_detail(manufacturer: str):
    """
    제조사 상세 정보 조회

    Args:
        manufacturer: 제조사 이름 (예: creality, bambulab)

    Returns:
        제조사 상세 정보 (시리즈, 모델, URL 등)
    """
    info = get_manufacturer(manufacturer)
    if not info:
        raise HTTPException(status_code=404, detail=f"제조사 '{manufacturer}'를 찾을 수 없습니다")

    return ManufacturerDetailResponse(
        name=info.name,
        series=[
            {
                "name": s.name,
                "models": s.models,
                "description": s.description
            }
            for s in info.series
        ],
        official_url=info.official_support_url,
        community_urls=info.community_urls,
        firmware_type=info.firmware_type
    )


@router.post("/diagnose", response_model=DiagnoseResponse)
async def diagnose_problem(request: DiagnoseRequest):
    """
    3D 프린터 문제 진단

    이미지와 증상 텍스트를 분석하여 문제를 진단하고 해결책을 제안합니다.

    Args:
        request: 진단 요청 (제조사, 모델, 증상 텍스트, 이미지 등)

    Returns:
        진단 결과 및 해결책
    """
    diagnosis_id = f"diag_{uuid.uuid4().hex[:12]}"
    token_usage = TokenUsage()

    # 언어 설정
    language = request.language or "ko"

    # 1. 이미지 분석 (이미지가 있는 경우)
    image_analysis = None
    if request.images:
        analyzer = ImageAnalyzer(language=language)
        image_analysis = await analyzer.analyze_images(
            images=request.images,
            additional_context=request.additional_context
        )
        token_usage.image_analysis = image_analysis.tokens_used

    # 2. 문제 유형 결정 (이미지 분석 또는 텍스트 기반)
    from .models import ProblemType
    if image_analysis and image_analysis.detected_problems:
        problem_type = image_analysis.detected_problems[0]
    else:
        # 텍스트 기반 추론 (SolutionGenerator에서 처리)
        problem_type = ProblemType.UNKNOWN

    # 3. 웹 검색 (사용자 플랜에 따라 검색 방식 분기)
    searcher = WebSearcher(language=language, user_plan=request.user_plan)
    search_results = await searcher.search(
        manufacturer=request.manufacturer,
        model=request.model,
        problem_type=problem_type,
        symptom_text=request.symptom_text
    )

    # 검색 결과에서 참조 자료 추출
    references = []
    for result in search_results:
        for ref in result.results:
            if ref not in references:
                references.append(ref)
        token_usage.search_summary += result.tokens_used

    # 4. 솔루션 생성
    generator = SolutionGenerator(language=language)
    solution_data = await generator.generate_solution(
        manufacturer=request.manufacturer,
        model=request.model,
        symptom_text=request.symptom_text,
        image_analysis=image_analysis,
        search_results=search_results,
        filament_type=request.filament_type
    )

    # 5. 프린터 정보 수집
    printer_info = {}
    if request.manufacturer:
        printer_info = get_search_context(request.manufacturer, request.model)

    # 6. 토큰 사용량 계산
    token_usage.total = (
        token_usage.image_analysis +
        token_usage.search_query +
        token_usage.search_summary +
        token_usage.solution_generation
    )

    # 응답 구성
    return DiagnoseResponse(
        diagnosis_id=diagnosis_id,
        problem=solution_data["problem"],
        solutions=solution_data["solutions"],
        references=references[:10],  # 상위 10개
        expert_opinion=solution_data["expert_opinion"],
        printer_info=printer_info,
        token_usage=token_usage
    )


@router.get("/problem-types")
async def list_problem_types():
    """
    지원하는 문제 유형 목록 조회

    Returns:
        문제 유형 목록 및 설명
    """
    from .models import ProblemType

    problem_descriptions = {
        "bed_adhesion": "첫 레이어 접착 불량",
        "stringing": "스트링/거미줄",
        "warping": "뒤틀림/휨",
        "layer_shifting": "레이어 쉬프트",
        "under_extrusion": "압출 부족",
        "over_extrusion": "과압출",
        "ghosting": "고스팅/링잉",
        "z_banding": "Z 밴딩",
        "blob": "블롭/얼룩",
        "clogging": "노즐 막힘",
        "layer_separation": "레이어 분리",
        "elephant_foot": "엘리펀트 풋",
        "bridging_issue": "브릿징 문제",
        "overhang_issue": "오버행 문제",
        "surface_quality": "표면 품질 문제",
        "bed_leveling": "베드 레벨링",
        "nozzle_damage": "노즐 손상",
        "extruder_skip": "익스트루더 스킵",
        "heating_failure": "가열 실패",
        "motor_issue": "모터 문제",
        "belt_tension": "벨트 텐션",
        "filament_jam": "필라멘트 걸림",
        "slicer_settings": "슬라이서 설정",
        "gcode_error": "G-code 오류",
        "firmware_issue": "펌웨어 문제",
    }

    return {
        "problem_types": [
            {
                "type": pt.value,
                "description": problem_descriptions.get(pt.value, pt.value)
            }
            for pt in ProblemType
            if pt.value not in ["unknown", "other"]
        ]
    }
