"""
LangGraph Workflow Nodes (Gold Standard Pattern)
각 노드는 명확한 역할을 가짐:
1. parse_node: G-code 파싱 + 구간 분류
2. comprehensive_summary_node: 종합 요약 분석 (Python 통계 ONLY)
3. analyze_events_node: Python 규칙 + 룰 엔진으로 1차 분석
4. llm_analyze_node: 문제 후보만 LLM에 전달 (Snippet Analysis)
5. expert_assessment_node: 최종 정답지(Answer Sheet) 생성 (Single LLM Source of Truth)
6. final_output_node: 결과 조립 (No LLM)
7. apply_patch_node: 패치 적용
"""
import asyncio
import copy
from typing import Dict, Any, List
from datetime import datetime
from .state import AnalysisState
from ..parser import parse_gcode
from ..summary import summarize_gcode, build_layer_map
from ..temp_tracker import extract_temp_events, extract_temp_changes
from ..rules.temp_scanner import scan_temperature_anomalies
from ..section_detector import detect_sections, SectionBoundaries
from ..event_analyzer import analyze_all_temp_events, get_summary, EventAnalysisResult
from ..data_preparer import extract_temp_event_snippets, detect_filament_from_gcode
from ..config import get_default_config
from ..gcode_summary_analyzer import analyze_gcode_summary

def add_timeline(state: dict, label: str, status: str = "done") -> List[dict]:
    """타임라인에 이벤트 추가"""
    timeline = state.get("timeline", [])
    timeline.append({
        "step": len(timeline) + 1,
        "label": label,
        "status": status,
        "timestamp": datetime.now().isoformat()
    })
    return timeline


def _extract_context(
    gcode_lines: List[str],
    line_number: int,
    context_window: int,
    total_lines: int
) -> str:
    """
    G-code 라인 주변 컨텍스트 추출

    Args:
        gcode_lines: G-code 라인 리스트
        line_number: 대상 라인 번호 (1-based)
        context_window: 앞뒤로 포함할 라인 수
        total_lines: 전체 라인 수

    Returns:
        라인 번호가 포함된 G-code 컨텍스트 문자열
    """
    if not line_number or line_number < 1:
        return ""

    # 0-based index로 변환
    target_idx = line_number - 1

    # 범위 계산 (위아래 context_window 줄씩)
    start_idx = max(0, target_idx - context_window)
    end_idx = min(total_lines, target_idx + context_window + 1)

    # 컨텍스트 생성
    context_parts = []
    for i in range(start_idx, end_idx):
        line_num = i + 1
        line_content = gcode_lines[i] if i < len(gcode_lines) else ""

        # 대상 라인 강조
        if i == target_idx:
            context_parts.append(f">>> {line_num}: {line_content}  <<< [문제 라인]")
        else:
            context_parts.append(f"    {line_num}: {line_content}")

    return '\n'.join(context_parts)

# ============================================================
# Node 1: 파싱 + 구간 분류
# ============================================================
def parse_node(state: AnalysisState) -> Dict[str, Any]:
    """
    G-code 파싱 및 구간 분류
    """
    file_path = state["file_path"]

    # 파싱 (ParseResult 객체 반환)
    parse_result = parse_gcode(file_path)
    parsed_lines = parse_result.lines
    total_lines = len(parsed_lines)

    # 원본 라인 추출 (gcode_context 생성용)
    raw_lines = [line.raw for line in parsed_lines]

    # 구간 분류
    boundaries = detect_sections(parsed_lines)

    # 요약
    summary = summarize_gcode(parsed_lines)

    # 레이어 매핑 생성 (line_index → layer_number)
    layer_map = build_layer_map(parsed_lines)

    # 필라멘트 타입 감지
    filament_type = state.get("filament_type") or detect_filament_from_gcode(parsed_lines)

    return {
        "parsed_lines": parsed_lines,
        "raw_lines": raw_lines,  # gcode_context 생성용
        "summary": summary.dict(),
        "layer_map": layer_map,
        "filament_type": filament_type,
        "section_boundaries": {
            "start_end": boundaries.start_end,
            "body_end": boundaries.body_end,
            "total_lines": boundaries.total_lines
        },
        "current_step": "parse",
        "progress": 0.15,
        "timeline": [{
            "step": 1,
            "label": f"G-code 파싱 완료 ({total_lines:,}줄)",
            "status": "done",
            "timestamp": datetime.now().isoformat()
        }, {
            "step": 2,
            "label": f"구간 분류: START(~{boundaries.start_end}), BODY(~{boundaries.body_end}), END(~{total_lines})",
            "status": "done",
            "timestamp": datetime.now().isoformat()
        }]
    }

# ============================================================
# Node 2: 종합 요약 분석 (Python Only)
# ============================================================
async def comprehensive_summary_node(state: AnalysisState, progress_tracker=None) -> Dict[str, Any]:
    """
    G-code 종합 요약 분석 (Python 통계만 수행, LLM 호출 없음)
    """
    parsed_lines = state["parsed_lines"]
    file_path = state["file_path"]
    
    timeline = state.get("timeline", [])
    timeline.append({
        "step": len(timeline) + 1,
        "label": "종합 통계 분석 중 (Python)...",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    })

    # 종합 요약 분석 실행 (Python 기반)
    comprehensive_summary = analyze_gcode_summary(parsed_lines, file_path)

    # 요약 결과를 딕셔너리로 변환
    summary_dict = comprehensive_summary.to_dict()

    # 타임라인 업데이트
    timeline[-1]["status"] = "done"
    timeline[-1]["label"] = f"통계 분석 완료 (평균속도: {comprehensive_summary.feed_rate.avg_speed:.0f}mm/min)"
    
    # 주요 통계 타임라인 추가
    timeline.append({
        "step": len(timeline) + 1,
        "label": f"레이어: {comprehensive_summary.layer.total_layers}층, 필라멘트: {comprehensive_summary.extrusion.total_filament_used:.1f}m",
        "status": "done",
        "timestamp": datetime.now().isoformat()
    })

    return {
        "comprehensive_summary": summary_dict,
        "current_step": "comprehensive_summary",
        "progress": 0.25,
        "timeline": timeline
    }


# ============================================================
# Node 3: 기본 체크 + LLM 직접 문제 탐지 (NEW!)
# ============================================================
async def analyze_events_node(state: AnalysisState) -> Dict[str, Any]:
    """
    새로운 LLM 중심 분석 구조:
    1. Rule Engine: 기본 체크만 (온도/베드 설정 유무)
    2. Flash Lite: 데이터 기반으로 직접 문제 탐지 (3가지 관점)
       - 온도 분석
       - 속도/동작 분석
       - 구조/시퀀스 분석
    3. LLM Validation: 감지된 이슈를 컨텍스트와 함께 LLM으로 검증하여 오탐 제거
    """
    from ..rule_engine import run_basic_checks, run_all_rules, get_rule_summary
    from ..llm.issue_detector import detect_issues_with_llm, convert_to_legacy_format
    from ..llm.issue_validator import validate_issues
    from dataclasses import asdict

    parsed_lines = state["parsed_lines"]
    boundaries_dict = state["section_boundaries"]
    filament_type = state.get("filament_type", "PLA")

    # SectionBoundaries 복원
    boundaries = SectionBoundaries(
        start_end=boundaries_dict["start_end"],
        body_end=boundaries_dict["body_end"],
        total_lines=boundaries_dict["total_lines"]
    )

    # 온도 이벤트 추출
    temp_events = extract_temp_events(parsed_lines)
    temp_changes = extract_temp_changes(temp_events)

    # ============================================================
    # 0. 온도 패턴 스캐너: BODY 전체 스캔 (LLM 없이 룰 기반)
    # ============================================================
    temp_scan_result = scan_temperature_anomalies(
        temp_events=temp_events,
        parsed_lines=parsed_lines,
        boundaries=boundaries,
        filament_type=filament_type
    )
    temp_grouped_issues = temp_scan_result.get("grouped_issues", [])

    timeline = state.get("timeline", [])
    timeline.append({
        "step": len(timeline) + 1,
        "label": f"기본 체크 및 데이터 추출 중...",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    })

    # ============================================================
    # 1. Rule Engine: 기본 체크 + 데이터 추출
    # ============================================================
    rule_output = run_basic_checks(parsed_lines, temp_events, boundaries)

    # 기본 체크 결과를 dict로 변환
    basic_checks = [
        {
            "check_name": c.check_name,
            "passed": c.passed,
            "message": c.message,
            "details": c.details
        }
        for c in rule_output.basic_checks
    ]

    # 추출된 데이터를 dict로 변환
    extracted_data = {
        "has_nozzle_temp": rule_output.extracted_data.has_nozzle_temp,
        "has_bed_temp": rule_output.extracted_data.has_bed_temp,
        "nozzle_temps": rule_output.extracted_data.nozzle_temps,
        "bed_temps": rule_output.extracted_data.bed_temps,
        "temp_changes_in_body": rule_output.extracted_data.temp_changes_in_body,
        "has_feed_rate": rule_output.extracted_data.has_feed_rate,
        "speed_stats": rule_output.extracted_data.speed_stats,
        "first_extrusion_line": rule_output.extracted_data.first_extrusion_line,
        "last_extrusion_line": rule_output.extracted_data.last_extrusion_line,
        "extrusion_before_temp_wait": rule_output.extracted_data.extrusion_before_temp_wait,
        "section_info": rule_output.extracted_data.section_info
    }

    # 치명적 플래그 (즉시 F등급)
    critical_flags = rule_output.critical_flags

    timeline[-1]["status"] = "done"
    timeline[-1]["label"] = f"기본 체크 완료 (통과: {sum(1 for c in basic_checks if c['passed'])}/{len(basic_checks)})"

    # ============================================================
    # 2. Flash Lite: 직접 문제 탐지 (3가지 관점 병렬 분석)
    # ============================================================
    timeline.append({
        "step": len(timeline) + 1,
        "label": "AI 문제 탐지 중 (온도/속도/구조 분석)...",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    })

    # LLM 직접 문제 탐지
    llm_analysis = await detect_issues_with_llm(
        extracted_data,
        basic_checks,
        filament_type
    )

    # 탐지된 이슈를 기존 형식으로 변환
    llm_detected_issues = convert_to_legacy_format(llm_analysis.issues)

    timeline[-1]["status"] = "done"
    timeline[-1]["label"] = f"AI 문제 탐지 완료 ({len(llm_detected_issues)}건 발견)"

    # ============================================================
    # 3. 치명적 플래그 → 이슈로 변환 (Rule Engine의 명백한 문제)
    # ============================================================
    critical_issues_from_flags = []
    for flag in critical_flags:
        flag_type, line_info = flag.split(":")
        line_num = int(line_info.replace("line_", ""))

        critical_issues_from_flags.append({
            "id": f"CRITICAL-{len(critical_issues_from_flags)+1}",
            "has_issue": True,
            "issue_type": flag_type.lower(),
            "severity": "critical",
            "description": f"치명적 문제: {flag_type.replace('_', ' ')}",
            "impact": "즉시 출력 중단 필요",
            "suggestion": "G-code 재생성 또는 수동 수정 필요",
            "affected_lines": [line_num],
            "event_line_index": line_num,
            "line": line_num,
            "from_rule_engine": True,
            "autofix_allowed": True
        })

    # ============================================================
    # 4. 모든 이슈 병합 (중복 제거)
    # ============================================================
    # 온도 스캐너 그룹 이슈 + 치명적 플래그 + LLM 탐지 이슈
    all_issues = temp_grouped_issues + critical_issues_from_flags + llm_detected_issues

    # 중복 제거 (같은 라인 또는 그룹)
    # 그룹 이슈에 포함된 라인들도 seen_lines에 추가하여 개별 이슈로 중복 등록 방지
    seen_lines = set()
    seen_groups = set()
    unique_issues = []

    for issue in all_issues:
        # lines 배열에서 라인 추출 (통일된 형식)
        issue_lines = issue.get("lines", [])

        # lines가 없으면 all_issues에서 추출 시도
        if not issue_lines and issue.get("all_issues"):
            issue_lines = [sub.get("line") for sub in issue.get("all_issues", []) if sub.get("line")]

        # 여전히 없으면 event_line_index 사용 (레거시 호환)
        if not issue_lines:
            legacy_line = issue.get("event_line_index")
            if legacy_line:
                issue_lines = [legacy_line]

        # 그룹화된 이슈인 경우
        if issue.get("is_grouped") or len(issue_lines) > 1:
            group_key = f"{issue.get('type')}_{issue.get('count', len(issue_lines))}"
            if group_key not in seen_groups:
                seen_groups.add(group_key)
                unique_issues.append(issue)
                # 그룹에 포함된 모든 라인을 seen_lines에 추가 (개별 이슈 중복 방지)
                for line in issue_lines:
                    seen_lines.add(line)
        else:
            # 개별 이슈인 경우 (lines 배열 첫 번째 사용)
            line = issue_lines[0] if issue_lines else None
            if line and line not in seen_lines:
                seen_lines.add(line)
                unique_issues.append(issue)

    # 심각도 순 정렬
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    unique_issues.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 4))

    # ============================================================
    # 5. LLM 검증: 감지된 이슈를 컨텍스트와 함께 검증하여 오탐 제거
    # ============================================================
    validated_issues = []
    filtered_issues = []
    validation_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    if unique_issues:
        timeline.append({
            "step": len(timeline) + 1,
            "label": f"이슈 검증 중 ({len(unique_issues)}건)...",
            "status": "running",
            "timestamp": datetime.now().isoformat()
        })

        language = state.get("language", "ko")

        # LLM으로 이슈 검증 (앞뒤 50줄 컨텍스트)
        validated_issues, filtered_issues, validation_tokens = await validate_issues(
            issues=unique_issues,
            parsed_lines=parsed_lines,
            language=language,
            context_lines=50
        )

        timeline[-1]["status"] = "done"
        timeline[-1]["label"] = f"이슈 검증 완료 (유효: {len(validated_issues)}, 오탐 제거: {len(filtered_issues)})"
    else:
        validated_issues = unique_issues  # 이슈가 없으면 그대로

    # 하위 호환을 위한 기존 형식 데이터 생성
    rule_results = run_all_rules(parsed_lines, temp_events, boundaries)
    rule_summary = get_rule_summary(rule_results)
    analysis_results = analyze_all_temp_events(temp_events, boundaries, parsed_lines)
    event_summary = get_summary(analysis_results)
    event_summary["rule_engine"] = rule_summary
    event_summary["llm_detector"] = {
        "issues_found": len(llm_detected_issues),
        "summaries": llm_analysis.summaries
    }
    event_summary["llm_validator"] = {
        "validated": len(validated_issues),
        "filtered_as_false_positive": len(filtered_issues)
    }

    # 검증 토큰 + 탐지 토큰 합산
    total_validation_tokens = {
        "input_tokens": llm_analysis.token_usage.get("input_tokens", 0) + validation_tokens["input_tokens"],
        "output_tokens": llm_analysis.token_usage.get("output_tokens", 0) + validation_tokens["output_tokens"],
        "total_tokens": llm_analysis.token_usage.get("total_tokens", 0) + validation_tokens["total_tokens"]
    }

    return {
        "temp_events": [e.dict() for e in temp_events],
        "temp_changes": temp_changes,
        "temp_scan_result": temp_scan_result,  # 온도 스캐너 결과 (전체)
        "basic_checks": basic_checks,
        "extracted_data": extracted_data,
        "critical_flags": critical_flags,
        "llm_detected_issues": llm_detected_issues,
        "llm_analysis_summaries": llm_analysis.summaries,
        "rule_confirmed_issues": validated_issues,  # 검증된 이슈만!
        "rule_filtered_issues": filtered_issues,  # 오탐으로 제거된 이슈
        "validation_tokens": total_validation_tokens,
        "event_analysis_results": [r.dict() for r in analysis_results],
        "events_needing_llm": [],  # 이제 LLM이 직접 탐지하므로 불필요
        "normal_events": [r.dict() for r in analysis_results],
        "event_summary": event_summary,
        "current_step": "analyze_events",
        "progress": 0.35,
        "timeline": timeline
    }

# ============================================================
# Node 4: LLM 분석 (Snippet Analysis)
# ============================================================
async def llm_analyze_node(state: AnalysisState, progress_tracker=None) -> Dict[str, Any]:
    """
    개별 이슈 후보에 대한 LLM 정밀 분석
    """
    from ..llm.analyze_snippet import analyze_snippet_with_llm
    from ..data_preparer import SnippetContext, LLMAnalysisInput
    from ..config import DEFAULT_FILAMENTS, get_default_config
    
    events_needing_llm = state.get("events_needing_llm", [])
    parsed_lines = state["parsed_lines"]
    summary = state["summary"]
    comprehensive_summary = state.get("comprehensive_summary")
    filament_type = state.get("filament_type")
    layer_map = state.get("layer_map", {})
    config = get_default_config()
    
    timeline = state.get("timeline", [])
    total_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    
    if not events_needing_llm:
        # LLM 분석 필요 없어도 Rule Engine 확정 이슈는 포함해야 함
        rule_confirmed_issues = copy.deepcopy(state.get("rule_confirmed_issues", []))

        # gcode_context 추가 (early return 경로에서도)
        # 모든 이슈는 all_issues 배열을 가짐 (단일이어도)
        raw_lines = state.get("raw_lines", [])
        if raw_lines:
            total_gcode_lines = len(raw_lines)
            context_window = 30
            for issue in rule_confirmed_issues:
                # all_issues 내 각 sub_issue에 gcode_context 추가
                for sub_issue in issue.get("all_issues", []):
                    line_num = sub_issue.get("line")
                    if line_num:
                        sub_issue["gcode_context"] = _extract_context(
                            raw_lines, line_num, context_window, total_gcode_lines
                        )

        return {
            "llm_results": [],
            "issues_found": rule_confirmed_issues,  # Rule Engine 이슈 포함!
            "token_usage": total_tokens,
            "current_step": "llm_analyze",
            "progress": 0.60,
            "timeline": timeline
        }
    
    timeline.append({
        "step": len(timeline) + 1,
        "label": f"이슈 정밀 분석 시작 ({len(events_needing_llm)}건)",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    })
    
    filament_info = None
    if filament_type and filament_type in DEFAULT_FILAMENTS:
        filament_info = DEFAULT_FILAMENTS[filament_type].dict()
    
    async def analyze_one(event_result: dict, event_index: int, total_events: int) -> tuple:
        event_line = event_result.get("event", {}).get("line_index")
        if not event_line:
            # 라인 번호가 없으면 기본 결과 반환
            return {
                "has_issue": False,
                "event_line_index": None,
                "layer": 0,
                "section": event_result.get("section", "unknown")
            }, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        idx_0 = event_line - 1
        window = config.snippet_window
        start_0 = max(0, idx_0 - window)
        end_0 = min(len(parsed_lines), idx_0 + window + 1)

        snippet_lines = parsed_lines[start_0:end_0]
        snippet_text = "\n".join([f"{line.index}: {line.raw.strip()}" for line in snippet_lines])

        snippet_context = SnippetContext(
            event_line_index=event_line,
            event_cmd=event_result["event"]["cmd"],
            event_temp=event_result["event"]["temp"],
            snippet_start=start_0 + 1,
            snippet_end=end_0,
            snippet_text=snippet_text,
            lines_after_event=len(parsed_lines) - event_line
        )

        llm_input = LLMAnalysisInput(
            summary=summary,
            comprehensive_summary=comprehensive_summary,
            snippet_context=snippet_context,
            filament_info=filament_info,
            printer_info=state.get("printer_info")
        )

        streaming_callback = None
        if progress_tracker:
            base_progress = 0.40 + (0.20 * event_index / max(total_events, 1))
            progress_tracker.clear_streaming_buffer()
            streaming_callback = progress_tracker.get_streaming_callback(base_progress, "llm_analyze")

        language = state.get("language", "ko")
        result, tokens = await analyze_snippet_with_llm(
            llm_input, config.snippet_window, streaming_callback, language
        )

        result["event_line_index"] = event_line
        result["layer"] = layer_map.get(event_line, 0)  # 레이어 번호 추가
        result["section"] = event_result["section"]

        return result, tokens
    
    total_events = len(events_needing_llm)
    results_with_tokens = []

    for idx, event_result in enumerate(events_needing_llm):
        if progress_tracker:
            progress_tracker.update(
                0.40 + (0.20 * idx / max(total_events, 1)),
                "llm_analyze",
                f"이슈 {idx + 1}/{total_events} 분석 중..."
            )
        result_tokens = await analyze_one(event_result, idx, total_events)
        results_with_tokens.append(result_tokens)
    
    llm_results = []
    for result, tokens in results_with_tokens:
        llm_results.append(result)
        total_tokens["input_tokens"] += tokens["input_tokens"]
        total_tokens["output_tokens"] += tokens["output_tokens"]
        total_tokens["total_tokens"] += tokens["total_tokens"]
    
    # LLM에서 발견한 이슈
    llm_issues = [r for r in llm_results if r.get("has_issue", False)]

    # 규칙 엔진에서 이미 확정된 이슈 병합 (중복 제거)
    # 깊은 복사하여 원본 손상 방지 및 gcode_context 추가 가능하게
    rule_confirmed_issues = copy.deepcopy(state.get("rule_confirmed_issues", []))

    # 확정된 이슈의 라인들 수집 (모든 이슈는 lines 배열 사용)
    confirmed_lines = set()
    for issue in rule_confirmed_issues:
        # lines 배열에서 모든 라인 추가
        for line in issue.get("lines", []):
            confirmed_lines.add(line)

    # LLM 이슈 중 규칙 엔진과 중복되지 않는 것만 추가
    unique_llm_issues = [
        i for i in llm_issues
        if i.get("event_line_index") not in confirmed_lines
    ]

    # 규칙 엔진 확정 이슈 + LLM 이슈 (규칙 엔진 이슈가 우선)
    issues_found = rule_confirmed_issues + unique_llm_issues

    # ============================================================
    # 각 이슈에 gcode_context 추가 (위아래 30줄, 총 60줄)
    # 모든 이슈는 all_issues 배열을 가짐 (단일이어도)
    # ============================================================
    raw_lines = state.get("raw_lines", [])
    if raw_lines:
        total_gcode_lines = len(raw_lines)
        context_window = 30  # 위아래 30줄씩

        for issue in issues_found:
            # all_issues 내 각 sub_issue에 gcode_context 추가
            for sub_issue in issue.get("all_issues", []):
                line_num = sub_issue.get("line")
                if line_num:
                    sub_issue["gcode_context"] = _extract_context(
                        raw_lines, line_num, context_window, total_gcode_lines
                    )

    timeline[-1]["status"] = "done"
    timeline[-1]["label"] = f"이슈 분석 완료 ({len(issues_found)}건 확정, 규칙: {len(rule_confirmed_issues)}건)"

    return {
        "llm_results": llm_results,
        "issues_found": issues_found,
        "token_usage": total_tokens,
        "current_step": "llm_analyze",
        "progress": 0.60,
        "timeline": timeline
    }

# ============================================================
# Node 5: Expert Assessment (Answer Sheet Generator) - NEW!
# ============================================================
async def expert_assessment_node(state: AnalysisState, progress_tracker=None) -> Dict[str, Any]:
    """
    모든 정보를 종합하여 최종 정답지(Expert Assessment)를 생성하는 노드.
    이곳이 유일한 'Intelligence Source of Truth'입니다.
    """
    from ..llm.expert_assessment import generate_expert_assessment
    
    comprehensive_summary = state.get("comprehensive_summary", {})
    issues_found = state.get("issues_found", [])
    prev_tokens = state.get("token_usage", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    
    timeline = state.get("timeline", [])
    timeline.append({
        "step": len(timeline) + 1,
        "label": "AI 품질 평가 리포트 생성 중 (Expert Analysis)...",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    })
    
    streaming_callback = None
    if progress_tracker:
        progress_tracker.clear_streaming_buffer()
        streaming_callback = progress_tracker.get_streaming_callback(0.70, "expert_assessment")
    
    language = state.get("language", "ko")
    
    # LLM 호출 (issues_found가 비어있어도 전체 평가를 위해 호출해야 할 수도 있음, 혹은 분기 처리)
    # Answer Sheet Pattern에서는 문제 없어도 "평가서"는 나와야 함 (점수 100점 등)
    # generate_expert_assessment 내부에서 처리하도록 함
    
    expert_result, tokens = await generate_expert_assessment(
        comprehensive_summary,
        issues_found,
        streaming_callback,
        language
    )
    
    # 토큰 합산
    total_tokens = {
        "input_tokens": prev_tokens["input_tokens"] + tokens["input_tokens"],
        "output_tokens": prev_tokens["output_tokens"] + tokens["output_tokens"],
        "total_tokens": prev_tokens["total_tokens"] + tokens["total_tokens"]
    }
    
    timeline[-1]["status"] = "done"
    timeline[-1]["label"] = f"품질 평가 완료 (등급: {expert_result.get('quality_grade', '?')}, 점수: {expert_result.get('quality_score', 0)})"
    
    return {
        "expert_assessment": expert_result,
        "token_usage": total_tokens,
        "current_step": "expert_assessment",
        "progress": 0.90,
        "timeline": timeline
    }

# ============================================================
# Node 6: 결과 조립 및 패치 생성 (Python Only - No LLM)
# ============================================================
def final_output_node(state: AnalysisState, progress_tracker=None) -> Dict[str, Any]:
    """
    최종 결과 구조 조립 및 패치 생성.
    Expert Assessment 결과를 기반으로 Python 규칙으로 패치 코드 생성.
    """
    from ..patcher import generate_patch_plan, format_patch_preview

    expert_result = state.get("expert_assessment", {})
    issues_found = state.get("issues_found", [])
    comprehensive_summary = state.get("comprehensive_summary", {})
    layer_map = state.get("layer_map", {})
    temp_changes = state.get("temp_changes", {})
    parsed_lines = state.get("parsed_lines", [])

    timeline = state.get("timeline", [])
    
    # 1. 패치 계획 생성 (Expert Assessment의 critical_issues 기반)
    # Expert Assessment가 선별한 최종 이슈들
    critical_issues = expert_result.get("critical_issues", [])

    patch_plan = None
    if critical_issues:
        # Patcher 호환 변환
        patch_candidates = []
        for issue in critical_issues:
            # issue에 fix_proposal이 있으므로 이를 action으로 사용
            patch_candidates.append({
                "line_index": issue.get("line"),
                "issue_type": issue.get("type"),
                "fix_action": issue.get("fix_proposal"),
                "description": issue.get("description"),
                "original_line": "N/A", # line_index로 조회 필요하지만 generate_patch_plan에서 함
                "priority": 1,
                "issue_id": issue.get("id")  # 이슈 ID 연결
            })

        patch_plan = generate_patch_plan(
            issues=patch_candidates,
            lines=state["parsed_lines"],
            file_path=state["file_path"],
            filament_type=state.get("filament_type", "PLA")
        )

    # 2. 패치에 ID 부여 및 이슈-패치 매핑 생성
    patch_id_map = {}  # line_index -> patch_id
    if patch_plan:
        for idx, patch in enumerate(patch_plan.patches):
            patch_id = f"PATCH-{idx + 1:03d}"
            patch_id_map[patch.line_index] = patch_id

    # 3. critical_issues에 patch_id 추가
    issues_with_patch = []
    for issue in critical_issues:
        issue_line = issue.get("line")
        patch_id = patch_id_map.get(issue_line)  # 매칭되는 패치 ID (없으면 None)

        issues_with_patch.append({
            **issue,
            "patch_id": patch_id,  # 연결된 패치 ID (없으면 null)
            "layer": layer_map.get(issue_line, 0)
        })
    
    # 4. 최종 결과 딕셔너리 구성
    final_output = {
        "expert_assessment": {
            **expert_result,
            # critical_issues를 patch_id가 포함된 버전으로 교체
            "critical_issues": issues_with_patch
        },

        # Legacy UI Compatibility
        "overall_quality_score": expert_result.get("quality_score"),
        "total_issues_found": len(critical_issues),
        "critical_issues_count": len([i for i in critical_issues if i.get("severity") in ["critical", "high"]]),
        "summary": expert_result.get("summary_text"),
        "issue_summary": expert_result.get("summary_text"),
        "recommendation": "\n".join(expert_result.get("overall_recommendations", [])),

        # 이슈 목록 (patch_id 포함)
        "issues": issues_with_patch,

        "analysis_stats": {
             "total_lines": comprehensive_summary.get("total_lines"),
             "print_time": comprehensive_summary.get("print_time", {}).get("formatted_time"),
        },

        # 온도 변화 전체 (노즐/베드)
        "temp_changes": temp_changes,

        "patch_available": bool(patch_plan),
        "patch_count": patch_plan.total_patches if patch_plan else 0,
        "patch_preview": format_patch_preview(patch_plan) if patch_plan else None
    }

    if patch_plan:
        timeline.append({
            "step": len(timeline) + 1,
            "label": f"패치 제안 생성 완료 ({patch_plan.total_patches}개)",
            "status": "done",
            "timestamp": datetime.now().isoformat()
        })

    # 5. 패치 목록에 ID 부여
    patches_with_id = []
    if patch_plan:
        for idx, p in enumerate(patch_plan.patches):
            patch_id = f"PATCH-{idx + 1:03d}"
            # 이 패치와 연결된 이슈 ID 찾기
            linked_issue_id = None
            for issue in issues_with_patch:
                if issue.get("line") == p.line_index:
                    linked_issue_id = issue.get("id")
                    break

            patches_with_id.append({
                "id": patch_id,  # 패치 고유 ID
                "issue_id": linked_issue_id,  # 연결된 이슈 ID
                "line": p.line_index,  # 프론트엔드용 (line_index alias)
                "line_index": p.line_index,
                "layer": layer_map.get(p.line_index, 0),
                "original": p.original_line,  # 프론트엔드용 (original_line alias)
                "original_line": p.original_line,
                "action": p.action,
                "modified": p.new_line,  # 프론트엔드용 (new_line alias) - 추가/수정할 코드
                "new_line": p.new_line,
                "position": p.position,  # before, after, replace
                "reason": p.reason,
                "issue_type": p.issue_type,
                "autofix_allowed": p.autofix_allowed,
                "vendor_extension": p.vendor_extension  # 벤더 확장 정보
            })

    return {
        "final_summary": final_output,
        "patch_plan": {
             "file_path": patch_plan.file_path if patch_plan else None,
             "total_patches": patch_plan.total_patches if patch_plan else 0,
             "patches": patches_with_id,
             "estimated_improvement": patch_plan.estimated_quality_improvement if patch_plan else 0
        } if patch_plan else None,
        "current_step": "final_output",
        "progress": 1.0,
        "timeline": timeline
    }

# ============================================================
# Node 7: 패치 적용
# ============================================================
def apply_patch_node(state: AnalysisState) -> Dict[str, Any]:
    """사용자 승인 후 패치 적용"""
    from ..patcher import apply_patches, save_patched_gcode, PatchPlan, PatchSuggestion
    
    timeline = state.get("timeline", [])
    
    if not state.get("user_approved", False):
        return {"current_step": "waiting", "timeline": timeline}
        
    patch_plan_dict = state.get("patch_plan")
    if not patch_plan_dict:
        return {"current_step": "no_patches", "timeline": timeline}
    
    try:
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
             ) for i, p in enumerate(patch_plan_dict["patches"])
        ]
        
        patch_plan = PatchPlan(
            file_path=patch_plan_dict["file_path"],
            total_patches=patch_plan_dict["total_patches"],
            patches=patches,
            estimated_quality_improvement=patch_plan_dict.get("estimated_improvement", 0)
        )
        
        with open(state["file_path"], "r", encoding="utf-8") as f:
            original_lines = f.readlines()
            
        new_lines, applied_log = apply_patches(original_lines, patch_plan)
        new_file_path = save_patched_gcode(new_lines, state["file_path"])
        
        timeline.append({
            "step": len(timeline) + 1,
            "label": f"패치 적용 및 저장 완료",
            "status": "done",
            "timestamp": datetime.now().isoformat()
        })
        
        return {
            "current_step": "patch_applied",
            "patch_results": {
                "status": "success", 
                "new_file": new_file_path,
                "applied_count": len(applied_log)
            },
            "timeline": timeline
        }
        
    except Exception as e:
        timeline.append({"step": len(timeline)+1, "label": f"에러: {e}", "status": "error"})
        return({"current_step": "error", "timeline": timeline})
