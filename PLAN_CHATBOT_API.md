# 통합 챗봇 API 설계 계획

## 현재 구조 분석

### 기존 3가지 독립 API
| 기능 | 엔드포인트 | 용도 |
|------|-----------|------|
| G-code 분석 | `POST /api/v1/gcode/analyze` | G-code 파일 분석 |
| 프린터 문제 진단 | `POST /api/v1/troubleshoot/diagnose` | 이미지/텍스트 기반 진단 |
| 3D 모델링 | `POST /v1/process/modelling` | Text/Image → 3D |

### 웹 UI 통합 요구사항
- 사용자가 챗봇에 자연어로 질문
- AI가 의도를 파악하여 적절한 기능으로 라우팅
- 통합된 대화 흐름 유지

---

## 통합 챗봇 API 설계

### 1. 새 엔드포인트: `/api/v1/chat`

```
POST /api/v1/chat
```

### 2. Request 스키마

```python
class ChatRequest(BaseModel):
    # 사용자 정보
    user_id: str                          # 사용자 ID
    user_plan: UserPlan = UserPlan.FREE   # 플랜 (free, basic, pro, enterprise)

    # 메시지
    message: str                          # 사용자 메시지
    conversation_id: Optional[str]        # 대화 세션 ID (연속 대화용)

    # 첨부 파일
    attachments: Optional[List[Attachment]] = None

    # 설정
    language: str = "ko"                  # 응답 언어

class Attachment(BaseModel):
    type: AttachmentType                  # "gcode", "image", "stl", "text"
    content: str                          # base64 또는 파일 경로
    filename: Optional[str] = None
```

### 3. Response 스키마

```python
class ChatResponse(BaseModel):
    # 메타
    conversation_id: str                  # 대화 세션 ID
    message_id: str                       # 메시지 ID

    # 라우팅 결과
    intent: ChatIntent                    # 감지된 의도
    tool_used: Optional[str]              # 사용된 도구

    # 응답
    response: str                         # AI 응답 텍스트

    # 도구별 추가 데이터
    tool_result: Optional[Dict[str, Any]] = None

    # 후속 액션
    suggested_actions: List[SuggestedAction] = []

    # 토큰 사용량
    token_usage: TokenUsage
```

### 4. Intent 분류 (의도 파악)

```python
class ChatIntent(str, Enum):
    # 도구 사용
    GCODE_ANALYSIS = "gcode_analysis"       # G-code 분석 요청
    TROUBLESHOOT = "troubleshoot"           # 프린터 문제 진단
    MODELLING = "modelling"                 # 3D 모델링 요청

    # 일반 대화
    GENERAL_QUESTION = "general_question"   # 3D 프린팅 관련 질문
    GREETING = "greeting"                   # 인사
    HELP = "help"                           # 도움말 요청

    # 컨텍스트 기반
    FOLLOW_UP = "follow_up"                 # 이전 대화 후속 질문
    CLARIFICATION = "clarification"         # 추가 정보 요청에 대한 응답
```

---

## 아키텍처 설계

### 전체 흐름

```
[웹 UI]
    ↓ POST /api/v1/chat
[ChatRouter] ─────────────────────────────────────────┐
    ↓ Intent 분류 (LLM)                                │
    ↓                                                  │
┌───┴───┬─────────────┬─────────────┬────────────┐   │
│       │             │             │            │   │
▼       ▼             ▼             ▼            ▼   │
[G-code] [Troubleshoot] [Modelling] [General] [Help] │
분석기    진단기          생성기      Q&A       안내   │
    │         │             │          │         │   │
    └─────────┴─────────────┴──────────┴─────────┘   │
                          ↓                          │
                   [응답 생성기]                       │
                          ↓                          │
                   ChatResponse ─────────────────────┘
```

### 모듈 구조

```
gcode_analyzer/
├── chat/                          # 새로 추가
│   ├── __init__.py
│   ├── router.py                  # FastAPI 라우터
│   ├── models.py                  # Request/Response 모델
│   ├── intent_classifier.py       # 의도 분류기 (LLM)
│   ├── conversation_manager.py    # 대화 세션 관리
│   ├── tool_dispatcher.py         # 도구별 분기 처리
│   ├── response_generator.py      # 응답 생성
│   └── prompts/
│       ├── intent_classification.py
│       ├── general_qa.py
│       └── response_formatting.py
```

---

## 핵심 컴포넌트 설계

### 1. Intent Classifier (의도 분류기)

```python
class IntentClassifier:
    """
    LLM을 사용해 사용자 의도 분류

    입력 분석:
    - 메시지 텍스트
    - 첨부 파일 타입
    - 대화 히스토리

    출력:
    - intent: ChatIntent
    - confidence: float
    - extracted_params: Dict (필요한 파라미터 추출)
    """

    async def classify(
        self,
        message: str,
        attachments: List[Attachment],
        conversation_history: List[Message]
    ) -> IntentResult
```

**분류 로직:**
```
1. 첨부 파일 기반 (명확한 경우)
   - .gcode 파일 → GCODE_ANALYSIS
   - 이미지 + "문제" 키워드 → TROUBLESHOOT
   - .stl 파일 → 슬라이싱 관련

2. 키워드 기반 (빠른 분류)
   - "분석", "파싱", "G코드" → GCODE_ANALYSIS
   - "문제", "고장", "안돼" → TROUBLESHOOT
   - "만들어", "생성", "모델링" → MODELLING

3. LLM 기반 (복잡한 경우)
   - 자연어 의도 파악
   - 컨텍스트 기반 분류
```

### 2. Tool Dispatcher (도구 분배기)

```python
class ToolDispatcher:
    """
    Intent에 따라 적절한 도구로 라우팅
    """

    def __init__(self):
        self.tools = {
            ChatIntent.GCODE_ANALYSIS: GCodeAnalysisTool(),
            ChatIntent.TROUBLESHOOT: TroubleshootTool(),
            ChatIntent.MODELLING: ModellingTool(),
            ChatIntent.GENERAL_QUESTION: GeneralQATool(),
        }

    async def dispatch(
        self,
        intent: ChatIntent,
        message: str,
        attachments: List[Attachment],
        user_plan: UserPlan,
        extracted_params: Dict
    ) -> ToolResult
```

### 3. Conversation Manager (대화 관리자)

```python
class ConversationManager:
    """
    대화 세션 및 히스토리 관리

    기능:
    - 세션 생성/조회
    - 히스토리 저장 (Redis 또는 File)
    - 컨텍스트 유지 (이전 분석 결과 참조)
    """

    async def get_or_create_session(
        self,
        conversation_id: Optional[str],
        user_id: str
    ) -> ConversationSession

    async def add_message(
        self,
        session: ConversationSession,
        role: str,  # "user" | "assistant"
        content: str,
        tool_result: Optional[Dict] = None
    )

    async def get_context(
        self,
        session: ConversationSession,
        max_messages: int = 10
    ) -> List[Message]
```

### 4. Response Generator (응답 생성기)

```python
class ResponseGenerator:
    """
    도구 결과를 자연스러운 대화형 응답으로 변환
    """

    async def generate(
        self,
        intent: ChatIntent,
        tool_result: ToolResult,
        language: str,
        conversation_context: List[Message]
    ) -> str
```

---

## 도구별 상세 처리

### 1. G-code Analysis Tool

```python
class GCodeAnalysisTool:
    """기존 analyzer.py 래핑"""

    async def execute(
        self,
        attachments: List[Attachment],  # gcode 파일
        params: Dict,                   # filament_type, printer_info 등
        user_plan: UserPlan
    ) -> ToolResult:
        # 1. G-code 파일 추출
        # 2. analyzer.run_analysis() 호출
        # 3. 결과 요약
```

**응답 예시:**
```
G-code 분석이 완료되었습니다!

📊 기본 정보:
- 슬라이서: OrcaSlicer
- 예상 출력 시간: 2시간 37분
- 필라멘트 사용량: 24.5g

🔍 품질 점수: 85/100

⚠️ 발견된 이슈:
1. 첫 레이어 온도가 권장값보다 낮습니다 (200°C → 210°C 권장)
2. 리트랙션 거리가 짧습니다

수정된 G-code를 다운로드하시겠습니까?
```

### 2. Troubleshoot Tool

```python
class TroubleshootTool:
    """기존 troubleshoot 모듈 래핑"""

    async def execute(
        self,
        message: str,                   # 증상 설명
        attachments: List[Attachment],  # 문제 이미지
        params: Dict,                   # manufacturer, model 등
        user_plan: UserPlan
    ) -> ToolResult:
        # 1. 이미지 분석 (있는 경우)
        # 2. 웹 검색 (플랜에 따라 분기)
        # 3. 솔루션 생성
```

**응답 예시:**
```
이미지와 설명을 분석한 결과, **첫 레이어 접착 불량** 문제로 보입니다.

🔧 추천 해결 방법:

1. 베드 레벨링 재조정
   - 프린터를 예열 (베드 60°C, 노즐 200°C)
   - 종이 테스트로 Z 높이 확인

2. 베드 청소
   - IPA로 베드 표면 닦기
   - 기름기 제거

3. 첫 레이어 설정 조정
   - 속도: 20-25mm/s로 낮춤
   - 온도: 베드 65°C로 상향

📚 참고 자료:
- [Creality 공식 가이드](https://...)
- [Reddit 토론](https://...)

추가로 궁금한 점이 있으신가요?
```

### 3. Modelling Tool

```python
class ModellingTool:
    """기존 modelling_api 래핑"""

    async def execute(
        self,
        message: str,                   # 프롬프트 또는 설명
        attachments: List[Attachment],  # 참조 이미지 (선택)
        params: Dict,
        user_plan: UserPlan
    ) -> ToolResult:
        # 1. Text-to-3D 또는 Image-to-3D 결정
        # 2. Meshy API 호출
        # 3. 결과 반환 (task_id, 진행 상황)
```

**응답 예시:**
```
3D 모델 생성을 시작했습니다! 🎨

입력: "귀여운 고양이 피규어"

⏳ 진행 상황: 생성 중... (약 2-3분 소요)

완료되면 알려드릴게요!

[진행률: ████████░░ 80%]
```

### 4. General QA Tool

```python
class GeneralQATool:
    """3D 프린팅 관련 일반 질문 답변"""

    async def execute(
        self,
        message: str,
        conversation_context: List[Message],
        user_plan: UserPlan
    ) -> ToolResult:
        # 1. RAG 또는 웹 검색으로 정보 수집
        # 2. LLM으로 답변 생성
```

---

## 구현 우선순위

### Phase 1: 기본 구조 (1주차)
1. [ ] `chat/` 모듈 구조 생성
2. [ ] Request/Response 모델 정의
3. [ ] Intent Classifier 구현 (키워드 + LLM)
4. [ ] 기본 라우터 설정

### Phase 2: 도구 통합 (2주차)
1. [ ] GCodeAnalysisTool 래핑
2. [ ] TroubleshootTool 래핑
3. [ ] ModellingTool 래핑
4. [ ] GeneralQATool 구현

### Phase 3: 대화 기능 (3주차)
1. [ ] ConversationManager 구현
2. [ ] 컨텍스트 유지 기능
3. [ ] ResponseGenerator 개선
4. [ ] 후속 질문 처리

### Phase 4: 최적화 (4주차)
1. [ ] 스트리밍 응답 지원
2. [ ] 캐싱 최적화
3. [ ] 에러 핸들링 강화
4. [ ] 테스트 작성

---

## API 예시

### 1. G-code 분석 요청

**Request:**
```json
{
    "user_id": "user_123",
    "user_plan": "pro",
    "message": "이 G코드 파일 분석해줘",
    "attachments": [
        {
            "type": "gcode",
            "content": "base64_encoded_gcode...",
            "filename": "benchy.gcode"
        }
    ],
    "language": "ko"
}
```

**Response:**
```json
{
    "conversation_id": "conv_abc123",
    "message_id": "msg_001",
    "intent": "gcode_analysis",
    "tool_used": "gcode_analyzer",
    "response": "G-code 분석이 완료되었습니다!\\n\\n📊 기본 정보:\\n- 슬라이서: OrcaSlicer...",
    "tool_result": {
        "analysis_id": "analysis_xyz",
        "summary": {...},
        "quality_score": 85,
        "issues": [...]
    },
    "suggested_actions": [
        {"label": "수정된 G-code 다운로드", "action": "download_patched"},
        {"label": "상세 분석 보기", "action": "view_details"}
    ],
    "token_usage": {"total": 1500}
}
```

### 2. 문제 진단 요청

**Request:**
```json
{
    "user_id": "user_123",
    "user_plan": "free",
    "message": "첫 레이어가 베드에 안 붙어요. 사진 첨부했어요.",
    "attachments": [
        {
            "type": "image",
            "content": "base64_encoded_image...",
            "filename": "problem.jpg"
        }
    ],
    "language": "ko"
}
```

### 3. 일반 질문

**Request:**
```json
{
    "user_id": "user_123",
    "message": "PLA랑 PETG 차이가 뭐야?",
    "language": "ko"
}
```

---

## 추가 고려사항

### 1. 스트리밍 응답
- SSE를 통한 실시간 응답 전송
- LLM 생성 중 부분 응답 표시

### 2. 파일 처리
- 대용량 G-code 파일 처리
- 이미지 리사이징/압축
- 임시 파일 정리

### 3. 에러 처리
- 도구 실행 실패 시 graceful fallback
- 사용자 친화적 에러 메시지

### 4. 보안
- 파일 검증 (악성 파일 차단)
- Rate limiting (플랜별)
- 입력 sanitization

### 5. 모니터링
- 의도 분류 정확도 추적
- 도구 사용 통계
- 응답 시간 모니터링
