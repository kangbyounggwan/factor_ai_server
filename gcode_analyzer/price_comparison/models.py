"""
가격비교 데이터 모델
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class PriceComparisonOptions(BaseModel):
    """가격비교 옵션"""
    marketplaces: List[str] = Field(
        default=["naver", "coupang", "amazon", "ebay"],
        description="검색할 마켓플레이스"
    )
    min_price: Optional[int] = Field(None, description="최소 가격 (KRW)")
    max_price: Optional[int] = Field(None, description="최대 가격 (KRW)")
    sort_by: str = Field(
        "relevance",
        description="정렬 기준 (price_asc, price_desc, rating, review_count, relevance)"
    )
    max_results: int = Field(10, description="최대 결과 수")
    category: Optional[str] = Field(
        None,
        description="카테고리 (3d_printer, filament, parts, accessories)"
    )
    in_stock_only: bool = Field(False, description="재고 있는 상품만")


class PriceComparisonProduct(BaseModel):
    """가격비교 상품"""
    id: str = Field(..., description="상품 ID")
    title: str = Field(..., description="상품명")
    price: float = Field(..., description="가격 (원래 통화)")
    currency: str = Field("KRW", description="통화")
    price_krw: int = Field(..., description="원화 가격")
    original_price: Optional[float] = Field(None, description="원래 가격 (할인 전)")
    discount_percent: Optional[int] = Field(None, description="할인율")
    marketplace: str = Field(..., description="마켓플레이스")
    product_url: str = Field(..., description="상품 URL")
    image_url: Optional[str] = Field(None, description="상품 이미지 URL")
    rating: Optional[float] = Field(None, description="평점")
    review_count: Optional[int] = Field(None, description="리뷰 수")
    in_stock: bool = Field(True, description="재고 여부")
    delivery: Optional[str] = Field(None, description="배송 정보")


class PriceComparisonResult(BaseModel):
    """가격비교 결과"""
    query: str = Field(..., description="검색 쿼리")
    results_count: int = Field(..., description="결과 수")
    markets_searched: List[str] = Field(..., description="검색한 마켓플레이스")
    products: List[PriceComparisonProduct] = Field(
        default_factory=list,
        description="상품 목록"
    )
    price_summary: Optional[dict] = Field(None, description="가격 요약 (min, avg, max)")
