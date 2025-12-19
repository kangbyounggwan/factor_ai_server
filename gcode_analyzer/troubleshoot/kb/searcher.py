"""
Knowledge Base 검색기

증상/설명으로 유사한 문제를 검색합니다.
실제 솔루션은 Perplexity 검색으로 언어별로 제공됩니다.
"""
import logging
from typing import List, Optional
from .models import KnowledgeEntry, KBSearchResult, KBSearchResponse
from .knowledge_data import get_all_entries

logger = logging.getLogger(__name__)


class KBSearcher:
    """
    Knowledge Base 검색기

    증상 텍스트로 유사한 문제를 찾습니다.
    벡터 검색(ChromaDB) 또는 키워드 매칭 사용.
    """

    def __init__(self, use_vector: bool = True):
        """
        Args:
            use_vector: ChromaDB 벡터 검색 사용 여부
        """
        self.use_vector = use_vector
        self.entries = get_all_entries()
        self.chroma_collection = None

        if use_vector:
            self._init_vector_db()

    def _init_vector_db(self):
        """ChromaDB 초기화"""
        try:
            import chromadb
            from chromadb.config import Settings

            # 인메모리 클라이언트 (영구 저장 필요시 persist_directory 설정)
            self.client = chromadb.Client(Settings(
                anonymized_telemetry=False
            ))

            # 컬렉션 생성 또는 가져오기
            self.chroma_collection = self.client.get_or_create_collection(
                name="3d_printer_problems",
                metadata={"description": "3D printer troubleshooting KB"}
            )

            # KB 데이터 인덱싱
            self._index_entries()
            logger.info(f"ChromaDB initialized with {len(self.entries)} entries")

        except ImportError:
            logger.warning("chromadb not installed, falling back to keyword search")
            self.use_vector = False
        except Exception as e:
            logger.error(f"ChromaDB init failed: {e}, falling back to keyword search")
            self.use_vector = False

    def _index_entries(self):
        """KB 항목을 벡터 DB에 인덱싱"""
        if not self.chroma_collection:
            return

        # 기존 데이터 확인
        existing = self.chroma_collection.count()
        if existing >= len(self.entries):
            logger.info("KB already indexed, skipping")
            return

        documents = []
        metadatas = []
        ids = []

        for entry in self.entries:
            # 검색용 텍스트 구성: 증상 + 키워드 + 시각적 징후
            search_text = " ".join([
                entry.problem_name,
                entry.problem_name_ko,
                " ".join(entry.symptoms),
                " ".join(entry.symptoms_ko),
                " ".join(entry.visual_signs),
                " ".join(entry.keywords),
            ])

            documents.append(search_text)
            metadatas.append({
                "problem_id": entry.id,
                "problem_name": entry.problem_name,
                "problem_name_ko": entry.problem_name_ko,
                "category": entry.category.value,
                "severity": entry.severity.value,
            })
            ids.append(entry.id)

        self.chroma_collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        logger.info(f"Indexed {len(documents)} KB entries")

    def search(
        self,
        query: str,
        description: str = "",
        visual_signs: List[str] = None,
        top_k: int = 3,
        min_score: float = 0.3
    ) -> KBSearchResponse:
        """
        증상으로 유사한 문제 검색

        Args:
            query: 사용자 증상 텍스트 (자연어)
            description: 이미지 분석 설명 (선택)
            visual_signs: 시각적 증거 목록 (선택)
            top_k: 반환할 최대 결과 수
            min_score: 최소 유사도 점수

        Returns:
            KBSearchResponse: 매칭된 문제 목록
        """
        # 검색 쿼리 구성
        search_query = query
        if description:
            search_query += " " + description
        if visual_signs:
            search_query += " " + " ".join(visual_signs)

        if self.use_vector and self.chroma_collection:
            return self._vector_search(search_query, top_k, min_score)
        else:
            return self._keyword_search(search_query, top_k, min_score)

    def _vector_search(
        self,
        query: str,
        top_k: int,
        min_score: float
    ) -> KBSearchResponse:
        """ChromaDB 벡터 검색"""
        results = self.chroma_collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )

        kb_results = []

        if results and results['ids'] and results['ids'][0]:
            for i, entry_id in enumerate(results['ids'][0]):
                # ChromaDB distance -> similarity score (거리가 작을수록 유사)
                distance = results['distances'][0][i] if results['distances'] else 1.0
                # L2 거리를 0-1 유사도로 변환 (근사)
                similarity = max(0, 1 - (distance / 2))

                if similarity < min_score:
                    continue

                entry = self._get_entry_by_id(entry_id)
                if entry:
                    kb_results.append(KBSearchResult(
                        entry=entry,
                        similarity_score=similarity,
                        matched_symptoms=self._find_matched_symptoms(query, entry)
                    ))

        return KBSearchResponse(
            query=query,
            results=kb_results,
            total_found=len(kb_results),
            search_method="vector"
        )

    def _keyword_search(
        self,
        query: str,
        top_k: int,
        min_score: float
    ) -> KBSearchResponse:
        """키워드 기반 검색 (폴백)"""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored_entries = []

        for entry in self.entries:
            # 키워드 매칭 점수 계산
            match_count = 0
            matched_symptoms = []

            # 키워드 매칭
            for kw in entry.keywords:
                if kw.lower() in query_lower:
                    match_count += 2
                    matched_symptoms.append(kw)

            # 증상 매칭
            for symptom in entry.symptoms + entry.symptoms_ko:
                symptom_lower = symptom.lower()
                if symptom_lower in query_lower:
                    match_count += 1
                    matched_symptoms.append(symptom)
                elif any(word in symptom_lower for word in query_words):
                    match_count += 0.5

            # 문제 이름 매칭
            if entry.problem_name.lower() in query_lower:
                match_count += 3
            if entry.problem_name_ko in query:
                match_count += 3

            if match_count > 0:
                # 정규화된 점수 (0-1)
                max_possible = len(entry.keywords) * 2 + len(entry.symptoms) + 3
                score = min(1.0, match_count / max_possible)

                if score >= min_score:
                    scored_entries.append((entry, score, matched_symptoms))

        # 점수순 정렬
        scored_entries.sort(key=lambda x: x[1], reverse=True)

        kb_results = [
            KBSearchResult(
                entry=entry,
                similarity_score=score,
                matched_symptoms=symptoms[:5]  # 최대 5개
            )
            for entry, score, symptoms in scored_entries[:top_k]
        ]

        return KBSearchResponse(
            query=query,
            results=kb_results,
            total_found=len(kb_results),
            search_method="keyword"
        )

    def _get_entry_by_id(self, entry_id: str) -> Optional[KnowledgeEntry]:
        """ID로 KB 항목 조회"""
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        return None

    def _find_matched_symptoms(
        self,
        query: str,
        entry: KnowledgeEntry
    ) -> List[str]:
        """쿼리와 매칭된 증상 찾기"""
        query_lower = query.lower()
        matched = []

        for symptom in entry.symptoms + entry.symptoms_ko:
            if symptom.lower() in query_lower or query_lower in symptom.lower():
                matched.append(symptom)

        for kw in entry.keywords:
            if kw.lower() in query_lower:
                matched.append(kw)

        return list(set(matched))[:5]


# 편의 함수
_searcher_instance: Optional[KBSearcher] = None


def get_searcher(use_vector: bool = True) -> KBSearcher:
    """싱글톤 검색기 인스턴스 반환"""
    global _searcher_instance
    if _searcher_instance is None:
        _searcher_instance = KBSearcher(use_vector=use_vector)
    return _searcher_instance


def search_kb(
    query: str,
    description: str = "",
    visual_signs: List[str] = None,
    top_k: int = 3
) -> KBSearchResponse:
    """
    KB 검색 편의 함수

    Args:
        query: 증상 텍스트
        description: 이미지 분석 설명
        visual_signs: 시각적 증거
        top_k: 최대 결과 수

    Returns:
        KBSearchResponse: 검색 결과
    """
    searcher = get_searcher()
    return searcher.search(
        query=query,
        description=description,
        visual_signs=visual_signs,
        top_k=top_k
    )
