"""
프론트엔드에 표시된 6개 LLM 모델 테스트
"""
import asyncio
from dotenv import load_dotenv

load_dotenv()

# 프론트엔드에 표시된 6개 모델
MODELS = [
    # Google Gemini (3개)
    ("gemini-2.5-flash-lite", "Google", "무료", "Gemini 2.5 Flash Lite"),
    ("gemini-2.5-flash", "Google", "유료", "Gemini 2.5 Flash"),
    ("gemini-2.5-pro", "Google", "유료", "Gemini 2.5 Pro"),

    # OpenAI (3개)
    ("gpt-4o-mini", "OpenAI", "무료", "GPT-4o mini"),
    ("gpt-4o", "OpenAI", "유료", "GPT-4o (웹 검색 지원)"),
    ("gpt-4.1", "OpenAI", "유료", "GPT-4.1"),
]

TEST_MESSAGE = "Hello, please introduce yourself in one sentence."


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
        result["error"] = str(e)[:150]

    return result


async def main():
    print("=" * 70)
    print("프론트엔드 6개 모델 테스트")
    print("=" * 70)

    results = []

    for model_name, provider, tier, display_name in MODELS:
        print(f"\n테스트: {model_name} ({display_name})...", end=" ", flush=True)
        result = await test_model(model_name)
        result["provider"] = provider
        result["tier"] = tier
        result["display_name"] = display_name
        results.append(result)

        if result["success"]:
            print("✅ 성공")
        else:
            print("❌ 실패")

    # 결과 요약
    print("\n" + "=" * 70)
    print("결과 요약")
    print("=" * 70)

    print("\n✅ 성공한 모델:")
    for r in results:
        if r["success"]:
            print(f"   - {r['model']} → {r['display_name']} ({r['tier']})")

    print("\n❌ 실패한 모델:")
    for r in results:
        if not r["success"]:
            print(f"   - {r['model']}: {r['error'][:80]}...")

    success_count = sum(1 for r in results if r["success"])
    print(f"\n총 {len(results)}개 중 {success_count}개 성공")


if __name__ == "__main__":
    asyncio.run(main())
