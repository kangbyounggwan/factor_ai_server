# G-code 분석 시스템 개발 계획서

## 프로젝트 개요

### 목표
G-code 파일을 업로드하면 자동으로 분석하여 이상 패턴을 탐지하고, LLM(Claude)이 문제점과 수정 방향을 제안하는 시스템 구축

### 핵심 기능
1. G-code 파일 업로드 및 파싱
2. 온도/설정/패턴 분석
3. 이상 구간 자동 탐지 (예: `M104 S0` 이후 익스트루전)
4. LLM 기반 이상 원인 설명 및 수정 방향 제안
5. 규칙 기반 G-code 패치 (또는 수정 가이드)
6. 분석 과정을 타임라인 UI로 시각화

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Frontend (React)                                │
│  ┌─────────────┐  ┌─────────────────┐  ┌──────────────┐  ┌───────────────┐ │
│  │ Upload Zone │  │ Analysis Result │  │ Timeline UI  │  │ Patch Preview │ │
│  └─────────────┘  └─────────────────┘  └──────────────┘  └───────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Backend (FastAPI)                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    LangGraph Workflow Orchestrator                    │  │
│  │  ┌────────┐  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌────────┐ │  │
│  │  │ Parse  │─▶│ Summarize│─▶│  Detect    │─▶│ Extract  │─▶│  LLM   │ │  │
│  │  │ G-code │  │  G-code  │  │ Anomalies  │  │ Snippets │  │ Explain│ │  │
│  │  └────────┘  └──────────┘  └────────────┘  └──────────┘  └────────┘ │  │
│  │                                                              │       │  │
│  │                                    ┌────────────┐  ┌────────▼──────┐│  │
│  │                                    │   Apply    │◀─│  LLM Strategy ││  │
│  │                                    │   Patches  │  │   Suggestion  ││  │
│  │                                    └────────────┘  └───────────────┘│  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Claude API (Anthropic)                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 개발 단계

### 1단계: 요구사항 및 데이터 정의

#### 1-1. 유즈케이스
| 구분 | 설명 |
|------|------|
| MVP | 단일 G-code 업로드 → 분석 → 리포트 출력 |
| 확장 | FACTOR 시스템 연동, 실시간 모니터링/알림 |

#### 1-2. 입출력 형식

**입력:**
- `.gcode` 파일

**내부 표현:**
- `List[str]` (라인 단위)

**분석 결과 (JSON):**
```json
{
  "global_summary": {
    "total_layers": 150,
    "layer_height": 0.2,
    "nozzle_temp_range": [200, 215],
    "bed_temp_range": [60, 60],
    "estimated_time": "2h 30m",
    "filament_used": "15.5m"
  },
  "temp_events": [
    {"line_index": 100, "cmd": "M104", "temp": 215},
    {"line_index": 5000, "cmd": "M104", "temp": 0}
  ],
  "anomalies": [
    {
      "type": "cold_extrusion",
      "line_index": 5010,
      "severity": "high",
      "message": "온도 0°C 설정 후 익스트루전 시도"
    }
  ],
  "llm_analysis": {
    "explanation": "...",
    "suggested_rules": ["..."]
  }
}
```

#### 1-3. 산출물
- [ ] 요구사항 문서
- [ ] G-code 예시 파일 (정상/문제)

---

### 2단계: G-code 파서 & 요약기 (Pure Python)

> LLM 없이 순수 코드로 구현

#### 2-1. 기본 파싱 모듈

**파일:** `gcode_analyzer/parser.py`

```python
from pydantic import BaseModel

class GCodeLine(BaseModel):
    index: int           # 라인 번호
    raw: str             # 원본 문자열
    cmd: str             # G1, G0, M104 등
    params: dict         # {"X": 10.2, "E": 42.123, "S": 215}
    comment: str | None  # 주석

def parse_gcode(file_path: str) -> list[GCodeLine]:
    """G-code 파일을 파싱하여 구조화된 리스트 반환"""
    pass
```

#### 2-2. 전역 요약 정보 추출

**파일:** `gcode_analyzer/summary.py`

추출 항목:
- 레이어 높이 추정
- 총 레이어 수 (추정/주석 기반)
- 노즐/베드 온도 범위
- 평균/최대 속도 (F 값)
- 리트랙션 카운트
- 필라멘트 타입 (주석에서 추출)

```python
from pydantic import BaseModel

class GCodeSummary(BaseModel):
    total_layers: int
    layer_height: float
    nozzle_temp_min: float
    nozzle_temp_max: float
    bed_temp_min: float
    bed_temp_max: float
    max_speed: float
    avg_speed: float
    retraction_count: int
    filament_type: str | None
    estimated_print_time: str | None

def summarize_gcode(lines: list[GCodeLine]) -> GCodeSummary:
    """파싱된 G-code에서 전역 요약 정보 추출"""
    pass
```

#### 2-3. CLI 도구

```bash
python -m gcode_analyzer.cli summarize file.gcode
```

#### 산출물
- [ ] `gcode_analyzer/parser.py`
- [ ] `gcode_analyzer/summary.py`
- [ ] `gcode_analyzer/cli.py`

---

### 3단계: 이상 패턴 탐지 (룰 엔진)

#### 3-1. 온도 이벤트 추출기

**파일:** `gcode_analyzer/temp_tracker.py`

```python
from pydantic import BaseModel

class TempEvent(BaseModel):
    line_index: int
    temp: float
    cmd: str  # M104 or M109

def extract_temp_events(lines: list[GCodeLine]) -> list[TempEvent]:
    """M104, M109 명령 추출"""
    pass
```

#### 3-2. 이상 패턴 정의

**파일:** `gcode_analyzer/anomaly_detector.py`

```python
from pydantic import BaseModel
from enum import Enum

class AnomalyType(str, Enum):
    COLD_EXTRUSION = "cold_extrusion"           # 차가운 상태에서 익스트루전
    EARLY_TEMP_OFF = "early_temp_off"           # 종료 전 조기 온도 OFF
    EXCESSIVE_RETRACTION = "excessive_retraction"  # 과도한 리트랙션
    RAPID_TEMP_CHANGE = "rapid_temp_change"     # 급격한 온도 변화
    MISSING_WARMUP = "missing_warmup"           # 예열 누락

class Anomaly(BaseModel):
    type: AnomalyType
    line_index: int
    severity: str  # low, medium, high
    temp_before: float | None
    temp_after: float | None
    message: str
    context: dict  # 추가 컨텍스트 정보

def detect_anomalies(
    lines: list[GCodeLine],
    temp_events: list[TempEvent]
) -> list[Anomaly]:
    """이상 패턴 탐지"""
    pass
```

#### 3-3. 탐지 규칙

| 규칙명 | 조건 | 심각도 |
|--------|------|--------|
| 차가운 상태 익스트루전 | `current_target_temp < 150°C` 인데 E값 증가 | HIGH |
| 조기 온도 OFF | `;End of Gcode` 또는 `M84` 이전에 `M104 S0` | MEDIUM |
| 과도한 리트랙션 | 연속 3회 이상 리트랙션 | LOW |
| 급격한 온도 변화 | 50°C 이상 급변 | MEDIUM |

#### 산출물
- [ ] `gcode_analyzer/temp_tracker.py`
- [ ] `gcode_analyzer/anomaly_detector.py`
- [ ] `gcode_analyzer/rules/` (개별 규칙 모듈)

---

### 4단계: 스니펫 추출 & 토큰 컨트롤

> LLM에 전달할 최소 정보만 추출

#### 4-1. 스니펫 추출 함수

**파일:** `gcode_analyzer/snippet_extractor.py`

```python
def extract_snippet(
    lines: list[str],
    center_idx: int,
    window: int = 50,
    max_lines: int = 200
) -> str:
    """이상 발생 지점 주변 G-code 스니펫 추출"""
    start = max(0, center_idx - window)
    end = min(len(lines), center_idx + window)

    snippet_lines = lines[start:end]
    if len(snippet_lines) > max_lines:
        # 중앙 기준으로 잘라냄
        half = max_lines // 2
        snippet_lines = lines[center_idx - half:center_idx + half]

    return "\n".join(snippet_lines)
```

#### 4-2. LLM 입력용 구조

```python
class LLMInput(BaseModel):
    global_summary: dict      # 짧게 요약된 정보
    anomaly: Anomaly          # 룰 엔진이 찾은 이상 정보
    snippet: str              # 주변 G-code 일부 (최대 200줄)

    def token_estimate(self) -> int:
        """대략적인 토큰 수 추정"""
        pass
```

#### 산출물
- [ ] `gcode_analyzer/snippet_extractor.py`
- [ ] `gcode_analyzer/llm_input.py`

---

### 5단계: Claude 통합 - 분석/설명 (LangChain 함수 1)

#### 5-1. Claude 클라이언트 설정

**파일:** `gcode_analyzer/llm/client.py`

```python
from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate

llm = ChatAnthropic(
    model="claude-sonnet-4-20250514",
    temperature=0,
    max_tokens=1024
)
```

#### 5-2. 분석/설명 프롬프트

**파일:** `gcode_analyzer/llm/explain_prompt.py`

```python
EXPLAIN_PROMPT = """
[컨텍스트]
- 이 G-code는 FDM 3D 프린터용입니다.
- 아래는 G-code 일부입니다. (온도 설정 명령과 그 주변)
- 아래 JSON은 분석기가 감지한 이상 패턴입니다.

[전역 요약]
{global_summary}

[이상 패턴]
{anomaly_json}

[G-code 스니펫]
```gcode
{snippet}
```

[요청]
1) 이 패턴이 실제 출력에서 어떤 문제를 만들 수 있는지 설명해줘.
2) 심각도를 low/medium/high 중 하나로 표시해줘.
3) 한 줄 요약을 만들어줘.

JSON 형식으로만 답해줘:
{{
  "severity": "...",
  "summary": "...",
  "details": "..."
}}
"""
```

#### 5-3. 래퍼 함수

**파일:** `gcode_analyzer/llm/explain.py`

```python
from pydantic import BaseModel

class LLMExplanation(BaseModel):
    severity: str
    summary: str
    details: str

async def llm_explain_anomaly(
    anomaly: Anomaly,
    snippet: str,
    global_summary: dict
) -> LLMExplanation:
    """Claude를 사용하여 이상 패턴 설명 생성"""
    pass
```

#### 산출물
- [ ] `gcode_analyzer/llm/client.py`
- [ ] `gcode_analyzer/llm/explain_prompt.py`
- [ ] `gcode_analyzer/llm/explain.py`

---

### 6단계: 수정 전략 제안 & 패치 (LangChain 함수 2)

> LLM은 전략/패턴만 제안, 실제 수정은 코드로

#### 6-1. 수정 전략 프롬프트

**파일:** `gcode_analyzer/llm/strategy_prompt.py`

```python
STRATEGY_PROMPT = """
[상황]
- 아래 anomaly는 {anomaly_type} 문제입니다.
- 우리는 안전한 G-code 수정을 선호합니다.

[이상 패턴]
{anomaly_json}

[G-code 스니펫]
```gcode
{snippet}
```

[요청]
1) 이 문제를 피하기 위한 수정 전략을 설명해줘.
2) 코드로 구현 가능한 규칙을 1~3개로 정리해줘.

예시:
- "출력 중간의 M104 S0는 모두 삭제한다."
- "마지막 M104 S0만 남기고 나머지는 제거한다."

JSON 형식:
{{
  "strategy_summary": "...",
  "rules": ["...", "..."],
  "risk_level": "low|medium|high"
}}
"""
```

#### 6-2. 안전한 패치 함수

**파일:** `gcode_analyzer/patcher.py`

```python
class PatchResult(BaseModel):
    original_lines: int
    modified_lines: int
    changes: list[dict]  # {"line": 100, "action": "remove", "reason": "..."}
    patched_gcode: list[str]

def remove_mid_print_m104_s0(lines: list[str]) -> PatchResult:
    """출력 중간의 M104 S0 제거"""
    pass

def move_temp_off_to_end(lines: list[str]) -> PatchResult:
    """온도 OFF 명령을 엔드 코드로 이동"""
    pass

def apply_safe_patches(
    lines: list[str],
    anomalies: list[Anomaly],
    strategy: dict
) -> PatchResult:
    """안전한 패치만 적용"""
    pass
```

#### 산출물
- [ ] `gcode_analyzer/llm/strategy_prompt.py`
- [ ] `gcode_analyzer/llm/strategy.py`
- [ ] `gcode_analyzer/patcher.py`

---

### 7단계: LangGraph 워크플로우 오케스트레이션

#### 7-1. 노드 구성

```python
# gcode_analyzer/workflow/graph.py

from langgraph.graph import StateGraph, END
from typing import TypedDict

class AnalysisState(TypedDict):
    file_path: str
    raw_lines: list[str]
    parsed_lines: list[GCodeLine]
    summary: GCodeSummary
    temp_events: list[TempEvent]
    anomalies: list[Anomaly]
    snippets: list[str]
    explanations: list[LLMExplanation]
    strategies: list[dict]
    patches: PatchResult | None
    timeline: list[dict]  # UI용 진행 상태

# 노드 정의
def parse_node(state: AnalysisState) -> AnalysisState:
    """G-code 파싱"""
    pass

def summarize_node(state: AnalysisState) -> AnalysisState:
    """요약 정보 추출"""
    pass

def detect_node(state: AnalysisState) -> AnalysisState:
    """이상 패턴 탐지"""
    pass

def extract_node(state: AnalysisState) -> AnalysisState:
    """스니펫 추출"""
    pass

def explain_node(state: AnalysisState) -> AnalysisState:
    """LLM 분석 (병렬 처리 가능)"""
    pass

def strategy_node(state: AnalysisState) -> AnalysisState:
    """수정 전략 제안"""
    pass

def patch_node(state: AnalysisState) -> AnalysisState:
    """패치 적용 (옵션)"""
    pass
```

#### 7-2. 그래프 구성

```python
workflow = StateGraph(AnalysisState)

workflow.add_node("parse", parse_node)
workflow.add_node("summarize", summarize_node)
workflow.add_node("detect", detect_node)
workflow.add_node("extract", extract_node)
workflow.add_node("explain", explain_node)
workflow.add_node("strategy", strategy_node)
workflow.add_node("patch", patch_node)

workflow.set_entry_point("parse")
workflow.add_edge("parse", "summarize")
workflow.add_edge("summarize", "detect")
workflow.add_edge("detect", "extract")
workflow.add_edge("extract", "explain")
workflow.add_edge("explain", "strategy")
workflow.add_edge("strategy", "patch")
workflow.add_edge("patch", END)

app = workflow.compile()
```

#### 7-3. 단순 버전 (LangGraph 없이)

```python
# gcode_analyzer/analyzer.py

async def analyze_gcode(file_path: str) -> AnalysisResult:
    """전체 분석 워크플로우 실행"""
    # 1. 파싱
    lines = read_gcode(file_path)
    parsed = parse_gcode(lines)

    # 2. 요약
    summary = summarize_gcode(parsed)

    # 3. 이상 탐지
    temp_events = extract_temp_events(parsed)
    anomalies = detect_anomalies(parsed, temp_events)

    # 4. 스니펫 추출
    snippets = [extract_snippet(lines, a.line_index) for a in anomalies]

    # 5. LLM 분석 (병렬)
    explanations = await asyncio.gather(*[
        llm_explain_anomaly(a, s, summary.dict())
        for a, s in zip(anomalies, snippets)
    ])

    # 6. 수정 전략 (필요시)
    strategies = await asyncio.gather(*[
        llm_suggest_strategy(a, s)
        for a, s in zip(anomalies, snippets)
    ])

    return AnalysisResult(
        summary=summary,
        anomalies=anomalies,
        explanations=explanations,
        strategies=strategies
    )
```

#### 산출물
- [ ] `gcode_analyzer/workflow/graph.py`
- [ ] `gcode_analyzer/workflow/nodes.py`
- [ ] `gcode_analyzer/analyzer.py`

---

### 8단계: API 엔드포인트 설계

#### 8-1. FastAPI 라우터

**파일:** `gcode_analyzer/api/routes.py`

```python
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/gcode", tags=["gcode"])

@router.post("/analyze")
async def analyze_gcode_endpoint(file: UploadFile = File(...)):
    """G-code 파일 분석"""
    pass

@router.post("/analyze/stream")
async def analyze_gcode_stream(file: UploadFile = File(...)):
    """스트리밍으로 분석 진행 상황 전달 (SSE)"""
    pass

@router.post("/patch")
async def apply_patch(
    file: UploadFile = File(...),
    anomaly_ids: list[str] = []
):
    """선택한 이상에 대해 패치 적용"""
    pass

@router.get("/download/{job_id}")
async def download_patched_gcode(job_id: str):
    """패치된 G-code 다운로드"""
    pass
```

#### 8-2. SSE 이벤트 구조

```python
class TimelineEvent(BaseModel):
    step: int
    label: str
    status: str  # pending, running, done, error
    data: dict | None = None
    timestamp: datetime

# SSE 이벤트 예시
[
    {"step": 1, "label": "G-code 파싱", "status": "done"},
    {"step": 2, "label": "온도 이벤트 분석 (14개)", "status": "done"},
    {"step": 3, "label": "이상 2개 감지", "status": "done"},
    {"step": 4, "label": "Claude 분석 요청", "status": "running"},
    {"step": 5, "label": "수정 전략 생성", "status": "pending"}
]
```

#### 산출물
- [ ] `gcode_analyzer/api/routes.py`
- [ ] `gcode_analyzer/api/schemas.py`
- [ ] `gcode_analyzer/api/sse.py`

---

### 9단계: UI/UX 설계

#### 9-1. 페이지 구성

| 페이지 | 설명 |
|--------|------|
| Upload | 파일 드롭존, 분석 시작 버튼 |
| Result | 요약 카드, 이상 목록, 상세 패널 |
| Patch Preview | Diff 뷰, 다운로드 버튼 |

#### 9-2. 컴포넌트 구조

```
src/
├── pages/
│   ├── GCodeUpload.tsx
│   ├── GCodeResult.tsx
│   └── GCodePatchPreview.tsx
├── components/
│   ├── gcode/
│   │   ├── UploadDropzone.tsx
│   │   ├── SummaryCard.tsx
│   │   ├── AnomalyTable.tsx
│   │   ├── SnippetViewer.tsx      # 하이라이트 지원
│   │   ├── TimelineProgress.tsx
│   │   └── DiffViewer.tsx
│   └── common/
│       ├── SeverityBadge.tsx
│       └── LoadingSpinner.tsx
└── hooks/
    ├── useGCodeAnalysis.ts
    └── useSSE.ts
```

#### 9-3. 타임라인 UI

```tsx
// TimelineProgress.tsx
interface TimelineStep {
  step: number;
  label: string;
  status: 'pending' | 'running' | 'done' | 'error';
}

const TimelineProgress: React.FC<{ steps: TimelineStep[] }> = ({ steps }) => {
  return (
    <div className="timeline">
      {steps.map((s) => (
        <div key={s.step} className={`timeline-item ${s.status}`}>
          <StatusIcon status={s.status} />
          <span>{s.label}</span>
        </div>
      ))}
    </div>
  );
};
```

#### 산출물
- [ ] UI 컴포넌트 명세
- [ ] Figma/디자인 시안 (선택)

---

### 10단계: 테스트 & 안전장치

#### 10-1. 테스트 케이스

| 구분 | 설명 |
|------|------|
| 정상 | 문제없는 G-code |
| 조기 온도 OFF | 중간에 M104 S0 포함 |
| 콜드 익스트루전 | 온도 0°C에서 E값 증가 |
| 복합 이상 | 여러 이상 동시 발생 |

#### 10-2. 안전장치

```python
# gcode_analyzer/safety.py

class SafetyChecker:
    """패치 전 안전성 검증"""

    def validate_patch(self, original: list[str], patched: list[str]) -> bool:
        """패치된 G-code 검증"""
        # 1. 시작/종료 코드 보존 확인
        # 2. 필수 명령어 존재 확인
        # 3. 온도 설정 적정성 확인
        pass

    def get_warning_labels(self) -> list[str]:
        """경고 라벨 생성"""
        return [
            "이 G-code는 자동 수정되었습니다.",
            "프린터에 보내기 전 반드시 검토하세요.",
            "G-code 시뮬레이터로 미리 확인을 권장합니다."
        ]
```

#### 산출물
- [ ] `tests/test_parser.py`
- [ ] `tests/test_anomaly_detector.py`
- [ ] `tests/test_patcher.py`
- [ ] `tests/fixtures/` (테스트용 G-code 파일)

---

### 11단계: FACTOR 연동 (확장)

#### 11-1. 연동 포인트

```python
# FACTOR 서버에서 출력 전 자동 검사
@router.post("/print/start")
async def start_print(print_job: PrintJob):
    # G-code 검사
    result = await analyze_gcode(print_job.gcode_path)

    if result.has_critical_anomaly():
        # 대시보드 알림
        await notify_dashboard(print_job.user_id, result)

        # Slack/카톡 알림
        await send_notification(
            channel="slack",
            message=f"G-code 이상 감지: {result.summary}"
        )

        return {"status": "warning", "anomalies": result.anomalies}

    # 정상 진행
    return {"status": "ok"}
```

#### 11-2. 향후 확장

- 실시간 모니터링 중 이상 감지 시 자동 일시정지
- 히스토리 분석으로 반복 패턴 학습
- 사용자 피드백 기반 규칙 개선

---

## 프로젝트 구조

```
gcode_analyzer/
├── __init__.py
├── parser.py              # G-code 파싱
├── summary.py             # 요약 정보 추출
├── temp_tracker.py        # 온도 이벤트 추적
├── anomaly_detector.py    # 이상 탐지
├── snippet_extractor.py   # 스니펫 추출
├── patcher.py             # G-code 패치
├── safety.py              # 안전성 검증
├── analyzer.py            # 통합 분석기
├── cli.py                 # CLI 도구
│
├── rules/                 # 개별 탐지 규칙
│   ├── __init__.py
│   ├── cold_extrusion.py
│   ├── early_temp_off.py
│   └── ...
│
├── llm/                   # LLM 통합
│   ├── __init__.py
│   ├── client.py
│   ├── explain.py
│   ├── strategy.py
│   └── prompts/
│       ├── explain.txt
│       └── strategy.txt
│
├── workflow/              # LangGraph 워크플로우
│   ├── __init__.py
│   ├── graph.py
│   └── nodes.py
│
├── api/                   # FastAPI 엔드포인트
│   ├── __init__.py
│   ├── routes.py
│   ├── schemas.py
│   └── sse.py
│
└── models/                # Pydantic 모델
    ├── __init__.py
    ├── gcode.py
    ├── anomaly.py
    └── analysis.py

tests/
├── __init__.py
├── test_parser.py
├── test_anomaly_detector.py
├── test_patcher.py
├── test_integration.py
└── fixtures/
    ├── normal.gcode
    ├── cold_extrusion.gcode
    └── early_temp_off.gcode
```

---

## 의존성

```txt
# requirements.txt
fastapi>=0.104.0
uvicorn>=0.24.0
pydantic>=2.0.0
python-multipart>=0.0.6

# LangChain & LangGraph
langchain>=0.1.0
langchain-anthropic>=0.1.0
langgraph>=0.0.20

# 유틸리티
aiofiles>=23.2.0
python-dotenv>=1.0.0

# 테스트
pytest>=7.4.0
pytest-asyncio>=0.21.0
httpx>=0.25.0
```

---

## 환경 변수

```env
# .env
ANTHROPIC_API_KEY=sk-ant-xxx
CLAUDE_MODEL=claude-sonnet-4-20250514

# Optional
LOG_LEVEL=INFO
MAX_GCODE_SIZE_MB=50
```

---

## 개발 우선순위 (권장)

1. **Phase 1 (Core):** 2-3단계
   - G-code 파서 & 요약기
   - 이상 패턴 탐지 룰 엔진

2. **Phase 2 (LLM):** 4-6단계
   - 스니펫 추출
   - Claude 통합 (분석/설명)
   - 수정 전략 제안

3. **Phase 3 (Integration):** 7-8단계
   - LangGraph 워크플로우
   - FastAPI 엔드포인트

4. **Phase 4 (UI):** 9단계
   - React 프론트엔드
   - 타임라인 UI

5. **Phase 5 (Production):** 10-11단계
   - 테스트 & 안전장치
   - FACTOR 연동

---

## 참고 사항

- LLM은 **분석/설명** 용도로만 사용, G-code 직접 수정은 **규칙 기반 코드**로
- 토큰 절약을 위해 전체 G-code가 아닌 **스니펫만** LLM에 전달
- 패치된 G-code는 반드시 **시뮬레이터 검증** 권장
- 프린터에 보내기 전 **사용자 확인** 필수
