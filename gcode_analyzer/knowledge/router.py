# -*- coding: utf-8 -*-
"""지식베이스 조회 API

GET  /api/v1/knowledge/stats                    지식베이스 상태 (건수, 버전, 검색 방식)
POST /api/v1/knowledge/search                   자유 질의로 유사 사례 검색
GET  /api/v1/knowledge/issues/{issue_type}      이슈 유형 코드로 유사 사례 검색
GET  /api/v1/knowledge/analysis/{analysis_id}   저장된 분석의 이슈마다 유사 사례
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .triple_kb import KnowledgeBase, get_knowledge_base, knowledge_base_source

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Base"])


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="증상·원인·조치를 설명하는 질의")
    top_k: int = Field(5, ge=1, le=50)
    symptom_type: Optional[str] = Field(None, description="이 증상 코드 안에서만 찾기 (예: cold_extrusion)")


def _require_kb() -> KnowledgeBase:
    kb = get_knowledge_base()
    if kb is None:
        raise HTTPException(
            status_code=503,
            detail="지식베이스가 설정되지 않았습니다 (KNOWLEDGE_BASE_PATH 또는 KNOWLEDGE_BASE_STORAGE).",
        )
    return kb


def _extract_issues(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """분석 결과에서 이슈 목록을 꺼낸다 (신·구 응답 형식 모두)."""
    if not isinstance(result, dict):
        return []
    for getter in (
        lambda r: r.get("issues"),
        lambda r: (r.get("expert_assessment") or {}).get("critical_issues"),
        lambda r: (r.get("final_output") or {}).get("issues"),
    ):
        try:
            issues = getter(result)
        except AttributeError:
            issues = None
        if isinstance(issues, list):
            return [i for i in issues if isinstance(i, dict)]
    return []


@router.get("/stats")
async def knowledge_stats():
    kb = get_knowledge_base()
    if kb is None:
        return {"available": False}
    return {**kb.stats(), "loaded_from": knowledge_base_source()}


@router.post("/search")
async def knowledge_search(request: KnowledgeSearchRequest):
    kb = _require_kb()
    results = kb.search(request.query, top_k=request.top_k, symptom_type=request.symptom_type)
    return {"query": request.query, "count": len(results), "results": results}


@router.get("/issues/{issue_type}")
async def knowledge_for_issue(
    issue_type: str,
    top_k: int = Query(3, ge=1, le=20),
    text: str = Query("", max_length=2000, description="이슈 제목·설명 (선택)"),
):
    kb = _require_kb()
    results = kb.similar_for_issue(issue_type, text, top_k=top_k)
    return {"issue_type": issue_type, "known_symptom": issue_type in kb.symptom_types,
            "count": len(results), "results": results}


@router.get("/analysis/{analysis_id}")
async def knowledge_for_analysis(analysis_id: str, top_k: int = Query(3, ge=1, le=10)):
    from gcode_analyzer.api.file_store import exists, get_analysis

    kb = _require_kb()
    if not exists(analysis_id):
        raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")
    data = get_analysis(analysis_id) or {}
    issues = _extract_issues(data.get("result") or {})
    out = []
    for issue in issues:
        text = " ".join(str(issue.get(k) or "") for k in ("title", "description"))
        issue_type = issue.get("type") or issue.get("issue_type") or ""
        out.append({
            "issue_id": issue.get("id"),
            "type": issue_type,
            "line": issue.get("line"),
            "title": issue.get("title"),
            "knowledge_cases": kb.similar_for_issue(issue_type, text, top_k=top_k),
        })
    return {"analysis_id": analysis_id, "issue_count": len(out), "issues": out}
