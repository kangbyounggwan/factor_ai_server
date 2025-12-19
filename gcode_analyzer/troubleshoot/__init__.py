"""
3D 프린터 고장 진단 및 해결 도구

새로운 3단계 흐름:
1. Vision + 질문 증강 (ImageAnalyzer) - 이미지 분석 및 검색용 쿼리 생성
2. Perplexity 검색 (PerplexitySearcher) - Evidence(근거) 수집
3. 구조화 편집 (StructuredEditor) - 근거 기반 응답 생성 (추론 없이 편집만)

주요 기능:
- 문제 이미지 분석 + 질문 증강 (Vision LLM)
- Perplexity API로 Evidence 수집 (검색 + 요약 + 출처)
- 구조화 편집 (근거 기반, 추론 없음)
- 사용자 선택 모델 지원 (gemini, gpt, claude)

사용법:
    from gcode_analyzer.troubleshoot import router

    # FastAPI 앱에 라우터 등록
    app.include_router(router)

    # 또는 직접 함수 사용
    from gcode_analyzer.troubleshoot.image_analyzer import analyze_problem_image
    from gcode_analyzer.troubleshoot.perplexity_searcher import search_with_perplexity
    from gcode_analyzer.troubleshoot.structured_editor import edit_with_evidence

API 엔드포인트:
    POST /api/v1/troubleshoot/diagnose - 문제 진단 (새 흐름)
    POST /api/v1/troubleshoot/diagnose-legacy - 문제 진단 (기존 흐름)
    GET /api/v1/troubleshoot/manufacturers - 제조사 목록
    GET /api/v1/troubleshoot/manufacturers/{manufacturer} - 제조사 상세
    GET /api/v1/troubleshoot/problem-types - 문제 유형 목록
"""

from .models import (
    DiagnoseRequest,
    DiagnoseResponse,
    Problem,
    Solution,
    Reference,
    ExpertOpinion,
    ProblemType,
    Difficulty,
    UserPlan,
    ImageAnalysisResult,
    SearchResult,
    SearchQueries,
    TokenUsage,
    # 새 모델
    Evidence,
    PerplexitySearchResult,
    StructuredDiagnosis,
    SearchDecision
)
from .router import router
from .printer_database import (
    get_manufacturer,
    get_all_manufacturers,
    get_search_context,
    find_manufacturer_by_model
)
# 새 모듈 편의 함수
from .image_analyzer import analyze_problem_image
from .perplexity_searcher import search_with_perplexity
from .structured_editor import edit_with_evidence

__all__ = [
    # Router
    'router',

    # Models
    'DiagnoseRequest',
    'DiagnoseResponse',
    'Problem',
    'Solution',
    'Reference',
    'ExpertOpinion',
    'ProblemType',
    'Difficulty',
    'UserPlan',
    'ImageAnalysisResult',
    'SearchResult',
    'SearchQueries',
    'TokenUsage',
    # 새 모델
    'Evidence',
    'PerplexitySearchResult',
    'StructuredDiagnosis',
    'SearchDecision',

    # Database functions
    'get_manufacturer',
    'get_all_manufacturers',
    'get_search_context',
    'find_manufacturer_by_model',

    # 편의 함수
    'analyze_problem_image',
    'search_with_perplexity',
    'edit_with_evidence',
]
