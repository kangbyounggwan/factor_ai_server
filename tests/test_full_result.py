"""
전체 분석 결과 확인 테스트
- run_analysis 결과의 모든 필드를 출력
"""
import asyncio
import json
import os
import sys

# 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gcode_analyzer.analyzer import run_analysis


async def test_full_result():
    """전체 분석 결과 출력"""

    # 테스트 파일
    gcode_file = r"C:\Users\USER\Downloads\qqqqqqqqqqqqqqqqqq.gcode"

    if not os.path.exists(gcode_file):
        print(f"[ERROR] 파일 없음: {gcode_file}")
        return

    print("=" * 70)
    print("G-code 전체 분석 결과")
    print("=" * 70)

    # 분석 실행
    result = await run_analysis(
        file_path=gcode_file,
        analysis_mode="full"
    )

    # 결과의 모든 키 출력
    print("\n[1] 결과 최상위 키:")
    for key in result.keys():
        value = result[key]
        if isinstance(value, dict):
            print(f"  - {key}: dict ({len(value)} keys)")
        elif isinstance(value, list):
            print(f"  - {key}: list ({len(value)} items)")
        else:
            print(f"  - {key}: {type(value).__name__}")

    # ========================================
    # printing_info (LLM 요약)
    # ========================================
    print("\n" + "=" * 70)
    print("[2] printing_info (LLM 프린팅 요약)")
    print("=" * 70)

    printing_info = result.get("printing_info", {})

    print(f"\n--- 개요 ---")
    print(printing_info.get("overview", "N/A"))

    print(f"\n--- 특성 ---")
    chars = printing_info.get("characteristics", {})
    print(f"  복잡도: {chars.get('complexity', 'N/A')}")
    print(f"  예상 품질: {chars.get('estimated_quality', 'N/A')}")
    print(f"  난이도: {chars.get('difficulty', 'N/A')}")

    print(f"\n--- 온도 분석 ---")
    print(printing_info.get("temperature_analysis", "N/A"))

    print(f"\n--- 속도 분석 ---")
    print(printing_info.get("speed_analysis", "N/A"))

    print(f"\n--- 재료 사용량 ---")
    print(printing_info.get("material_usage", "N/A"))

    print(f"\n--- 주의사항 ---")
    for w in printing_info.get("warnings", []):
        print(f"  - {w}")

    print(f"\n--- 권장사항 ---")
    for r in printing_info.get("recommendations", []):
        print(f"  - {r}")

    print(f"\n--- 요약 텍스트 ---")
    print(printing_info.get("summary_text", "N/A"))

    # ========================================
    # comprehensive_summary (Python 분석)
    # ========================================
    print("\n" + "=" * 70)
    print("[3] comprehensive_summary (데이터 분석)")
    print("=" * 70)

    comp = result.get("comprehensive_summary", {})

    print(f"\n슬라이서: {comp.get('slicer_info', 'N/A')}")
    print(f"총 라인: {comp.get('total_lines', 0):,}")

    # 출력 시간
    print_time = comp.get("print_time", {})
    print(f"\n--- 출력 시간 ---")
    print(f"  총 시간: {print_time.get('formatted_time', 'N/A')}")
    print(f"  이동 시간: {print_time.get('travel_time_formatted', 'N/A')}")
    print(f"  출력 시간: {print_time.get('extrusion_time_formatted', 'N/A')}")

    # 온도
    temp = comp.get("temperature", {})
    print(f"\n--- 온도 ---")
    print(f"  노즐: {temp.get('nozzle_min', 0)}-{temp.get('nozzle_max', 0)}°C (평균: {temp.get('nozzle_avg', 0):.1f}°C)")
    print(f"  베드: {temp.get('bed_min', 0)}-{temp.get('bed_max', 0)}°C")
    print(f"  온도 변경: {temp.get('nozzle_changes', 0)}회")

    # 속도
    feed = comp.get("feed_rate", {})
    print(f"\n--- 속도 (mm/min) ---")
    print(f"  범위: {feed.get('min_speed', 0):.0f} - {feed.get('max_speed', 0):.0f}")
    print(f"  평균: {feed.get('avg_speed', 0):.0f}")
    print(f"  출력 속도: {feed.get('print_speed_avg', 0):.0f}")
    print(f"  이동 속도: {feed.get('travel_speed_avg', 0):.0f}")

    # 익스트루전
    ext = comp.get("extrusion", {})
    print(f"\n--- 익스트루전 ---")
    print(f"  필라멘트: {ext.get('total_filament_used', 0):.2f}m")
    print(f"  리트랙션: {ext.get('retraction_count', 0)}회")
    print(f"  평균 리트랙션: {ext.get('avg_retraction', 0):.2f}mm")

    # 레이어
    layer = comp.get("layer", {})
    print(f"\n--- 레이어 ---")
    print(f"  총 레이어: {layer.get('total_layers', 0)}층")
    print(f"  레이어 높이: {layer.get('avg_layer_height', 0):.2f}mm")

    # 서포트
    support = comp.get("support", {})
    print(f"\n--- 서포트 ---")
    print(f"  사용: {'예' if support.get('has_support') else '아니오'}")
    if support.get('has_support'):
        print(f"  비율: {support.get('support_ratio', 0):.1f}%")
        print(f"  레이어: {support.get('support_layers', 0)}개")

    # 팬
    fan = comp.get("fan", {})
    print(f"\n--- 팬 ---")
    print(f"  사용: {'예' if fan.get('has_fan_control') else '아니오'}")
    print(f"  평균 속도: {fan.get('avg_fan_speed', 0):.0f}%")

    # ========================================
    # expert_assessment (정답지)
    # ========================================
    print("\n" + "=" * 70)
    print("[4] expert_assessment (정답지)")
    print("=" * 70)

    expert = result.get("expert_assessment", {})
    if not expert:
        # 호환성을 위해 final_summary도 체크
        expert = result.get("final_summary", {}).get("expert_assessment", {})

    print(f"\n품질 등급: {expert.get('quality_grade', 'N/A')}")
    print(f"품질 점수: {expert.get('quality_score', 'N/A')}")
    
    chars = expert.get("print_characteristics", {})
    print(f"\n[특성]")
    print(f"  복잡도: {chars.get('complexity')}")
    print(f"  난이도: {chars.get('difficulty')}")
    print(f"  태그: {chars.get('tags')}")
    
    print(f"\n[총평]")
    print(expert.get("summary_text", "N/A"))

    print(f"\n[체크포인트]")
    check_points = expert.get("check_points", {})
    for k, v in check_points.items():
        print(f"  - {k}: {v.get('status')} ({v.get('comment')})")

    print(f"\n[주요 이슈]")
    for issue in expert.get("critical_issues", []):
        print(f"  - [{issue.get('severity')}] Line {issue.get('line')}: {issue.get('title')}")
        print(f"    제안: {issue.get('fix_proposal')}")

    print(f"\n[권장사항]")
    for rec in expert.get("overall_recommendations", []):
        print(f"  - {rec}")

    # JSON 저장
    print("\n" + "=" * 70)
    print("[저장]")
    print("=" * 70)

    output_path = r"c:\Users\USER\factor_AI_python\tests\full_result.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n결과 저장됨: {output_path}")


if __name__ == "__main__":
    asyncio.run(test_full_result())
