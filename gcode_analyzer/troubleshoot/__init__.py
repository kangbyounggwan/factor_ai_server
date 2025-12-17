"""
3D 프린터 고장 진단 및 해결 도구

주요 기능:
- 문제 이미지 분석 (Gemini Vision)
- 증상 텍스트 분석
- 웹 검색 (제조사 공식 문서, 커뮤니티)
- 솔루션 생성

사용법:
    from gcode_analyzer.troubleshoot import router

    # FastAPI 앱에 라우터 등록
    app.include_router(router)

    # 또는 직접 함수 사용
    from gcode_analyzer.troubleshoot.image_analyzer import analyze_problem_image
    from gcode_analyzer.troubleshoot.web_searcher import search_solutions
    from gcode_analyzer.troubleshoot.solution_generator import generate_troubleshooting_solution

API 엔드포인트:
    POST /api/v1/troubleshoot/diagnose - 문제 진단
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
    TokenUsage
)
from .router import router
from .printer_database import (
    get_manufacturer,
    get_all_manufacturers,
    get_search_context,
    find_manufacturer_by_model
)

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

    # Database functions
    'get_manufacturer',
    'get_all_manufacturers',
    'get_search_context',
    'find_manufacturer_by_model',
]
