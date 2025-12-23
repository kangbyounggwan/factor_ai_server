"""
Brave 이미지 검색기 - 문제 진단 시 관련 참조 이미지 검색

사용자의 문제 상황에 맞는 참조 이미지를 검색하여 제공합니다.
이미지 분석 결과(augmented_query)와 대화 컨텍스트를 활용하여
정확한 검색 쿼리를 생성합니다.
"""
import os
import re
import time
from typing import List, Dict, Any, Optional

import requests
from langchain_core.messages import HumanMessage

from ..llm.client import get_llm_client
from .models import ImageAnalysisResult, ProblemType


# 문제 유형별 검색 쿼리 템플릿
PROBLEM_SEARCH_TEMPLATES = {
    ProblemType.STRINGING: "3D print stringing oozing example {symptoms}",
    ProblemType.BED_ADHESION: "3D print first layer adhesion problem {symptoms}",
    ProblemType.WARPING: "3D print warping curling lifting {symptoms}",
    ProblemType.LAYER_SHIFTING: "3D print layer shift misalignment {symptoms}",
    ProblemType.UNDER_EXTRUSION: "3D print under extrusion gaps {symptoms}",
    ProblemType.OVER_EXTRUSION: "3D print over extrusion blobs {symptoms}",
    ProblemType.GHOSTING: "3D print ghosting ringing ripples {symptoms}",
    ProblemType.Z_BANDING: "3D print z banding horizontal lines {symptoms}",
    ProblemType.CLOGGING: "3D printer nozzle clogging jam {symptoms}",
    ProblemType.LAYER_SEPARATION: "3D print layer separation delamination {symptoms}",
    ProblemType.ELEPHANT_FOOT: "3D print elephant foot bottom bulge {symptoms}",
    ProblemType.BRIDGING_ISSUE: "3D print bridging sagging drooping {symptoms}",
    ProblemType.OVERHANG_ISSUE: "3D print overhang quality problem {symptoms}",
    ProblemType.BED_LEVELING: "3D printer bed leveling uneven {symptoms}",
    ProblemType.BLOB: "3D print blob zits surface defect {symptoms}",
    ProblemType.SURFACE_QUALITY: "3D print surface quality rough {symptoms}",
}


class BraveImageSearcher:
    """
    Brave 이미지 검색기

    문제 진단 컨텍스트를 활용하여 관련 참조 이미지를 검색합니다.
    """

    def __init__(self):
        self.api_key = os.getenv('BRAVE_API_KEY')
        self.api_base = os.getenv('BRAVE_SEARCH_API_BASE', 'https://api.search.brave.com/res/v1')
        self.llm = None  # 필요시 지연 로드

    def _get_llm(self):
        """LLM 클라이언트 지연 로드"""
        if self.llm is None:
            self.llm = get_llm_client(temperature=0.0, max_output_tokens=256)
        return self.llm

    async def generate_search_query(
        self,
        problem_type: Optional[ProblemType],
        image_analysis: Optional[ImageAnalysisResult],
        symptom_text: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        LLM을 사용하여 최적의 이미지 검색 쿼리 생성

        Args:
            problem_type: 감지된 문제 유형
            image_analysis: 이미지 분석 결과 (augmented_query 포함)
            symptom_text: 사용자 증상 설명
            conversation_history: 이전 대화 히스토리

        Returns:
            최적화된 영어 검색 쿼리
        """
        # 1. 이미지 분석의 augmented_query가 있으면 우선 사용
        if image_analysis and image_analysis.augmented_query:
            base_query = image_analysis.augmented_query
            # 이미지 검색에 적합하도록 조정
            return self._optimize_for_image_search(base_query)

        # 2. 문제 유형 기반 템플릿 사용
        if problem_type and problem_type in PROBLEM_SEARCH_TEMPLATES:
            symptoms = ""
            if image_analysis and image_analysis.specific_symptoms:
                symptoms = " ".join(image_analysis.specific_symptoms[:3])
            elif image_analysis and image_analysis.visual_evidence:
                symptoms = " ".join(image_analysis.visual_evidence[:2])

            template = PROBLEM_SEARCH_TEMPLATES[problem_type]
            return template.format(symptoms=symptoms).strip()

        # 3. LLM으로 쿼리 생성 (컨텍스트 활용)
        return await self._generate_query_with_llm(
            symptom_text,
            image_analysis,
            conversation_history
        )

    async def _generate_query_with_llm(
        self,
        symptom_text: str,
        image_analysis: Optional[ImageAnalysisResult],
        conversation_history: Optional[List[Dict[str, str]]]
    ) -> str:
        """LLM을 사용하여 검색 쿼리 생성"""

        # 컨텍스트 구성
        context_parts = []

        if symptom_text:
            context_parts.append(f"User symptom: {symptom_text}")

        if image_analysis:
            if image_analysis.description:
                context_parts.append(f"Image analysis: {image_analysis.description}")
            if image_analysis.visual_evidence:
                context_parts.append(f"Visual evidence: {', '.join(image_analysis.visual_evidence[:3])}")
            if image_analysis.detected_problems:
                problems = [p.value for p in image_analysis.detected_problems[:3]]
                context_parts.append(f"Detected problems: {', '.join(problems)}")

        if conversation_history:
            recent = conversation_history[-4:]  # 최근 4개
            conv_summary = []
            for item in recent:
                role = item.get("role", "user")
                content = item.get("content", "")[:100]
                conv_summary.append(f"{role}: {content}")
            context_parts.append(f"Conversation: {' | '.join(conv_summary)}")

        context = "\n".join(context_parts)

        prompt = f"""Generate a concise English image search query for finding reference images of 3D printing problems.

Context:
{context}

Requirements:
- Query should find images showing SIMILAR problems (not generic 3D printer images)
- Include specific visual symptoms (strings, blobs, gaps, lines, etc.)
- Include the problem type name
- Maximum 10 words
- English only

Output only the search query, nothing else."""

        try:
            llm = self._get_llm()
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            query = response.content.strip()
            # 따옴표 제거
            query = query.strip('"\'')
            return query if query else "3D print quality problem example"
        except Exception:
            # 폴백: 기본 쿼리
            return "3D print quality problem troubleshooting"

    def _optimize_for_image_search(self, query: str) -> str:
        """쿼리를 이미지 검색에 최적화"""
        # 너무 긴 쿼리 줄이기
        words = query.split()
        if len(words) > 12:
            # 핵심 키워드만 추출
            keywords = []
            important_terms = [
                "3d", "print", "stringing", "warping", "adhesion", "layer",
                "extrusion", "ghosting", "banding", "clogging", "blob",
                "bridging", "overhang", "surface", "quality", "problem",
                "rough", "gap", "shift", "curl", "lift"
            ]
            for word in words:
                if word.lower() in important_terms or len(keywords) < 8:
                    keywords.append(word)
            query = " ".join(keywords[:10])

        # "example" 또는 "photo" 추가하여 실제 사례 이미지 검색
        if "example" not in query.lower() and "photo" not in query.lower():
            query += " example"

        return query

    def search_images(
        self,
        query: str,
        count: int = 10,
        retry_delay: float = 1.5
    ) -> List[Dict[str, Any]]:
        """
        이미지 검색 수행

        Args:
            query: 검색 쿼리
            count: 결과 수 (최대 10)
            retry_delay: Rate limit 시 재시도 대기 시간

        Returns:
            이미지 검색 결과 리스트
        """
        if not self.api_key:
            print("[WARN] BRAVE_API_KEY not set")
            return []

        headers = {
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'X-Subscription-Token': self.api_key
        }

        url = f'{self.api_base}/images/search'
        params = {
            'q': query,
            'count': min(count, 10),
            'safesearch': 'off'
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=15)

                if response.status_code == 200:
                    data = response.json()
                    results = data.get('results', [])

                    images = []
                    for img in results:
                        images.append({
                            'title': img.get('title', ''),
                            'thumbnail_url': img.get('thumbnail', {}).get('src', ''),
                            'source_url': img.get('url', ''),
                            'page_url': img.get('page_url', ''),
                            'width': img.get('thumbnail', {}).get('width', 0),
                            'height': img.get('thumbnail', {}).get('height', 0),
                        })
                    return images

                elif response.status_code == 429:
                    # Rate limit - 재시도
                    if attempt < max_retries:
                        time.sleep(retry_delay)
                        continue
                    else:
                        return []
                else:
                    return []

            except Exception:
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
                return []

        return []

    def download_images(
        self,
        images: List[Dict[str, Any]],
        save_dir: str
    ) -> List[Dict[str, Any]]:
        """
        이미지를 로컬에 다운로드

        Args:
            images: 이미지 정보 리스트
            save_dir: 저장 디렉토리

        Returns:
            다운로드된 이미지 정보 (local_path 포함)
        """
        os.makedirs(save_dir, exist_ok=True)
        downloaded = []

        for i, img in enumerate(images, 1):
            thumbnail_url = img.get('thumbnail_url', '')
            if not thumbnail_url:
                continue

            try:
                # 확장자 결정
                ext = '.jpg'
                if '.png' in thumbnail_url.lower():
                    ext = '.png'
                elif '.webp' in thumbnail_url.lower():
                    ext = '.webp'

                # 안전한 파일명 생성
                safe_title = "".join(
                    c for c in img.get('title', '')[:30]
                    if c.isalnum() or c in (' ', '-', '_')
                ).strip()
                filename = f"{i:02d}_{safe_title}{ext}" if safe_title else f"{i:02d}_image{ext}"
                filepath = os.path.join(save_dir, filename)

                # 다운로드
                response = requests.get(
                    thumbnail_url,
                    timeout=10,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )

                if response.status_code == 200:
                    with open(filepath, 'wb') as f:
                        f.write(response.content)

                    img_info = img.copy()
                    img_info['local_path'] = filepath
                    img_info['file_size'] = len(response.content)
                    downloaded.append(img_info)

            except Exception:
                continue

        return downloaded


async def search_reference_images(
    problem_type: Optional[ProblemType] = None,
    image_analysis: Optional[ImageAnalysisResult] = None,
    symptom_text: str = "",
    conversation_history: Optional[List[Dict[str, str]]] = None,
    count: int = 10,
    download_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    문제 진단 컨텍스트 기반 참조 이미지 검색

    Args:
        problem_type: 감지된 문제 유형
        image_analysis: 이미지 분석 결과
        symptom_text: 사용자 증상 설명
        conversation_history: 대화 히스토리
        count: 검색할 이미지 수
        download_dir: 이미지 저장 디렉토리 (None이면 다운로드 안함)

    Returns:
        {
            "query": 사용된 검색 쿼리,
            "images": 검색된 이미지 목록,
            "downloaded": 다운로드된 이미지 목록 (download_dir 지정 시)
        }
    """
    searcher = BraveImageSearcher()

    # 최적화된 검색 쿼리 생성
    query = await searcher.generate_search_query(
        problem_type=problem_type,
        image_analysis=image_analysis,
        symptom_text=symptom_text,
        conversation_history=conversation_history
    )

    # 이미지 검색
    images = searcher.search_images(query, count=count)

    result = {
        "query": query,
        "images": images,
        "downloaded": []
    }

    # 다운로드 (선택적)
    if download_dir and images:
        result["downloaded"] = searcher.download_images(images, download_dir)

    return result
