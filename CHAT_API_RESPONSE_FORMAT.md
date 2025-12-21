# Chat API Response Format

## API Endpoint

```
POST /api/v1/chat
```

---

## Request Format

```json
{
  "user_id": "test_user_123",
  "user_plan": "free",
  "message": "이 G-code 파일 분석해줘",
  "conversation_id": null,
  "conversation_history": null,
  "attachments": [
    {
      "type": "gcode",
      "content": "<base64 encoded gcode file>",
      "filename": "snowman.gcode",
      "mime_type": null
    }
  ],
  "selected_tool": null,
  "selected_model": null,
  "printer_info": null,
  "filament_type": null,
  "analysis_id": null,
  "issue_to_resolve": null,
  "language": "ko"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | ✅ | 사용자 ID (비로그인 시 프론트에서 `anon_xxx` 생성) |
| `user_plan` | string | ❌ | 사용자 플랜 (`free`, `starter`, `pro`, `enterprise`) |
| `message` | string | ✅ | 사용자 메시지 |
| `conversation_id` | string | ❌ | 대화 세션 ID (없으면 자동 생성) |
| `conversation_history` | array | ❌ | 이전 대화 히스토리 |
| `attachments` | array | ❌ | 첨부 파일 목록 |
| `selected_tool` | string | ❌ | UI에서 선택한 도구 (`troubleshoot`, `gcode`, `modelling`, `resolve_issue`) |
| `selected_model` | string | ❌ | UI에서 선택한 LLM 모델 |
| `printer_info` | object | ❌ | 프린터 정보 |
| `filament_type` | string | ❌ | 필라멘트 타입 |
| `analysis_id` | string | ❌ | G-code 분석 ID (이슈 해결 시 필요) |
| `issue_to_resolve` | object | ❌ | 해결할 이슈 정보 |
| `language` | string | ❌ | 응답 언어 (기본값: `ko`) |

### Attachment Types

| Type | Description |
|------|-------------|
| `gcode` | G-code 파일 (.gcode) |
| `image` | 이미지 파일 (jpg, png, webp) |
| `stl` | STL 3D 모델 파일 (.stl) |
| `text` | 텍스트 파일 |

---

## Response Format (G-code 분석)

```json
{
  "conversation_id": "conv_a1b2c3d4e5f6",
  "message_id": "msg_x1y2z3w4v5u6",
  "timestamp": "2024-12-20T15:30:00.000000",
  "intent": "gcode_analysis",
  "confidence": 1.0,
  "response": "**G-code 분석 시작!**\n\n**파일:** snowman.gcode\n**상태:** 세그먼트 추출 완료, LLM 분석 진행 중...\n\n**감지된 정보:**\n- 총 레이어: **998개**\n- 압출 경로: 1,234,567개\n- 이동 경로: 567,890개\n\n3D 뷰어에서 레이어를 확인할 수 있습니다.\n상세 분석이 완료되면 품질 점수와 이슈를 알려드릴게요!",
  "tool_result": {
    "tool_name": "gcode_analysis",
    "success": true,
    "data": {
      "analysis_id": "432fd5d1-a508-4f39-89f9-2e9848059072",
      "status": "segments_ready",
      "segments": {
        "layers": [
          {
            "layerNum": 0,
            "z": 0.3,
            "extrusionData": "<base64 encoded Float32Array>",
            "travelData": "<base64 encoded Float32Array>",
            "extrusionCount": 1234,
            "travelCount": 567
          },
          {
            "layerNum": 1,
            "z": 0.4,
            "extrusionData": "<base64 encoded Float32Array>",
            "travelData": "<base64 encoded Float32Array>",
            "extrusionCount": 2345,
            "travelCount": 678
          }
        ],
        "metadata": {
          "totalLayers": 998,
          "minZ": 0.3,
          "maxZ": 99.8,
          "bounds": {
            "minX": 83.873,
            "maxX": 145.321,
            "minY": 73.765,
            "maxY": 125.741
          }
        }
      },
      "layer_count": 998,
      "filename": "snowman.gcode",
      "message": "세그먼트 추출 완료. 998개 레이어를 감지했습니다. LLM 분석이 백그라운드에서 진행됩니다."
    },
    "error": null,
    "analysis_id": "432fd5d1-a508-4f39-89f9-2e9848059072",
    "segments": {
      "layers": [...],
      "metadata": {...}
    }
  },
  "suggested_actions": [
    {
      "label": "분석 상태 확인",
      "action": "check_status",
      "data": {
        "analysis_id": "432fd5d1-a508-4f39-89f9-2e9848059072"
      }
    },
    {
      "label": "레이어 탐색",
      "action": "explore_layers",
      "data": {
        "analysis_id": "432fd5d1-a508-4f39-89f9-2e9848059072"
      }
    }
  ],
  "token_usage": {
    "intent_classification": 0,
    "tool_execution": 0,
    "response_generation": 0,
    "total": 0
  },
  "analysis_id": "432fd5d1-a508-4f39-89f9-2e9848059072"
}
```

---

## Response Fields

### Top Level

| Field | Type | Description |
|-------|------|-------------|
| `conversation_id` | string | 대화 세션 ID |
| `message_id` | string | 메시지 ID |
| `timestamp` | datetime | 응답 타임스탬프 |
| `intent` | string | 감지된 의도 |
| `confidence` | float | 의도 확신도 (0.0 ~ 1.0) |
| `response` | string | AI 응답 텍스트 (Markdown 형식) |
| `tool_result` | object | 도구 실행 결과 |
| `suggested_actions` | array | 추천 액션 목록 |
| `token_usage` | object | 토큰 사용량 |
| `analysis_id` | string | G-code 분석 ID (최상위 레벨 - 편의용) |

### Intent Types

| Intent | Description |
|--------|-------------|
| `gcode_analysis` | G-code 파일 분석 |
| `gcode_general` | G-code 일반 질문 |
| `gcode_issue_resolve` | G-code 이슈 해결 |
| `troubleshoot` | 프린터 문제 진단 |
| `modelling_text` | Text-to-3D 요청 |
| `modelling_image` | Image-to-3D 요청 |
| `general_question` | 3D 프린팅 관련 질문 |
| `greeting` | 인사 |
| `help` | 도움말 요청 |
| `follow_up` | 이전 대화 후속 질문 |
| `clarification` | 추가 정보 제공 |

### tool_result (G-code 분석)

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | string | 사용된 도구명 (`gcode_analysis`) |
| `success` | boolean | 성공 여부 |
| `data` | object | 결과 데이터 |
| `error` | string | 에러 메시지 (실패 시) |
| `analysis_id` | string | G-code 분석 ID |
| `segments` | object | G-code 세그먼트 데이터 |

### data (G-code 분석 결과)

| Field | Type | Description |
|-------|------|-------------|
| `analysis_id` | string | 분석 ID |
| `status` | string | 상태 (`segments_ready`) |
| `segments` | object | 세그먼트 데이터 |
| `layer_count` | integer | 총 레이어 수 |
| `filename` | string | 파일명 |
| `message` | string | 상태 메시지 |

### segments

| Field | Type | Description |
|-------|------|-------------|
| `layers` | array | 레이어별 데이터 |
| `metadata` | object | 메타데이터 |

### layers[i] (레이어 데이터)

| Field | Type | Description |
|-------|------|-------------|
| `layerNum` | integer | 레이어 번호 (0부터 시작) |
| `z` | float | Z 높이 (mm) |
| `extrusionData` | string | 압출 경로 데이터 (Base64 인코딩된 Float32Array) |
| `travelData` | string | 이동 경로 데이터 (Base64 인코딩된 Float32Array) |
| `extrusionCount` | integer | 압출 경로 점 개수 |
| `travelCount` | integer | 이동 경로 점 개수 |

### metadata

| Field | Type | Description |
|-------|------|-------------|
| `totalLayers` | integer | 총 레이어 수 |
| `minZ` | float | 최소 Z 높이 |
| `maxZ` | float | 최대 Z 높이 |
| `bounds` | object | XY 경계 (`minX`, `maxX`, `minY`, `maxY`) |

### suggested_actions[i]

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | 버튼 레이블 |
| `action` | string | 액션 ID |
| `data` | object | 액션 데이터 |

### token_usage

| Field | Type | Description |
|-------|------|-------------|
| `intent_classification` | integer | 의도 분류 토큰 |
| `tool_execution` | integer | 도구 실행 토큰 |
| `response_generation` | integer | 응답 생성 토큰 |
| `total` | integer | 총 토큰 |

---

## Segment Data Decoding (JavaScript)

```javascript
// Base64 → Float32Array 디코딩
function decodeSegmentData(base64String) {
  const binaryString = atob(base64String);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return new Float32Array(bytes.buffer);
}

// 사용 예시
const layer = response.tool_result.segments.layers[0];
const extrusionPoints = decodeSegmentData(layer.extrusionData);

// Float32Array 구조: [x1, y1, z1, x2, y2, z2, ...]
// 3개씩 묶어서 3D 좌표로 사용
for (let i = 0; i < extrusionPoints.length; i += 3) {
  const x = extrusionPoints[i];
  const y = extrusionPoints[i + 1];
  const z = extrusionPoints[i + 2];
  // 3D 렌더링에 사용
}
```

---

## 분석 상태 확인 (폴링)

LLM 분석 진행률을 확인하려면 폴링 API를 사용합니다.

### Endpoint

```
GET /api/v1/gcode/analysis/{analysis_id}
```

### Response

```json
{
  "analysis_id": "432fd5d1-a508-4f39-89f9-2e9848059072",
  "status": "running",
  "progress": 45,
  "current_step": "llm_analysis",
  "progress_message": "이슈 분석 중...",
  "timeline": [
    {
      "step": "segment_extraction",
      "status": "completed",
      "timestamp": "2024-12-20T15:30:00.000000"
    },
    {
      "step": "llm_analysis",
      "status": "running",
      "timestamp": "2024-12-20T15:30:05.000000"
    }
  ],
  "result": null,
  "error": null
}
```

### Status Values

| Status | Description |
|--------|-------------|
| `pending` | 대기 중 |
| `running` | 분석 진행 중 |
| `segments_ready` | 세그먼트 추출 완료 |
| `running_error_analysis` | 에러 분석 진행 중 |
| `summary_completed` | 요약 분석 완료 |
| `completed` | 전체 분석 완료 |
| `error` | 오류 발생 |

---

## 완료된 분석 결과

분석이 완료되면 (`status: "completed"`) `result` 필드에 전체 분석 결과가 포함됩니다.

```json
{
  "analysis_id": "432fd5d1-a508-4f39-89f9-2e9848059072",
  "status": "completed",
  "progress": 100,
  "result": {
    "summary": {
      "total_layers": 998,
      "print_time_estimate": "1h 51m",
      "filament_usage": "15.2m",
      "temperatures": {
        "nozzle": 205,
        "bed": 60
      }
    },
    "quality_score": 85,
    "issues": [
      {
        "type": "over_extrusion",
        "severity": "warning",
        "description": "일부 레이어에서 과압출이 감지되었습니다.",
        "affected_layers": [45, 46, 47],
        "suggestion": "압출 배율을 95%로 줄여보세요."
      }
    ],
    "expert_assessment": "이 G-code는 전반적으로 양호한 품질을 보입니다..."
  }
}
```

---

## Error Response

```json
{
  "detail": "G-code 파일 디코딩 실패: utf-8 decode error"
}
```

| HTTP Status | Description |
|-------------|-------------|
| 400 | 잘못된 요청 |
| 404 | 분석을 찾을 수 없음 |
| 429 | Rate Limit 초과 |
| 500 | 서버 오류 |
