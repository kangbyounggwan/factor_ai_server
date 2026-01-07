"""
SerpAPI 클라이언트 - Google Shopping 검색
"""
import os
import logging
import hashlib
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

import httpx

from .models import (
    PriceComparisonOptions,
    PriceComparisonProduct,
    PriceComparisonResult
)

logger = logging.getLogger(__name__)

# 간단한 메모리 캐시 (1시간)
_cache: Dict[str, tuple] = {}  # {cache_key: (result, timestamp)}
CACHE_TTL = timedelta(hours=1)


class SerpAPIClient:
    """SerpAPI Google Shopping 클라이언트"""

    BASE_URL = "https://serpapi.com/search"

    # 환율 (USD → KRW) - 실제로는 환율 API 사용 권장
    USD_TO_KRW = 1350

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SERPAPI_KEY")
        if not self.api_key:
            raise ValueError("SERPAPI_KEY is required")

    async def search(
        self,
        query: str,
        options: Optional[PriceComparisonOptions] = None
    ) -> PriceComparisonResult:
        """
        Google Shopping에서 상품 검색

        Args:
            query: 검색 쿼리
            options: 검색 옵션

        Returns:
            PriceComparisonResult: 검색 결과
        """
        options = options or PriceComparisonOptions()

        # 캐시 확인
        cache_key = self._get_cache_key(query, options)
        cached = self._get_from_cache(cache_key)
        if cached:
            logger.info(f"Cache hit for query: {query}")
            return cached

        # SerpAPI 검색 실행
        products = []
        markets_searched = []

        # Google Shopping 검색 (글로벌 - Amazon, eBay 등 포함)
        if any(m in options.marketplaces for m in ["amazon", "ebay", "google"]):
            google_results = await self._search_google_shopping(query, options)
            products.extend(google_results)
            markets_searched.append("google")

        # Naver Shopping 검색 (한국)
        if "naver" in options.marketplaces:
            naver_results = await self._search_naver_shopping(query, options)
            products.extend(naver_results)
            markets_searched.append("naver")

        # 정렬
        products = self._sort_products(products, options.sort_by)

        # 가격 필터링
        products = self._filter_by_price(products, options.min_price, options.max_price)

        # 재고 필터링
        if options.in_stock_only:
            products = [p for p in products if p.in_stock]

        # 최대 결과 수 제한
        products = products[:options.max_results]

        # 가격 요약 계산
        price_summary = self._calculate_price_summary(products)

        result = PriceComparisonResult(
            query=query,
            results_count=len(products),
            markets_searched=markets_searched,
            products=products,
            price_summary=price_summary
        )

        # 캐시 저장
        self._save_to_cache(cache_key, result)

        return result

    async def _search_google_shopping(
        self,
        query: str,
        options: PriceComparisonOptions
    ) -> List[PriceComparisonProduct]:
        """Google Shopping 검색"""
        params = {
            "engine": "google_shopping",
            "q": query,
            "hl": "ko",
            "gl": "kr",
            "num": options.max_results * 2,  # 필터링 고려해서 더 많이 검색
            "api_key": self.api_key
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

            shopping_results = data.get("shopping_results", [])
            products = []

            for idx, item in enumerate(shopping_results):
                product = self._parse_google_shopping_item(item, idx)
                if product:
                    products.append(product)

            logger.info(f"Google Shopping: Found {len(products)} products for '{query}'")
            return products

        except Exception as e:
            logger.error(f"Google Shopping search failed: {e}")
            return []

    async def _search_naver_shopping(
        self,
        query: str,
        options: PriceComparisonOptions
    ) -> List[PriceComparisonProduct]:
        """Naver Shopping 검색 (SerpAPI)"""
        params = {
            "engine": "naver_shopping",
            "query": query,
            "num": options.max_results * 2,
            "api_key": self.api_key
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

            shopping_results = data.get("shopping_results", [])
            products = []

            for idx, item in enumerate(shopping_results):
                product = self._parse_naver_shopping_item(item, idx)
                if product:
                    products.append(product)

            logger.info(f"Naver Shopping: Found {len(products)} products for '{query}'")
            return products

        except Exception as e:
            logger.error(f"Naver Shopping search failed: {e}")
            return []

    def _parse_google_shopping_item(
        self,
        item: Dict[str, Any],
        idx: int
    ) -> Optional[PriceComparisonProduct]:
        """Google Shopping 결과 파싱"""
        try:
            # 가격 추출
            price = item.get("extracted_price", 0)
            currency = "USD"  # Google Shopping 기본 통화

            # 원화 가격 계산
            if "₩" in str(item.get("price", "")):
                currency = "KRW"
                price_krw = int(price) if price else 0
            else:
                price_krw = int(price * self.USD_TO_KRW) if price else 0

            # 마켓플레이스 추출
            source = item.get("source", "").lower()
            marketplace = self._detect_marketplace(source)

            # 할인 정보 (old_price가 dict 또는 string일 수 있음)
            original_price = None
            old_price_data = item.get("old_price")
            if isinstance(old_price_data, dict):
                original_price = old_price_data.get("extracted")
            elif isinstance(old_price_data, (int, float)):
                original_price = old_price_data

            discount_percent = None
            if original_price and price and original_price > price:
                discount_percent = int((1 - price / original_price) * 100)

            # URL 추출: product_link > link 순서로 시도
            product_url = item.get("product_link") or item.get("link", "")

            return PriceComparisonProduct(
                id=f"google_{idx}_{hashlib.md5(item.get('title', '').encode()).hexdigest()[:8]}",
                title=item.get("title", ""),
                price=price,
                currency=currency,
                price_krw=price_krw,
                original_price=original_price,
                discount_percent=discount_percent,
                marketplace=marketplace,
                product_url=product_url,
                image_url=item.get("thumbnail", ""),
                rating=item.get("rating"),
                review_count=item.get("reviews"),
                in_stock=True,  # Google Shopping은 재고 정보 없음
                delivery=item.get("delivery", "")
            )

        except Exception as e:
            logger.warning(f"Failed to parse Google Shopping item: {e}")
            return None

    def _parse_naver_shopping_item(
        self,
        item: Dict[str, Any],
        idx: int
    ) -> Optional[PriceComparisonProduct]:
        """Naver Shopping 결과 파싱"""
        try:
            price = item.get("price", 0)
            if isinstance(price, str):
                price = int(price.replace(",", "").replace("원", ""))

            # 마켓플레이스 추출 (쿠팡, 11번가 등)
            mall_name = item.get("mall_name", "").lower()
            if "coupang" in mall_name or "쿠팡" in mall_name:
                marketplace = "coupang"
            elif "11st" in mall_name or "11번가" in mall_name:
                marketplace = "11st"
            else:
                marketplace = "naver"

            return PriceComparisonProduct(
                id=f"naver_{idx}_{hashlib.md5(item.get('title', '').encode()).hexdigest()[:8]}",
                title=item.get("title", ""),
                price=price,
                currency="KRW",
                price_krw=int(price),
                original_price=None,
                discount_percent=None,
                marketplace=marketplace,
                product_url=item.get("link", ""),
                image_url=item.get("thumbnail", ""),
                rating=item.get("rating"),
                review_count=item.get("review_count"),
                in_stock=True,
                delivery=item.get("delivery", "")
            )

        except Exception as e:
            logger.warning(f"Failed to parse Naver Shopping item: {e}")
            return None

    def _detect_marketplace(self, source: str) -> str:
        """판매처 이름으로 마켓플레이스 감지"""
        source_lower = source.lower()

        if "amazon" in source_lower:
            return "amazon"
        elif "ebay" in source_lower:
            return "ebay"
        elif "aliexpress" in source_lower:
            return "aliexpress"
        elif "coupang" in source_lower or "쿠팡" in source_lower:
            return "coupang"
        elif "naver" in source_lower or "네이버" in source_lower:
            return "naver"
        else:
            return source[:20] if source else "other"

    def _sort_products(
        self,
        products: List[PriceComparisonProduct],
        sort_by: str
    ) -> List[PriceComparisonProduct]:
        """상품 정렬"""
        if sort_by == "price_asc":
            return sorted(products, key=lambda x: x.price_krw)
        elif sort_by == "price_desc":
            return sorted(products, key=lambda x: x.price_krw, reverse=True)
        elif sort_by == "rating":
            return sorted(products, key=lambda x: x.rating or 0, reverse=True)
        elif sort_by == "review_count":
            return sorted(products, key=lambda x: x.review_count or 0, reverse=True)
        else:
            return products  # relevance - 원래 순서 유지

    def _filter_by_price(
        self,
        products: List[PriceComparisonProduct],
        min_price: Optional[int],
        max_price: Optional[int]
    ) -> List[PriceComparisonProduct]:
        """가격 범위 필터링"""
        filtered = products

        if min_price is not None:
            filtered = [p for p in filtered if p.price_krw >= min_price]

        if max_price is not None:
            filtered = [p for p in filtered if p.price_krw <= max_price]

        return filtered

    def _calculate_price_summary(
        self,
        products: List[PriceComparisonProduct]
    ) -> Optional[dict]:
        """가격 요약 계산"""
        if not products:
            return None

        prices = [p.price_krw for p in products if p.price_krw > 0]
        if not prices:
            return None

        return {
            "min": min(prices),
            "max": max(prices),
            "avg": int(sum(prices) / len(prices)),
            "count": len(prices)
        }

    def _get_cache_key(self, query: str, options: PriceComparisonOptions) -> str:
        """캐시 키 생성"""
        key_str = f"{query}_{options.sort_by}_{options.max_results}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_from_cache(self, key: str) -> Optional[PriceComparisonResult]:
        """캐시에서 결과 조회"""
        if key in _cache:
            result, timestamp = _cache[key]
            if datetime.now() - timestamp < CACHE_TTL:
                return result
            else:
                del _cache[key]
        return None

    def _save_to_cache(self, key: str, result: PriceComparisonResult):
        """캐시에 결과 저장"""
        _cache[key] = (result, datetime.now())

        # 캐시 크기 제한 (최대 100개)
        if len(_cache) > 100:
            oldest_key = min(_cache.keys(), key=lambda k: _cache[k][1])
            del _cache[oldest_key]
