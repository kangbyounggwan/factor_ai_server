"""
G-code 패치 생성기
발견된 문제에 대한 수정 제안 생성
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from .models import GCodeLine
from .segment_extractor import SlicerDetector, SlicerType
import re


# 벤더별 확장 파라미터 매핑
VENDOR_EXTENSIONS = {
    # Bambu Lab 프린터 (BambuStudio, OrcaSlicer 사용)
    # H: 히터 인덱스 또는 타겟 온도, P: 추가 파라미터
    "bambu": {
        "slicers": [SlicerType.BAMBUSTUDIO, SlicerType.ORCASLICER],
        "params": ["H", "P"],
        "description": "Bambu Lab printer extension"
    },
    # Prusa 프린터
    "prusa": {
        "slicers": [SlicerType.PRUSASLICER],
        "params": [],
        "description": "Prusa printer extension"
    },
}

@dataclass
class PatchSuggestion:
    """개별 패치 제안"""
    line_index: int
    original_line: str
    action: str  # "delete", "modify", "add", "review"
    new_line: Optional[str]
    reason: str
    priority: int
    issue_type: str
    vendor_extension: Optional[Dict[str, Any]] = None  # 벤더 확장 정보
    autofix_allowed: bool = True  # 자동 패치 허용 여부

@dataclass
class PatchPlan:
    """전체 패치 계획"""
    file_path: str
    total_patches: int
    patches: List[PatchSuggestion]
    estimated_quality_improvement: int  # 0-100 점수 개선 예상치

def _detect_vendor_extension(
    line: str,
    slicer_type: Optional[SlicerType] = None
) -> Optional[Dict[str, Any]]:
    """
    벤더 확장 파라미터 감지 (Bambu H, P 등)

    슬라이서 정보가 있으면 더 정확하게 벤더 식별 가능.

    예: M109 S25 H140 → {"H": 140, "vendor": "bambu", "confidence": "high"}

    Args:
        line: G-code 라인
        slicer_type: 감지된 슬라이서 타입 (optional)

    Returns:
        벤더 확장 정보 또는 None
    """
    if not line:
        return None

    # H 파라미터 (Bambu 히터 인덱스 또는 타겟 온도)
    h_match = re.search(r'\bH(\d+)', line, re.IGNORECASE)
    # P 파라미터 (Bambu 추가 파라미터)
    p_match = re.search(r'\bP(\d+)', line, re.IGNORECASE)

    if not (h_match or p_match):
        return None

    # 슬라이서 정보로 벤더 확정
    detected_vendor = None
    confidence = "low"

    if slicer_type:
        for vendor_name, vendor_info in VENDOR_EXTENSIONS.items():
            if slicer_type in vendor_info["slicers"]:
                detected_vendor = vendor_name
                confidence = "high"
                break

    # 슬라이서 정보 없으면 파라미터로 추정
    if not detected_vendor:
        if h_match or p_match:
            # H, P 파라미터는 Bambu 특유의 확장
            detected_vendor = "bambu"
            confidence = "medium"  # 슬라이서 정보 없이 추정

    if detected_vendor:
        vendor_result = {
            "vendor": detected_vendor,
            "confidence": confidence
        }
        if h_match:
            vendor_result["H"] = int(h_match.group(1))
        if p_match:
            vendor_result["P"] = int(p_match.group(1))
        return vendor_result

    return None


def _is_temperature_command(line: str) -> bool:
    """온도 관련 명령어인지 확인"""
    if not line:
        return False
    temp_cmds = ["M104", "M109", "M140", "M190", "M106"]
    return any(cmd in line.upper() for cmd in temp_cmds)


def identify_vendor_from_gcode(lines: List[GCodeLine]) -> Dict[str, Any]:
    """
    G-code 파일에서 벤더/슬라이서 정보 식별

    Args:
        lines: 파싱된 G-code 라인들

    Returns:
        {
            "slicer": SlicerType,
            "slicer_name": str,
            "slicer_version": str or None,
            "vendor": str or None,
            "vendor_extensions_found": List[Dict]
        }
    """
    # 슬라이서 감지
    slicer_type, slicer_version = SlicerDetector.detect(lines)

    slicer_name_map = {
        SlicerType.BAMBUSTUDIO: "BambuStudio",
        SlicerType.ORCASLICER: "OrcaSlicer",
        SlicerType.CURA: "Cura",
        SlicerType.PRUSASLICER: "PrusaSlicer",
        SlicerType.SIMPLIFY3D: "Simplify3D",
        SlicerType.IDEAMAKER: "IdeaMaker",
        SlicerType.UNKNOWN: "Unknown",
    }

    # 슬라이서로 벤더 추정
    vendor = None
    for vendor_name, vendor_info in VENDOR_EXTENSIONS.items():
        if slicer_type in vendor_info["slicers"]:
            vendor = vendor_name
            break

    # 벤더 확장 파라미터 검색 (처음 500줄)
    vendor_extensions_found = []
    for idx, line in enumerate(lines[:500]):
        raw = line.raw or ""
        if _is_temperature_command(raw):
            ext = _detect_vendor_extension(raw, slicer_type)
            if ext:
                vendor_extensions_found.append({
                    "line": idx + 1,
                    "raw": raw.strip()[:80],
                    "extension": ext
                })
                if len(vendor_extensions_found) >= 5:
                    break

    return {
        "slicer": slicer_type,
        "slicer_name": slicer_name_map.get(slicer_type, "Unknown"),
        "slicer_version": slicer_version,
        "vendor": vendor,
        "vendor_extensions_found": vendor_extensions_found
    }


def generate_patch_plan(
    issues: List[Dict[str, Any]],
    lines: List[GCodeLine],
    file_path: str,
    slicer_type: Optional[SlicerType] = None
) -> PatchPlan:
    """
    발견된 문제들에 대한 패치 계획 생성

    Args:
        issues: 발견된 문제 목록
        lines: 파싱된 G-code 라인들
        file_path: 파일 경로
        slicer_type: 슬라이서 타입 (SlicerType enum)
    """
    patches = []

    # 슬라이서 타입이 없으면 자동 감지 시도
    detected_slicer = slicer_type
    if not detected_slicer and lines:
        detected_slicer, _ = SlicerDetector.detect(lines)

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

        # 벤더 확장 파라미터 감지 (슬라이서 정보 활용)
        vendor_extension = _detect_vendor_extension(original_line, detected_slicer)
        autofix_allowed = True
        action = "review"
        new_line = None

        # Bambu 벤더 확장이 있는 온도 명령 → 자동 패치 금지, 검토 필요로 전환
        if vendor_extension and _is_temperature_command(original_line):
            # 온도 관련 이슈인데 H 파라미터가 있으면 → 검토 필요
            if issue_type in ["temperature_error", "temp_error", "dangerous_temp",
                             "cold_extrusion", "overtemp"]:
                autofix_allowed = False
                action = "review"
                new_line = None
                # 이유에 벤더 확장 정보 추가 (confidence 포함)
                confidence = vendor_extension.get("confidence", "unknown")
                vendor_note = f" [{vendor_extension.get('vendor', 'unknown').upper()} 벤더 확장 감지: H={vendor_extension.get('H', '?')}, 신뢰도={confidence}]"
                fix_action = (fix_action or issue.get("description", "")) + vendor_note

        # 패치 액션 결정 (벤더 확장으로 인한 review가 아닌 경우)
        if autofix_allowed:
            if fix_gcode and fix_gcode.lower() not in ["null", "none", ""]:
                # 수정 제안이 있음
                if "제거" in fix_action or "삭제" in fix_action:
                    action = "delete"
                    new_line = None
                else:
                    action = "modify"
                    new_line = fix_gcode.split("\n")[0] if fix_gcode else None
            elif "제거" in fix_action or "삭제" in fix_action:
                action = "delete"
                new_line = None
            elif "추가" in fix_action or "삽입" in fix_action:
                action = "add"
                new_line = fix_gcode.split("\n")[0] if fix_gcode else None
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
            issue_type=issue_type,
            vendor_extension=vendor_extension,
            autofix_allowed=autofix_allowed
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

        if patch.action == "delete":
            lines.append(f"    액션: ❌ 삭제")
        elif patch.action == "modify" and patch.new_line:
            lines.append(f"    액션: ✏️ 수정 → {patch.new_line[:60]}...")
        elif patch.action == "add" and patch.new_line:
            lines.append(f"    액션: ➕ 추가 → {patch.new_line[:60]}...")
        else:
            lines.append(f"    액션: ⚠️ 검토 필요")

        # 벤더 확장 정보 표시
        if patch.vendor_extension:
            lines.append(f"    벤더: {patch.vendor_extension}")

        if not patch.autofix_allowed:
            lines.append(f"    ⚠️ 자동 패치 불가 - 사용자 확인 필요")

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

    # autofix_allowed=True인 패치만 적용
    patches_by_action = {
        "delete": [],
        "modify": [],
        "add": []
    }

    for patch in patch_plan.patches:
        # 자동 패치가 허용된 경우만 적용
        if not patch.autofix_allowed:
            applied_patches.append({
                "action": "skipped",
                "line": patch.line_index,
                "reason": "자동 패치 불가 - 사용자 확인 필요",
                "vendor_extension": patch.vendor_extension
            })
            continue

        if patch.action == "delete":
            patches_by_action["delete"].append(patch)
        elif patch.action == "modify" and patch.new_line:
            patches_by_action["modify"].append(patch)
        elif patch.action == "add" and patch.new_line:
            patches_by_action["add"].append(patch)

    # 수정 먼저 적용
    for patch in patches_by_action["modify"]:
        idx = patch.line_index - 1
        if 0 <= idx < len(new_lines):
            old_line = new_lines[idx]
            new_lines[idx] = patch.new_line + "\n"
            applied_patches.append({
                "action": "modify",
                "line": patch.line_index,
                "old": old_line.strip(),
                "new": patch.new_line.strip()
            })

    # 삭제는 역순으로 적용
    delete_indices = sorted([p.line_index - 1 for p in patches_by_action["delete"]], reverse=True)
    for idx in delete_indices:
        if 0 <= idx < len(new_lines):
            old_line = new_lines[idx]
            del new_lines[idx]
            applied_patches.append({
                "action": "delete",
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
