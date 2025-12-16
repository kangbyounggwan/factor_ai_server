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
from typing import Dict, Any, List
from datetime import datetime
from .state import AnalysisState
from ..parser import parse_gcode
from ..summary import summarize_gcode, build_layer_map
from ..temp_tracker import extract_temp_events, extract_temp_changes
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
# Node 3: 이벤트 추출 + 룰 엔진
# ============================================================
def analyze_events_node(state: AnalysisState) -> Dict[str, Any]:
    """
    온도 이벤트 추출 및 룰/Rule 기반 분석
    """
    from ..rule_engine import run_all_rules, get_rule_summary, get_llm_review_needed
    
    parsed_lines = state["parsed_lines"]
    boundaries_dict = state["section_boundaries"]
    
    # SectionBoundaries 복원
    boundaries = SectionBoundaries(
        start_end=boundaries_dict["start_end"],
        body_end=boundaries_dict["body_end"],
        total_lines=boundaries_dict["total_lines"]
    )
    
    # 온도 이벤트 추출
    temp_events = extract_temp_events(parsed_lines)

    # 온도 변화 추출 (노즐/베드 분리)
    temp_changes = extract_temp_changes(temp_events)

    # 룰 엔진 실행
    rule_results = run_all_rules(parsed_lines, temp_events, boundaries)
    rule_summary = get_rule_summary(rule_results)
    llm_review_from_rules = get_llm_review_needed(rule_results)
    
    # Python 규칙으로 1차 분석
    analysis_results = analyze_all_temp_events(temp_events, boundaries, parsed_lines)
    
    # 요약
    event_summary = get_summary(analysis_results)
    event_summary["rule_engine"] = rule_summary
    
    # LLM에 보낼 이벤트 필터링
    needs_llm = [r for r in analysis_results if r.needs_llm_analysis]
    normal_events = [r for r in analysis_results if not r.needs_llm_analysis]
    
    # 룰 엔진에서 발견한 이상 추가
    for rule_result in llm_review_from_rules:
        if rule_result.anomaly:
            already_exists = any(
                e["event"]["line_index"] == rule_result.anomaly.line_index 
                for e in [r.dict() for r in needs_llm]
            )
            if not already_exists:
                event_dict = {
                    "line_index": rule_result.anomaly.line_index,
                    "cmd": rule_result.anomaly.context.get("cmd", "M104"),
                    "temp": rule_result.anomaly.context.get("temp", 0)
                }
                needs_llm.append(EventAnalysisResult(
                    event=event_dict,
                    section="BODY",
                    section_info={},
                    is_anomaly=True,
                    confidence="certain",
                    anomaly_type=rule_result.anomaly.type.value,
                    reason=rule_result.anomaly.message,
                    needs_llm_analysis=True
                ))
    
    timeline = state.get("timeline", [])
    timeline.append({
        "step": len(timeline) + 1,
        "label": f"이벤트 분석: {len(temp_events)}개 이벤트, {len(needs_llm)}개 정밀 분석 필요",
        "status": "done",
        "timestamp": datetime.now().isoformat()
    })
    
    return {
        "temp_events": [e.dict() for e in temp_events],
        "temp_changes": temp_changes,  # 온도 변화 전체 (노즐/베드)
        "rule_results": [{"rule_name": r.rule_name, "triggered": r.triggered,
                         "confidence": r.confidence,
                         "anomaly": r.anomaly.dict() if r.anomaly else None}
                        for r in rule_results],
        "event_analysis_results": [r.dict() for r in analysis_results],
        "events_needing_llm": [r.dict() if hasattr(r, 'dict') else r for r in needs_llm],
        "normal_events": [r.dict() for r in normal_events],
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
        return {
            "llm_results": [],
            "issues_found": [],
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
        event_line = event_result["event"]["line_index"]
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
    
    issues_found = [r for r in llm_results if r.get("has_issue", False)]
    
    timeline[-1]["status"] = "done"
    timeline[-1]["label"] = f"이슈 분석 완료 ({len(issues_found)}건 확정)"
    
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
# Node 6: 결과 조립 및 패치 계획 (No LLM)
# ============================================================
def final_output_node(state: AnalysisState) -> Dict[str, Any]:
    """
    최종 결과 구조 조립 및 패치 데이터 포맷팅.
    LLM을 사용하지 않고 'Expert Assessment' 결과를 기반으로 출력 데이터 생성.
    """
    from ..patcher import generate_patch_plan, format_patch_preview
    
    expert_result = state.get("expert_assessment", {})
    issues_found = state.get("issues_found", [])
    comprehensive_summary = state.get("comprehensive_summary", {})
    layer_map = state.get("layer_map", {})
    temp_changes = state.get("temp_changes", {})

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
            file_path=state["file_path"]
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
                "line_index": p.line_index,
                "layer": layer_map.get(p.line_index, 0),
                "original_line": p.original_line,
                "action": p.action,
                "new_line": p.new_line,
                "reason": p.reason,
                "issue_type": p.issue_type,
                "autofix_allowed": getattr(p, 'autofix_allowed', True)
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
                 line_index=p["line_index"],
                 original_line=p["original_line"],
                 action=p["action"],
                 new_line=p.get("new_line"),
                 reason=p["reason"],
                 priority=i,
                 issue_type=p["issue_type"]
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
