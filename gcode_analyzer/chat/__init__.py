"""
통합 챗봇 API 모듈

웹 UI의 챗봇 인터페이스를 통해 모든 AI 기능을 통합 제공:
- G-code 분석
- 프린터 문제 진단
- 3D 모델링 (Text-to-3D, Image-to-3D)
- 일반 질문 답변

사용법:
    from gcode_analyzer.chat import router

    # FastAPI 앱에 라우터 등록
    app.include_router(router)

API 엔드포인트:
    POST /api/v1/chat - 챗봇 메시지 처리
    GET /api/v1/chat/intents - 지원 의도 목록
    GET /api/v1/chat/attachment-types - 지원 첨부 타입
    GET /api/v1/chat/plans - 사용자 플랜 정보
"""

from .models import (
    # Request/Response
    ChatRequest,
    ChatResponse,
    Attachment,
    AttachmentType,
    SuggestedAction,
    ToolResult,
    TokenUsage,

    # Enums
    ChatIntent,
    UserPlan,

    # Internal models
    IntentResult,
    ConversationMessage,
    ConversationSession,

    # Tool params
    GCodeAnalysisParams,
    TroubleshootParams,
    ModellingParams,
)

from .router import router
from .intent_classifier import IntentClassifier
from .tool_dispatcher import ToolDispatcher
from .response_generator import ResponseGenerator

__all__ = [
    # Router
    'router',

    # Models - Request/Response
    'ChatRequest',
    'ChatResponse',
    'Attachment',
    'AttachmentType',
    'SuggestedAction',
    'ToolResult',
    'TokenUsage',

    # Models - Enums
    'ChatIntent',
    'UserPlan',

    # Models - Internal
    'IntentResult',
    'ConversationMessage',
    'ConversationSession',

    # Models - Tool params
    'GCodeAnalysisParams',
    'TroubleshootParams',
    'ModellingParams',

    # Classes
    'IntentClassifier',
    'ToolDispatcher',
    'ResponseGenerator',
]
