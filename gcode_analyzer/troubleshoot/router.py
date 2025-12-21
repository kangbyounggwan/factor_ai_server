"""
트러블슈팅 API 라우터

새로운 3단계 흐름:
1. Vision + 질문 증강 + KB 검색 (ImageAnalyzer + KBSearcher)
2. Perplexity 검색 (PerplexitySearcher) - Evidence 수집 (언어별)
3. 구조화 편집기 (StructuredEditor) - 근거 기반 응답 생성

핵심 원칙:
- 솔루션은 명확하고 간단하게
- 솔루션에는 반드시 출처 URL 포함
- 언어별 검색: 한국어면 한국어로, 영어면 영어로

POST /api/v1/troubleshoot/diagnose - 3D 프린터 문제 진단 (새 흐름)
POST /api/v1/troubleshoot/diagnose-legacy - 기존 흐름 (하위 호환성)
GET /api/v1/troubleshoot/manufacturers - 지원 제조사 목록
GET /api/v1/troubleshoot/models/{manufacturer} - 제조사별 모델 목록
GET /api/v1/troubleshoot/kb/search - KB 검색 (내부 지식 베이스)
"""
import uuid
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .models import (
    DiagnoseRequest, DiagnoseResponse,
    Problem, Solution, Reference, ExpertOpinion, TokenUsage,
    ProblemType, SearchDecision, Difficulty, PerplexitySearchResult,
    QueryAugmentation
)
from .printer_database import (
    get_all_manufacturers, get_manufacturer,
    get_series_for_manufacturer, get_search_context
)
from .image_analyzer import ImageAnalyzer
from .perplexity_searcher import PerplexitySearcher, get_perplexity_api_key
from .structured_editor import StructuredEditor
from .kb import search_kb, get_all_entries, get_entry_by_id
# 하위 호환성을 위한 기존 모듈
from .web_searcher import WebSearcher
from .solution_generator import SolutionGenerator

logger = logging.getLogger(__name__)


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
    3D 프린터 문제 진단 (새로운 3단계 흐름)

    1단계: Vision + 질문 증강 - 이미지 분석 및 검색용 쿼리 생성
    2단계: Perplexity 검색 - Evidence(근거) 수집
    3단계: 구조화 편집 - 근거 기반 응답 생성 (추론 없이 편집만)

    Args:
        request: 진단 요청 (제조사, 모델, 증상 텍스트, 이미지, 사용자 모델 등)

    Returns:
        진단 결과 및 해결책
    """
    diagnosis_id = f"diag_{uuid.uuid4().hex[:12]}"
    token_usage = TokenUsage()

    # 언어 및 모델 설정
    language = request.language or "ko"
    model_name = request.model_name  # 사용자 선택 모델

    logger.info(f"Starting diagnosis {diagnosis_id} with model: {model_name or 'default'}")

    # ================================================================
    # 1단계: Vision + 질문 증강
    # ================================================================
    image_analysis = None
    augmented_query = ""

    if request.images:
        analyzer = ImageAnalyzer(language=language, model_name=model_name)
        image_analysis = await analyzer.analyze_images(
            images=request.images,
            additional_context=request.additional_context,
            symptom_text=request.symptom_text  # 모호한 질문도 컨텍스트로 활용
        )
        token_usage.image_analysis = image_analysis.tokens_used
        augmented_query = image_analysis.augmented_query
        logger.info(f"Image analysis complete. Augmented query: {augmented_query[:100]}...")

    # 문제 유형 결정
    if image_analysis and image_analysis.detected_problems:
        problem_type = image_analysis.detected_problems[0]
    else:
        problem_type = ProblemType.UNKNOWN

    # 이미지가 없으면 증상 텍스트를 검색 쿼리로 사용
    if not augmented_query:
        augmented_query = f"3D printer {request.symptom_text} troubleshooting fix solution"

    # ================================================================
    # Gate: 검색 필요 여부 판단
    # ================================================================
    needs_search = SearchDecision.RECOMMENDED  # 기본값
    search_skipped = False
    internal_solution = ""

    if image_analysis:
        needs_search = image_analysis.needs_search
        internal_solution = image_analysis.internal_solution
        logger.info(f"Gate decision: needs_search={needs_search.value}")

    # ================================================================
    # 1.5단계: KB 검색 (유사 증상 매칭)
    # ================================================================
    kb_problem_name = None
    kb_results = None

    try:
        # 증상 텍스트 + 이미지 분석 결과로 KB 검색
        search_text = request.symptom_text or ""
        if image_analysis:
            search_text += " " + image_analysis.description
            visual_signs = image_analysis.visual_evidence
        else:
            visual_signs = []

        kb_results = search_kb(
            query=search_text,
            description=augmented_query,
            visual_signs=visual_signs,
            top_k=3
        )

        if kb_results.results:
            # 가장 유사한 문제 이름 추출 (Perplexity 검색에 활용)
            top_match = kb_results.results[0]
            if language == "ko":
                kb_problem_name = top_match.entry.problem_name_ko
            else:
                kb_problem_name = top_match.entry.problem_name

            logger.info(f"KB match: {kb_problem_name} (score: {top_match.similarity_score:.2f})")
    except Exception as e:
        logger.warning(f"KB search failed: {e}")
        kb_results = None

    # ================================================================
    # 2단계: Perplexity 검색 (Evidence 수집) - 언어별 검색
    # ================================================================
    if needs_search == SearchDecision.NOT_NEEDED:
        # 검색 스킵 - 하지만 KB 결과는 활용
        search_skipped = True
        search_result = PerplexitySearchResult(
            query=augmented_query,
            findings=[],
            citations=[],
            summary=internal_solution,
            tokens_used=0
        )
        logger.info(f"Search skipped. Reason: {image_analysis.search_skip_reason if image_analysis else 'N/A'}")
    else:
        # Perplexity 검색 수행 (언어별, KB 문제 이름 전달)
        perplexity_searcher = PerplexitySearcher(
            user_plan=request.user_plan,
            language=language
        )
        search_result = await perplexity_searcher.search(
            augmented_query=augmented_query,
            problem_type=problem_type,
            manufacturer=request.manufacturer,
            model=request.model,
            kb_problem_name=kb_problem_name  # KB 매칭 결과 전달
        )
        token_usage.search_summary = search_result.tokens_used
        logger.info(f"Perplexity search complete. Found {len(search_result.findings)} findings")

    # Evidence에서 Reference 추출
    references = []
    for evidence in search_result.findings:
        if evidence.source_url:
            references.append(Reference(
                title=evidence.source_title or evidence.fact[:50],
                url=evidence.source_url,
                source="perplexity",
                relevance=evidence.relevance,
                snippet=evidence.fact[:200] if evidence.fact else None
            ))

    # citations도 추가
    for url in search_result.citations:
        if url and not any(r.url == url for r in references):
            references.append(Reference(
                title=url.split('//')[-1].split('/')[0],  # 도메인 추출
                url=url,
                source="citation",
                relevance=0.7,
                snippet=None
            ))

    # ================================================================
    # 3단계: 구조화 편집 (근거 기반 응답 생성)
    # ================================================================
    editor = StructuredEditor(language=language, model_name=model_name)
    structured_diagnosis = await editor.edit(
        image_analysis=image_analysis,
        search_result=search_result,
        symptom_text=request.symptom_text,
        problem_type=problem_type
    )
    logger.info("Structured editing complete")

    # 기존 응답 형식으로 변환 (하위 호환성)
    solution_data = editor.to_legacy_format(
        diagnosis=structured_diagnosis,
        problem_type=problem_type,
        search_result=search_result
    )

    # ================================================================
    # 응답 구성
    # ================================================================
    # 프린터 정보 수집
    printer_info = {}
    if request.manufacturer:
        printer_info = get_search_context(request.manufacturer, request.model)

    # follow_up_questions 추가 (새로운 필드)
    if image_analysis and image_analysis.follow_up_questions:
        printer_info["follow_up_questions"] = image_analysis.follow_up_questions

    # Gate 정보 추가
    printer_info["search_skipped"] = search_skipped
    if search_skipped and image_analysis:
        printer_info["search_skip_reason"] = image_analysis.search_skip_reason

    # KB 매칭 결과 추가
    if kb_results and kb_results.results:
        printer_info["kb_matches"] = [
            {
                "problem_name": r.entry.problem_name,
                "problem_name_ko": r.entry.problem_name_ko,
                "similarity_score": r.similarity_score,
                "matched_symptoms": r.matched_symptoms,
                "quick_checks": r.entry.quick_checks,
                "causes": r.entry.causes
            }
            for r in kb_results.results[:3]
        ]

    # 토큰 사용량 계산
    token_usage.total = (
        token_usage.image_analysis +
        token_usage.search_query +
        token_usage.search_summary +
        token_usage.solution_generation
    )

    # 질문 증강 결과 구성
    query_augmentation = QueryAugmentation(
        original_symptom=request.symptom_text or "",
        augmented_query=augmented_query,
        detected_problems=[p.value for p in (image_analysis.detected_problems if image_analysis else [])],
        visual_evidence=image_analysis.visual_evidence if image_analysis else [],
        specific_symptoms=image_analysis.specific_symptoms if image_analysis else [],
        follow_up_questions=image_analysis.follow_up_questions if image_analysis else [],
        search_decision=needs_search.value
    )

    return DiagnoseResponse(
        diagnosis_id=diagnosis_id,
        problem=solution_data["problem"],
        solutions=solution_data["solutions"],
        references=references[:10],
        expert_opinion=solution_data["expert_opinion"],
        printer_info=printer_info,
        token_usage=token_usage,
        query_augmentation=query_augmentation
    )


@router.post("/diagnose-legacy", response_model=DiagnoseResponse)
async def diagnose_problem_legacy(request: DiagnoseRequest):
    """
    3D 프린터 문제 진단 (기존 흐름 - 하위 호환성)

    기존 방식: ImageAnalyzer → WebSearcher → SolutionGenerator

    Args:
        request: 진단 요청

    Returns:
        진단 결과 및 해결책
    """
    diagnosis_id = f"diag_{uuid.uuid4().hex[:12]}"
    token_usage = TokenUsage()

    language = request.language or "ko"

    # 1. 이미지 분석
    image_analysis = None
    if request.images:
        analyzer = ImageAnalyzer(language=language)
        image_analysis = await analyzer.analyze_images(
            images=request.images,
            additional_context=request.additional_context
        )
        token_usage.image_analysis = image_analysis.tokens_used

    # 2. 문제 유형 결정
    if image_analysis and image_analysis.detected_problems:
        problem_type = image_analysis.detected_problems[0]
    else:
        problem_type = ProblemType.UNKNOWN

    # 3. 웹 검색 (기존 WebSearcher)
    searcher = WebSearcher(language=language, user_plan=request.user_plan)
    search_results = await searcher.search(
        manufacturer=request.manufacturer,
        model=request.model,
        problem_type=problem_type,
        symptom_text=request.symptom_text
    )

    references = []
    for result in search_results:
        for ref in result.results:
            if ref not in references:
                references.append(ref)
        token_usage.search_summary += result.tokens_used

    # 4. 솔루션 생성 (기존 SolutionGenerator)
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

    token_usage.total = (
        token_usage.image_analysis +
        token_usage.search_query +
        token_usage.search_summary +
        token_usage.solution_generation
    )

    return DiagnoseResponse(
        diagnosis_id=diagnosis_id,
        problem=solution_data["problem"],
        solutions=solution_data["solutions"],
        references=references[:10],
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


# ============================================================
# KB Search Endpoint (내부 지식 베이스 검색)
# ============================================================
class KBSearchRequest(BaseModel):
    """KB 검색 요청"""
    query: str  # 증상 텍스트
    description: Optional[str] = None  # 추가 설명
    visual_signs: Optional[List[str]] = None  # 시각적 증거
    top_k: int = 5  # 반환할 최대 결과 수
    language: str = "ko"  # 응답 언어


@router.post("/kb/search")
async def search_knowledge_base(request: KBSearchRequest):
    """
    내부 Knowledge Base 검색

    증상 텍스트로 유사한 3D 프린팅 문제를 검색합니다.
    Perplexity 검색 없이 즉시 결과를 반환합니다.

    ## 요청 예시
    ```json
    {
        "query": "출력물 표면이 거칠고 레이어가 잘 안보임",
        "description": "필라멘트에서 팝핑 소리가 남",
        "top_k": 3,
        "language": "ko"
    }
    ```

    ## 응답
    - 매칭된 문제 목록 (유사도 점수 포함)
    - 각 문제의 원인, 즉시 확인 사항
    - 관련 키워드

    Note: 실제 솔루션과 출처 URL은 /diagnose API에서 Perplexity 검색으로 제공됩니다.
    """
    try:
        results = search_kb(
            query=request.query,
            description=request.description or "",
            visual_signs=request.visual_signs,
            top_k=request.top_k
        )

        # 언어에 맞게 결과 포맷팅
        formatted_results = []
        for r in results.results:
            if request.language == "ko":
                formatted_results.append({
                    "problem_id": r.entry.id,
                    "problem_name": r.entry.problem_name_ko,
                    "problem_name_en": r.entry.problem_name,
                    "category": r.entry.category.value,
                    "severity": r.entry.severity.value,
                    "similarity_score": round(r.similarity_score, 3),
                    "matched_symptoms": r.matched_symptoms,
                    "symptoms": r.entry.symptoms_ko,
                    "causes": r.entry.causes,
                    "quick_checks": r.entry.quick_checks,
                    "keywords": r.entry.keywords
                })
            else:
                formatted_results.append({
                    "problem_id": r.entry.id,
                    "problem_name": r.entry.problem_name,
                    "problem_name_ko": r.entry.problem_name_ko,
                    "category": r.entry.category.value,
                    "severity": r.entry.severity.value,
                    "similarity_score": round(r.similarity_score, 3),
                    "matched_symptoms": r.matched_symptoms,
                    "symptoms": r.entry.symptoms,
                    "causes": r.entry.causes,
                    "quick_checks": r.entry.quick_checks,
                    "keywords": r.entry.keywords
                })

        return {
            "success": True,
            "query": request.query,
            "total_found": results.total_found,
            "search_method": results.search_method,
            "results": formatted_results,
            "note": "솔루션과 출처 URL은 /diagnose API에서 Perplexity 검색으로 제공됩니다."
        }

    except Exception as e:
        logger.error(f"KB search failed: {e}")
        raise HTTPException(status_code=500, detail=f"KB 검색 실패: {str(e)}")


@router.get("/kb/problems")
async def list_kb_problems(language: str = "ko"):
    """
    Knowledge Base에 등록된 모든 문제 목록 조회

    Args:
        language: 응답 언어 (ko, en)

    Returns:
        등록된 문제 목록
    """
    entries = get_all_entries()

    problems = []
    for entry in entries:
        if language == "ko":
            problems.append({
                "id": entry.id,
                "name": entry.problem_name_ko,
                "name_en": entry.problem_name,
                "category": entry.category.value,
                "severity": entry.severity.value,
                "symptoms_count": len(entry.symptoms_ko),
                "keywords": entry.keywords[:5]
            })
        else:
            problems.append({
                "id": entry.id,
                "name": entry.problem_name,
                "name_ko": entry.problem_name_ko,
                "category": entry.category.value,
                "severity": entry.severity.value,
                "symptoms_count": len(entry.symptoms),
                "keywords": entry.keywords[:5]
            })

    return {
        "success": True,
        "total": len(problems),
        "problems": problems
    }


@router.get("/kb/problems/{problem_id}")
async def get_kb_problem_detail(problem_id: str, language: str = "ko"):
    """
    특정 문제의 상세 정보 조회

    Args:
        problem_id: 문제 ID (예: under_extrusion, stringing)
        language: 응답 언어

    Returns:
        문제 상세 정보 (증상, 원인, 즉시 확인 사항)
    """
    entry = get_entry_by_id(problem_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"문제 '{problem_id}'를 찾을 수 없습니다")

    if language == "ko":
        return {
            "success": True,
            "problem": {
                "id": entry.id,
                "name": entry.problem_name_ko,
                "name_en": entry.problem_name,
                "category": entry.category.value,
                "severity": entry.severity.value,
                "symptoms": entry.symptoms_ko,
                "visual_signs": entry.visual_signs,
                "causes": entry.causes,
                "quick_checks": entry.quick_checks,
                "keywords": entry.keywords,
                "printer_types": entry.printer_types,
                "filament_types": entry.filament_types
            },
            "note": "솔루션과 출처 URL은 /diagnose API에서 Perplexity 검색으로 제공됩니다."
        }
    else:
        return {
            "success": True,
            "problem": {
                "id": entry.id,
                "name": entry.problem_name,
                "name_ko": entry.problem_name_ko,
                "category": entry.category.value,
                "severity": entry.severity.value,
                "symptoms": entry.symptoms,
                "visual_signs": entry.visual_signs,
                "causes": entry.causes,
                "quick_checks": entry.quick_checks,
                "keywords": entry.keywords,
                "printer_types": entry.printer_types,
                "filament_types": entry.filament_types
            },
            "note": "Solutions with source URLs are provided via /diagnose API using Perplexity search."
        }
