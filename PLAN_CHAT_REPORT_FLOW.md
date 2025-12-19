# Chat API 통합 리포트 흐름 구현 계획

## 현재 상황 분석

### 기존 흐름 (2번 요청 문제)
```
웹 클라이언트
    │
    ├─1→ POST /api/v1/chat (챗봇 메시지)
    │     └─ 200 OK
    │
    ├─2→ POST /api/v1/gcode/analyze-with-segments (G-code 분석)
    │     └─ segments + analysis_id 반환
    │
    ├─3→ GET /api/v1/gcode/analysis/{id}/stream (SSE 연결)
    │     └─ 진행률 스트리밍
    │
    └─4→ GET /api/v1/gcode/analysis/{id} (최종 결과)
          └─ 분석 결과 반환
```

**문제점:**
- `/api/v1/chat`과 `/api/v1/gcode/analyze-with-segments` 두 번 요청
- 클라이언트가 별도로 G-code API를 호출해야 함
- 일관성 없는 응답 형식

### 목표 흐름 (Chat API 통합)
```
웹 클라이언트
    │
    ├─1→ POST /api/v1/chat (G-code 파일 첨부)
    │     └─ { analysis_id, segments, stream_url } 반환
    │
    ├─2→ GET /api/v1/gcode/analysis/{id}/stream (SSE 연결)
    │     └─ 진행률 스트리밍
    │
    └─3→ GET /api/v1/gcode/analysis/{id} (최종 결과)
          └─ 분석 결과 반환
```

---

## 현재 코드 구조 분석

### 1. Chat API 엔드포인트 (`/api/v1/chat`)
**위치:** `gcode_analyzer/chat/router.py`

```python
class ChatRequest:
    user_id: str
    message: str
    attachments: Optional[List[Attachment]]  # gcode, image, stl, text
    selected_tool: Optional[str]  # troubleshoot, gcode, modelling
    printer_info: Optional[Dict]
    filament_type: Optional[str]
    language: str = "ko"
```

**현재 처리 흐름:**
1. Intent 분류 → `IntentClassifier`
2. Tool 디스패치 → `ToolDispatcher`
3. 응답 생성 → `ResponseGenerator`

### 2. G-code 분석 엔드포인트 (`/api/v1/gcode/analyze-with-segments`)
**위치:** `gcode_analyzer/api/router.py`

**현재 처리 흐름:**
1. G-code 파싱 및 세그먼트 추출 (즉시 반환)
2. 백그라운드 LLM 분석 시작
3. SSE 스트림 URL 제공

### 3. Tool Dispatcher
**위치:** `gcode_analyzer/chat/dispatcher.py`

현재 `GCODE_ANALYSIS` intent 처리:
- `/analyze-with-segments` 또는 `/summary` API 호출
- 결과를 `ToolResult`로 변환

---

## 구현 계획

### Phase 1: Tool Dispatcher 수정

**파일:** `gcode_analyzer/chat/dispatcher.py`

#### 변경 사항:
1. G-code 분석 시 외부 API 호출 대신 내부 함수 직접 호출
2. 세그먼트 추출 + 백그라운드 분석 통합
3. SSE 스트림 URL 포함하여 반환

```python
# 수정 전 (외부 API 호출)
async def _handle_gcode_analysis(self, request: ChatRequest) -> ToolResult:
    response = await httpx.post("/api/v1/gcode/analyze-with-segments", ...)
    return ToolResult(data=response.json())

# 수정 후 (내부 함수 직접 호출)
async def _handle_gcode_analysis(self, request: ChatRequest) -> ToolResult:
    from gcode_analyzer.api.router import process_gcode_analysis_internal

    result = await process_gcode_analysis_internal(
        gcode_content=request.attachments[0].content,
        printer_info=request.printer_info,
        filament_type=request.filament_type,
        language=request.language
    )

    return ToolResult(
        tool_name="gcode_analysis",
        success=True,
        data={
            "analysis_id": result.analysis_id,
            "segments": result.segments,
            "stream_url": f"/api/v1/gcode/analysis/{result.analysis_id}/stream",
            "status": "segments_ready"
        }
    )
```

### Phase 2: 내부 처리 함수 분리

**파일:** `gcode_analyzer/api/router.py`

#### 새 함수 추가:
```python
async def process_gcode_analysis_internal(
    gcode_content: str,
    printer_info: Optional[PrinterInfo] = None,
    filament_type: Optional[str] = None,
    user_id: Optional[str] = None,
    language: str = "ko"
) -> GCodeAnalysisInternalResult:
    """
    Chat API에서 직접 호출하는 내부 함수
    - 세그먼트 추출
    - 백그라운드 분석 시작
    - analysis_id 및 stream_url 반환
    """
    analysis_id = str(uuid.uuid4())

    # 1. 세그먼트 추출 (동기)
    segments = await extract_segments(gcode_content)

    # 2. 초기 상태 저장
    await set_analysis(analysis_id, {
        "status": "segments_ready",
        "progress": 0.2,
        "segments": segments
    })

    # 3. 백그라운드 분석 시작
    asyncio.create_task(
        run_gcode_analysis_task(analysis_id, gcode_content, ...)
    )

    return GCodeAnalysisInternalResult(
        analysis_id=analysis_id,
        segments=segments,
        stream_url=f"/api/v1/gcode/analysis/{analysis_id}/stream"
    )
```

### Phase 3: ChatResponse 모델 확장

**파일:** `gcode_analyzer/chat/models.py`

```python
class ToolResult(BaseModel):
    tool_name: str
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # 새 필드 추가
    analysis_id: Optional[str] = None  # G-code 분석용
    stream_url: Optional[str] = None   # SSE 스트림 URL
    segments: Optional[Dict] = None    # 세그먼트 데이터

class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    intent: ChatIntent
    response: str
    tool_result: Optional[ToolResult]
    suggested_actions: List[SuggestedAction]

    # G-code 분석 전용 필드 (tool_result에도 있지만 편의를 위해)
    analysis_id: Optional[str] = None
    stream_url: Optional[str] = None
```

### Phase 4: Response Generator 수정

**파일:** `gcode_analyzer/chat/response_generator.py`

G-code 분석 응답 생성 시:
```python
def generate_gcode_analysis_response(tool_result: ToolResult) -> str:
    if tool_result.data.get("status") == "segments_ready":
        return (
            "G-code 파일 분석을 시작했습니다.\n"
            f"총 {tool_result.data['segments']['metadata']['layerCount']}개 레이어를 감지했습니다.\n"
            "상세 분석이 백그라운드에서 진행 중입니다."
        )
```

---

## 웹 클라이언트 요청 흐름

### Step 1: Chat API 요청 (G-code 분석)

```javascript
// POST /api/v1/chat
const response = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        user_id: 'user-123',
        message: 'G-code 분석해줘',
        attachments: [{
            type: 'gcode',
            content: gcodeFileContent,  // G-code 파일 내용
            filename: 'model.gcode'
        }],
        selected_tool: 'gcode',  // 명시적 도구 선택 (선택사항)
        printer_info: {
            manufacturer: 'Bambu Lab',
            model: 'X1 Carbon'
        },
        filament_type: 'PLA',
        language: 'ko'
    })
});

const result = await response.json();
// result 구조:
// {
//     conversation_id: "conv-xxx",
//     message_id: "msg-xxx",
//     intent: "gcode_analysis",
//     response: "G-code 파일 분석을 시작했습니다...",
//     tool_result: {
//         tool_name: "gcode_analysis",
//         success: true,
//         data: {
//             analysis_id: "cec7161d-92d6-4ee1-b4df-e5a2e56a71b2",
//             status: "segments_ready",
//             segments: { layers: [...], metadata: {...} },
//             stream_url: "/api/v1/gcode/analysis/cec7161d.../stream"
//         }
//     },
//     analysis_id: "cec7161d-92d6-4ee1-b4df-e5a2e56a71b2",
//     stream_url: "/api/v1/gcode/analysis/cec7161d.../stream"
// }
```

### Step 2: 세그먼트 렌더링 (즉시)

```javascript
// Step 1 응답에서 세그먼트 데이터 추출
const { segments, analysis_id, stream_url } = result.tool_result.data;

// Three.js로 3D 뷰어에 세그먼트 렌더링
renderGCodeSegments(segments);
```

### Step 3: SSE 스트림 연결 (진행률)

```javascript
const eventSource = new EventSource(stream_url);

eventSource.addEventListener('progress', (event) => {
    const data = JSON.parse(event.data);
    // { progress: 0.45, step: "llm_analyze", message: "이슈 분석 중..." }
    updateProgressBar(data.progress);
    updateStatusMessage(data.message);
});

eventSource.addEventListener('timeline', (event) => {
    const data = JSON.parse(event.data);
    // { step: 1, label: "파싱 완료", status: "done" }
    addTimelineItem(data);
});

eventSource.addEventListener('complete', (event) => {
    const result = JSON.parse(event.data);
    eventSource.close();
    displayAnalysisResult(result);
});

eventSource.addEventListener('error', (event) => {
    const error = JSON.parse(event.data);
    eventSource.close();
    showError(error.message);
});
```

### Step 4: 최종 결과 조회 (선택사항)

SSE `complete` 이벤트로 결과를 받지만, 필요시 직접 조회 가능:

```javascript
const analysisResult = await fetch(`/api/v1/gcode/analysis/${analysis_id}`);
const data = await analysisResult.json();
// 전체 분석 결과
```

---

## 전체 시퀀스 다이어그램

```
┌─────────┐          ┌──────────────┐          ┌──────────────┐          ┌────────────┐
│   Web   │          │  Chat API    │          │ G-code API   │          │ File Store │
│ Client  │          │ /api/v1/chat │          │ (Internal)   │          │            │
└────┬────┘          └──────┬───────┘          └──────┬───────┘          └─────┬──────┘
     │                      │                         │                        │
     │  POST /api/v1/chat   │                         │                        │
     │  (G-code 첨부)       │                         │                        │
     │─────────────────────>│                         │                        │
     │                      │                         │                        │
     │                      │  Intent: GCODE_ANALYSIS │                        │
     │                      │─────────────────────────│                        │
     │                      │                         │                        │
     │                      │  process_gcode_internal │                        │
     │                      │────────────────────────>│                        │
     │                      │                         │                        │
     │                      │                         │  세그먼트 추출          │
     │                      │                         │  (동기 처리)           │
     │                      │                         │                        │
     │                      │                         │  set_analysis()        │
     │                      │                         │───────────────────────>│
     │                      │                         │                        │
     │                      │                         │  백그라운드 분석 시작   │
     │                      │                         │  (asyncio.create_task) │
     │                      │                         │                        │
     │                      │  { analysis_id,         │                        │
     │                      │    segments,            │                        │
     │                      │    stream_url }         │                        │
     │                      │<────────────────────────│                        │
     │                      │                         │                        │
     │  ChatResponse        │                         │                        │
     │  { analysis_id,      │                         │                        │
     │    segments,         │                         │                        │
     │    stream_url,       │                         │                        │
     │    response: "분석 시작..." }                   │                        │
     │<─────────────────────│                         │                        │
     │                      │                         │                        │
     │  세그먼트 렌더링     │                         │                        │
     │  (즉시 3D 표시)      │                         │                        │
     │                      │                         │                        │
     │  GET /stream (SSE)   │                         │                        │
     │─────────────────────────────────────────────────────────────────────────>│
     │                      │                         │                        │
     │                      │                         │  백그라운드 분석 진행   │
     │                      │                         │  update_analysis()     │
     │                      │                         │───────────────────────>│
     │                      │                         │                        │
     │  event: progress     │                         │                        │
     │  { progress: 0.45 }  │                         │                        │
     │<─────────────────────────────────────────────────────────────────────────│
     │                      │                         │                        │
     │  event: timeline     │                         │                        │
     │  { step: 2 }         │                         │                        │
     │<─────────────────────────────────────────────────────────────────────────│
     │                      │                         │                        │
     │  ...                 │                         │                        │
     │                      │                         │                        │
     │  event: complete     │                         │                        │
     │  { result: {...} }   │                         │                        │
     │<─────────────────────────────────────────────────────────────────────────│
     │                      │                         │                        │
     │  결과 표시           │                         │                        │
     │                      │                         │                        │
```

---

## 수정이 필요한 파일 목록

| 파일 | 수정 내용 |
|------|-----------|
| `gcode_analyzer/chat/dispatcher.py` | G-code 분석 내부 함수 직접 호출 |
| `gcode_analyzer/chat/models.py` | `ToolResult`, `ChatResponse` 필드 추가 |
| `gcode_analyzer/chat/response_generator.py` | G-code 분석 응답 메시지 생성 |
| `gcode_analyzer/api/router.py` | `process_gcode_analysis_internal()` 함수 추가 |

---

## 추가 고려사항

### 1. 대용량 G-code 파일 처리
- 현재 `attachments.content`에 전체 파일 내용 포함
- 대용량 파일은 multipart/form-data로 별도 업로드 고려
- 또는 파일 URL 참조 방식 사용

### 2. 에러 처리
```javascript
// Chat API 에러 응답
{
    "conversation_id": "conv-xxx",
    "intent": "gcode_analysis",
    "response": "G-code 파일 분석 중 오류가 발생했습니다.",
    "tool_result": {
        "success": false,
        "error": "Invalid G-code format"
    }
}
```

### 3. 분석 취소 기능
```javascript
// 분석 취소 (선택사항)
await fetch(`/api/v1/gcode/analysis/${analysis_id}/cancel`, { method: 'POST' });
```

### 4. Rate Limiting
- Chat API에서 기존 Rate Limiter 재사용
- 사용자별/서버별 제한 유지

---

## 테스트 계획

1. **단위 테스트**
   - `process_gcode_analysis_internal()` 함수
   - Intent 분류 정확도
   - ToolResult 직렬화

2. **통합 테스트**
   - Chat API → 세그먼트 반환 → SSE 스트림 → 최종 결과
   - 에러 케이스 (잘못된 G-code, 타임아웃)

3. **성능 테스트**
   - 대용량 G-code (100MB+) 처리
   - 동시 요청 처리

---

## 마이그레이션 가이드

### 기존 클라이언트 (변경 전)
```javascript
// 1. Chat API 호출
await fetch('/api/v1/chat', { ... });

// 2. 별도로 G-code API 호출
const analysis = await fetch('/api/v1/gcode/analyze-with-segments', { ... });
const { analysis_id } = await analysis.json();

// 3. SSE 연결
new EventSource(`/api/v1/gcode/analysis/${analysis_id}/stream`);
```

### 새 클라이언트 (변경 후)
```javascript
// 1. Chat API만 호출 (G-code 첨부)
const result = await fetch('/api/v1/chat', {
    body: JSON.stringify({
        message: 'G-code 분석해줘',
        attachments: [{ type: 'gcode', content: gcodeContent }]
    })
});
const { analysis_id, stream_url, tool_result } = await result.json();

// 2. 세그먼트 즉시 렌더링
renderSegments(tool_result.data.segments);

// 3. SSE 연결 (동일)
new EventSource(stream_url);
```

---

## 요약

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| API 요청 수 | 2회 (chat + analyze) | 1회 (chat만) |
| 세그먼트 반환 | analyze API 응답 | chat API 응답 |
| SSE URL | analyze API 응답 | chat API 응답 |
| 진행률 확인 | 동일 (SSE) | 동일 (SSE) |
| 최종 결과 | 동일 (GET) | 동일 (GET) |

이 계획을 통해 웹 클라이언트는 `/api/v1/chat` 단일 엔드포인트만 사용하여 G-code 분석을 요청하고, 기존과 동일한 진행률 추적 및 결과 조회 기능을 유지할 수 있습니다.

---

## ✅ 구현 완료 (2024-12-18)

### 수정된 파일

| 파일 | 변경 내용 |
|------|-----------|
| `gcode_analyzer/api/router.py` | `process_gcode_analysis_internal()` 내부 함수 추가 |
| `gcode_analyzer/chat/models.py` | `ToolResult`, `ChatResponse`에 `analysis_id`, `stream_url`, `segments` 필드 추가 |
| `gcode_analyzer/chat/tool_dispatcher.py` | G-code 분석 시 내부 함수 직접 호출로 변경 |
| `gcode_analyzer/chat/response_generator.py` | 스트리밍 분석 응답 생성 메서드 추가 |
| `gcode_analyzer/chat/router.py` | ChatResponse에 `analysis_id`, `stream_url` 최상위 노출 |

### ChatResponse 구조 (G-code 분석 시)

```json
{
    "conversation_id": "conv_xxx",
    "message_id": "msg_xxx",
    "intent": "gcode_analysis",
    "confidence": 1.0,
    "response": "G-code 분석 시작! ...",
    "tool_result": {
        "tool_name": "gcode_analysis",
        "success": true,
        "data": {
            "analysis_id": "uuid-xxx",
            "status": "segments_ready",
            "segments": { "layers": [...], "metadata": {...} },
            "stream_url": "/api/v1/gcode/analysis/uuid-xxx/stream",
            "layer_count": 373,
            "filename": "model.gcode"
        },
        "analysis_id": "uuid-xxx",
        "stream_url": "/api/v1/gcode/analysis/uuid-xxx/stream",
        "segments": { ... }
    },
    "suggested_actions": [...],
    "analysis_id": "uuid-xxx",
    "stream_url": "/api/v1/gcode/analysis/uuid-xxx/stream"
}
```

### 웹 클라이언트 사용 예시

```javascript
// 1. Chat API 한 번만 요청
const response = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        user_id: 'user-123',
        message: 'G-code 분석해줘',
        attachments: [{
            type: 'gcode',
            content: btoa(gcodeFileContent),  // base64 인코딩
            filename: 'model.gcode'
        }]
    })
});

const result = await response.json();

// 2. 세그먼트 즉시 렌더링
const { segments, analysis_id, stream_url } = result;
renderGCodeSegments(segments || result.tool_result?.segments);

// 3. SSE 연결 (기존과 동일)
const eventSource = new EventSource(stream_url || result.tool_result?.data?.stream_url);

eventSource.addEventListener('progress', (e) => {
    const data = JSON.parse(e.data);
    updateProgressBar(data.progress);
});

eventSource.addEventListener('complete', (e) => {
    const finalResult = JSON.parse(e.data);
    displayAnalysisResult(finalResult);
    eventSource.close();
});
```
