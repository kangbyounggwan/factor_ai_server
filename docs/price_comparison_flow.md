# 3D 프린터 부품/소모품 가격비교 기능 설계

## 개요

SerpAPI를 활용하여 3D 프린터 관련 제품(필라멘트, 노즐, 부품 등)의 가격비교 정보를 제공하는 기능입니다.

---

## 시스템 흐름도

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           사용자 질문                                    │
│          "PLA 필라멘트 추천해줘" / "노즐 어디서 사는게 싸?"              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    1. Intent Classification                              │
│                    (의도 분류 - LLM)                                     │
├─────────────────────────────────────────────────────────────────────────┤
│  - 가격비교 필요 여부 판단                                               │
│  - 제품 카테고리 추출 (필라멘트, 노즐, 부품 등)                          │
│  - 검색 키워드 추출                                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
        ┌───────────────────┐           ┌───────────────────┐
        │   일반 답변 분기   │           │  가격비교 분기     │
        │ (GENERAL_QUESTION)│           │ (PRICE_COMPARISON) │
        └───────────────────┘           └───────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    2. Query Generation                                   │
│                    (검색 쿼리 생성 - LLM)                                │
├─────────────────────────────────────────────────────────────────────────┤
│  입력: 사용자 메시지, 제품 카테고리                                      │
│  출력:                                                                   │
│    - search_query: "PLA 필라멘트 1kg"                                   │
│    - product_type: "filament"                                           │
│    - specifications: ["1.75mm", "1kg", "PLA"]                           │
│    - price_range: { min: null, max: 30000 }  (optional)                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    3. SerpAPI Search                                     │
│                    (상품 검색)                                           │
├─────────────────────────────────────────────────────────────────────────┤
│  API: Google Shopping API via SerpAPI                                   │
│                                                                         │
│  요청 파라미터:                                                          │
│    - engine: "google_shopping"                                          │
│    - q: "{search_query}"                                                │
│    - location: "South Korea"                                            │
│    - hl: "ko"                                                           │
│    - gl: "kr"                                                           │
│    - num: 20                                                            │
│                                                                         │
│  응답 데이터:                                                            │
│    - shopping_results[]:                                                │
│        - title: 상품명                                                  │
│        - price: 가격                                                    │
│        - extracted_price: 숫자 가격                                     │
│        - link: 상품 URL                                                 │
│        - source: 판매처 (쿠팡, 11번가 등)                               │
│        - thumbnail: 이미지 URL                                          │
│        - rating: 평점                                                   │
│        - reviews: 리뷰 수                                               │
│        - delivery: 배송 정보                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    4. Data Processing                                    │
│                    (데이터 정제)                                         │
├─────────────────────────────────────────────────────────────────────────┤
│  - 가격 기준 정렬 (최저가순)                                             │
│  - 중복 상품 제거                                                        │
│  - 스펙 불일치 상품 필터링                                               │
│  - 신뢰도 낮은 판매처 필터링 (optional)                                  │
│  - 상위 N개 선별 (기본 5개)                                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    5. Response Generation                                │
│                    (응답 생성 - LLM)                                     │
├─────────────────────────────────────────────────────────────────────────┤
│  입력:                                                                   │
│    - 원본 질문                                                          │
│    - 검색 결과 (상품 목록)                                               │
│    - 제품 카테고리                                                       │
│                                                                         │
│  출력 (마크다운 형식):                                                   │
│    - 요약: 최저가/평균가/최고가                                         │
│    - 추천 상품 TOP 3~5                                                  │
│    - 구매 팁 (해당 제품 관련)                                           │
│    - 주의사항 (저가 제품 품질 이슈 등)                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         최종 응답                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 상세 설계

### 1. Intent Classification (의도 분류)

가격비교가 필요한 질문 패턴:
- "~~ 추천해줘" + 제품명
- "~~ 어디서 사?" / "어디가 싸?"
- "~~ 가격" / "~~ 얼마?"
- "~~ 구매" / "~~ 주문"

```python
# 가격비교 트리거 키워드
PRICE_COMPARISON_KEYWORDS = [
    # 구매 의도
    "추천", "사고 싶", "구매", "주문", "어디서", "어디가",
    # 가격 관련
    "가격", "얼마", "싸", "저렴", "최저가", "비교",
    # 영어
    "buy", "purchase", "price", "cheap", "recommend"
]

# 제품 카테고리
PRODUCT_CATEGORIES = {
    "filament": ["필라멘트", "PLA", "ABS", "PETG", "TPU", "실"],
    "nozzle": ["노즐", "nozzle", "핫엔드"],
    "bed": ["베드", "빌드플레이트", "유리판", "PEI"],
    "parts": ["익스트루더", "모터", "벨트", "베어링", "팬"],
    "tools": ["스패츌라", "니퍼", "핀셋", "윤활유"],
    "printer": ["프린터", "3D프린터", "printer"]
}
```

### 2. SerpAPI 연동

```python
# SerpAPI Google Shopping 요청 예시
import serpapi

def search_products(query: str, num_results: int = 20) -> dict:
    params = {
        "engine": "google_shopping",
        "q": query,
        "location": "South Korea",
        "hl": "ko",
        "gl": "kr",
        "num": num_results,
        "api_key": SERPAPI_KEY
    }

    search = serpapi.search(params)
    return search.get("shopping_results", [])
```

### 3. 응답 포맷

```markdown
## PLA 필라멘트 가격비교 결과

### 가격 요약
| 구분 | 가격 |
|------|------|
| 최저가 | ₩12,900 |
| 평균가 | ₩18,500 |
| 최고가 | ₩29,000 |

---

### 추천 상품 TOP 5

#### 1. [eSUN PLA+ 1kg] - ₩12,900 ⭐ 최저가
- **판매처:** 쿠팡
- **평점:** ★★★★☆ (4.5/5, 1,234개 리뷰)
- **배송:** 로켓배송 (내일 도착)
- **[구매 링크](https://...)**

#### 2. [Creality PLA 1kg] - ₩14,500
- **판매처:** 11번가
- **평점:** ★★★★☆ (4.3/5, 856개 리뷰)
- **배송:** 무료배송
- **[구매 링크](https://...)**

...

---

### 구매 팁
- PLA 필라멘트는 습기에 약하므로 **밀봉 포장** 제품을 선택하세요
- 1.75mm 규격이 가장 보편적입니다 (프린터 호환 확인)
- 색상별 가격 차이가 있을 수 있습니다

### 주의사항
- 극저가 제품은 품질 편차가 있을 수 있습니다
- 해외 직구 제품은 배송 기간(2~3주)을 고려하세요
```

---

## 데이터 모델

### Request Model

```python
class PriceComparisonRequest(BaseModel):
    """가격비교 요청"""
    user_message: str              # 원본 메시지
    product_category: str          # 제품 카테고리
    search_query: str              # 검색 쿼리
    specifications: List[str]      # 스펙 조건
    price_range: Optional[Dict]    # 가격 범위
    num_results: int = 10          # 결과 개수
```

### Response Model

```python
class ProductItem(BaseModel):
    """상품 아이템"""
    title: str                     # 상품명
    price: int                     # 가격 (원)
    price_display: str             # 표시 가격 ("₩12,900")
    source: str                    # 판매처
    link: str                      # 상품 URL
    thumbnail: Optional[str]       # 이미지 URL
    rating: Optional[float]        # 평점
    reviews: Optional[int]         # 리뷰 수
    delivery: Optional[str]        # 배송 정보


class PriceComparisonResult(BaseModel):
    """가격비교 결과"""
    search_query: str              # 검색 쿼리
    total_count: int               # 총 검색 결과 수
    price_summary: Dict[str, int]  # 가격 요약 (min, avg, max)
    products: List[ProductItem]    # 상품 목록
    generated_response: str        # LLM 생성 응답
    search_timestamp: datetime     # 검색 시간
```

---

## 파일 구조

```
gcode_analyzer/
├── price_comparison/
│   ├── __init__.py
│   ├── router.py              # API 엔드포인트
│   ├── models.py              # 데이터 모델
│   ├── serp_client.py         # SerpAPI 클라이언트
│   ├── query_generator.py     # 검색 쿼리 생성 (LLM)
│   ├── data_processor.py      # 데이터 정제
│   ├── response_generator.py  # 응답 생성 (LLM)
│   └── prompts/
│       ├── __init__.py
│       ├── query_generation.py
│       └── response_generation.py
```

---

## API 엔드포인트

### Chat API 통합

기존 Chat API에 `PRICE_COMPARISON` Intent 추가:

```
POST /api/v1/chat
{
    "message": "PLA 필라멘트 추천해줘",
    "user_id": "user_123"
}

Response:
{
    "intent": "price_comparison",
    "response": "## PLA 필라멘트 가격비교 결과...",
    "tool_result": {
        "tool_name": "price_comparison",
        "data": {
            "products": [...],
            "price_summary": {...}
        }
    }
}
```

### 독립 API (Optional)

```
POST /api/v1/price/compare
{
    "query": "PLA 필라멘트 1kg",
    "category": "filament",
    "num_results": 10
}
```

---

## 환경 변수

```env
# SerpAPI
SERPAPI_KEY=your_serpapi_key_here
```

---

## 고려사항

### 비용 관리
- SerpAPI 호출당 비용 발생 (약 $0.01~0.05/요청)
- 캐싱 전략 필요 (동일 쿼리 1시간 캐싱)
- Rate limiting 적용

### 품질 관리
- 검색 결과 필터링 (관련성 낮은 상품 제외)
- 신뢰도 높은 판매처 우선 노출
- 가격 이상치 제거 (극단적 저가/고가)

### 사용자 경험
- 검색 중 로딩 상태 표시
- 검색 결과 없을 때 대안 제시
- 이전 검색 기록 저장 (optional)
