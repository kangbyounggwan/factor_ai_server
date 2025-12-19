"""
G-code Issue Types Database Helper

gcode_issue_types 테이블 관리 모듈
- 이슈 유형 조회/생성/업데이트
- 코드 기반 이슈 유형 자동 동기화
"""
import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from supabase import Client

logger = logging.getLogger(__name__)


# 코드에서 정의된 모든 이슈 유형 (DB와 동기화용)
DEFINED_ISSUE_TYPES: Dict[str, Dict[str, Any]] = {
    # === Temperature Issues ===
    "cold_extrusion": {
        "label": "압출 불량",
        "label_en": "Cold Extrusion",
        "description": "노즐 온도가 녹는점보다 낮아 압출이 불가능한 위험 상태",
        "category": "temperature",
        "severity_default": "high",
        "color": "red",
        "icon": "snowflake"
    },
    "early_temp_off": {
        "label": "조기 온도 차단",
        "label_en": "Early Temp Off",
        "description": "출력 완료 전 히팅 베드 또는 노즐 전원이 꺼지는 현상",
        "category": "temperature",
        "severity_default": "high",
        "color": "orange",
        "icon": "power"
    },
    "early_bed_off": {
        "label": "베드 조기 차단",
        "label_en": "Early Bed Off",
        "description": "출력 완료 전 베드 히터가 꺼지는 현상",
        "category": "temperature",
        "severity_default": "medium",
        "color": "orange",
        "icon": "power"
    },
    "extreme_cold": {
        "label": "극저온 상태",
        "label_en": "Extreme Cold",
        "description": "노즐 온도가 극도로 낮은 상태",
        "category": "temperature",
        "severity_default": "critical",
        "color": "red",
        "icon": "snowflake"
    },
    "nozzle_clog_risk": {
        "label": "노즐 막힘 위험",
        "label_en": "Nozzle Clog Risk",
        "description": "온도 변화가 급격하여 노즐 막힘 위험",
        "category": "temperature",
        "severity_default": "high",
        "color": "red",
        "icon": "alert-triangle"
    },
    "layer_adhesion_risk": {
        "label": "레이어 접착 위험",
        "label_en": "Layer Adhesion Risk",
        "description": "첫 레이어 온도 설정이 부적절",
        "category": "temperature",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "layers"
    },
    "rapid_temp_change": {
        "label": "급격한 온도 변화",
        "label_en": "Rapid Temperature Change",
        "description": "50°C 이상의 급격한 온도 변화 감지",
        "category": "temperature",
        "severity_default": "medium",
        "color": "orange",
        "icon": "thermometer"
    },
    "low_temp": {
        "label": "저온 상태",
        "label_en": "Low Temperature",
        "description": "권장 최소 온도 미만의 설정",
        "category": "temperature",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "thermometer"
    },
    "temp_wait_missing": {
        "label": "온도 대기 누락",
        "label_en": "Temperature Wait Missing",
        "description": "M104 설정 후 M109 대기 명령 누락",
        "category": "temperature",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "clock"
    },
    "temp_zero": {
        "label": "온도 0 설정",
        "label_en": "Temperature Zero",
        "description": "출력 중 온도가 0으로 설정됨",
        "category": "temperature",
        "severity_default": "high",
        "color": "red",
        "icon": "alert-circle"
    },
    "no_bed_temp": {
        "label": "베드 온도 미설정",
        "label_en": "No Bed Temperature",
        "description": "베드 온도 설정이 없음",
        "category": "temperature",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "thermometer"
    },
    "missing_bed_temp": {
        "label": "베드 온도 누락",
        "label_en": "Missing Bed Temperature",
        "description": "베드 온도 설정이 누락됨",
        "category": "temperature",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "thermometer"
    },
    "bed_temp_off_early": {
        "label": "베드 온도 조기 차단",
        "label_en": "Bed Temp Off Early",
        "description": "출력 완료 전 M140 S0으로 베드 온도 차단",
        "category": "temperature",
        "severity_default": "medium",
        "color": "orange",
        "icon": "power"
    },
    "missing_warmup": {
        "label": "예열 대기 누락",
        "label_en": "Missing Warmup",
        "description": "M104 설정 후 M109 대기 없이 진행",
        "category": "temperature",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "clock"
    },
    "excessive_temp": {
        "label": "과도한 온도",
        "label_en": "Excessive Temperature",
        "description": "설정 온도가 권장 범위를 초과",
        "category": "temperature",
        "severity_default": "high",
        "color": "red",
        "icon": "flame"
    },
    "dangerous_temp": {
        "label": "위험 온도",
        "label_en": "Dangerous Temperature",
        "description": "안전 범위를 벗어난 위험한 온도 설정",
        "category": "temperature",
        "severity_default": "critical",
        "color": "red",
        "icon": "alert-triangle"
    },

    # === Speed Issues ===
    "speed_mismatch": {
        "label": "속도 불일치",
        "label_en": "Speed Mismatch",
        "description": "이동 속도와 출력 속도의 비율이 부적절",
        "category": "speed",
        "severity_default": "low",
        "color": "blue",
        "icon": "activity"
    },
    "excessive_speed": {
        "label": "과속",
        "label_en": "Excessive Speed",
        "description": "출력 속도가 300mm/s를 초과",
        "category": "speed",
        "severity_default": "high",
        "color": "red",
        "icon": "zap"
    },
    "too_slow": {
        "label": "저속",
        "label_en": "Too Slow",
        "description": "출력 속도가 5mm/s 미만으로 너무 느림",
        "category": "speed",
        "severity_default": "low",
        "color": "blue",
        "icon": "clock"
    },
    "no_feed_rate": {
        "label": "피드레이트 누락",
        "label_en": "No Feed Rate",
        "description": "F 파라미터(피드레이트)가 누락됨",
        "category": "speed",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "alert-circle"
    },
    "rapid_accel": {
        "label": "급가속",
        "label_en": "Rapid Acceleration",
        "description": "급격한 가속/감속이 감지됨",
        "category": "speed",
        "severity_default": "medium",
        "color": "orange",
        "icon": "trending-up"
    },
    "inconsistent_speed": {
        "label": "불규칙한 속도",
        "label_en": "Inconsistent Speed",
        "description": "속도 변화가 불규칙하거나 일관성 없음",
        "category": "speed",
        "severity_default": "low",
        "color": "blue",
        "icon": "activity"
    },
    "zero_speed_extrusion": {
        "label": "0속도 압출",
        "label_en": "Zero Speed Extrusion",
        "description": "속도가 정의되지 않은 상태에서 압출",
        "category": "speed",
        "severity_default": "high",
        "color": "red",
        "icon": "alert-circle"
    },

    # === Retraction Issues ===
    "high_retraction": {
        "label": "과도한 리트렉션",
        "label_en": "Excessive Retraction",
        "description": "리트렉션 횟수가 과도하게 많음",
        "category": "retraction",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "repeat"
    },
    "excessive_retraction": {
        "label": "과다 리트렉션",
        "label_en": "Excessive Retraction",
        "description": "리트렉션 설정이 과도함",
        "category": "retraction",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "repeat"
    },

    # === Structure Issues ===
    "structure_abnormal": {
        "label": "비정상 구조",
        "label_en": "Abnormal Structure",
        "description": "G-code 구조 비율이 비정상적",
        "category": "structure",
        "severity_default": "medium",
        "color": "purple",
        "icon": "file-text"
    },
    "missing_end": {
        "label": "종료 코드 누락",
        "label_en": "Missing End Code",
        "description": "END_GCODE 섹션이 누락되거나 불완전",
        "category": "structure",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "file-minus"
    },
    "excessive_body_temp": {
        "label": "과다 온도 명령",
        "label_en": "Excessive Body Temp Commands",
        "description": "BODY 섹션에 온도 명령이 너무 많음",
        "category": "structure",
        "severity_default": "low",
        "color": "blue",
        "icon": "thermometer"
    },
    "missing_setup": {
        "label": "설정 누락",
        "label_en": "Missing Setup",
        "description": "필수 설정 명령어가 누락됨",
        "category": "structure",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "settings"
    },
    "missing_temp_wait": {
        "label": "온도 대기 명령 누락",
        "label_en": "Missing Temperature Wait",
        "description": "M109 온도 대기 명령이 누락됨",
        "category": "structure",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "clock"
    },

    # === Vendor Extension (Info) ===
    "vendor_extension": {
        "label": "벤더 확장 코드",
        "label_en": "Vendor Extension",
        "description": "Bambu Lab/OrcaSlicer 등 벤더 고유 확장 코드 감지",
        "category": "vendor",
        "severity_default": "info",
        "color": "gray",
        "icon": "info"
    },

    # === Print Quality Issues (Troubleshoot) ===
    "bed_adhesion": {
        "label": "베드 접착 불량",
        "label_en": "Bed Adhesion Issue",
        "description": "첫 레이어 베드 접착 실패",
        "category": "print_quality",
        "severity_default": "high",
        "color": "red",
        "icon": "layers"
    },
    "stringing": {
        "label": "스트링잉",
        "label_en": "Stringing",
        "description": "실 늘어짐/거미줄 현상",
        "category": "print_quality",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "git-branch"
    },
    "warping": {
        "label": "뒤틀림",
        "label_en": "Warping",
        "description": "출력물 뒤틀림/휘어짐",
        "category": "print_quality",
        "severity_default": "high",
        "color": "orange",
        "icon": "trending-down"
    },
    "layer_shifting": {
        "label": "레이어 밀림",
        "label_en": "Layer Shifting",
        "description": "레이어 오프셋/밀림 현상",
        "category": "print_quality",
        "severity_default": "high",
        "color": "red",
        "icon": "move"
    },
    "under_extrusion": {
        "label": "언더익스트루전",
        "label_en": "Under Extrusion",
        "description": "재료 부족으로 인한 압출 부족",
        "category": "print_quality",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "minus-circle"
    },
    "over_extrusion": {
        "label": "오버익스트루전",
        "label_en": "Over Extrusion",
        "description": "과다 재료로 인한 과압출",
        "category": "print_quality",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "plus-circle"
    },
    "ghosting": {
        "label": "고스팅",
        "label_en": "Ghosting",
        "description": "고스팅/링잉 현상",
        "category": "print_quality",
        "severity_default": "low",
        "color": "blue",
        "icon": "copy"
    },
    "z_banding": {
        "label": "Z축 밴딩",
        "label_en": "Z-Banding",
        "description": "Z축 밴딩 패턴",
        "category": "print_quality",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "bar-chart-2"
    },
    "blob": {
        "label": "블롭",
        "label_en": "Blob",
        "description": "표면 블롭/돌기",
        "category": "print_quality",
        "severity_default": "low",
        "color": "blue",
        "icon": "circle"
    },
    "clogging": {
        "label": "노즐 막힘",
        "label_en": "Clogging",
        "description": "노즐 막힘 현상",
        "category": "print_quality",
        "severity_default": "high",
        "color": "red",
        "icon": "x-circle"
    },
    "layer_separation": {
        "label": "레이어 분리",
        "label_en": "Layer Separation",
        "description": "레이어 박리/분리",
        "category": "print_quality",
        "severity_default": "high",
        "color": "red",
        "icon": "layers"
    },
    "elephant_foot": {
        "label": "코끼리발",
        "label_en": "Elephant Foot",
        "description": "하단 변형(코끼리발)",
        "category": "print_quality",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "square"
    },
    "bridging_issue": {
        "label": "브릿징 불량",
        "label_en": "Bridging Issue",
        "description": "브릿징 실패/처짐",
        "category": "print_quality",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "minus"
    },
    "overhang_issue": {
        "label": "오버행 불량",
        "label_en": "Overhang Issue",
        "description": "오버행 처짐",
        "category": "print_quality",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "corner-down-right"
    },
    "surface_quality": {
        "label": "표면 품질 불량",
        "label_en": "Surface Quality Issue",
        "description": "일반적인 표면 품질 문제",
        "category": "print_quality",
        "severity_default": "low",
        "color": "blue",
        "icon": "grid"
    },

    # === Equipment Issues ===
    "bed_leveling": {
        "label": "베드 레벨링 문제",
        "label_en": "Bed Leveling Issue",
        "description": "베드 수평 문제",
        "category": "equipment",
        "severity_default": "high",
        "color": "orange",
        "icon": "align-center"
    },
    "nozzle_damage": {
        "label": "노즐 손상",
        "label_en": "Nozzle Damage",
        "description": "노즐 마모/손상",
        "category": "equipment",
        "severity_default": "high",
        "color": "red",
        "icon": "tool"
    },
    "extruder_skip": {
        "label": "익스트루더 스킵",
        "label_en": "Extruder Skip",
        "description": "익스트루더 스테퍼 스킵",
        "category": "equipment",
        "severity_default": "high",
        "color": "red",
        "icon": "skip-forward"
    },
    "heating_failure": {
        "label": "히터 고장",
        "label_en": "Heating Failure",
        "description": "히터 오작동",
        "category": "equipment",
        "severity_default": "critical",
        "color": "red",
        "icon": "alert-triangle"
    },
    "motor_issue": {
        "label": "모터 문제",
        "label_en": "Motor Issue",
        "description": "모터 문제",
        "category": "equipment",
        "severity_default": "high",
        "color": "red",
        "icon": "settings"
    },
    "belt_tension": {
        "label": "벨트 장력 문제",
        "label_en": "Belt Tension Issue",
        "description": "벨트 장력 문제",
        "category": "equipment",
        "severity_default": "medium",
        "color": "yellow",
        "icon": "link"
    },
    "filament_jam": {
        "label": "필라멘트 걸림",
        "label_en": "Filament Jam",
        "description": "필라멘트 걸림/막힘",
        "category": "equipment",
        "severity_default": "high",
        "color": "red",
        "icon": "x-circle"
    },

    # === Software Issues ===
    "slicer_settings": {
        "label": "슬라이서 설정 오류",
        "label_en": "Slicer Settings Issue",
        "description": "잘못된 슬라이서 설정",
        "category": "software",
        "severity_default": "medium",
        "color": "purple",
        "icon": "sliders"
    },
    "gcode_error": {
        "label": "G-code 오류",
        "label_en": "G-code Error",
        "description": "G-code 형식/구문 오류",
        "category": "software",
        "severity_default": "high",
        "color": "red",
        "icon": "code"
    },
    "firmware_issue": {
        "label": "펌웨어 문제",
        "label_en": "Firmware Issue",
        "description": "펌웨어 문제",
        "category": "software",
        "severity_default": "high",
        "color": "purple",
        "icon": "cpu"
    },

    # === Other ===
    "unknown": {
        "label": "알 수 없는 문제",
        "label_en": "Unknown Issue",
        "description": "분류되지 않은 문제",
        "category": "other",
        "severity_default": "medium",
        "color": "gray",
        "icon": "help-circle"
    },
    "other": {
        "label": "기타",
        "label_en": "Other",
        "description": "기타 문제",
        "category": "other",
        "severity_default": "low",
        "color": "gray",
        "icon": "more-horizontal"
    },
}


def _get_supabase_client() -> Client:
    """Supabase 클라이언트 가져오기"""
    from supabase_client import get_supabase_client
    return get_supabase_client()


def get_all_issue_types(supabase: Client = None) -> List[Dict[str, Any]]:
    """
    모든 이슈 유형 조회

    Returns:
        List[Dict]: 이슈 유형 목록
    """
    if supabase is None:
        supabase = _get_supabase_client()

    try:
        response = supabase.table("gcode_issue_types")\
            .select("*")\
            .eq("is_active", True)\
            .order("category")\
            .execute()

        return response.data if response.data else []
    except Exception as e:
        logger.error(f"[IssueTypes] Failed to get all issue types: {e}")
        return []


def get_issue_type_by_code(type_code: str, supabase: Client = None) -> Optional[Dict[str, Any]]:
    """
    type_code로 이슈 유형 조회

    Args:
        type_code: 이슈 유형 코드 (예: "cold_extrusion")

    Returns:
        Dict or None: 이슈 유형 정보
    """
    if supabase is None:
        supabase = _get_supabase_client()

    try:
        response = supabase.table("gcode_issue_types")\
            .select("*")\
            .eq("type_code", type_code)\
            .single()\
            .execute()

        return response.data if response.data else None
    except Exception as e:
        # single() raises if no match
        logger.debug(f"[IssueTypes] Issue type not found: {type_code}")
        return None


def create_issue_type(
    type_code: str,
    label: str,
    label_en: str,
    description: str,
    category: str,
    severity_default: str = "medium",
    color: str = "gray",
    icon: str = "alert-circle",
    rule_metadata: Optional[Dict] = None,
    supabase: Client = None
) -> Optional[Dict[str, Any]]:
    """
    새 이슈 유형 생성

    Args:
        type_code: 유니크한 이슈 유형 코드
        label: 한글 라벨
        label_en: 영문 라벨
        description: 설명
        category: 카테고리 (temperature, speed, retraction, structure, etc.)
        severity_default: 기본 심각도 (low, medium, high, critical, info)
        color: UI 색상
        icon: 아이콘 이름
        rule_metadata: 추가 규칙 메타데이터

    Returns:
        Dict or None: 생성된 레코드
    """
    if supabase is None:
        supabase = _get_supabase_client()

    data = {
        "id": str(uuid.uuid4()),
        "type_code": type_code,
        "label": label,
        "label_en": label_en,
        "description": description,
        "category": category,
        "severity_default": severity_default,
        "color": color,
        "icon": icon,
        "rule_metadata": rule_metadata,
        "is_active": True
    }

    try:
        response = supabase.table("gcode_issue_types").insert(data).execute()
        logger.info(f"[IssueTypes] Created issue type: {type_code}")
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"[IssueTypes] Failed to create issue type {type_code}: {e}")
        return None


def update_issue_type(
    type_code: str,
    updates: Dict[str, Any],
    supabase: Client = None
) -> Optional[Dict[str, Any]]:
    """
    이슈 유형 업데이트

    Args:
        type_code: 이슈 유형 코드
        updates: 업데이트할 필드들

    Returns:
        Dict or None: 업데이트된 레코드
    """
    if supabase is None:
        supabase = _get_supabase_client()

    updates["updated_at"] = datetime.utcnow().isoformat()

    try:
        response = supabase.table("gcode_issue_types")\
            .update(updates)\
            .eq("type_code", type_code)\
            .execute()

        logger.info(f"[IssueTypes] Updated issue type: {type_code}")
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"[IssueTypes] Failed to update issue type {type_code}: {e}")
        return None


def ensure_issue_type_exists(type_code: str, supabase: Client = None) -> bool:
    """
    이슈 유형이 존재하는지 확인하고, 없으면 생성

    Args:
        type_code: 이슈 유형 코드

    Returns:
        bool: 존재 여부 (생성 포함)
    """
    if supabase is None:
        supabase = _get_supabase_client()

    # 이미 존재하는지 확인
    existing = get_issue_type_by_code(type_code, supabase)
    if existing:
        return True

    # 정의된 유형에서 찾기
    if type_code in DEFINED_ISSUE_TYPES:
        issue_def = DEFINED_ISSUE_TYPES[type_code]
        result = create_issue_type(
            type_code=type_code,
            label=issue_def["label"],
            label_en=issue_def["label_en"],
            description=issue_def["description"],
            category=issue_def["category"],
            severity_default=issue_def["severity_default"],
            color=issue_def["color"],
            icon=issue_def["icon"],
            supabase=supabase
        )
        return result is not None

    # 정의되지 않은 유형은 기본값으로 생성
    logger.warning(f"[IssueTypes] Unknown issue type, creating with defaults: {type_code}")
    result = create_issue_type(
        type_code=type_code,
        label=type_code.replace("_", " ").title(),
        label_en=type_code.replace("_", " ").title(),
        description=f"자동 생성된 이슈 유형: {type_code}",
        category="other",
        severity_default="medium",
        color="gray",
        icon="alert-circle",
        supabase=supabase
    )
    return result is not None


def sync_issue_types_from_code(supabase: Client = None) -> Dict[str, Any]:
    """
    코드에서 정의된 모든 이슈 유형을 DB와 동기화

    Returns:
        Dict: 동기화 결과 {created: [], updated: [], skipped: []}
    """
    if supabase is None:
        supabase = _get_supabase_client()

    result = {
        "created": [],
        "updated": [],
        "skipped": [],
        "errors": []
    }

    # 기존 DB 유형 조회
    existing_types = {
        item["type_code"]: item
        for item in get_all_issue_types(supabase)
    }

    for type_code, definition in DEFINED_ISSUE_TYPES.items():
        try:
            if type_code in existing_types:
                # 이미 존재 - 업데이트 필요 여부 확인
                existing = existing_types[type_code]
                needs_update = False

                # 주요 필드 비교
                for field in ["label", "label_en", "description", "category", "severity_default"]:
                    if existing.get(field) != definition.get(field):
                        needs_update = True
                        break

                if needs_update:
                    update_issue_type(type_code, definition, supabase)
                    result["updated"].append(type_code)
                else:
                    result["skipped"].append(type_code)
            else:
                # 새로 생성
                create_issue_type(
                    type_code=type_code,
                    label=definition["label"],
                    label_en=definition["label_en"],
                    description=definition["description"],
                    category=definition["category"],
                    severity_default=definition["severity_default"],
                    color=definition["color"],
                    icon=definition["icon"],
                    supabase=supabase
                )
                result["created"].append(type_code)

        except Exception as e:
            logger.error(f"[IssueTypes] Failed to sync {type_code}: {e}")
            result["errors"].append({"type_code": type_code, "error": str(e)})

    logger.info(
        f"[IssueTypes] Sync complete - "
        f"Created: {len(result['created'])}, "
        f"Updated: {len(result['updated'])}, "
        f"Skipped: {len(result['skipped'])}, "
        f"Errors: {len(result['errors'])}"
    )

    return result


def get_issue_type_info(type_code: str) -> Dict[str, Any]:
    """
    이슈 유형 정보 조회 (DB 우선, 없으면 코드 정의)

    Args:
        type_code: 이슈 유형 코드

    Returns:
        Dict: 이슈 유형 정보
    """
    # DB에서 먼저 조회
    db_info = get_issue_type_by_code(type_code)
    if db_info:
        return db_info

    # 코드 정의에서 조회
    if type_code in DEFINED_ISSUE_TYPES:
        return {
            "type_code": type_code,
            **DEFINED_ISSUE_TYPES[type_code]
        }

    # 기본값 반환
    return {
        "type_code": type_code,
        "label": type_code.replace("_", " ").title(),
        "label_en": type_code.replace("_", " ").title(),
        "description": f"Unknown issue type: {type_code}",
        "category": "other",
        "severity_default": "medium",
        "color": "gray",
        "icon": "help-circle"
    }


if __name__ == "__main__":
    # 테스트 실행
    print("Testing Issue Types DB Module...")

    # 동기화 실행
    result = sync_issue_types_from_code()
    print(f"\nSync Result:")
    print(f"  Created: {len(result['created'])} - {result['created'][:5]}...")
    print(f"  Updated: {len(result['updated'])}")
    print(f"  Skipped: {len(result['skipped'])}")
    print(f"  Errors: {len(result['errors'])}")

    # 조회 테스트
    all_types = get_all_issue_types()
    print(f"\nTotal issue types in DB: {len(all_types)}")

    # 특정 유형 조회
    cold_ext = get_issue_type_by_code("cold_extrusion")
    if cold_ext:
        print(f"\ncold_extrusion: {cold_ext['label']} ({cold_ext['severity_default']})")
