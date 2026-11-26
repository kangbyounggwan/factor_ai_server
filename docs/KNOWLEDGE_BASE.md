# 온톨로지 트리플 지식베이스 (증상 → 원인 → 해결)

2026 데이터바우처 사업에서 구축한 **3D 프린터 설비 이상 실증 데이터**(온톨로지 트리플 2,971건)를
분석 서버가 직접 조회해, 이슈 해결 응답에 **유사 실증 사례와 신뢰도 W(n)** 를 함께 돌려준다.

## 데이터

| 항목 | 값 |
|---|---|
| 원본 | `TB_YFIELD_FACTOR_GCODE_ONTOLOGY_TRIPLES.csv` (데이터바우처 산출물 ①, 41컬럼) |
| 건수 | 2,971건 · 증상 29종 |
| 출처 구성 | 실서비스 LLM 진단 1,634 · 현장 재분석(룰) 200 · 파라미터 스윕 생성 1,137 (`data_source`) |
| 서비스용 파일 | `scripts/build_knowledge_base.py` 로 만든 `.json.gz` (약 0.4 MB) |
| 넣지 않는 컬럼 | 보고서 식별자(`source_report_id`), G-code 원문(`gcode_context`), 시계열(`signal_series`) 등 |

**데이터 파일은 이 공개 저장소에 올리지 않는다.** 서버에는 환경변수로 위치를 알려 준다.

```
KNOWLEDGE_BASE_PATH=/var/www/factor_ai_server/data/ontology_triples_kb_v1.json.gz   # 로컬 파일
KNOWLEDGE_BASE_STORAGE=knowledge-base/ontology_triples_kb_v1.json.gz                 # 또는 Supabase Storage (비공개 버킷)
```

둘 다 없거나 읽지 못하면 지식베이스 없이 기존처럼 동작한다(`knowledge_cases` 는 빈 목록).

## 검색 방식 (오프라인 평가와 같은 2단계)

1. 질의 어휘 BM25(k1=1.5, b=0.75)로 **후보 20건**을 좁힌다. 색인 문서는 `symptom_type + cause_param + solution_text`,
   토큰은 영문·숫자 단어와 한글 2글자 묶음.
2. 후보 안에서만 `0.5·W(n)/max(W) + 0.5·BM25/max(BM25)` 로 **재순위화**한다.
   W(n) = D(t)·(0.3·C + 0.5·R + 0.2·F) — 트리플의 `confidence` 값(경로 검증 위반 ×0.05, 생성분 보정 포함).

이슈 유형 코드가 지식베이스의 증상 코드와 같으면 그 증상 안에서만 찾는다.

## API

| 메서드 · 경로 | 내용 |
|---|---|
| `GET /api/v1/knowledge/stats` | 건수 · 증상 수 · 출처 구성 · 버전 · 검색 방식 |
| `POST /api/v1/knowledge/search` | `{"query": "...", "top_k": 5, "symptom_type": null}` 자유 질의 검색 |
| `GET /api/v1/knowledge/issues/{issue_type}?top_k=3&text=...` | 이슈 유형 코드로 유사 사례 |
| `GET /api/v1/knowledge/analysis/{analysis_id}` | 저장된 분석의 이슈마다 유사 사례 |

**이슈 해결 연동** — `resolve_issue()` 가 `knowledge_cases` 를 함께 돌려주므로 아래 경로에 모두 실린다.

- `POST /api/v1/gcode/analysis/{analysis_id}/resolve-issue`
- `POST /api/v1/gcode/resolve-issue`
- 챗 `GCODE_ISSUE_RESOLVE` 도구 결과 (`data.resolution.knowledge_cases`)

`knowledge_cases` 항목: `triple_id, symptom_type, cause_param, cause_value, cause_ref_range, solution_text,
solution_label, confidence(W(n)), data_source, mechanism, resolution_basis, score, ...`

## 데이터 만들기 · 올리기

```bash
python scripts/build_knowledge_base.py TB_YFIELD_FACTOR_GCODE_ONTOLOGY_TRIPLES.csv ontology_triples_kb_v1.json.gz --version 2026-11-26.v1
# Supabase Storage 비공개 버킷에 올리기 (서비스 키 필요)
python scripts/build_knowledge_base.py TB_YFIELD_FACTOR_GCODE_ONTOLOGY_TRIPLES.csv ontology_triples_kb_v1.json.gz --upload knowledge-base/ontology_triples_kb_v1.json.gz
```

## 검증 (2026-11-26)

- 단위 시험: `python -m unittest tests.test_knowledge_base tests.test_filament_detection -v` → 29개 통과
  (합성 데이터 — 실제 데이터 없이 동작)
- 검색 정확도: 이 모듈로 질의 144개(가명처리 보고서 요약문)를 재측정한 값이 데이터바우처 오프라인 평가값과 같다.

| 지표 (질의 144 · 트리플 2,971) | 2단계(이 모듈) | BM25 단독 |
|---|---|---|
| Hit@1 | 68.8% | 66.0% |
| **Hit@3** | **88.9%** | 87.5% |
| Hit@5 | 93.8% | 93.1% |
| P@3 | 0.6644 | 0.6227 |
| MRR | 0.7956 | 0.7788 |
| Hit@3 엄격 기준 (같은 증상·원인 · 다른 보고서) | 87.5% | 84.7% |

정답은 증상 코드 일치로 자동 생성했다. W(n) 재순위의 기여는 BM25 단독 대비 Hit@3 +1.4%p(엄격 기준 +2.8%p).

## 한계

- 트리플의 38.3%(1,137건)는 파라미터 스윕 생성분이다 (`data_source=synthetic_sweep`, 신뢰도 보정 적용).
- 증상의 약 84%가 온도 계열이라 형상·품질 계열 질의는 정확도가 낮을 수 있다.
- 이슈 해결 LLM 프롬프트에는 아직 유사 사례를 넣지 않았다 (응답에 별도 필드로만 제공).
