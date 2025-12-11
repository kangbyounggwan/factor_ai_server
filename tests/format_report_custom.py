import json
import sys

def main():
    try:
        with open(r"c:\Users\USER\factor_AI_python\tests\full_result.json", "r", encoding="utf-8") as f:
            result = json.load(f)
    except FileNotFoundError:
        print("Error: full_result.json not found.")
        return

    # =============================================
    # 프린팅 정보 (LLM 요약)
    # =============================================
    printing_info = result.get("printing_info", {})
    print(f"\n=== 프린팅 정보 (LLM 요약) ===")
    print(f"개요: {printing_info.get('overview', 'N/A')}")
    
    chars = printing_info.get("characteristics", {})
    print(f"\n특성:")
    print(f"  - 복잡도: {chars.get('complexity', 'N/A')}")
    print(f"  - 예상 품질: {chars.get('estimated_quality', 'N/A')}")
    print(f"  - 난이도: {chars.get('difficulty', 'N/A')}")
    
    print(f"\n온도 분석: {printing_info.get('temperature_analysis', 'N/A')}")
    print(f"속도 분석: {printing_info.get('speed_analysis', 'N/A')}")
    print(f"재료 사용량: {printing_info.get('material_usage', 'N/A')}")
    
    print(f"\n주의사항:")
    for w in printing_info.get("warnings", []):
        print(f"  - {w}")
    
    print(f"\n권장사항 (프린팅):")
    for r in printing_info.get("recommendations", []):
        print(f"  - {r}")
    
    print(f"\n프린팅 요약: {printing_info.get('summary_text', 'N/A')}")
    
    # =============================================
    # 종합 분석 데이터
    # =============================================
    comp = result.get("comprehensive_summary", {})
    print(f"\n=== 종합 분석 데이터 ===")
    print(f"슬라이서: {comp.get('slicer_info', 'N/A')}")
    
    print_time = comp.get("print_time", {})
    print(f"예상 출력 시간: {print_time.get('formatted_time', 'N/A')}")
    
    temp = comp.get("temperature", {})
    print(f"노즐 온도: {temp.get('nozzle_min', 0)}-{temp.get('nozzle_max', 0)}°C (평균: {temp.get('nozzle_avg', 0):.1f}°C)")
    print(f"베드 온도: {temp.get('bed_min', 0)}-{temp.get('bed_max', 0)}°C")
    
    ext = comp.get("extrusion", {})
    print(f"필라멘트: {ext.get('total_filament_used', 0):.2f}m")
    print(f"리트랙션: {ext.get('retraction_count', 0)}회")
    
    layer = comp.get("layer", {})
    print(f"레이어: {layer.get('total_layers', 0)}층")
    
    support = comp.get("support", {})
    if support.get('has_support'):
        print(f"서포트: 있음 ({support.get('support_ratio', 0):.1f}%)")
    else:
        print(f"서포트: 없음")
    
    # 최종 요약
    final_summary = result.get("final_summary", {})
    print(f"\n=== 최종 요약 ===")
    print(f"품질 점수: {final_summary.get('overall_quality_score', 'N/A')}점")
    print(f"총 이슈: {final_summary.get('total_issues_found', 0)}개")
    print(f"심각한 이슈: {final_summary.get('critical_issues', 0)}개")
    print(f"\n요약: {final_summary.get('summary', '')}")
    print(f"\n권장사항: {final_summary.get('recommendation', '')}")
    print(f"\n예상 개선: {final_summary.get('expected_improvement', '')}")
    
    # 발견된 이슈 목록
    issues = result.get("issues_found", [])
    # Filter issues that have 'has_issue' set to True
    real_issues = [i for i in issues if i.get("has_issue")]
    print(f"\n=== 발견된 이슈 ({len(real_issues)}개) ===")
    for idx, issue in enumerate(real_issues, 1):
        print(f"\n[{idx}] {issue.get('issue_type', 'unknown')}")
        print(f"    심각도: {issue.get('severity', 'N/A')}")
        # Prioritize 'line_index' but fallback to 'event_line_index' if needed
        line_idx = issue.get('line_index') or issue.get('event_line_index') or 'N/A'
        print(f"    라인: {line_idx}")
        print(f"    설명: {issue.get('description', '')}")
        print(f"    영향: {issue.get('impact', '')}")
        print(f"    제안: {issue.get('suggestion', '')}")
    
    # 토큰 사용량
    tokens = result.get("token_usage", {})
    print(f"\n=== 토큰 사용량 ===")
    print(f"입력: {tokens.get('input_tokens', 0):,}")
    print(f"출력: {tokens.get('output_tokens', 0):,}")
    print(f"총: {tokens.get('total_tokens', 0):,}")
    
    # 패치 제안
    patch_plan = result.get("patch_plan")
    if patch_plan:
        patches = patch_plan.get("patches", [])
        print(f"\n=== 패치 제안 ({len(patches)}개) ===")
        for idx, patch in enumerate(patches, 1):
            print(f"\n[{idx}] 라인 {patch.get('line_index')}: {patch.get('action')}")
            print(f"    원본: {patch.get('original_line', '').strip()}")
            if patch.get('new_line'):
                print(f"    수정: {patch.get('new_line').strip()}")
            print(f"    이유: {patch.get('reason', '')}")

if __name__ == "__main__":
    main()
