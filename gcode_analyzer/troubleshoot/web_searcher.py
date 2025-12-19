"""
웹 검색기 - 3D 프린터 문제 해결 정보 검색

검색 우선순위:
1. Tavily API (유료, 고품질) - TAVILY_API_KEY 환경변수 필요
2. DuckDuckGo + Wikipedia (무료) - API 키 불필요
3. 정적 리소스 (항상 제공)
"""
import os
import json
import re
from typing import List, Dict, Any, Optional
import asyncio
import logging

from langchain_core.messages import HumanMessage

from ..llm.client import get_llm_client_lite
from .models import Reference, SearchResult, SearchQueries, ProblemType, UserPlan
from .printer_database import get_search_context, get_manufacturer
from .prompts.search_query import SEARCH_QUERY_PROMPT, SEARCH_QUERY_PROMPT_KO

logger = logging.getLogger(__name__)


def get_tavily_api_key() -> Optional[str]:
    """Tavily API 키 가져오기"""
    return os.getenv("TAVILY_API_KEY")


class FreeSearchProvider:
    """
    무료 검색 프로바이더 - DuckDuckGo + Wikipedia

    익명 사용자 및 API 키 없는 환경용
    """

    def __init__(self):
        self.ddg_available = False
        self.wiki_available = False

        # DuckDuckGo 초기화 (ddgs 패키지 사용)
        try:
            from ddgs import DDGS
            self.ddg_client = DDGS
            self.ddg_available = True
        except ImportError:
            logger.warning("ddgs not installed. DuckDuckGo search disabled.")

        # Wikipedia 초기화
        try:
            import wikipedia
            self.wikipedia = wikipedia
            self.wiki_available = True
        except ImportError:
            logger.warning("wikipedia not installed. Wikipedia search disabled.")

    async def search_ddg(self, query: str, max_results: int = 5) -> List[Reference]:
        """DuckDuckGo 검색"""
        if not self.ddg_available:
            return []

        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: list(self.ddg_client().text(query, max_results=max_results))
            )

            references = []
            for item in results:
                references.append(Reference(
                    title=item.get("title", ""),
                    url=item.get("href", item.get("link", "")),
                    source="duckduckgo",
                    relevance=0.7,
                    snippet=item.get("body", "")[:200]
                ))

            return references

        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
            return []

    async def search_wikipedia(self, query: str, max_results: int = 3) -> List[Reference]:
        """Wikipedia 검색"""
        if not self.wiki_available:
            return []

        try:
            loop = asyncio.get_event_loop()

            # 검색어로 관련 페이지 찾기
            search_results = await loop.run_in_executor(
                None,
                lambda: self.wikipedia.search(query, results=max_results)
            )

            references = []
            for title in search_results[:max_results]:
                try:
                    # 페이지 요약 가져오기
                    summary = await loop.run_in_executor(
                        None,
                        lambda t=title: self.wikipedia.summary(t, sentences=2)
                    )

                    page = await loop.run_in_executor(
                        None,
                        lambda t=title: self.wikipedia.page(t)
                    )

                    references.append(Reference(
                        title=f"Wikipedia: {title}",
                        url=page.url,
                        source="wikipedia",
                        relevance=0.6,
                        snippet=summary[:200]
                    ))
                except Exception:
                    continue  # 개별 페이지 오류는 무시

            return references

        except Exception as e:
            logger.warning(f"Wikipedia search failed: {e}")
            return []

    async def search(self, query: str) -> List[Reference]:
        """통합 무료 검색 (DuckDuckGo + Wikipedia)"""
        tasks = []

        if self.ddg_available:
            tasks.append(self.search_ddg(query, max_results=10))

        if self.wiki_available:
            # Wikipedia는 영어 키워드로 검색하는 게 더 효과적
            wiki_query = f"3D printing {query}"
            tasks.append(self.search_wikipedia(wiki_query, max_results=3))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_refs = []
        for result in results:
            if isinstance(result, list):
                all_refs.extend(result)

        return all_refs


class WebSearcher:
    """
    웹 검색기 - 3D 프린터 문제 해결 정보 검색

    사용자 플랜별 검색 방식:
    - FREE: DuckDuckGo + Wikipedia (무료)
    - BASIC: Tavily basic (5개 결과)
    - PRO: Tavily advanced (10개 결과, 더 깊은 검색)
    - ENTERPRISE: Tavily advanced + 모든 쿼리 타입 (15개 결과)
    """

    # 플랜별 설정
    PLAN_CONFIG = {
        UserPlan.FREE: {
            "use_tavily": False,
            "max_results": 10,
            "search_depth": "basic",
            "query_types": ["official", "general", "community"],
        },
        UserPlan.BASIC: {
            "use_tavily": True,
            "max_results": 10,
            "search_depth": "basic",
            "query_types": ["official", "general", "community"],
        },
        UserPlan.PRO: {
            "use_tavily": True,
            "max_results": 15,
            "search_depth": "advanced",
            "query_types": ["official", "general", "community"],
        },
        UserPlan.ENTERPRISE: {
            "use_tavily": True,
            "max_results": 20,
            "search_depth": "advanced",
            "query_types": ["official", "general", "community"],
        },
    }

    def __init__(self, language: str = "ko", user_plan: UserPlan = UserPlan.FREE):
        """
        Args:
            language: 검색 언어 (ko, en)
            user_plan: 사용자 플랜 (free, basic, pro, enterprise)
        """
        self.language = language
        self.user_plan = user_plan
        self.config = self.PLAN_CONFIG.get(user_plan, self.PLAN_CONFIG[UserPlan.FREE])
        self.llm = get_llm_client_lite(temperature=0.0, max_output_tokens=512)
        self.tavily_client = None
        self.free_search = FreeSearchProvider()

        # Tavily 초기화 (유료 플랜이고 API 키가 있는 경우만)
        if self.config["use_tavily"]:
            api_key = get_tavily_api_key()
            if api_key:
                try:
                    from tavily import TavilyClient
                    self.tavily_client = TavilyClient(api_key=api_key)
                    logger.info(f"Tavily API initialized for {user_plan.value} plan")
                except ImportError:
                    logger.warning("tavily-python not installed, falling back to free search")
            else:
                logger.warning(f"No Tavily API key for {user_plan.value} plan, falling back to free search")
        else:
            logger.info(f"Using free search for {user_plan.value} plan")

    async def generate_search_queries(
        self,
        manufacturer: Optional[str],
        model: Optional[str],
        problem_type: ProblemType,
        symptom_text: str
    ) -> SearchQueries:
        """
        LLM을 사용해 최적화된 검색 쿼리 생성
        """
        prompt_template = SEARCH_QUERY_PROMPT_KO if self.language == "ko" else SEARCH_QUERY_PROMPT

        prompt = prompt_template.format(
            manufacturer=manufacturer or "unknown",
            model=model or "unknown",
            problem_type=problem_type.value,
            symptom_text=symptom_text,
            language=self.language
        )

        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return self._parse_query_response(response.content)
        except Exception as e:
            # 기본 쿼리 생성
            return SearchQueries(
                official_query=f"{manufacturer} {problem_type.value} official guide",
                community_query=f"reddit {manufacturer} {model} {problem_type.value}",
                general_query=f"3D printing {problem_type.value} fix",
                tokens_used=0
            )

    def _parse_query_response(self, content: str) -> SearchQueries:
        """검색 쿼리 응답 파싱"""
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content

            data = json.loads(json_str)

            return SearchQueries(
                official_query=data.get("official_query", ""),
                community_query=data.get("community_query", ""),
                general_query=data.get("general_query", ""),
                tokens_used=0
            )
        except:
            return SearchQueries(
                official_query="",
                community_query="",
                general_query="",
                tokens_used=0
            )

    async def search(
        self,
        manufacturer: Optional[str],
        model: Optional[str],
        problem_type: ProblemType,
        symptom_text: str
    ) -> List[SearchResult]:
        """
        통합 검색 실행 (사용자 플랜에 따라 분기)

        Args:
            manufacturer: 프린터 제조사
            model: 프린터 모델
            problem_type: 문제 유형
            symptom_text: 사용자 증상 설명

        Returns:
            List[SearchResult]: 검색 결과 리스트
        """
        results = []

        # 검색 쿼리 생성
        queries = await self.generate_search_queries(
            manufacturer, model, problem_type, symptom_text
        )

        logger.info(f"Searching with {self.user_plan.value} plan (max_results={self.config['max_results']})")

        # 플랜에 따른 검색 분기
        if self.config["use_tavily"] and self.tavily_client:
            # 유료 플랜: Tavily 검색
            try:
                tavily_results = await self._search_tavily(queries)
                results.extend(tavily_results)
                logger.info(f"Tavily search returned {sum(len(r.results) for r in tavily_results)} results")
            except Exception as e:
                logger.warning(f"Tavily search failed: {e}, falling back to free search")
                # Tavily 실패시 무료 검색으로 폴백
                free_results = await self._search_free(queries)
                results.extend(free_results)
        else:
            # 무료 플랜 또는 Tavily 불가: DuckDuckGo + Wikipedia
            try:
                free_results = await self._search_free(queries)
                results.extend(free_results)
                logger.info(f"Free search returned {sum(len(r.results) for r in free_results)} results")
            except Exception as e:
                logger.warning(f"Free search failed: {e}")

        # 정적 참조 (항상 추가)
        static_refs = self._get_static_references(manufacturer, model, problem_type)
        results.append(SearchResult(
            query="static_references",
            results=static_refs,
            tokens_used=0
        ))

        return results

    async def _search_free(self, queries: SearchQueries) -> List[SearchResult]:
        """무료 검색 (DuckDuckGo + Wikipedia) - 플랜 설정 적용"""
        results = []

        search_tasks = []
        query_types = []
        allowed_types = self.config["query_types"]
        max_results = self.config["max_results"]

        # 플랜에 허용된 쿼리 타입만 검색
        query_mapping = {
            "official": ("official", queries.official_query),
            "general": ("general", queries.general_query),
            "community": ("community", queries.community_query),
        }

        for query_type in allowed_types:
            if query_type in query_mapping:
                qtype, query = query_mapping[query_type]
                if query:
                    search_tasks.append(self.free_search.search(query))
                    query_types.append((qtype, query))

        if not search_tasks:
            return results

        # 병렬 실행
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        for i, result in enumerate(search_results):
            if isinstance(result, list) and result:
                query_type, query = query_types[i]
                # max_results 제한 적용
                limited_results = result[:max_results]
                results.append(SearchResult(
                    query=query,
                    results=limited_results,
                    tokens_used=0
                ))

        return results

    async def _search_tavily(self, queries: SearchQueries) -> List[SearchResult]:
        """Tavily API로 검색 - 플랜 설정 적용"""
        results = []

        if not self.tavily_client:
            return results

        search_tasks = []
        allowed_types = self.config["query_types"]

        # 플랜에 허용된 쿼리 타입만 검색
        query_mapping = {
            "official": ("official", queries.official_query),
            "general": ("general", queries.general_query),
            "community": ("community", queries.community_query),
        }

        for query_type in allowed_types:
            if query_type in query_mapping:
                qtype, query = query_mapping[query_type]
                if query:
                    search_tasks.append(self._tavily_search_single(query, qtype))

        # 병렬 실행
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        for result in search_results:
            if isinstance(result, SearchResult):
                results.append(result)

        return results

    async def _tavily_search_single(self, query: str, source_type: str) -> SearchResult:
        """단일 Tavily 검색 - 플랜 설정 적용"""
        try:
            loop = asyncio.get_event_loop()
            max_results = self.config["max_results"]
            search_depth = self.config["search_depth"]

            response = await loop.run_in_executor(
                None,
                lambda: self.tavily_client.search(
                    query=query,
                    search_depth=search_depth,
                    max_results=max_results,
                    include_answer=False
                )
            )

            references = []
            for item in response.get("results", []):
                references.append(Reference(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    source=source_type,
                    relevance=item.get("score", 0.5),
                    snippet=item.get("content", "")[:200]
                ))

            return SearchResult(
                query=query,
                results=references,
                tokens_used=0
            )

        except Exception as e:
            return SearchResult(
                query=query,
                results=[],
                tokens_used=0
            )

    def _get_static_references(
        self,
        manufacturer: Optional[str],
        model: Optional[str],
        problem_type: ProblemType
    ) -> List[Reference]:
        """정적 참조 리소스 가져오기"""
        references = []

        if manufacturer:
            context = get_search_context(manufacturer, model)

            # 공식 문서 URL
            if context.get("official_url"):
                references.append(Reference(
                    title=f"{context['manufacturer']} Official Support",
                    url=context["official_url"],
                    source="official",
                    relevance=0.9,
                    snippet="Official manufacturer support and downloads"
                ))

            if context.get("official_docs_url"):
                references.append(Reference(
                    title=f"{context['manufacturer']} Documentation",
                    url=context["official_docs_url"],
                    source="official",
                    relevance=0.85,
                    snippet="Official technical documentation"
                ))

            # 커뮤니티 URL
            for url in context.get("community_urls", [])[:3]:
                source = "reddit" if "reddit" in url else "community"
                references.append(Reference(
                    title=f"{context['manufacturer']} Community",
                    url=url,
                    source=source,
                    relevance=0.75,
                    snippet="Community forum and discussions"
                ))

        # 문제 유형별 일반 리소스
        problem_resources = self._get_problem_resources(problem_type)
        references.extend(problem_resources)

        return references

    def _get_problem_resources(self, problem_type: ProblemType) -> List[Reference]:
        """문제 유형별 일반 참조 리소스"""
        resources = {
            ProblemType.BED_ADHESION: [
                Reference(
                    title="First Layer Adhesion Guide",
                    url="https://all3dp.com/2/3d-printer-first-layer-problems/",
                    source="guide",
                    relevance=0.8,
                    snippet="Comprehensive guide to first layer adhesion issues"
                ),
            ],
            ProblemType.STRINGING: [
                Reference(
                    title="Stringing Prevention Guide",
                    url="https://all3dp.com/2/3d-print-stringing-easy-ways-to-prevent-it/",
                    source="guide",
                    relevance=0.8,
                    snippet="How to prevent and fix stringing issues"
                ),
            ],
            ProblemType.WARPING: [
                Reference(
                    title="Warping Prevention Guide",
                    url="https://all3dp.com/2/3d-print-warping-what-it-is-how-to-fix-it/",
                    source="guide",
                    relevance=0.8,
                    snippet="How to prevent print warping"
                ),
            ],
            ProblemType.LAYER_SHIFTING: [
                Reference(
                    title="Layer Shifting Fix",
                    url="https://all3dp.com/2/3d-printing-layer-shifting/",
                    source="guide",
                    relevance=0.8,
                    snippet="Fixing layer shift problems"
                ),
            ],
            ProblemType.UNDER_EXTRUSION: [
                Reference(
                    title="Under Extrusion Guide",
                    url="https://all3dp.com/2/under-extrusion-3d-printing/",
                    source="guide",
                    relevance=0.8,
                    snippet="Causes and fixes for under extrusion"
                ),
            ],
            ProblemType.CLOGGING: [
                Reference(
                    title="Clogged Nozzle Fix",
                    url="https://all3dp.com/2/3d-printer-clogged-nozzle-how-to-perform-a-cold-pull/",
                    source="guide",
                    relevance=0.8,
                    snippet="How to clear and prevent nozzle clogs"
                ),
            ],
        }

        return resources.get(problem_type, [])


async def search_solutions(
    manufacturer: Optional[str],
    model: Optional[str],
    problem_type: ProblemType,
    symptom_text: str,
    language: str = "ko"
) -> List[SearchResult]:
    """
    편의 함수 - 솔루션 검색

    Args:
        manufacturer: 프린터 제조사
        model: 프린터 모델
        problem_type: 문제 유형
        symptom_text: 증상 설명
        language: 언어

    Returns:
        List[SearchResult]: 검색 결과
    """
    searcher = WebSearcher(language=language)
    return await searcher.search(manufacturer, model, problem_type, symptom_text)
