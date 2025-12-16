"""
LangGraph Workflow Graph Definition (Gold Standard Version)
"""
from typing import Optional
from langgraph.graph import StateGraph, END
from .state import AnalysisState
from .callback import ProgressTracker
from .nodes import (
    parse_node,
    comprehensive_summary_node,
    analyze_events_node,
    llm_analyze_node,
    expert_assessment_node,  # NEW
    final_output_node,       # NEW
    apply_patch_node
)


def create_analysis_workflow(mode: str = "full", progress_tracker: Optional[ProgressTracker] = None) -> StateGraph:
    """
    G-code 분석 워크플로우 생성 (Answer Sheet Pattern)

    Flow (full):
    parse → comprehensive_summary → analyze_events → llm_analyze → expert_assessment → final_output → apply_patch → END

    Flow (summary_only):
    parse → comprehensive_summary → END
    """
    workflow = StateGraph(AnalysisState)

    # 1. Parse
    def parse_with_progress(state):
        if progress_tracker:
            progress_tracker.update(0.05, "parse", "G-code 파싱 시작...")
        result = parse_node(state)
        total_lines = len(result.get("parsed_lines", []))
        if progress_tracker:
            progress_tracker.update(0.15, "parse", f"파싱 완료: {total_lines:,}줄 처리")
        return result

    # 2. Comprehensive Summary (Python Only)
    async def summary_with_progress(state):
        if progress_tracker:
            progress_tracker.update(0.18, "comprehensive_summary", "종합 요약 분석 중...")
        result = await comprehensive_summary_node(state, progress_tracker)
        if progress_tracker:
            comp = result.get("comprehensive_summary", {})
            layers = comp.get("layer", {}).get("total_layers", 0)
            progress_tracker.update(0.25, "comprehensive_summary", f"통계 분석 완료 (레이어 {layers}층)")
        return result

    # 3. Analyze Events + Flash Lite 검증
    async def events_with_progress(state):
        if progress_tracker:
            progress_tracker.update(0.30, "analyze_events", "온도 이벤트 분석 중...")
        result = await analyze_events_node(state)
        llm_count = len(result.get("events_needing_llm", []))
        rule_count = len(result.get("rule_confirmed_issues", []))
        filtered_count = len(result.get("rule_filtered_issues", []))
        if progress_tracker:
            msg = f"이벤트 분석 완료: 규칙 {rule_count}건 확정, {llm_count}개 정밀 분석 대상"
            if filtered_count > 0:
                msg += f", {filtered_count}건 오탐 필터링"
            progress_tracker.update(0.40, "analyze_events", msg)
        return result

    # 4. LLM Analysis (Snippets)
    async def llm_with_progress(state):
        if progress_tracker:
            progress_tracker.update(0.45, "llm_analyze", "이슈 정밀 분석 시작...")
        result = await llm_analyze_node(state, progress_tracker)
        issues = [i for i in result.get("issues_found", []) if i.get("has_issue")]
        if progress_tracker:
            msg = f"이슈 분석 완료: {len(issues)}개 확정"
            progress_tracker.update(0.65, "llm_analyze", msg)
        return result
        
    # 5. Expert Assessment (Answer Sheet Generator)
    async def expert_with_progress(state):
        if progress_tracker:
            progress_tracker.update(0.70, "expert_assessment", "최종 품질 리포트 작성 중...")
        result = await expert_assessment_node(state, progress_tracker)
        score = result.get("expert_assessment", {}).get("quality_score", "?")
        if progress_tracker:
            progress_tracker.update(0.90, "expert_assessment", f"리포트 작성 완료 (점수: {score})")
        return result

    # 6. Final Output Assembly
    def output_with_progress(state):
        if progress_tracker:
            progress_tracker.update(0.95, "final_output", "결과 데이터 조립 중...")
        result = final_output_node(state, progress_tracker)
        if progress_tracker:
            progress_tracker.update(0.98, "final_output", "분석 완료")
        return result

    # 7. Apply Patch
    def patch_with_progress(state):
        if progress_tracker:
            progress_tracker.update(0.99, "apply_patch", "패치 적용 중...")
        result = apply_patch_node(state)
        if progress_tracker:
            progress_tracker.update(1.0, "apply_patch", "작업 완료")
        return result

    # 노드 추가
    workflow.add_node("parse", parse_with_progress)
    workflow.add_node("comprehensive_summary", summary_with_progress)
    workflow.add_node("analyze_events", events_with_progress)
    workflow.add_node("llm_analyze", llm_with_progress)
    workflow.add_node("expert_assessment", expert_with_progress)
    workflow.add_node("final_output", output_with_progress)
    workflow.add_node("apply_patch", patch_with_progress)

    # 엣지 연결
    workflow.set_entry_point("parse")
    workflow.add_edge("parse", "comprehensive_summary")

    # 분기: Full vs Summary Only
    def check_analysis_mode(state: AnalysisState) -> str:
        mode = state.get("analysis_mode", "full")
        if mode == "summary_only":
            return END
        return "analyze_events"

    workflow.add_conditional_edges(
        "comprehensive_summary",
        check_analysis_mode,
        {
            "analyze_events": "analyze_events",
            END: END
        }
    )

    workflow.add_edge("analyze_events", "llm_analyze")
    workflow.add_edge("llm_analyze", "expert_assessment")
    workflow.add_edge("expert_assessment", "final_output")

    # 승인 대기 로직 (final_output 후 승인 대기)
    def check_approval(state: AnalysisState) -> str:
        if state.get("user_approved", False):
            return "apply_patch"
        return END

    workflow.add_conditional_edges(
        "final_output",
        check_approval,
        {
            "apply_patch": "apply_patch",
            END: END
        }
    )

    workflow.add_edge("apply_patch", END)

    return workflow


def compile_workflow(mode: str = "full", progress_tracker: Optional[ProgressTracker] = None):
    workflow = create_analysis_workflow(mode, progress_tracker)
    return workflow.compile()


def create_summary_only_workflow() -> StateGraph:
    return create_analysis_workflow(mode="summary_only")
