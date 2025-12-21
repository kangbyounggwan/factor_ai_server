"""
통합 챗봇 API 라우터

POST /api/v1/chat - 챗봇 메시지 처리
"""
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .models import (
    ChatRequest, ChatResponse, ChatIntent,
    Attachment, AttachmentType, ToolResult,
    SuggestedAction, TokenUsage, UserPlan
)
from .intent_classifier import IntentClassifier
from .tool_dispatcher import ToolDispatcher
from .response_generator import ResponseGenerator


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


# ============================================================
# Simplified Request Model for API docs
# ============================================================
class SimpleChatRequest(BaseModel):
    """간소화된 챗봇 요청 (API 문서용)"""
    user_id: str
    user_plan: str = "free"
    message: str
    conversation_id: Optional[str] = None
    attachments: Optional[list] = None
    selected_tool: Optional[str] = None
    printer_info: Optional[Dict[str, Any]] = None
    filament_type: Optional[str] = None
    language: str = "ko"


# ============================================================
# API Endpoints
# ============================================================
@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    통합 챗봇 메시지 처리

    사용자 메시지와 첨부 파일을 분석하여 적절한 도구로 라우팅하고 응답을 생성합니다.

    ## 지원 기능:
    - **G-code 분석**: G-code 파일 첨부 시 자동 분석
    - **프린터 문제 진단**: 이미지 + 문제 설명으로 진단
    - **3D 모델링**: 텍스트 또는 이미지로 3D 모델 생성
    - **일반 질문**: 3D 프린팅 관련 질문 답변

    ## 요청 예시:

    ### G-code 분석
    ```json
    {
        "user_id": "user_123",
        "message": "이 G코드 파일 분석해줘",
        "attachments": [
            {"type": "gcode", "content": "base64_encoded...", "filename": "test.gcode"}
        ]
    }
    ```

    ### 문제 진단
    ```json
    {
        "user_id": "user_123",
        "message": "첫 레이어가 베드에 안 붙어요",
        "attachments": [
            {"type": "image", "content": "base64_encoded...", "filename": "problem.jpg"}
        ]
    }
    ```

    ### 3D 모델링 (Text-to-3D)
    ```json
    {
        "user_id": "user_123",
        "message": "귀여운 고양이 피규어 만들어줘",
        "selected_tool": "modelling"
    }
    ```

    ### 3D 모델링 (Image-to-3D)
    ```json
    {
        "user_id": "user_123",
        "message": "이 이미지로 3D 모델 만들어줘",
        "attachments": [
            {"type": "image", "content": "base64_encoded...", "filename": "ref.jpg"}
        ],
        "selected_tool": "modelling"
    }
    ```

    Args:
        request: 챗봇 요청

    Returns:
        ChatResponse: 챗봇 응답
    """
    conversation_id = request.conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
    message_id = f"msg_{uuid.uuid4().hex[:12]}"

    token_usage = TokenUsage()

    try:
        # 1. 의도 분류
        classifier = IntentClassifier(language=request.language)
        intent_result = await classifier.classify(
            message=request.message,
            attachments=request.attachments,
            selected_tool=request.selected_tool
        )

        logger.info(
            f"[Chat] Intent classified: {intent_result.intent.value} "
            f"(confidence: {intent_result.confidence:.2f})"
        )

        # 2. 도구 실행
        dispatcher = ToolDispatcher(
            language=request.language,
            selected_model=request.selected_model
        )
        tool_result = await dispatcher.dispatch(
            intent=intent_result.intent,
            message=request.message,
            attachments=request.attachments,
            user_id=request.user_id,
            user_plan=request.user_plan,
            extracted_params=intent_result.extracted_params,
            printer_info=request.printer_info,
            filament_type=request.filament_type,
            conversation_history=request.conversation_history,
            analysis_id=request.analysis_id,
            issue_to_resolve=request.issue_to_resolve
        )

        logger.info(
            f"[Chat] Tool executed: {tool_result.tool_name} "
            f"(success: {tool_result.success})"
        )

        # 3. 응답 생성
        generator = ResponseGenerator(language=request.language)
        response_text, suggested_actions = generator.generate(
            intent=intent_result.intent,
            tool_result=tool_result,
            original_message=request.message
        )

        # G-code 분석인 경우 analysis_id를 최상위에 노출
        analysis_id = None
        if tool_result.success and intent_result.intent == ChatIntent.GCODE_ANALYSIS:
            analysis_id = tool_result.analysis_id or (tool_result.data or {}).get("analysis_id")

        return ChatResponse(
            conversation_id=conversation_id,
            message_id=message_id,
            timestamp=datetime.now(),
            intent=intent_result.intent,
            confidence=intent_result.confidence,
            response=response_text,
            tool_result=tool_result if tool_result.success else None,
            suggested_actions=suggested_actions,
            token_usage=token_usage,
            # G-code 분석 전용 필드
            analysis_id=analysis_id
        )

    except Exception as e:
        logger.error(f"[Chat] Error processing request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intents")
async def list_intents():
    """
    지원하는 의도(Intent) 목록 조회

    Returns:
        의도 목록 및 설명
    """
    intent_descriptions = {
        "gcode_analysis": "G-code 파일 분석",
        "troubleshoot": "프린터 문제 진단",
        "modelling_text": "텍스트로 3D 모델 생성 (Text-to-3D)",
        "modelling_image": "이미지로 3D 모델 생성 (Image-to-3D)",
        "general_question": "3D 프린팅 관련 일반 질문",
        "greeting": "인사",
        "help": "도움말"
    }

    return {
        "intents": [
            {"intent": intent.value, "description": intent_descriptions.get(intent.value, "")}
            for intent in ChatIntent
        ]
    }


@router.get("/attachment-types")
async def list_attachment_types():
    """
    지원하는 첨부 파일 타입 목록

    Returns:
        첨부 파일 타입 목록
    """
    type_descriptions = {
        "gcode": "G-code 파일 (.gcode)",
        "image": "이미지 파일 (jpg, png, webp)",
        "stl": "STL 3D 모델 파일 (.stl)",
        "text": "텍스트 파일"
    }

    return {
        "attachment_types": [
            {"type": t.value, "description": type_descriptions.get(t.value, "")}
            for t in AttachmentType
        ]
    }


@router.get("/models")
async def list_models():
    """
    지원하는 LLM 모델 목록

    Returns:
        프로바이더별 모델 목록
    """
    models = {
        "gemini": {
            "name": "Google Gemini",
            "models": [
                {
                    "id": "gemini-2.5-flash-lite",
                    "name": "Gemini 2.5 Flash Lite",
                    "description": "빠르고 효율적",
                    "tier": "free"
                },
                {
                    "id": "gemini-2.5-flash",
                    "name": "Gemini 2.5 Flash",
                    "description": "빠른 응답",
                    "tier": "paid"
                }
            ]
        },
        "openai": {
            "name": "OpenAI",
            "models": [
                {
                    "id": "gpt-4o-mini",
                    "name": "GPT-4o mini",
                    "description": "빠르고 효율적",
                    "tier": "free"
                },
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "description": "가장 강력한 모델",
                    "tier": "paid"
                }
            ]
        }
    }

    return {"providers": models}


@router.get("/plans")
async def list_plans():
    """
    사용자 플랜 목록 및 기능

    Returns:
        플랜별 기능 설명
    """
    plans = {
        "free": {
            "name": "무료",
            "features": [
                "G-code 분석 (기본)",
                "문제 진단 (DuckDuckGo + Wikipedia 검색)",
                "일반 질문 답변"
            ],
            "limits": {
                "search_results": 5,
                "search_depth": "basic"
            }
        },
        "starter": {
            "name": "스타터",
            "features": [
                "G-code 분석 (전체)",
                "문제 진단 (Tavily 검색)",
                "Text-to-3D 모델링",
                "일반 질문 답변"
            ],
            "limits": {
                "search_results": 5,
                "search_depth": "basic"
            }
        },
        "pro": {
            "name": "프로",
            "features": [
                "G-code 분석 (전체 + 패치)",
                "문제 진단 (고급 검색)",
                "Text-to-3D / Image-to-3D 모델링",
                "공식 문서 검색 포함"
            ],
            "limits": {
                "search_results": 10,
                "search_depth": "advanced"
            }
        },
        "enterprise": {
            "name": "엔터프라이즈",
            "features": [
                "모든 기능",
                "최대 검색 결과",
                "우선 처리"
            ],
            "limits": {
                "search_results": 15,
                "search_depth": "advanced"
            }
        }
    }

    return {"plans": plans}
