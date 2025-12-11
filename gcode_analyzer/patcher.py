"""
G-code 패치 생성기
발견된 문제에 대한 수정 제안 생성
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from .models import GCodeLine

@dataclass
class PatchSuggestion:
    """개별 패치 제안"""
    line_index: int
    original_line: str
    action: str  # "remove", "modify", "insert_before", "insert_after"
    new_line: Optional[str]
    reason: str
    priority: int
    issue_type: str

@dataclass
class PatchPlan:
    """전체 패치 계획"""
    file_path: str
    total_patches: int
    patches: List[PatchSuggestion]
    estimated_quality_improvement: int  # 0-100 점수 개선 예상치

def generate_patch_plan(
    issues: List[Dict[str, Any]],
    lines: List[GCodeLine],
    file_path: str
) -> PatchPlan:
    """
    발견된 문제들에 대한 패치 계획 생성
    """
    patches = []
    
    for issue in issues:
        line_index = issue.get("line_index") or 0
        issue_type = issue.get("issue_type") or "unknown"
        fix_gcode = issue.get("fix_gcode")
        fix_action = issue.get("fix_action") or ""
        priority = issue.get("priority") or 99
        
        # 원본 라인 찾기
        original_line = ""
        if 0 < line_index <= len(lines):
            original_line = lines[line_index - 1].raw.strip()
        
        # 패치 액션 결정
        if fix_gcode and fix_gcode.lower() not in ["null", "none", ""]:
            # 수정 제안이 있음
            if "제거" in fix_action or "삭제" in fix_action:
                action = "remove"
                new_line = None
            else:
                action = "modify"
                new_line = fix_gcode.split("\n")[0] if fix_gcode else None
        elif "제거" in fix_action or "삭제" in fix_action:
            action = "remove"
            new_line = None
        else:
            # 기본: 수정 필요하지만 구체적 코드 없음
            action = "review"
            new_line = None
        
        patches.append(PatchSuggestion(
            line_index=line_index,
            original_line=original_line,
            action=action,
            new_line=new_line,
            reason=fix_action[:200] if fix_action else issue.get("description", "")[:200],
            priority=priority,
            issue_type=issue_type
        ))
    
    # 우선순위로 정렬
    patches.sort(key=lambda p: p.priority)
    
    # 품질 개선 예상치 계산
    improvement = min(len(patches) * 10, 90)  # 패치당 10점, 최대 90점
    
    return PatchPlan(
        file_path=file_path,
        total_patches=len(patches),
        patches=patches,
        estimated_quality_improvement=improvement
    )

def format_patch_preview(patch_plan: PatchPlan) -> str:
    """
    사용자에게 보여줄 패치 미리보기 생성
    """
    lines = []
    lines.append(f"📝 G-code 수정 계획")
    lines.append(f"=" * 50)
    lines.append(f"파일: {patch_plan.file_path}")
    lines.append(f"총 수정 사항: {patch_plan.total_patches}개")
    lines.append(f"예상 품질 개선: +{patch_plan.estimated_quality_improvement}점")
    lines.append("")
    
    for i, patch in enumerate(patch_plan.patches, 1):
        lines.append(f"[{i}] Line {patch.line_index} ({patch.issue_type})")
        lines.append(f"    현재: {patch.original_line[:60]}...")
        
        if patch.action == "remove":
            lines.append(f"    수정: ❌ 삭제")
        elif patch.action == "modify" and patch.new_line:
            lines.append(f"    수정: ✏️ {patch.new_line[:60]}...")
        else:
            lines.append(f"    수정: ⚠️ 수동 검토 필요")
        
        lines.append(f"    이유: {patch.reason[:80]}...")
        lines.append("")
    
    return "\n".join(lines)

def apply_patches(
    original_lines: List[str],
    patch_plan: PatchPlan
) -> tuple[List[str], List[Dict]]:
    """
    패치를 적용하여 수정된 G-code 생성
    
    Returns:
        Tuple[List[str], List[Dict]]: (수정된 라인들, 적용된 패치 로그)
    """
    # 원본 복사
    new_lines = original_lines.copy()
    applied_patches = []
    
    # 삭제할 라인들을 먼저 수집 (역순으로 처리해야 인덱스 문제 없음)
    patches_by_action = {
        "remove": [],
        "modify": [],
        "insert": []
    }
    
    for patch in patch_plan.patches:
        if patch.action == "remove":
            patches_by_action["remove"].append(patch)
        elif patch.action == "modify" and patch.new_line:
            patches_by_action["modify"].append(patch)
    
    # 수정 먼저 적용
    for patch in patches_by_action["modify"]:
        idx = patch.line_index - 1
        if 0 <= idx < len(new_lines):
            old_line = new_lines[idx]
            new_lines[idx] = patch.new_line + "\n"
            applied_patches.append({
                "action": "modified",
                "line": patch.line_index,
                "old": old_line.strip(),
                "new": patch.new_line.strip()
            })
    
    # 삭제는 역순으로 적용
    remove_indices = sorted([p.line_index - 1 for p in patches_by_action["remove"]], reverse=True)
    for idx in remove_indices:
        if 0 <= idx < len(new_lines):
            old_line = new_lines[idx]
            del new_lines[idx]
            applied_patches.append({
                "action": "removed",
                "line": idx + 1,
                "old": old_line.strip()
            })
    
    return new_lines, applied_patches

def save_patched_gcode(
    new_lines: List[str],
    original_path: str,
    suffix: str = "_patched"
) -> str:
    """
    수정된 G-code를 새 파일로 저장
    """
    import os
    
    base, ext = os.path.splitext(original_path)
    new_path = f"{base}{suffix}{ext}"
    
    with open(new_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    return new_path
