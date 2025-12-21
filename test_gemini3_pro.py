"""
Gemini 3 Pro 모델 테스트
"""
import asyncio
from dotenv import load_dotenv

load_dotenv()

# 테스트할 Gemini 3 모델들
GEMINI_3_MODELS = [
    "gemini-3-flash",
    "gemini-3-pro",
    "gemini-3.0-flash",
    "gemini-3.0-pro",
    "gemini-exp-1206",  # 실험 모델
]

TEST_MESSAGE = "Hello, please introduce yourself briefly."


async def test_model(model_name: str) -> dict:
    """단일 모델 테스트"""
    from gcode_analyzer.llm.client import get_llm_by_model
    from langchain_core.messages import HumanMessage

    result = {
        "model": model_name,
        "success": False,
        "response": None,
        "error": None
    }

    try:
        llm = get_llm_by_model(
            model_name=model_name,
            temperature=0.3,
            max_output_tokens=100
        )

        response = await llm.ainvoke([HumanMessage(content=TEST_MESSAGE)])
        result["success"] = True
        result["response"] = response.content[:80] + "..." if len(response.content) > 80 else response.content

    except Exception as e:
        result["error"] = str(e)[:100]

    return result


async def main():
    print("=" * 60)
    print("Gemini 3 모델 테스트")
    print("=" * 60)

    for model_name in GEMINI_3_MODELS:
        print(f"\n테스트: {model_name}...", end=" ", flush=True)
        result = await test_model(model_name)

        if result["success"]:
            print("✅ 성공")
            print(f"   응답: {result['response']}")
        else:
            print("❌ 실패")
            print(f"   오류: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
