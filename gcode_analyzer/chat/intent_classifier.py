"""
의도 분류기 - 웹 UI에서 선택한 도구 기반 분기

LLM 미사용 - 단순 라우팅만 수행
"""
import re
import logging
from typing import List, Optional, Dict, Any

from .models import (
    ChatIntent, Attachment, AttachmentType, IntentResult
)

logger = logging.getLogger(__name__)


class IntentClassifier:
    """
    사용자 의도 분류기 - LLM 미사용

    분류 우선순위:
    1. UI에서 선택한 도구 (selected_tool) - 필수
    2. 첨부 파일 타입 기반 (fallback)
    3. 키워드 기반 (fallback)
    """

    # 키워드 기반 분류 (fallback용)
    KEYWORD_PATTERNS = {
        ChatIntent.GCODE_ANALYSIS: [
            r"g-?code", r"분석", r"analyze", r"파싱", r"parse", r"검사"
        ],
        ChatIntent.TROUBLESHOOT: [
            r"문제", r"고장", r"안[돼되]", r"오류", r"에러", r"실패",
            r"problem", r"issue", r"error", r"fix", r"not working",
            r"안\s*붙", r"떨어", r"스트링", r"뒤틀", r"막힘"
        ],
        ChatIntent.MODELLING_TEXT: [
            r"만들어", r"생성", r"모델링", r"3d.*만", r"create", r"generate", r"model"
        ],
        ChatIntent.GREETING: [
            r"^안녕", r"^하이", r"^hello", r"^hi\b", r"반가"
        ],
        ChatIntent.HELP: [
            r"도움", r"사용법", r"뭘.*할.*수", r"help", r"how to use"
        ],
    }

    def __init__(self, language: str = "ko"):
        self.language = language

    async def classify(
        self,
        message: str,
        attachments: Optional[List[Attachment]] = None,
        selected_tool: Optional[str] = None
    ) -> IntentResult:
        """
        의도 분류 실행 (LLM 미사용)

        Args:
            message: 사용자 메시지
            attachments: 첨부 파일 목록
            selected_tool: UI에서 선택한 도구 (필수 권장)

        Returns:
            IntentResult: 분류 결과
        """
        attachments = attachments or []

        # 1. UI에서 선택한 도구가 있으면 바로 사용 (권장)
        if selected_tool:
            intent = self._map_selected_tool(selected_tool, attachments)
            if intent:
                return IntentResult(
                    intent=intent,
                    confidence=1.0,
                    extracted_params=self._extract_params(message, intent),
                    reasoning=f"UI selected tool: {selected_tool}"
                )

        # 2. 첨부 파일 타입 기반 분류 (fallback)
        intent = self._classify_by_attachment(attachments, message)
        if intent:
            return IntentResult(
                intent=intent,
                confidence=0.95,
                extracted_params=self._extract_params(message, intent),
                reasoning="Classified by attachment type"
            )

        # 3. 키워드 기반 분류 (fallback)
        intent = self._classify_by_keyword(message)
        if intent:
            return IntentResult(
                intent=intent,
                confidence=0.85,
                extracted_params=self._extract_params(message, intent),
                reasoning="Classified by keyword matching"
            )

        # 4. 기본값: 일반 질문
        return IntentResult(
            intent=ChatIntent.GENERAL_QUESTION,
            confidence=0.5,
            extracted_params={},
            reasoning="Default fallback - no tool selected"
        )

    def _map_selected_tool(
        self,
        selected_tool: str,
        attachments: List[Attachment]
    ) -> Optional[ChatIntent]:
        """UI 선택 도구를 Intent로 매핑"""
        tool_mapping = {
            "troubleshoot": ChatIntent.TROUBLESHOOT,
            "gcode": ChatIntent.GCODE_ANALYSIS,
            "resolve_issue": ChatIntent.GCODE_ISSUE_RESOLVE,  # AI 해결하기
            "modelling": None,  # 이미지 여부에 따라 분기
        }

        if selected_tool == "modelling":
            # 이미지 첨부 여부로 분기
            has_image = any(a.type == AttachmentType.IMAGE for a in attachments)
            return ChatIntent.MODELLING_IMAGE if has_image else ChatIntent.MODELLING_TEXT

        return tool_mapping.get(selected_tool)

    def _classify_by_attachment(
        self,
        attachments: List[Attachment],
        message: str
    ) -> Optional[ChatIntent]:
        """첨부 파일 타입으로 분류"""
        if not attachments:
            return None

        for attachment in attachments:
            # G-code 파일 (도구 선택 없이 첨부 → 제너럴 모드 → 텍스트 답변만)
            if attachment.type == AttachmentType.GCODE:
                return ChatIntent.GCODE_GENERAL

            # 이미지 파일
            if attachment.type == AttachmentType.IMAGE:
                # 문제 관련 키워드 있으면 troubleshoot
                problem_keywords = ["문제", "고장", "안돼", "오류", "problem", "issue", "error"]
                if any(kw in message.lower() for kw in problem_keywords):
                    return ChatIntent.TROUBLESHOOT
                # 모델링 관련 키워드 있으면 image-to-3d
                modelling_keywords = ["만들어", "생성", "모델", "3d", "create", "generate"]
                if any(kw in message.lower() for kw in modelling_keywords):
                    return ChatIntent.MODELLING_IMAGE
                # 기본: troubleshoot (이미지는 대부분 문제 진단용)
                return ChatIntent.TROUBLESHOOT

            # STL 파일
            if attachment.type == AttachmentType.STL:
                # STL은 보통 슬라이싱 관련
                return ChatIntent.GCODE_ANALYSIS

        return None

    def _classify_by_keyword(self, message: str) -> Optional[ChatIntent]:
        """키워드 기반 분류 (fallback)"""
        message_lower = message.lower()

        for intent, patterns in self.KEYWORD_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower, re.IGNORECASE):
                    return intent

        return None

    def _extract_params(self, message: str, intent: ChatIntent) -> Dict[str, Any]:
        """의도에 따른 파라미터 추출"""
        params = {}

        if intent == ChatIntent.TROUBLESHOOT:
            params["symptom"] = message

        elif intent in [ChatIntent.MODELLING_TEXT, ChatIntent.MODELLING_IMAGE]:
            # 모델링 프롬프트 추출 (간단한 정리)
            prompt = message
            # "만들어줘", "생성해줘" 등 제거
            prompt = re.sub(r"(만들어|생성해|모델링해)\s*(줘|주세요)?", "", prompt)
            prompt = re.sub(r"3[dD]\s*(모델|모델링)?\s*(을|를)?", "", prompt)
            params["prompt"] = prompt.strip() or message

        elif intent == ChatIntent.GCODE_ANALYSIS:
            params["analysis_mode"] = "full"

        return params
