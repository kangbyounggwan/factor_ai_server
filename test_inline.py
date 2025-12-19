"""
인라인 테스트 - 이미지 URL 또는 base64로 직접 테스트

테스트 흐름:
1. 이미지 분석 + 질문 증강 + Gate 판단
2. KB 검색 (유사 증상 매칭)
3. Perplexity 검색 (언어별, KB 결과 활용)
4. 구조화 편집
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from gcode_analyzer.troubleshoot.image_analyzer import ImageAnalyzer
from gcode_analyzer.troubleshoot.perplexity_searcher import PerplexitySearcher
from gcode_analyzer.troubleshoot.structured_editor import StructuredEditor
from gcode_analyzer.troubleshoot.models import UserPlan, ProblemType, SearchDecision, PerplexitySearchResult
from gcode_analyzer.troubleshoot.kb import search_kb


async def test_with_image_bytes(image_bytes: bytes, symptom_text: str = "현재증상뭐야? 어떻게해야해"):
    """이미지 바이트로 테스트"""
    image_data = base64.b64encode(image_bytes).decode("utf-8")
    return await run_full_pipeline(image_data, symptom_text)


async def run_full_pipeline(image_base64: str, symptom_text: str):
    """전체 파이프라인 실행"""
    results = {
        "input": {"symptom_text": symptom_text},
        "step1_image_analysis": None,
        "step1_5_kb_search": None,
        "step2_search": None,
        "step3_solution": None
    }

    # 1단계: 이미지 분석
    print("\n" + "=" * 60)
    print("[1단계] 이미지 분석 + 질문 증강 + Gate 판단")
    print("=" * 60)

    analyzer = ImageAnalyzer(language="ko")
    image_analysis = await analyzer.analyze_images(
        images=[image_base64],
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

    print(f"\n[감지된 문제]: {[p.value for p in image_analysis.detected_problems]}")
    print(f"[확신도]: {image_analysis.confidence_scores}")
    print(f"\n[설명]:\n{image_analysis.description}")
    print(f"\n[증강된 검색 쿼리]:\n{image_analysis.augmented_query}")
    print(f"\n[추가 질문]:")
    for i, q in enumerate(image_analysis.follow_up_questions, 1):
        print(f"   {i}. {q}")
    print(f"\n[Gate 판단]: {image_analysis.needs_search.value}")

    # 1.5단계: KB 검색 (유사 증상 매칭)
    print("\n" + "=" * 60)
    print("[1.5단계] KB 검색 (유사 증상 매칭)")
    print("=" * 60)

    kb_problem_name = None
    try:
        search_text = symptom_text + " " + image_analysis.description
        kb_results = search_kb(
            query=search_text,
            description=image_analysis.augmented_query,
            visual_signs=image_analysis.visual_evidence,
            top_k=3
        )

        results["step1_5_kb_search"] = {
            "total_found": kb_results.total_found,
            "search_method": kb_results.search_method,
            "matches": [
                {
                    "problem_name": r.entry.problem_name,
                    "problem_name_ko": r.entry.problem_name_ko,
                    "similarity_score": r.similarity_score,
                    "matched_symptoms": r.matched_symptoms,
                    "causes": r.entry.causes,
                    "quick_checks": r.entry.quick_checks
                }
                for r in kb_results.results
            ]
        }

        if kb_results.results:
            top_match = kb_results.results[0]
            kb_problem_name = top_match.entry.problem_name_ko
            print(f"\n[KB 매칭 결과]: {kb_results.total_found}개 발견 (방법: {kb_results.search_method})")
            for i, r in enumerate(kb_results.results, 1):
                print(f"   {i}. {r.entry.problem_name_ko} (score: {r.similarity_score:.2f})")
                print(f"      원인: {r.entry.causes[:2]}")
        else:
            print("\n[KB 매칭 결과]: 매칭 없음")
    except Exception as e:
        print(f"\n[KB 검색 실패]: {e}")
        results["step1_5_kb_search"] = {"error": str(e)}

    # 2단계: Perplexity 검색
    print("\n" + "=" * 60)
    print("[2단계] Perplexity 검색 (언어별)")
    print("=" * 60)

    problem_type = image_analysis.detected_problems[0] if image_analysis.detected_problems else ProblemType.UNKNOWN

    if image_analysis.needs_search == SearchDecision.NOT_NEEDED:
        print("\n>> 검색 스킵 - 내부 KB로 해결")
        search_result = PerplexitySearchResult(
            query=image_analysis.augmented_query,
            findings=[],
            citations=[],
            summary=image_analysis.internal_solution,
            tokens_used=0
        )
        results["step2_search"] = {"skipped": True, "reason": image_analysis.search_skip_reason}
    else:
        searcher = PerplexitySearcher(user_plan=UserPlan.FREE, language="ko")
        search_result = await searcher.search(
            augmented_query=image_analysis.augmented_query,
            problem_type=problem_type,
            kb_problem_name=kb_problem_name  # KB 매칭 결과 전달
        )

        results["step2_search"] = {
            "skipped": False,
            "query": search_result.query,
            "findings": [{"fact": e.fact, "source_url": e.source_url} for e in search_result.findings],
            "citations": search_result.citations,
            "summary": search_result.summary,
            "tokens_used": search_result.tokens_used
        }

        print(f"\n[검색 쿼리]: {search_result.query[:100]}...")
        print(f"\n[Evidence] {len(search_result.findings)}개 발견")
        for i, e in enumerate(search_result.findings[:3], 1):
            fact_preview = e.fact[:80] if e.fact else "(no fact)"
            print(f"   {i}. {fact_preview}...")
            print(f"      URL: {e.source_url}")

    # 3단계: 구조화 편집
    print("\n" + "=" * 60)
    print("[3단계] 구조화 편집")
    print("=" * 60)

    editor = StructuredEditor(language="ko")
    diagnosis = await editor.edit(
        image_analysis=image_analysis,
        search_result=search_result,
        symptom_text=symptom_text,
        problem_type=problem_type
    )

    results["step3_solution"] = {
        "observed": diagnosis.observed,
        "likely_causes": diagnosis.likely_causes,
        "immediate_checks": diagnosis.immediate_checks,
        "solutions": diagnosis.solutions,
        "need_more_info": diagnosis.need_more_info
    }

    print(f"\n[관찰된 증상]: {diagnosis.observed}")
    print(f"\n[원인]: {len(diagnosis.likely_causes)}개")
    print(f"[해결책]: {len(diagnosis.solutions)}개")

    return results


def save_markdown(results: dict, output_path: str = "troubleshoot_result.md"):
    """결과를 마크다운으로 저장"""
    step1 = results['step1_image_analysis']
    step2 = results['step2_search']
    step3 = results['step3_solution']

    md = f"""# 🔍 3D 프린터 문제 진단 결과

## 입력
- **증상**: "{results['input']['symptom_text']}"

---

## 📸 1단계: 이미지 분석 + 질문 증강

### 감지된 문제
"""
    for p in step1['detected_problems']:
        conf = step1['confidence_scores'].get(p, 'N/A')
        md += f"- **{p}** (확신도: {conf})\n"

    md += f"""
### 설명
{step1['description']}

### 시각적 증거
"""
    for ev in step1['visual_evidence']:
        md += f"- {ev}\n"

    md += f"""
### 🔍 증강된 검색 쿼리 (Augmented Query)
```
{step1['augmented_query']}
```

### ❓ 추가 질문 (Follow-up Questions)
"""
    for i, q in enumerate(step1['follow_up_questions'], 1):
        md += f"{i}. {q}\n"

    md += f"""
### 🚦 Gate 판단
- **검색 필요**: `{step1['needs_search']}`
"""
    if step1['search_skip_reason']:
        md += f"- **스킵 이유**: {step1['search_skip_reason']}\n"
    if step1['internal_solution']:
        md += f"\n**내부 솔루션**:\n{step1['internal_solution']}\n"

    md += """
---

## 🔎 2단계: Perplexity 검색

"""
    if step2.get('skipped'):
        md += f"### ⏭️ 검색 스킵\n- 이유: {step2.get('reason', 'N/A')}\n"
    else:
        md += f"""### 검색 쿼리
```
{step2['query']}
```

### Evidence ({len(step2['findings'])}개)

| # | 사실 | 출처 |
|---|------|------|
"""
        for i, f in enumerate(step2['findings'], 1):
            fact = f['fact'][:80].replace('\n', ' ') + '...' if len(f['fact']) > 80 else f['fact']
            md += f"| {i} | {fact} | {f['source_url']} |\n"

        md += f"""
### 📎 Citations
"""
        for url in step2.get('citations', []):
            md += f"- {url}\n"

        md += f"""
### Raw Summary
```
{step2['summary'][:1500]}
```
"""

    md += """
---

## 📋 3단계: 구조화된 결과

"""
    md += f"""### 관찰된 증상
{step3['observed']}

### 🎯 가능한 원인
"""
    for c in step3['likely_causes']:
        md += f"- **{c.get('cause', 'N/A')}** (출처: {c.get('source', 'N/A')})\n"

    md += """
### ✅ 즉시 확인
"""
    for ch in step3['immediate_checks']:
        md += f"- {ch}\n"

    md += """
### 🔧 해결책
"""
    for i, s in enumerate(step3['solutions'], 1):
        md += f"\n**{i}. {s.get('title', 'N/A')}** (난이도: {s.get('difficulty', 'N/A')})\n"
        md += f"- 출처: {s.get('source', 'N/A')}\n"
        for step in s.get('steps', []):
            md += f"  - {step}\n"

    md += """
### ❓ 추가 정보 필요
"""
    for info in step3['need_more_info']:
        md += f"- {info}\n"

    md += f"""
---

## 📊 Raw JSON

<details>
<summary>전체 데이터</summary>

```json
{json.dumps(results, indent=2, ensure_ascii=False)}
```

</details>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"\n[OK] 저장됨: {output_path}")


async def main():
    """이미지 파일로 테스트"""
    if len(sys.argv) < 2:
        print("사용법: python test_inline.py <이미지_경로>")
        return

    image_path = sys.argv[1]
    with open(image_path, 'rb') as f:
        image_bytes = f.read()

    results = await test_with_image_bytes(image_bytes)
    save_markdown(results)


if __name__ == "__main__":
    asyncio.run(main())
