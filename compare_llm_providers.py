"""
LLM Provider Comparison Script
Gemini vs GPT-4o accuracy comparison on G-code analysis
"""
import asyncio
import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gcode_analyzer.analyzer import run_analysis

# Test files
TEST_FILES = [
    r"C:\Users\USER\Downloads\1765894653684_gg_fixed_heateroff_at_end.gcode",
    r"C:\Users\USER\Downloads\1765728704381_cup2_14_2_A1_modified_modified.gcode",
    r"C:\Users\USER\Downloads\1765788815298_3DBenchy_PLA_56m24s.gcode",
    r"C:\Users\USER\Downloads\snowman.gcode",
]

PROVIDERS = ["flash-lite", "flash", "pro"]

# 모델 매핑
MODEL_MAP = {
    "flash-lite": "gemini-2.5-flash-lite",
    "flash": "gemini-2.5-flash",
    "pro": "gemini-2.5-pro",
}


async def analyze_with_provider(file_path: str, provider: str) -> Dict[str, Any]:
    """Run analysis with specific provider"""
    # Set provider in environment
    os.environ["LLM_PROVIDER"] = "gemini"

    # Reload client module and override model
    import importlib
    import gcode_analyzer.llm.client as client_module
    importlib.reload(client_module)

    # Override model for this test
    client_module.MODELS["gemini"] = MODEL_MAP[provider]

    try:
        result = await run_analysis(
            file_path=file_path,
            filament_type="PLA",
            auto_approve=False,
            analysis_mode="full",
            language="ko"
        )
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def extract_metrics(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract key metrics from analysis result"""
    if not result.get("success"):
        return {"error": result.get("error")}

    data = result["result"]

    # Issues
    issues = data.get("issues_found", [])
    rule_issues = [i for i in issues if i.get("from_rule_engine")]
    llm_issues = [i for i in issues if not i.get("from_rule_engine")]

    # Severity counts
    severity_counts = {}
    for issue in issues:
        sev = issue.get("severity", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Expert assessment
    expert = data.get("expert_assessment", {})

    # Token usage
    tokens = data.get("token_usage", {})

    return {
        "total_issues": len(issues),
        "rule_engine_issues": len(rule_issues),
        "llm_detected_issues": len(llm_issues),
        "severity_breakdown": severity_counts,
        "quality_score": expert.get("quality_score"),
        "quality_grade": expert.get("quality_grade"),
        "token_usage": tokens,
        "issues_detail": [
            {
                "line": i.get("event_line_index") or i.get("line_index") or i.get("line"),
                "type": i.get("issue_type") or i.get("event_type"),
                "severity": i.get("severity"),
                "from_rule": i.get("from_rule_engine", False),
                "description": (i.get("description") or "")[:100]
            }
            for i in issues
        ]
    }


async def run_comparison():
    """Run full comparison between providers"""
    print("=" * 70)
    print("LLM Provider Comparison: Gemini vs GPT-4o")
    print("=" * 70)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results = {}

    for file_path in TEST_FILES:
        file_name = os.path.basename(file_path)

        # Check if file exists
        if not os.path.exists(file_path):
            print(f"[SKIP] File not found: {file_name}")
            continue

        print(f"\n{'='*70}")
        print(f"File: {file_name}")
        print("=" * 70)

        results[file_name] = {}

        for provider in PROVIDERS:
            print(f"\n--- Testing with {provider.upper()} ---")

            start_time = datetime.now()
            result = await analyze_with_provider(file_path, provider)
            elapsed = (datetime.now() - start_time).total_seconds()

            metrics = extract_metrics(result)
            metrics["elapsed_seconds"] = elapsed

            results[file_name][provider] = metrics

            # Print summary
            if "error" in metrics:
                print(f"  ERROR: {metrics['error']}")
            else:
                print(f"  Issues Found: {metrics['total_issues']}")
                print(f"    - Rule Engine: {metrics['rule_engine_issues']}")
                print(f"    - LLM Detected: {metrics['llm_detected_issues']}")
                print(f"  Quality Score: {metrics['quality_score']} ({metrics['quality_grade']})")
                print(f"  Time: {elapsed:.1f}s")
                print(f"  Tokens: {metrics['token_usage']}")

                if metrics['issues_detail']:
                    print(f"  Issue Details:")
                    for issue in metrics['issues_detail']:
                        src = "[RULE]" if issue['from_rule'] else "[LLM]"
                        print(f"    {src} Line {issue['line']}: {issue['type']} ({issue['severity']})")

    # Final comparison summary
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)

    for file_name, file_results in results.items():
        print(f"\n{file_name}:")

        gemini = file_results.get("gemini", {})
        openai = file_results.get("openai", {})

        if "error" not in gemini and "error" not in openai:
            print(f"  {'Metric':<25} {'Gemini':<15} {'GPT-4o':<15}")
            print(f"  {'-'*55}")
            print(f"  {'Total Issues':<25} {gemini.get('total_issues', 'N/A'):<15} {openai.get('total_issues', 'N/A'):<15}")
            print(f"  {'Rule Engine Issues':<25} {gemini.get('rule_engine_issues', 'N/A'):<15} {openai.get('rule_engine_issues', 'N/A'):<15}")
            print(f"  {'LLM Detected Issues':<25} {gemini.get('llm_detected_issues', 'N/A'):<15} {openai.get('llm_detected_issues', 'N/A'):<15}")
            print(f"  {'Quality Score':<25} {gemini.get('quality_score', 'N/A'):<15} {openai.get('quality_score', 'N/A'):<15}")
            print(f"  {'Quality Grade':<25} {gemini.get('quality_grade', 'N/A'):<15} {openai.get('quality_grade', 'N/A'):<15}")
            print(f"  {'Time (seconds)':<25} {gemini.get('elapsed_seconds', 0):.1f}{'s':<14} {openai.get('elapsed_seconds', 0):.1f}s")

    # Save detailed results to JSON
    output_path = os.path.join(os.path.dirname(__file__), "llm_comparison_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nDetailed results saved to: {output_path}")
    print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return results


if __name__ == "__main__":
    asyncio.run(run_comparison())
