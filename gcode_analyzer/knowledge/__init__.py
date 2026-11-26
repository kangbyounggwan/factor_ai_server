"""온톨로지 트리플 지식베이스 (증상 → 원인 → 해결) 조회 모듈"""
from .triple_kb import (
    KnowledgeBase,
    get_knowledge_base,
    knowledge_base_source,
    set_knowledge_base,
    similar_cases_for_issue,
    tokenize,
)

__all__ = [
    "KnowledgeBase",
    "get_knowledge_base",
    "knowledge_base_source",
    "set_knowledge_base",
    "similar_cases_for_issue",
    "tokenize",
]
