"""
트러블슈팅 API 테스트 벤치
이미지 기반 문제 진단 테스트
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

# 프로젝트 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from gcode_analyzer.troubleshoot.image_analyzer import ImageAnalyzer
from gcode_analyzer.troubleshoot.perplexity_searcher import PerplexitySearcher
from gcode_analyzer.troubleshoot.structured_editor import StructuredEditor
from gcode_analyzer.troubleshoot.models import UserPlan, ProblemType, SearchDecision


async def run_test(image_path: str, symptom_text: str):
    """
    트러블슈팅 흐름 테스트
    """
    print("=" * 60)
    print("🔍 3D 프린터 문제 진단 테스트")
    print("=" * 60)

    # 1. 이미지 로드
    print(f"\n📷 이미지 로드: {image_path}")
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    results = {
        "input": {
            "image_path": image_path,
            "symptom_text": symptom_text
        },
        "step1_image_analysis": None,
        "step2_search": None,
        "step3_solution": None
    }

    # ================================================================
    # 1단계: Vision + 질문 증강 + Gate
    # ================================================================
    print("\n" + "=" * 60)
    print("📸 1단계: 이미지 분석 + 질문 증강 + Gate 판단")
    print("=" * 60)

    analyzer = ImageAnalyzer(language="ko")
    image_analysis = await analyzer.analyze_images(
        images=[image_data],
        symptom_text=symptom_text
    )

    results["step1_image_analysis"] = {
        "detected_problems": [p.value for p in image_analysis.detected_problems],
        "confidence_scores": image_analysis.confidence_scores,
        "description": image_analysis.description,
        "visual_evidence": image_analysis.visual_evidence,
        "augmented_query": image_analysis.augmented_query,
        "follow_up_questions": image_analysis.follow_up_questions,
        "specific_symptoms": image_analysis.specific_symptoms,
        "needs_search": image_analysis.needs_search.value,
        "search_skip_reason": image_analysis.search_skip_reason,
        "internal_solution": image_analysis.internal_solution
    }

    print(f"\n🔎 감지된 문제: {[p.value for p in image_analysis.detected_problems]}")
    print(f"📊 확신도: {image_analysis.confidence_scores}")
    print(f"\n📝 설명:\n{image_analysis.description}")
    print(f"\n🔍 증강된 검색 쿼리:\n{image_analysis.augmented_query}")
    print(f"\n❓ 추가 질문:")
    for i, q in enumerate(image_analysis.follow_up_questions, 1):
        print(f"   {i}. {q}")
    print(f"\n🚦 Gate 판단: {image_analysis.needs_search.value}")
    if image_analysis.search_skip_reason:
        print(f"   스킵 이유: {image_analysis.search_skip_reason}")
    if image_analysis.internal_solution:
        print(f"   내부 솔루션: {image_analysis.internal_solution[:200]}...")

    # ================================================================
    # 2단계: Perplexity 검색 (Gate 통과 시)
    # ================================================================
    print("\n" + "=" * 60)
    print("🔎 2단계: Perplexity 검색 (Evidence 수집)")
    print("=" * 60)

    if image_analysis.needs_search == SearchDecision.NOT_NEEDED:
        print("\n⏭️ 검색 스킵 - 내부 KB로 해결 가능")
        from gcode_analyzer.troubleshoot.models import PerplexitySearchResult
        search_result = PerplexitySearchResult(
            query=image_analysis.augmented_query,
            findings=[],
            citations=[],
            summary=image_analysis.internal_solution,
            tokens_used=0
        )
        results["step2_search"] = {
            "skipped": True,
            "reason": image_analysis.search_skip_reason,
            "internal_solution": image_analysis.internal_solution
        }
    else:
        print(f"\n🔍 검색 쿼리: {image_analysis.augmented_query}")

        searcher = PerplexitySearcher(user_plan=UserPlan.FREE, language="ko")
        problem_type = image_analysis.detected_problems[0] if image_analysis.detected_problems else ProblemType.UNKNOWN

        search_result = await searcher.search(
            augmented_query=image_analysis.augmented_query,
            problem_type=problem_type
        )

        results["step2_search"] = {
            "skipped": False,
            "query": search_result.query,
            "findings": [
                {
                    "fact": e.fact,
                    "source_url": e.source_url,
                    "source_title": e.source_title
                }
                for e in search_result.findings
            ],
            "citations": search_result.citations,
            "summary": search_result.summary,
            "tokens_used": search_result.tokens_used
        }

        print(f"\n📚 검색 결과: {len(search_result.findings)}개 Evidence 발견")
        for i, evidence in enumerate(search_result.findings[:5], 1):
            print(f"\n   {i}. {evidence.fact[:100]}...")
            print(f"      출처: {evidence.source_url}")

        if search_result.citations:
            print(f"\n📎 인용 URL ({len(search_result.citations)}개):")
            for url in search_result.citations[:5]:
                print(f"   - {url}")

    # ================================================================
    # 3단계: 구조화 편집
    # ================================================================
    print("\n" + "=" * 60)
    print("📋 3단계: 구조화 편집 (Evidence 기반)")
    print("=" * 60)

    editor = StructuredEditor(language="ko")
    structured_diagnosis = await editor.edit(
        image_analysis=image_analysis,
        search_result=search_result,
        symptom_text=symptom_text,
        problem_type=problem_type if 'problem_type' in dir() else ProblemType.UNKNOWN
    )

    results["step3_solution"] = {
        "observed": structured_diagnosis.observed,
        "likely_causes": structured_diagnosis.likely_causes,
        "immediate_checks": structured_diagnosis.immediate_checks,
        "solutions": structured_diagnosis.solutions,
        "need_more_info": structured_diagnosis.need_more_info
    }

    print(f"\n📍 관찰된 증상:\n{structured_diagnosis.observed}")

    print(f"\n🎯 가능한 원인:")
    for cause in structured_diagnosis.likely_causes:
        print(f"   - {cause.get('cause', 'N/A')}")
        print(f"     출처: {cause.get('source', 'N/A')}")

    print(f"\n✅ 즉시 확인할 사항:")
    for check in structured_diagnosis.immediate_checks:
        print(f"   - {check}")

    print(f"\n🔧 해결책:")
    for sol in structured_diagnosis.solutions:
        print(f"\n   📌 {sol.get('title', 'N/A')}")
        for step in sol.get('steps', []):
            print(f"      - {step}")
        print(f"      출처: {sol.get('source', 'N/A')}")

    print(f"\n❓ 추가 정보 필요:")
    for info in structured_diagnosis.need_more_info:
        print(f"   - {info}")

    return results


def save_results_as_markdown(results: dict, output_path: str):
    """결과를 마크다운 파일로 저장"""
    md_content = f"""# 🔍 3D 프린터 문제 진단 결과

## 📥 입력 정보
- **이미지**: `{results['input']['image_path']}`
- **증상 텍스트**: "{results['input']['symptom_text']}"

---

## 📸 1단계: 이미지 분석 + 질문 증강

### 감지된 문제
"""

    step1 = results['step1_image_analysis']
    for prob in step1['detected_problems']:
        confidence = step1['confidence_scores'].get(prob, 'N/A')
        md_content += f"- **{prob}** (확신도: {confidence})\n"

    md_content += f"""
### 이미지 분석 설명
{step1['description']}

### 시각적 증거
"""
    for evidence in step1['visual_evidence']:
        md_content += f"- {evidence}\n"

    md_content += f"""
### 🔍 증강된 검색 쿼리 (Augmented Query)
```
{step1['augmented_query']}
```

### ❓ 추가 질문 (Follow-up Questions)
"""
    for i, q in enumerate(step1['follow_up_questions'], 1):
        md_content += f"{i}. {q}\n"

    md_content += f"""
### 🚦 Gate 판단
- **검색 필요 여부**: `{step1['needs_search']}`
"""
    if step1['search_skip_reason']:
        md_content += f"- **스킵 이유**: {step1['search_skip_reason']}\n"
    if step1['internal_solution']:
        md_content += f"- **내부 솔루션**: {step1['internal_solution']}\n"

    md_content += """
---

## 🔎 2단계: Perplexity 검색 결과

"""

    step2 = results['step2_search']
    if step2.get('skipped'):
        md_content += f"""### ⏭️ 검색 스킵됨
- **이유**: {step2.get('reason', 'N/A')}
- **내부 솔루션 사용**: {step2.get('internal_solution', 'N/A')[:500]}...
"""
    else:
        md_content += f"""### 검색 쿼리
```
{step2['query']}
```

### 📚 검색된 Evidence ({len(step2['findings'])}개)

| # | 사실/정보 | 출처 |
|---|----------|------|
"""
        for i, finding in enumerate(step2['findings'], 1):
            fact = finding['fact'][:100].replace('\n', ' ') + '...' if len(finding['fact']) > 100 else finding['fact'].replace('\n', ' ')
            url = finding['source_url']
            title = finding.get('source_title', '-')
            md_content += f"| {i} | {fact} | [{title}]({url}) |\n"

        md_content += f"""
### 📎 인용 URL (Citations)
"""
        for url in step2.get('citations', []):
            md_content += f"- {url}\n"

        md_content += f"""
### 📝 검색 요약 (Raw)
```
{step2['summary'][:2000]}
```

### 토큰 사용량
- **총 토큰**: {step2['tokens_used']}
"""

    md_content += """
---

## 📋 3단계: 구조화된 진단 결과

"""

    step3 = results['step3_solution']
    md_content += f"""### 📍 관찰된 증상
{step3['observed']}

### 🎯 가능한 원인
"""
    for cause in step3['likely_causes']:
        md_content += f"- **{cause.get('cause', 'N/A')}**\n"
        md_content += f"  - 출처: {cause.get('source', 'N/A')}\n"

    md_content += """
### ✅ 즉시 확인할 사항
"""
    for check in step3['immediate_checks']:
        md_content += f"- {check}\n"

    md_content += """
### 🔧 해결책
"""
    for i, sol in enumerate(step3['solutions'], 1):
        md_content += f"""
#### {i}. {sol.get('title', 'N/A')}
- **난이도**: {sol.get('difficulty', 'N/A')}
- **출처**: {sol.get('source', 'N/A')}
- **단계**:
"""
        for step in sol.get('steps', []):
            md_content += f"  1. {step}\n"

    md_content += """
### ❓ 추가로 필요한 정보
"""
    for info in step3['need_more_info']:
        md_content += f"- {info}\n"

    md_content += """
---

## 📊 Raw JSON 결과

<details>
<summary>전체 JSON 데이터 보기</summary>

```json
""" + json.dumps(results, indent=2, ensure_ascii=False) + """
```

</details>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"\n✅ 결과가 저장되었습니다: {output_path}")


async def main():
    import sys

    # 명령행 인자로 이미지 경로 받기
    if len(sys.argv) > 1:
        test_image = sys.argv[1]
    else:
        # 기본 테스트 이미지 경로
        test_image = "test_print.jpg"

        # 현재 디렉토리에서 이미지 찾기
        for ext in ['jpg', 'jpeg', 'png']:
            candidates = list(Path('.').glob(f'*.{ext}'))
            if candidates:
                test_image = str(candidates[0])
                break

    if not Path(test_image).exists():
        print(f"❌ 이미지를 찾을 수 없습니다: {test_image}")
        print("   사용법: python test_troubleshoot.py <이미지_경로>")
        return

    symptom_text = "현재증상뭐야? 어떻게해야해"

    results = await run_test(test_image, symptom_text)

    # 결과를 마크다운으로 저장
    output_path = "troubleshoot_result.md"
    save_results_as_markdown(results, output_path)


if __name__ == "__main__":
    asyncio.run(main())
