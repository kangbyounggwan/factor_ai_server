"""G-code 컨텍스트 추출 테스트"""
import sys
sys.path.insert(0, '.')

from gcode_analyzer.llm.issue_resolver import extract_gcode_context

# 테스트: G-code 파일 읽기
with open('C:/Users/USER/Downloads/snowman.gcode', 'r', encoding='utf-8') as f:
    gcode_content = f.read()

print(f'총 라인 수: {len(gcode_content.splitlines())}')

# 임의의 라인 번호로 테스트 (예: 137번 라인)
test_line = 137
context = extract_gcode_context(gcode_content, test_line, context_lines=30)
print(f'\n=== 라인 {test_line} 주변 30줄 컨텍스트 ===')
print(context[:3000])
