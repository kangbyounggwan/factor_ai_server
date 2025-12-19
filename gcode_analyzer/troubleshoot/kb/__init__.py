"""
3D Printer Troubleshooting Knowledge Base

증상 기반 문제 검색 및 분류를 위한 KB 모듈
실제 솔루션은 Perplexity 검색으로 언어별로 제공됩니다.
"""
from .models import (
    KnowledgeEntry,
    KBSearchResult,
    KBSearchResponse,
    ProblemCategory,
    Severity,
    Solution,
)
from .knowledge_data import (
    get_all_entries,
    get_entry_by_id,
    get_entries_by_category,
)
from .searcher import (
    KBSearcher,
    get_searcher,
    search_kb,
)

__all__ = [
    # Models
    "KnowledgeEntry",
    "KBSearchResult",
    "KBSearchResponse",
    "ProblemCategory",
    "Severity",
    "Solution",
    # Data functions
    "get_all_entries",
    "get_entry_by_id",
    "get_entries_by_category",
    # Searcher
    "KBSearcher",
    "get_searcher",
    "search_kb",
]
