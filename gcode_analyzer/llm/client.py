"""
LLM Client - Multi-Provider Support (Gemini, OpenAI)
"""
import os
import dotenv
from typing import Literal, Optional
from langchain_core.language_models.chat_models import BaseChatModel

# Load .env explicitly if needed
dotenv.load_dotenv()


# Provider 타입
LLMProvider = Literal["gemini", "openai"]


# 기본 모델 설정
MODELS = {
    "gemini": "gemini-2.5-flash",  # 정밀 분석용
    "gemini_lite": "gemini-2.5-flash-lite",  # 빠른 검증용
    "openai": "gpt-4o",
}


def get_llm_client_lite(
    temperature: float = 0.0,
    max_output_tokens: int = 512
) -> "BaseChatModel":
    """
    빠른 검증용 LLM Client (Flash Lite)
    - Rule Engine 이슈 검증
    - 간단한 Yes/No 판단
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = get_gemini_api_key()
    model_name = MODELS["gemini_lite"]

    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def get_provider() -> LLMProvider:
    """환경 변수에서 LLM 프로바이더 가져오기"""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider not in ["gemini", "openai"]:
        provider = "gemini"
    return provider


def get_gemini_api_key() -> str:
    """Gemini API 키 가져오기"""
    api_key = os.getenv("VITE_GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("VITE_GEMINI_API_KEY or GOOGLE_API_KEY not found in environment.")
    return api_key


def get_openai_api_key() -> str:
    """OpenAI API 키 가져오기"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment.")
    return api_key


def get_llm_client(
    temperature: float = 0.0,
    max_output_tokens: int = 1024,
    provider: Optional[LLMProvider] = None
) -> BaseChatModel:
    """
    Get the configured LLM Chat Client.

    Args:
        temperature: 온도 (0.0 = 결정적)
        max_output_tokens: 최대 출력 토큰
        provider: LLM 프로바이더 ("gemini" | "openai"). None이면 환경변수 사용.

    Returns:
        LangChain BaseChatModel
    """
    if provider is None:
        provider = get_provider()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        api_key = get_openai_api_key()
        model_name = MODELS["openai"]

        llm = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_output_tokens,
        )
        return llm

    else:  # gemini (default)
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = get_gemini_api_key()
        model_name = MODELS["gemini"]

        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        return llm


def get_model_name(provider: Optional[LLMProvider] = None) -> str:
    """현재 사용 중인 모델 이름 반환"""
    if provider is None:
        provider = get_provider()
    return MODELS.get(provider, MODELS["gemini"])


# 하위 호환성을 위한 별칭
def get_api_key() -> str:
    """기존 코드 호환용 - Gemini API 키 반환"""
    return get_gemini_api_key()
