"""
LLM Client - Gemini API 클라이언트
"""
import os
import dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models.chat_models import BaseChatModel

# Load .env explicitly if needed, but python-dotenv usually handles it at app startup.
dotenv.load_dotenv()


# 고정 모델 (gemini-2.5-flash-lite)
MODEL_NAME = "gemini-2.5-flash-lite"


def get_api_key() -> str:
    """API 키 가져오기"""
    api_key = os.getenv("VITE_GEMINI_API_KEY")
    if not api_key:
        api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("VITE_GEMINI_API_KEY or GOOGLE_API_KEY not found in environment.")
    return api_key


def get_llm_client(
    temperature: float = 0.0,
    max_output_tokens: int = 1024
) -> BaseChatModel:
    """
    Get the configured Gemini Chat Client.

    Args:
        temperature: 온도 (0.0 = 결정적)
        max_output_tokens: 최대 출력 토큰

    Returns:
        LangChain BaseChatModel (gemini-2.5-flash-lite 고정)
    """
    api_key = get_api_key()

    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=api_key,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    return llm
