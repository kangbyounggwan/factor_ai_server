# -*- coding: utf-8 -*-
"""온톨로지 트리플 지식베이스 (증상 → 원인 → 해결)

데이터바우처 사업(2026)에서 구축한 G-code 설비 이상 트리플 데이터셋을
서비스에서 조회하기 위한 모듈이다. 검색은 오프라인 평가와 같은 2단계 구조다.

  1단계  질의 어휘 BM25(k1=1.5, b=0.75)로 후보 20건을 좁힌다        ← 질의 의존
  2단계  후보 안에서만 0.5·W(n) + 0.5·BM25 로 재순위화한다          ← 신뢰도 반영
         W(n) = D(t)·(0.3·C + 0.5·R + 0.2·F)
         (트리플의 confidence 값을 최댓값으로 정규화해 쓴다)

지식베이스 데이터는 공개 저장소에 두지 않는다. 아래 환경변수 중 하나로 위치를 준다.

  KNOWLEDGE_BASE_PATH     로컬 파일 경로 (.json 또는 .json.gz)
  KNOWLEDGE_BASE_STORAGE  Supabase Storage 경로 "버킷/객체" (서비스 키 필요)

설정이 없거나 읽기에 실패하면 get_knowledge_base() 가 None 을 돌려주고,
호출하는 쪽은 지식베이스 없이 기존처럼 동작한다.
"""
from __future__ import annotations

import collections
import gzip
import json
import logging
import math
import os
import re
import threading
from typing import Any, Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

K1 = 1.5
B = 0.75
DEFAULT_CANDIDATES = 20
DEFAULT_WEIGHT = 0.5

# 응답에 싣는 필드. 식별자·G-code 원문·시계열은 지식베이스 파일에 처음부터 넣지 않는다.
PUBLIC_FIELDS = (
    "triple_id", "symptom_type", "symptom_severity", "symptom_desc", "impact",
    "cause_param", "cause_value", "cause_ref_range",
    "solution_text", "solution_label", "grade", "confidence", "data_source",
    "mechanism", "defect_manifestation", "resolution_basis",
)

_EN = re.compile(r"[a-z0-9_]+")
_KO = re.compile(r"[가-힣]+")


def tokenize(text: Optional[str]) -> List[str]:
    """영문·숫자 단어와 한글 2글자 묶음으로 나눈다 (오프라인 평가와 같은 규칙)."""
    s = (text or "").lower()
    out = _EN.findall(s)
    for w in _KO.findall(s):
        out += [w] if len(w) < 2 else [w[i:i + 2] for i in range(len(w) - 1)]
    return out


class KnowledgeBase:
    """트리플 목록을 메모리에 올리고 BM25 색인을 만든다."""

    def __init__(self, triples: List[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None):
        if not triples:
            raise ValueError("지식베이스가 비어 있습니다")
        self.meta: Dict[str, Any] = dict(meta or {})
        self.triples = triples
        self._docs = [
            tokenize(f"{t.get('symptom_type', '')} {t.get('cause_param', '')} {t.get('solution_text', '')}")
            for t in triples
        ]
        self._post: Dict[str, List[tuple]] = collections.defaultdict(list)
        df: collections.Counter = collections.Counter()
        for i, doc in enumerate(self._docs):
            for tok, cnt in collections.Counter(doc).items():
                df[tok] += 1
                self._post[tok].append((i, cnt))
        n = len(triples)
        self._avgdl = (sum(len(d) for d in self._docs) / n) or 1.0
        self._idf = {tok: math.log(1 + (n - v + 0.5) / (v + 0.5)) for tok, v in df.items()}
        weights = [float(t.get("confidence") or 0.0) for t in triples]
        top = max(weights) or 1.0
        self._wn = [w / top for w in weights]
        self._by_symptom: Dict[str, List[int]] = collections.defaultdict(list)
        for i, t in enumerate(triples):
            self._by_symptom[str(t.get("symptom_type") or "")].append(i)

    # ------------------------------------------------------------------ 불러오기
    @classmethod
    def from_bytes(cls, data: bytes) -> "KnowledgeBase":
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        obj = json.loads(data.decode("utf-8"))
        if isinstance(obj, list):
            return cls(obj)
        return cls(obj.get("triples") or [], obj.get("meta") or {})

    @classmethod
    def from_file(cls, path: str) -> "KnowledgeBase":
        with open(path, "rb") as f:
            return cls.from_bytes(f.read())

    # ------------------------------------------------------------------ 조회
    def __len__(self) -> int:
        return len(self.triples)

    @property
    def symptom_types(self) -> List[str]:
        return sorted(k for k in self._by_symptom if k)

    def bm25(self, tokens: Iterable[str], pool: Optional[Set[int]] = None) -> Dict[int, float]:
        scores: Dict[int, float] = collections.defaultdict(float)
        for tok in set(tokens):
            postings = self._post.get(tok)
            if not postings:
                continue
            idf = self._idf[tok]
            for i, cnt in postings:
                if pool is not None and i not in pool:
                    continue
                dl = len(self._docs[i])
                scores[i] += idf * cnt * (K1 + 1) / (cnt + K1 * (1 - B + B * dl / self._avgdl))
        return scores

    def search(
        self,
        query: str,
        top_k: int = 5,
        symptom_type: Optional[str] = None,
        candidates: int = DEFAULT_CANDIDATES,
        weight: float = DEFAULT_WEIGHT,
    ) -> List[Dict[str, Any]]:
        """질의와 비슷한 사례를 찾는다. symptom_type 을 주면 그 증상 안에서만 찾는다."""
        top_k = max(1, min(int(top_k), 50))
        pool: Optional[Set[int]] = None
        if symptom_type:
            idx = self._by_symptom.get(symptom_type)
            if not idx:
                return []
            pool = set(idx)
        scores = self.bm25(tokenize(query), pool)
        if scores:
            cand = sorted(scores, key=lambda i: -scores[i])[:candidates]
            top = max(scores[i] for i in cand) or 1.0
            final = {i: weight * self._wn[i] + (1 - weight) * scores[i] / top for i in cand}
            ranked = sorted(cand, key=lambda i: -final[i])
            return [self._result(i, final[i], scores[i]) for i in ranked[:top_k]]
        if pool is not None:
            # 어휘가 하나도 겹치지 않으면 같은 증상 안에서 신뢰도 순으로 돌려준다
            ranked = sorted(pool, key=lambda i: -self._wn[i])
            return [self._result(i, weight * self._wn[i], 0.0) for i in ranked[:top_k]]
        return []

    def similar_for_issue(self, issue_type: Optional[str], text: str = "", top_k: int = 3) -> List[Dict[str, Any]]:
        """분석 이슈(유형 코드 + 설명)와 비슷한 실증 사례를 찾는다."""
        issue_type = (issue_type or "").strip()
        if issue_type in self._by_symptom:
            return self.search(f"{issue_type} {text}", top_k=top_k, symptom_type=issue_type)
        return self.search(f"{issue_type.replace('_', ' ')} {text}", top_k=top_k)

    def _result(self, i: int, score: float, bm25: float) -> Dict[str, Any]:
        t = self.triples[i]
        out = {k: t.get(k) for k in PUBLIC_FIELDS}
        out["score"] = round(score, 4)
        out["bm25"] = round(bm25, 4)
        out["weight_normalized"] = round(self._wn[i], 4)
        return out

    def stats(self) -> Dict[str, Any]:
        return {
            "available": True,
            "count": len(self.triples),
            "symptom_types": len(self.symptom_types),
            "data_source": dict(collections.Counter(t.get("data_source") for t in self.triples)),
            "version": self.meta.get("kb_version"),
            "source_file": self.meta.get("source_file"),
            "source_sha256": self.meta.get("source_sha256"),
            "retrieval": {
                "stage1": f"BM25(k1={K1}, b={B}) 후보 {DEFAULT_CANDIDATES}건",
                "stage2": f"{DEFAULT_WEIGHT}·W(n) + {1 - DEFAULT_WEIGHT}·BM25 재순위",
            },
        }


# ---------------------------------------------------------------------- 서비스 전역 인스턴스
_lock = threading.Lock()
_kb: Optional[KnowledgeBase] = None
_loaded = False
_source: Optional[str] = None


def _load_from_storage(spec: str) -> bytes:
    bucket, _, obj = spec.strip().strip("/").partition("/")
    if not bucket or not obj:
        raise ValueError("KNOWLEDGE_BASE_STORAGE 는 '버킷/객체' 형식이어야 합니다")
    from supabase_client import get_supabase_client  # 환경변수가 없을 때는 여기서만 실패한다
    return get_supabase_client().storage.from_(bucket).download(obj)


def get_knowledge_base(reload: bool = False) -> Optional[KnowledgeBase]:
    """환경변수가 가리키는 지식베이스를 한 번만 불러온다. 없으면 None."""
    global _kb, _loaded, _source
    if _loaded and not reload:
        return _kb
    with _lock:
        if _loaded and not reload:
            return _kb
        kb: Optional[KnowledgeBase] = None
        src: Optional[str] = None
        path = os.getenv("KNOWLEDGE_BASE_PATH", "").strip()
        storage = os.getenv("KNOWLEDGE_BASE_STORAGE", "").strip()
        try:
            if path:
                kb, src = KnowledgeBase.from_file(path), f"file:{os.path.basename(path)}"
            elif storage:
                kb, src = KnowledgeBase.from_bytes(_load_from_storage(storage)), f"storage:{storage}"
        except Exception as e:  # 지식베이스가 없어도 서비스는 계속 돈다
            logger.warning("[Knowledge] 지식베이스를 불러오지 못했습니다 (%s): %s", path or storage, e)
            kb, src = None, None
        if kb is not None:
            logger.info("[Knowledge] 지식베이스 %d건 로드 (%s, 버전 %s)", len(kb), src, kb.meta.get("kb_version"))
        _kb, _source, _loaded = kb, src, True
        return _kb


def set_knowledge_base(kb: Optional[KnowledgeBase], source: str = "manual") -> None:
    """테스트나 수동 적재용."""
    global _kb, _loaded, _source
    with _lock:
        _kb, _source, _loaded = kb, (source if kb is not None else None), True


def knowledge_base_source() -> Optional[str]:
    return _source


def similar_cases_for_issue(issue: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
    """분석 이슈 dict 에 맞는 유사 사례. 지식베이스가 없거나 실패하면 빈 목록."""
    try:
        kb = get_knowledge_base()
        if kb is None or not isinstance(issue, dict):
            return []
        issue_type = issue.get("type") or issue.get("issue_type") or ""
        text = " ".join(str(issue.get(k) or "") for k in ("title", "description"))
        return kb.similar_for_issue(issue_type, text, top_k=top_k)
    except Exception as e:
        logger.warning("[Knowledge] 유사 사례 조회 실패: %s", e)
        return []
