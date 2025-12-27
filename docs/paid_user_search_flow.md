# 유료 사용자 웹 검색 흐름 분석

## 1. 플랜별 설정 요약

| 플랜 | 검색 엔진 | 검색 깊이 | 결과/쿼리 |
|------|----------|----------|----------|
| **FREE** | DuckDuckGo + Wikipedia | - | 10개 |
| **STARTER** | Tavily API | basic | 10개 |
| **PRO** | Tavily API | advanced | 15개 |
| **ENTERPRISE** | Tavily API | advanced | 20개 |

---

## 2. 전체 흐름도

```
┌─────────────────────────────────────────────────────────────────┐
│                    사용자 요청 (이미지 + 텍스트)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  1단계: 이미지 분석 (ImageAnalyzer)                               │
│  - Vision LLM으로 이미지 분석                                     │
│  - symptom_text (사용자 입력) 함께 전달                           │
│  - detected_problems, augmented_query 생성                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2단계: 검색 쿼리 생성 (generate_search_queries)                  │
│  - official_query: 공식 문서용                                    │
│  - general_query: 일반 웹용                                       │
│  - community_query: 커뮤니티용                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  플랜 확인       │
                    │  use_tavily?    │
                    └─────────────────┘
                     │              │
            ┌────────┘              └────────┐
            │ YES (유료)                      │ NO (무료)
            ▼                                ▼
┌───────────────────────┐        ┌───────────────────────┐
│  Tavily API 검색       │        │  무료 검색             │
│  (STARTER/PRO/ENTERPRISE)│      │  (FREE)               │
│                        │        │                       │
│  - search_depth 적용   │        │  - DuckDuckGo         │
│  - max_results 적용    │        │  - Wikipedia          │
└───────────────────────┘        └───────────────────────┘
            │                                │
            └────────────┬───────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  3단계: 솔루션 생성 (SolutionGenerator)                           │
│  - 검색 결과 기반 해결책 생성                                      │
│  - 출처 URL 포함                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4단계: 참조 이미지 검색 (BraveImageSearcher)                     │
│  - 문제 유형 기반 이미지 검색                                     │
│  - 최대 10개 이미지 반환                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 코드 위치 및 상세 흐름

### 3.1 플랜 설정 정의

**파일**: `gcode_analyzer/troubleshoot/models.py`
```python
class UserPlan(str, Enum):
    FREE = "free"              # 무료 - DuckDuckGo + Wikipedia
    STARTER = "starter"        # 스타터 유료 - Tavily basic
    PRO = "pro"                # 프로 - Tavily advanced
    ENTERPRISE = "enterprise"  # 기업용 - 모든 기능
```

### 3.2 WebSearcher 플랜 설정

**파일**: `gcode_analyzer/troubleshoot/web_searcher.py`
```python
PLAN_CONFIG = {
    UserPlan.FREE: {
        "use_tavily": False,
        "max_results": 10,
        "search_depth": "basic",
        "query_types": ["official", "general", "community"],
    },
    UserPlan.STARTER: {
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
```

---

## 4. Tavily API 검색 흐름 (유료 사용자)

**파일**: `gcode_analyzer/troubleshoot/web_searcher.py`

### 4.1 검색 실행
```python
async def search(self, manufacturer, model, problem_type, symptom_text):
    # 1. 검색 쿼리 생성
    queries = await self.generate_search_queries(...)

    # 2. 플랜에 따른 분기
    if self.config["use_tavily"] and self.tavily_client:
        # 유료: Tavily API
        return await self._search_tavily(queries)
    else:
        # 무료: DuckDuckGo + Wikipedia
        return await self._search_free(queries)
```

### 4.2 Tavily 단일 검색
```python
async def _tavily_search_single(self, query: str, source_type: str):
    max_results = self.config["max_results"]      # 플랜별: 10/15/20
    search_depth = self.config["search_depth"]    # basic/advanced

    response = await loop.run_in_executor(
        None,
        lambda: self.tavily_client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_answer=False
        )
    )
```

---

## 5. 폴백 메커니즘

Tavily API 실패 시 자동으로 무료 검색으로 전환:

```python
try:
    tavily_results = await self._search_tavily(queries)
except Exception as e:
    logger.warning(f"Tavily search failed: {e}, falling back to free search")
    free_results = await self._search_free(queries)
```

---

## 6. 진단 API 흐름

### `POST /api/v1/troubleshoot/diagnose`

```
1. ImageAnalyzer.analyze_images()     → Vision 분석 + 질문 증강
2. WebSearcher.search()               → 플랜별 Tavily/무료 검색
3. SolutionGenerator.generate()       → 솔루션 생성
4. BraveImageSearcher.search_images() → 참조 이미지 검색
```

---

## 7. 환경 변수 요구사항

| 플랜 | 필수 환경 변수 |
|------|---------------|
| FREE | 없음 |
| STARTER/PRO/ENTERPRISE | `TAVILY_API_KEY` |

---

## 8. 검색 결과 수 비교

| 플랜 | 쿼리 수 | 결과/쿼리 | 총 최대 결과 |
|------|--------|----------|-------------|
| FREE | 3 | 10 | 30개 |
| STARTER | 3 | 10 | 30개 |
| PRO | 3 | 15 | 45개 |
| ENTERPRISE | 3 | 20 | 60개 |
