"""
Perplexity 검색기 - Evidence Supplier

Perplexity API를 사용하여 3D 프린터 문제 해결 정보를 검색합니다.
검색 + 요약 + 출처를 한번에 제공하여 토큰 효율성을 높입니다.

주요 역할:
- 검색용 증강 쿼리로 웹 검색 (언어별)
- 사실 기반 근거(Evidence) 수집
- URL 출처(citations) 자동 제공
- 솔루션은 명확하고 간단하게, 반드시 출처 URL 포함
"""
import os
import re
import logging
from typing import List, Optional

from .models import Evidence, PerplexitySearchResult, ProblemType, UserPlan

logger = logging.getLogger(__name__)


def get_perplexity_api_key() -> Optional[str]:
    """Perplexity API 키 가져오기"""
    return os.getenv("PERPLEXITY_API_KEY")


class PerplexitySearcher:
    """
    Perplexity API 기반 Evidence Supplier

    역할: 검색 + 요약된 근거 수집 (추론 X, 사실만)

    사용자 플랜별 모델:
    - FREE/STARTER: sonar (빠른 검색)
    - PRO: sonar-pro (심층 검색)
    - ENTERPRISE: sonar-pro (심층 검색)
    """

    PLAN_CONFIG = {
        UserPlan.FREE: {
            "model": "sonar",
            "max_tokens": 1024,
        },
        UserPlan.STARTER: {
            "model": "sonar",
            "max_tokens": 1500,
        },
        UserPlan.PRO: {
            "model": "sonar-pro",
            "max_tokens": 2000,
        },
        UserPlan.ENTERPRISE: {
            "model": "sonar-pro",
            "max_tokens": 2500,
        },
    }

    def __init__(self, user_plan: UserPlan = UserPlan.FREE, language: str = "ko"):
        """
        Args:
            user_plan: 사용자 플랜
            language: 응답 언어 (ko, en)
        """
        self.user_plan = user_plan
        self.language = language
        self.config = self.PLAN_CONFIG.get(user_plan, self.PLAN_CONFIG[UserPlan.FREE])
        self.api_key = get_perplexity_api_key()
        self.client = None

        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://api.perplexity.ai"
                )
                logger.info(f"Perplexity API initialized for {user_plan.value} plan")
            except ImportError:
                logger.warning("openai package not installed for Perplexity API")
        else:
            logger.warning("PERPLEXITY_API_KEY not found")

    async def search(
        self,
        augmented_query: str,
        problem_type: Optional[ProblemType] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        kb_problem_name: Optional[str] = None
    ) -> PerplexitySearchResult:
        """
        Perplexity API로 Evidence 검색

        언어별 검색:
        - 한국어(ko): 한국어 쿼리로 검색, 한국 사이트 우선
        - 영어(en): 영어 쿼리로 검색

        Args:
            augmented_query: 이미지 분석에서 생성된 증강 쿼리
            problem_type: 문제 유형
            manufacturer: 프린터 제조사
            model: 프린터 모델
            kb_problem_name: KB에서 매칭된 문제 이름 (검색 정확도 향상용)

        Returns:
            PerplexitySearchResult: 검색된 근거 목록 + 출처
        """
        if not self.client:
            logger.warning("Perplexity client not available, returning empty result")
            return PerplexitySearchResult(
                query=augmented_query,
                findings=[],
                citations=[],
                summary="Perplexity API를 사용할 수 없습니다.",
                tokens_used=0
            )

        # 언어별 검색 쿼리 구성
        search_query = self._build_search_query(
            augmented_query, problem_type, manufacturer, model, kb_problem_name
        )

        # 시스템 프롬프트: Evidence Supplier 역할
        system_prompt = self._get_system_prompt()

        try:
            import asyncio
            loop = asyncio.get_event_loop()

            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=self.config["model"],
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": search_query}
                    ],
                    max_tokens=self.config["max_tokens"],
                    temperature=0.0,
                )
            )

            return self._parse_response(response, search_query)

        except Exception as e:
            logger.error(f"Perplexity search failed: {e}")
            return PerplexitySearchResult(
                query=augmented_query,
                findings=[],
                citations=[],
                summary=f"검색 중 오류 발생: {str(e)}",
                tokens_used=0
            )

    def _build_search_query(
        self,
        augmented_query: str,
        problem_type: Optional[ProblemType],
        manufacturer: Optional[str],
        model: Optional[str],
        kb_problem_name: Optional[str] = None
    ) -> str:
        """
        언어별 검색 쿼리 구성

        한국어: 한국어로 검색 + 해결방법 요청
        영어: 영어로 검색 + solution 요청
        """
        if self.language == "ko":
            # 한국어 검색 쿼리
            parts = ["3D프린터"]

            if kb_problem_name:
                parts.append(kb_problem_name)

            parts.append(augmented_query)

            if manufacturer:
                parts.append(manufacturer)
            if model:
                parts.append(model)

            parts.append("해결방법")

            return " ".join(parts)
        else:
            # 영어 검색 쿼리
            parts = ["3D printer"]

            if kb_problem_name:
                parts.append(kb_problem_name)

            parts.append(augmented_query)

            if manufacturer:
                parts.append(f"for {manufacturer}")
            if model:
                parts.append(model)
            if problem_type and problem_type != ProblemType.UNKNOWN:
                parts.append(f"{problem_type.value}")

            parts.append("fix solution")

            return " ".join(parts)

    def _get_system_prompt(self) -> str:
        """Evidence Supplier용 시스템 프롬프트 - 언어별"""
        if self.language == "ko":
            return """당신은 3D 프린터 문제 해결 정보 검색 전문가입니다.

## 역할: Evidence Supplier (근거 공급자)
- 검색된 사실과 해결책만 제공
- 추론이나 의견 금지
- 모든 정보에 반드시 출처 URL 명시

## 응답 형식
각 해결책을 다음 형식으로 작성:

### 원인
- [원인 설명]: 출처URL

### 해결방법
1. [간단하고 명확한 해결 단계]: 출처URL
2. [다음 단계]: 출처URL

## 중요
- 해결방법은 간단하고 명확하게
- 반드시 URL 출처 포함
- 한국어 사이트 우선 (네이버, 티스토리, 다나와 등)
- 없으면 영어 사이트도 가능

검색된 정보만 전달하세요."""
        else:
            return """You are a 3D printer troubleshooting information search expert.

## Role: Evidence Supplier
- Provide only searched facts and solutions
- No inference or opinions
- MUST cite source URL for all information

## Response Format
Write each solution as:

### Cause
- [Cause description]: SourceURL

### Solution
1. [Clear, simple fix step]: SourceURL
2. [Next step]: SourceURL

## Important
- Keep solutions simple and clear
- MUST include URL source
- Prefer reputable sources (All3DP, Simplify3D, Prusa, Reddit)

Deliver only searched information."""

    def _parse_response(
        self,
        response,
        query: str
    ) -> PerplexitySearchResult:
        """Perplexity 응답 파싱"""
        findings = []
        citations = []
        summary = ""
        tokens_used = 0

        try:
            content = response.choices[0].message.content
            summary = content

            # 토큰 사용량
            if hasattr(response, 'usage') and response.usage:
                tokens_used = response.usage.total_tokens

            # citations 추출 (Perplexity 응답에 포함된 경우)
            if hasattr(response, 'citations') and response.citations:
                citations = response.citations

            # 응답에서 URL과 사실 추출
            findings = self._extract_findings(content, citations)

        except Exception as e:
            logger.error(f"Failed to parse Perplexity response: {e}")
            summary = f"응답 파싱 실패: {str(e)}"

        return PerplexitySearchResult(
            query=query,
            findings=findings,
            citations=citations,
            summary=summary,
            tokens_used=tokens_used
        )

    def _extract_findings(self, content: str, citations: List[str]) -> List[Evidence]:
        """응답에서 Evidence 추출"""
        findings = []

        # URL 패턴으로 추출
        url_pattern = r'https?://[^\s\)\]\>]+'
        lines = content.split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # "- [사실]: URL" 형식 파싱
            urls = re.findall(url_pattern, line)

            if urls:
                # URL 제거하고 사실만 추출
                fact = re.sub(url_pattern, '', line)
                fact = re.sub(r'^[-•*]\s*', '', fact)  # 불릿 제거
                fact = re.sub(r':\s*$', '', fact)  # 끝 콜론 제거
                fact = fact.strip()

                if fact and len(fact) > 10:
                    findings.append(Evidence(
                        fact=fact,
                        source_url=urls[0],
                        source_title=self._extract_domain(urls[0]),
                        relevance=0.8
                    ))

        # citations에서 추가 (findings에 없는 URL)
        existing_urls = {f.source_url for f in findings}
        for url in citations:
            if url not in existing_urls:
                findings.append(Evidence(
                    fact="",  # 사실은 없지만 출처로 참조
                    source_url=url,
                    source_title=self._extract_domain(url),
                    relevance=0.6
                ))

        return findings

    def _extract_domain(self, url: str) -> str:
        """URL에서 도메인 추출"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain
        except Exception:
            return url[:50]


async def search_with_perplexity(
    augmented_query: str,
    problem_type: Optional[ProblemType] = None,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    user_plan: UserPlan = UserPlan.FREE,
    language: str = "ko"
) -> PerplexitySearchResult:
    """
    편의 함수 - Perplexity 검색 실행

    Args:
        augmented_query: 증강 검색 쿼리
        problem_type: 문제 유형
        manufacturer: 프린터 제조사
        model: 프린터 모델
        user_plan: 사용자 플랜
        language: 응답 언어

    Returns:
        PerplexitySearchResult: 검색된 근거 + 출처
    """
    searcher = PerplexitySearcher(user_plan=user_plan, language=language)
    return await searcher.search(augmented_query, problem_type, manufacturer, model)
