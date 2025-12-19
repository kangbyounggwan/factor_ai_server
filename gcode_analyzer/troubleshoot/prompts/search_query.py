"""
검색 쿼리 생성 프롬프트
"""

SEARCH_QUERY_PROMPT = """You are a 3D printing expert creating search queries to find solutions for printer issues.

## Context
- Printer Manufacturer: {manufacturer}
- Printer Model: {model}
- Problem Type: {problem_type}
- User Description: {symptom_text}
- Language: {language}

## Task
Generate 3 optimized search queries to find relevant solutions.

**IMPORTANT**:
- ALL queries MUST be in English for better search results
- Include specific symptoms from user description
- Make each query DIFFERENT and SPECIFIC to find diverse results

1. **official_query**: For manufacturer's official documentation/support
   - Include manufacturer name, model, and specific problem
   - Example: "Bambu Lab X1 Carbon first layer adhesion troubleshooting guide"

2. **community_query**: For Reddit, forums, and community resources
   - Start with "reddit" or "forum"
   - Include specific symptoms and printer model
   - Example: "reddit Bambu Lab first layer not sticking to textured PEI plate"

3. **general_query**: For general web search
   - Include "3D printing" and specific problem details
   - Example: "3D printing first layer adhesion PLA textured bed fix"

## Response Format (JSON)
```json
{{
    "official_query": "query for official docs in English",
    "community_query": "query for reddit/forums in English",
    "general_query": "query for general web search in English",
    "search_keywords": ["keyword1", "keyword2", "keyword3"]
}}
```

Generate search queries:
"""

SEARCH_QUERY_PROMPT_KO = """당신은 3D 프린팅 전문가입니다. 프린터 문제 해결을 위한 검색 쿼리를 생성합니다.

## 컨텍스트
- 프린터 제조사: {manufacturer}
- 프린터 모델: {model}
- 문제 유형: {problem_type}
- 사용자 설명: {symptom_text}
- 언어: {language}

## 작업
관련 솔루션을 찾기 위한 3개의 최적화된 검색 쿼리 생성

**중요**:
- 모든 쿼리는 **영어로** 작성하세요 (더 좋은 검색 결과를 위해)
- 사용자 설명에서 구체적인 증상을 포함하세요
- 각 쿼리가 **서로 다르고 구체적**이어야 다양한 결과를 얻을 수 있습니다

1. **official_query**: 제조사 공식 문서/지원용
   - 제조사명, 모델명, 구체적 문제 포함
   - 예: "Bambu Lab X1 Carbon first layer adhesion troubleshooting guide"

2. **community_query**: Reddit, 포럼 등 커뮤니티 리소스용
   - "reddit" 또는 "forum"으로 시작
   - 구체적 증상과 프린터 모델 포함
   - 예: "reddit Bambu Lab first layer not sticking to textured PEI plate"

3. **general_query**: 일반 웹 검색용
   - "3D printing"과 구체적 문제 상황 포함
   - 예: "3D printing first layer adhesion PLA textured bed fix"

## 응답 형식 (JSON)
```json
{{
    "official_query": "영어로 된 공식 문서용 쿼리",
    "community_query": "영어로 된 reddit/포럼용 쿼리",
    "general_query": "영어로 된 일반 웹 검색용 쿼리",
    "search_keywords": ["keyword1", "keyword2", "keyword3"]
}}
```

검색 쿼리 생성:
"""
