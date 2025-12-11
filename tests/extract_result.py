import json

try:
    with open(r"c:\Users\USER\factor_AI_python\tests\full_result.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    final_summary = data.get("final_summary", {})
    issues = final_summary.get("issues_by_priority", [])
    
    print("# Final Summary Issues")
    for issue in issues:
        print(f"- Priority: {issue.get('priority')}")
        print(f"  - Type: {issue.get('issue_type')}")
        print(f"  - Line: {issue.get('line_index')}")
        print(f"  - Description: {issue.get('description')}")
        print("")
        
except Exception as e:
    print(f"Error: {e}")
