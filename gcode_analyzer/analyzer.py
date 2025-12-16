"""
통합 분석기 - 워크플로우 실행 엔트리포인트
"""
import asyncio
from typing import Dict, Any, Optional
from .workflow import compile_workflow, AnalysisState
from .workflow.callback import ProgressCallback, ProgressTracker


def _create_initial_state(
    file_path: str,
    filament_type: Optional[str] = None,
    printer_info: Optional[Dict[str, Any]] = None,
    auto_approve: bool = False,
    analysis_mode: str = "full",
    language: str = "ko"
) -> AnalysisState:
    """초기 상태 생성"""
    return {
        "file_path": file_path,
        "filament_type": filament_type,
        "printer_info": printer_info,
        "analysis_mode": analysis_mode,
        "language": language,  # 언어 설정
        "raw_lines": [],
        "parsed_lines": [],
        "summary": {},
        "layer_map": {},  # line_index → layer_number 매핑
        "comprehensive_summary": None,
        "section_boundaries": {},
        "temp_events": [],
        "rule_results": [],
        "event_analysis_results": [],
        "events_needing_llm": [],
        "normal_events": [],
        "event_summary": {},
        "significant_events": [],
        "snippets": [],
        "llm_results": [],
        "issues_found": [],
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "patch_plan": None,
        "patch_results": None,
        "patched_gcode": None,
        "final_summary": {},
        "user_approved": auto_approve,
        "current_step": "init",
        "progress": 0.0,
        "timeline": []
    }


async def run_analysis(
    file_path: str,
    filament_type: Optional[str] = None,
    printer_info: Optional[Dict[str, Any]] = None,
    auto_approve: bool = False,
    analysis_mode: str = "full",
    progress_callback: Optional[ProgressCallback] = None,
    language: str = "ko"
) -> Dict[str, Any]:
    """
    G-code 분석 워크플로우 실행

    Args:
        file_path: G-code 파일 경로
        filament_type: 필라멘트 타입 (None이면 자동 감지)
        printer_info: 프린터 정보 (DB에서 가져온 것)
        auto_approve: 자동 승인 여부
        analysis_mode: 분석 모드 ("summary_only" | "full")
        progress_callback: 진행 상황 콜백 함수 (실시간 업데이트용)
        language: 결과 언어 ("ko" | "en" | "ja" | "zh", 기본값: 한국어)

    Returns:
        분석 결과 딕셔너리
    """
    # Progress tracker 생성
    tracker = ProgressTracker(progress_callback)
    tracker.update(0.0, "init", "분석 시작...")

    # 초기 상태
    initial_state = _create_initial_state(
        file_path, filament_type, printer_info, auto_approve, analysis_mode, language
    )

    # 워크플로우 컴파일 및 실행 (콜백 전달)
    app = compile_workflow(mode=analysis_mode, progress_tracker=tracker)

    # 비동기 실행
    final_state = await app.ainvoke(initial_state)

    # 완료 콜백
    tracker.update(1.0, "completed", "분석 완료")

    # expert_assessment에서 정보 추출 (Legacy Compatibility)
    expert_assessment = final_state.get("expert_assessment", {})
    check_points = expert_assessment.get("check_points", {})

    # 결과 구성
    result = {
        "summary": final_state.get("summary", {}),
        "comprehensive_summary": final_state.get("comprehensive_summary", {}),
        "timeline": final_state.get("timeline", []),
        "printing_info": {
            "overview": expert_assessment.get("summary_text", ""),
            "characteristics": {
                **expert_assessment.get("print_characteristics", {}),
                "estimated_quality": f"Grade {expert_assessment.get('quality_grade', '?')} ({expert_assessment.get('quality_score', 0)})"
            },
            "temperature_analysis": check_points.get("temperature", {}).get("comment", ""),
            "speed_analysis": check_points.get("speed", {}).get("comment", ""),
            "material_usage": check_points.get("retraction", {}).get("comment", ""),
            "warnings": [i["title"] for i in expert_assessment.get("critical_issues", [])],
            "recommendations": expert_assessment.get("overall_recommendations", []),
            "summary_text": expert_assessment.get("summary_text", ""),
            "raw_data": {}
        },
        "token_usage": final_state.get("token_usage", {})
    }

    # 모드에 따라 추가 결과 포함
    if analysis_mode != "summary_only":
        result.update({
            "issues_found": final_state.get("issues_found", []),
            "final_summary": final_state.get("final_summary", {}),
            "expert_assessment": final_state.get("expert_assessment", {}),  # NEW
            "llm_results": final_state.get("llm_results", []),
            "patch_plan": final_state.get("patch_plan"),
        })

    return result


async def run_error_analysis_only(
    file_path: str,
    filament_type: Optional[str] = None,
    printer_info: Optional[Dict[str, Any]] = None,
    existing_summary: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[ProgressCallback] = None,
    language: str = "ko"
) -> Dict[str, Any]:
    """
    에러 분석만 실행 (기존 요약 결과 활용)

    이미 요약 분석이 완료된 경우, 에러 분석만 수행합니다.
    파싱과 요약은 이미 완료된 것을 재사용합니다.

    Args:
        file_path: G-code 파일 경로
        filament_type: 필라멘트 타입
        printer_info: 프린터 정보
        existing_summary: 기존 종합 요약 결과
        progress_callback: 진행 상황 콜백 함수
        language: 결과 언어 ("ko" | "en" | "ja" | "zh", 기본값: 한국어)

    Returns:
        에러 분석 결과 딕셔너리
    """
    from .parser import parse_gcode
    from .section_detector import detect_sections
    from .summary import summarize_gcode, build_layer_map
    from .workflow.nodes import analyze_events_node, llm_analyze_node, expert_assessment_node, final_output_node
    from datetime import datetime

    # Progress tracker 생성
    tracker = ProgressTracker(progress_callback)
    tracker.update(0.0, "init", "에러 분석 시작...")

    # 파싱 (기존 결과가 없으면 다시 수행)
    tracker.update(0.1, "parsing", "G-code 파싱 중...")
    parse_result = parse_gcode(file_path)
    parsed_lines = parse_result.lines
    boundaries = detect_sections(parsed_lines)
    summary = summarize_gcode(parsed_lines)
    tracker.update(0.2, "parsing", f"파싱 완료: {len(parsed_lines):,}줄")

    # 상태 초기화
    state = _create_initial_state(
        file_path, filament_type, printer_info,
        auto_approve=False, analysis_mode="error_analysis", language=language
    )
    state["parsed_lines"] = parsed_lines
    state["summary"] = summary.dict()
    state["layer_map"] = build_layer_map(parsed_lines)  # 레이어 매핑 생성
    state["comprehensive_summary"] = existing_summary
    state["section_boundaries"] = {
        "start_end": boundaries.start_end,
        "body_end": boundaries.body_end,
        "total_lines": boundaries.total_lines
    }
    state["timeline"] = [{
        "step": 1,
        "label": "기존 요약 결과 로드",
        "status": "done",
        "timestamp": datetime.now().isoformat()
    }]

    # 이벤트 분석 노드 실행
    tracker.update(0.3, "event_analysis", "온도 이벤트 분석 중...")
    events_result = analyze_events_node(state)
    state.update(events_result)
    event_count = len(state.get("events_needing_llm", []))
    tracker.update(0.4, "event_analysis", f"이벤트 분석 완료: {event_count}개 LLM 분석 필요")

    # LLM 분석 노드 실행
    tracker.update(0.5, "llm_analysis", "LLM 분석 중...")
    llm_result = await llm_analyze_node(state)
    state.update(llm_result)
    issues_count = len([i for i in state.get("issues_found", []) if i.get("has_issue")])
    tracker.update(0.65, "llm_analysis", f"LLM 분석 완료: {issues_count}개 이슈 발견")

    # Expert Assessment (Answer Sheet) 실행
    tracker.update(0.70, "expert_assessment", "전문가 분석 리포트 생성 중...")
    expert_result = await expert_assessment_node(state)
    state.update(expert_result)
    tracker.update(0.90, "expert_assessment", "리포트 생성 완료")

    # 최종 출력 조립
    tracker.update(0.95, "final_output", "최종 결과 조립 중...")
    output_result = final_output_node(state)
    state.update(output_result)
    tracker.update(1.0, "completed", "에러 분석 완료")

    return {
        "issues_found": state.get("issues_found", []),
        "final_summary": state.get("final_summary", {}),
        "expert_assessment": state.get("expert_assessment", {}), # New API field
        "llm_results": state.get("llm_results", []),
        "patch_plan": state.get("patch_plan"),
        "token_usage": state.get("token_usage", {}),
        "timeline": state.get("timeline", [])
    }



def run_analysis_sync(
    file_path: str,
    filament_type: Optional[str] = None,
    printer_info: Optional[Dict[str, Any]] = None,
    auto_approve: bool = False,
    analysis_mode: str = "full"
) -> Dict[str, Any]:
    """동기 버전"""
    return asyncio.run(run_analysis(
        file_path, filament_type, printer_info, auto_approve, analysis_mode
    ))
