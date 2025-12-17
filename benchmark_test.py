"""
G-code 분석 벤치마킹 테스트
4개 파일을 분석하고 결과를 JSON으로 저장
"""
import asyncio
import json
from dataclasses import asdict
from gcode_analyzer.parser import parse_gcode
from gcode_analyzer.temp_tracker import extract_temp_events
from gcode_analyzer.section_detector import detect_sections
from gcode_analyzer.rule_engine import run_basic_checks, extract_data_for_llm
from gcode_analyzer.llm.issue_detector import detect_issues_with_llm, convert_to_legacy_format


async def analyze_file(path):
    print(f'\n{"="*60}')
    print(f'Analyzing: {path}')
    print(f'{"="*60}')

    result = parse_gcode(path)
    lines = result.lines
    print(f'Total lines: {len(lines)}')

    temp_events = extract_temp_events(lines)
    print(f'Temperature events: {len(temp_events)}')

    boundaries = detect_sections(lines)
    print(f'Sections: START(1~{boundaries.start_end}), BODY({boundaries.start_end}~{boundaries.body_end}), END({boundaries.body_end}~{boundaries.total_lines})')

    # 기본 체크
    output = run_basic_checks(lines, temp_events, boundaries)
    print(f'\nBasic checks:')
    for check in output.basic_checks:
        status = "PASS" if check.passed else "FAIL"
        print(f'  [{status}] {check.check_name}: {check.message}')

    # 치명적 플래그
    if output.critical_flags:
        print(f'\nCritical flags: {output.critical_flags}')
    else:
        print(f'\nNo critical flags')

    # LLM 분석용 데이터
    extracted = extract_data_for_llm(lines, temp_events, boundaries)
    extracted_dict = asdict(extracted)

    # LLM 이슈 탐지
    basic_checks_dict = [
        {'check_name': c.check_name, 'passed': c.passed, 'message': c.message}
        for c in output.basic_checks
    ]

    print('\nRunning LLM issue detection (3-way parallel)...')
    analysis = await detect_issues_with_llm(extracted_dict, basic_checks_dict, 'PLA')

    print(f'\nLLM detected {len(analysis.issues)} issues:')
    for i, issue in enumerate(analysis.issues, 1):
        print(f'\n  [{i}] {issue.severity.upper()} - {issue.type}')
        print(f'      Line: {issue.line}')
        print(f'      Description: {issue.description}')
        print(f'      Evidence: {issue.evidence}')
        print(f'      Fix: {issue.fix}')
        print(f'      Source: {issue.source}')

    print(f'\nSummaries:')
    for key, val in analysis.summaries.items():
        print(f'  [{key}] {val}')

    print(f'\nToken usage: {analysis.token_usage}')

    return {
        'file': path,
        'total_lines': len(lines),
        'temp_events': len(temp_events),
        'basic_checks': [
            {'name': c.check_name, 'passed': c.passed, 'message': c.message}
            for c in output.basic_checks
        ],
        'critical_flags': output.critical_flags,
        'llm_issues': [
            {
                'type': i.type,
                'severity': i.severity,
                'line': i.line,
                'description': i.description,
                'evidence': i.evidence,
                'fix': i.fix,
                'source': i.source
            }
            for i in analysis.issues
        ],
        'summaries': analysis.summaries,
        'token_usage': analysis.token_usage
    }


async def main():
    files = [
        r'C:\Users\USER\Downloads\armoredtyrannosaurus (1).gcode',
        r'C:\Users\USER\Downloads\1765938755263_18_PLA_1h37m.gcode',
        r'C:\Users\USER\Downloads\1765896343738_gg_fixed_bed55_photo_applied.gcode',
        r'C:\Users\USER\Downloads\1765801225883_hh.gcode',
    ]

    all_results = []

    for f in files:
        try:
            result = await analyze_file(f)
            all_results.append(result)
        except Exception as e:
            print(f'\nError analyzing {f}:')
            import traceback
            traceback.print_exc()
            all_results.append({
                'file': f,
                'error': str(e)
            })

    # 결과 저장
    with open('benchmark_results.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f'\n\n{"="*60}')
    print('BENCHMARK COMPLETE')
    print(f'{"="*60}')
    print(f'Results saved to benchmark_results.json')

    return all_results


if __name__ == '__main__':
    asyncio.run(main())
