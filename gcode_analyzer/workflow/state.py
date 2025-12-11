"""
LangGraph Workflow State Definition (개선 버전)
"""
from typing import TypedDict, List, Dict, Any, Optional

class AnalysisState(TypedDict):
    """워크플로우 상태"""
    # 입력
    file_path: str
    filament_type: Optional[str]
    printer_info: Optional[Dict[str, Any]]

    # 분석 모드
    # "summary_only": 요약만 수행 (LLM 분석 안 함)
    # "full": 요약 + 에러 분석 (전체)
    # "error_analysis": 기존 요약 기반 에러 분석만
    analysis_mode: str

    # 결과 언어 ("ko" | "en" | "ja" | "zh")
    language: str

    # 파싱 결과
    raw_lines: List[str]
    parsed_lines: List[Any]  # List[GCodeLine]
    summary: Dict[str, Any]  # 기존 간단 요약
    layer_map: Dict[int, int]  # {line_index: layer_number} 매핑

    # 종합 요약 - GCodeComprehensiveSummary (온도, 피드, 서포트 등)
    comprehensive_summary: Optional[Dict[str, Any]]

    # 구간 분류
    section_boundaries: Dict[str, int]  # {start_end, body_end, total_lines}

    # 온도 이벤트 및 분석
    temp_events: List[Any]
    temp_changes: Dict[str, Any]                  # 온도 변화 전체 (노즐/베드)
    rule_results: List[Dict[str, Any]]            # 룰 엔진 결과
    event_analysis_results: List[Dict[str, Any]]  # Python 분석 결과
    events_needing_llm: List[Dict[str, Any]]      # LLM 분석 필요한 것만
    normal_events: List[Dict[str, Any]]           # 정상 이벤트
    event_summary: Dict[str, Any]                 # 분석 요약

    # 기존 필드 (호환성)
    significant_events: List[Any]
    snippets: List[Dict[str, Any]]

    # LLM 분석 결과
    llm_results: List[Dict[str, Any]]
    issues_found: List[Dict[str, Any]]
    expert_assessment: Optional[Dict[str, Any]]   # Answer Sheet (NEW)

    # 토큰 사용량
    token_usage: Dict[str, int]

    # 패치 관련
    patch_plan: Optional[Dict[str, Any]]
    patch_results: Optional[Dict[str, Any]]
    patched_gcode: Optional[List[str]]

    # 최종 결과
    final_summary: Dict[str, Any]

    # 사용자 승인 및 패치
    user_approved: bool

    # 진행 상태 (SSE용)
    current_step: str
    progress: float
    timeline: List[Dict[str, Any]]
