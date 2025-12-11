import sys
import argparse
import json
from .parser import parse_gcode
from .summary import summarize_gcode

def main():
    parser = argparse.ArgumentParser(description="G-code Analyzer CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Summarize command
    sum_parser = subparsers.add_parser("summarize", help="Summarize G-code file")
    sum_parser.add_argument("file", help="Path to G-code file")

    # Analyze command (기존 규칙 기반 - deprecated)
    analyze_parser = subparsers.add_parser("analyze", help="[Legacy] Rule-based analysis")
    analyze_parser.add_argument("file", help="Path to G-code file")

    # Workflow command (새로운 LLM 기반)
    workflow_parser = subparsers.add_parser("workflow", help="Run LLM-based analysis workflow")
    workflow_parser.add_argument("file", help="Path to G-code file")
    workflow_parser.add_argument("--filament", "-f", help="Filament type (PLA, ABS, PETG, TPU)", default=None)
    workflow_parser.add_argument("--auto-apply", "-a", action="store_true", help="Auto apply patches without confirmation")
    workflow_parser.add_argument("--no-patch", "-n", action="store_true", help="Skip patch application")

    args = parser.parse_args()

    if args.command == "summarize":
        try:
            parsed = parse_gcode(args.file)
            summary = summarize_gcode(parsed)
            print(json.dumps(summary.dict(), indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
            
    elif args.command == "analyze":
        # Legacy: 규칙 기반 분석 (하위 호환)
        try:
            from .temp_tracker import extract_temp_events
            from .anomaly_detector import detect_anomalies
            
            parsed = parse_gcode(args.file)
            summary = summarize_gcode(parsed)
            temp_events = extract_temp_events(parsed)
            anomalies = detect_anomalies(parsed, temp_events)
            
            result = {
                "summary": summary.dict(),
                "anomalies": [a.dict() for a in anomalies]
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "workflow":
        # 새로운 LLM 기반 워크플로우
        try:
            from .analyzer import run_analysis_sync
            
            print("🔄 G-code 분석 워크플로우 시작...", file=sys.stderr)
            
            result = run_analysis_sync(
                file_path=args.file,
                filament_type=args.filament,
                auto_approve=False  # 처음에는 승인 없이 분석만
            )
            
            # 타임라인 출력
            print("\n📊 분석 타임라인:", file=sys.stderr)
            for event in result.get("timeline", []):
                status_icon = "✅" if event["status"] == "done" else "🔄"
                print(f"  {status_icon} {event['label']}", file=sys.stderr)
            
            # 분석 통계 출력
            stats = result.get("final_summary", {}).get("analysis_stats", {})
            if stats:
                print("\n📈 분석 통계:", file=sys.stderr)
                print(f"  총 온도 이벤트: {stats.get('total_temp_events', 0)}개", file=sys.stderr)
                by_section = stats.get("by_section", {})
                if by_section:
                    print(f"  ├─ START_GCODE: {by_section.get('START_GCODE', 0)}개", file=sys.stderr)
                    print(f"  ├─ BODY: {by_section.get('BODY', 0)}개", file=sys.stderr)
                    print(f"  └─ END_GCODE: {by_section.get('END_GCODE', 0)}개", file=sys.stderr)
                print(f"  정상 이벤트: {stats.get('normal_events', 0)}개", file=sys.stderr)
                print(f"  LLM 분석 대상: {stats.get('analyzed_by_llm', 0)}개", file=sys.stderr)
                print(f"  확인된 문제: {stats.get('confirmed_issues', 0)}개", file=sys.stderr)
            
            # 결과 JSON 출력
            print("\n📋 최종 분석 결과:", file=sys.stderr)
            final_summary = result.get("final_summary", {})
            # analysis_stats, patch_preview는 이미 출력했으므로 제외
            output_summary = {k: v for k, v in final_summary.items() 
                           if k not in ["analysis_stats", "patch_preview"]}
            print(json.dumps(output_summary, indent=2, ensure_ascii=False))
            
            # 발견된 문제 출력
            issues = result.get("issues_found", [])
            if issues:
                print(f"\n⚠️ 발견된 문제: {len(issues)}개", file=sys.stderr)
                for issue in issues:
                    section = issue.get("section", "?")
                    line_idx = issue.get("event_line_index", "?")
                    desc = issue.get("description", "N/A")[:100]
                    print(f"  [{section}] Line {line_idx}: {desc}", file=sys.stderr)
            else:
                print("\n✅ 문제가 발견되지 않았습니다.", file=sys.stderr)
            
            # ===== 패치 승인 흐름 (NEW) =====
            patch_plan = result.get("patch_plan")
            if patch_plan and patch_plan.get("total_patches", 0) > 0:
                print("\n" + "=" * 60, file=sys.stderr)
                print("📝 G-code 수정 제안", file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                
                # 패치 미리보기 출력
                patch_preview = final_summary.get("patch_preview", "")
                if patch_preview:
                    print(patch_preview, file=sys.stderr)
                else:
                    print(f"총 {patch_plan['total_patches']}개 수정 제안이 있습니다.", file=sys.stderr)
                    for p in patch_plan.get("patches", [])[:5]:  # 처음 5개만
                        print(f"  Line {p['line_index']}: {p['action']} - {p['issue_type']}", file=sys.stderr)
                    if patch_plan['total_patches'] > 5:
                        print(f"  ... 외 {patch_plan['total_patches'] - 5}개", file=sys.stderr)
                
                print("\n" + "-" * 60, file=sys.stderr)
                
                # 사용자 승인 요청
                if args.no_patch:
                    print("ℹ️ --no-patch 옵션으로 패치 적용을 건너뜁니다.", file=sys.stderr)
                    apply_patch = False
                elif args.auto_apply:
                    print("ℹ️ --auto-apply 옵션으로 자동 적용합니다.", file=sys.stderr)
                    apply_patch = True
                else:
                    # 대화형 승인 요청
                    print("\n수정 사항을 적용하시겠습니까?", file=sys.stderr)
                    print("  [Y] 예, 수정된 G-code 파일을 생성합니다", file=sys.stderr)
                    print("  [N] 아니오, 분석 결과만 확인합니다", file=sys.stderr)
                    print("  [V] 상세 변경 사항을 봅니다", file=sys.stderr)
                    
                    while True:
                        try:
                            choice = input("\n선택 (Y/N/V): ").strip().upper()
                        except EOFError:
                            choice = "N"
                            break
                        
                        if choice == "Y":
                            apply_patch = True
                            break
                        elif choice == "N":
                            apply_patch = False
                            break
                        elif choice == "V":
                            # 상세 변경 사항 출력
                            print("\n📋 상세 변경 사항:", file=sys.stderr)
                            for i, p in enumerate(patch_plan.get("patches", []), 1):
                                print(f"\n[{i}] Line {p['line_index']} ({p['issue_type']})", file=sys.stderr)
                                print(f"    현재: {p['original_line'][:80]}", file=sys.stderr)
                                if p['action'] == 'remove':
                                    print(f"    수정: ❌ 삭제", file=sys.stderr)
                                elif p['action'] == 'modify' and p.get('new_line'):
                                    print(f"    수정: ✏️ {p['new_line'][:80]}", file=sys.stderr)
                                else:
                                    print(f"    수정: ⚠️ 수동 검토 필요", file=sys.stderr)
                                print(f"    이유: {p['reason'][:100]}...", file=sys.stderr)
                        else:
                            print("Y, N, 또는 V를 입력해주세요.", file=sys.stderr)
                
                # 패치 적용
                if apply_patch:
                    print("\n🔧 패치 적용 중...", file=sys.stderr)
                    
                    from .patcher import generate_patch_plan, apply_patches, save_patched_gcode, PatchPlan, PatchSuggestion
                    
                    # PatchPlan 복원
                    patches = [
                        PatchSuggestion(
                            line_index=p["line_index"],
                            original_line=p["original_line"],
                            action=p["action"],
                            new_line=p.get("new_line"),
                            reason=p["reason"],
                            priority=i,
                            issue_type=p["issue_type"]
                        )
                        for i, p in enumerate(patch_plan["patches"])
                    ]
                    
                    plan = PatchPlan(
                        file_path=args.file,
                        total_patches=patch_plan["total_patches"],
                        patches=patches,
                        estimated_quality_improvement=patch_plan.get("estimated_improvement", 0)
                    )
                    
                    # 원본 파일 읽기
                    with open(args.file, "r", encoding="utf-8") as f:
                        original_lines = f.readlines()
                    
                    # 패치 적용
                    new_lines, applied_log = apply_patches(original_lines, plan)
                    
                    # 새 파일로 저장
                    new_file_path = save_patched_gcode(new_lines, args.file)
                    
                    print(f"\n✅ 패치 적용 완료!", file=sys.stderr)
                    print(f"  수정된 항목: {len(applied_log)}개", file=sys.stderr)
                    print(f"  저장 위치: {new_file_path}", file=sys.stderr)
                    
                    # 적용된 패치 요약
                    print("\n적용된 변경 사항:", file=sys.stderr)
                    for log in applied_log[:5]:
                        if log['action'] == 'modified':
                            print(f"  Line {log['line']}: {log['old'][:40]}... → {log['new'][:40]}...", file=sys.stderr)
                        else:
                            print(f"  Line {log['line']}: 삭제됨", file=sys.stderr)
                    if len(applied_log) > 5:
                        print(f"  ... 외 {len(applied_log) - 5}개", file=sys.stderr)
                else:
                    print("\n패치 적용을 건너뛰었습니다.", file=sys.stderr)
                    print("수정 제안은 위 분석 결과에서 확인할 수 있습니다.", file=sys.stderr)
                
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()

