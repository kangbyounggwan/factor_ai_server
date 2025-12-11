"""
언어 설정 유틸리티
"""
from typing import Dict

# 지원되는 언어
SUPPORTED_LANGUAGES = ["ko", "en", "ja", "zh"]

# 언어별 지시문
LANGUAGE_INSTRUCTIONS: Dict[str, str] = {
    "ko": "모든 응답은 한국어로 작성해주세요.",
    "en": "Please write all responses in English.",
    "ja": "すべての回答は日本語で書いてください。",
    "zh": "请用中文写所有回复。"
}

# 언어별 이름
LANGUAGE_NAMES: Dict[str, str] = {
    "ko": "Korean",
    "en": "English",
    "ja": "Japanese",
    "zh": "Chinese"
}


def get_language_instruction(language: str) -> str:
    """
    언어 코드에 해당하는 지시문 반환

    Args:
        language: 언어 코드 ("ko", "en", "ja", "zh")

    Returns:
        해당 언어의 지시문
    """
    return LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["ko"])


def validate_language(language: str) -> str:
    """
    언어 코드 유효성 검사 및 기본값 반환

    Args:
        language: 언어 코드

    Returns:
        유효한 언어 코드 (지원하지 않으면 "ko" 반환)
    """
    if language in SUPPORTED_LANGUAGES:
        return language
    return "ko"
