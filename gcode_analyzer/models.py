from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# --- From Parser ---
class GCodeLine(BaseModel):
    index: int           # 1-based line number (원본 라인 번호)
    raw: str             # Original string
    cmd: str             # G1, G0, M104, etc.
    params: Dict[str, float] # {"X": 10.2, "E": 42.123}
    comment: Optional[str]  # Comment

# --- From Summary (Python Stats) ---
class GCodeSummary(BaseModel):
    total_layers: int
    layer_height: float
    nozzle_temp_min: float
    nozzle_temp_max: float
    bed_temp_min: float
    bed_temp_max: float
    max_speed: float
    avg_speed: float
    retraction_count: int
    filament_type: Optional[str]
    estimated_print_time: Optional[str]

# --- From Temp Tracker ---
class TempEvent(BaseModel):
    line_index: int
    temp: float
    cmd: str

# --- From Anomaly Detector ---
class AnomalyType(str, Enum):
    COLD_EXTRUSION = "cold_extrusion"
    EARLY_TEMP_OFF = "early_temp_off"
    EXCESSIVE_RETRACTION = "excessive_retraction"
    RAPID_TEMP_CHANGE = "rapid_temp_change"
    LOW_TEMP = "low_temp"
    BED_TEMP_OFF_EARLY = "bed_temp_off_early"
    # 속도 관련
    EXCESSIVE_SPEED = "excessive_speed"          # 과도한 속도
    INCONSISTENT_SPEED = "inconsistent_speed"    # 일관성 없는 속도 변화
    ZERO_SPEED_EXTRUSION = "zero_speed_extrusion"  # 속도 0에서 익스트루전

class Anomaly(BaseModel):
    type: AnomalyType
    line_index: int
    severity: str  # critical, high, medium, low (critical=즉시 출력 금지)
    temp_before: Optional[float] = None
    temp_after: Optional[float] = None
    message: str
    context: Dict[str, Any] = {}

# --- New: Expert Assessment (The Answer Sheet) ---
class IssueDetail(BaseModel):
    id: str                 # 식별자 (ISSUE-001)
    line: int               # 발생 라인
    type: str               # 문제 유형
    severity: str           # critical, high, medium, low (critical=출력 금지 수준)
    title: str              # 문제 제목 (한글)
    description: str        # 상세 설명
    fix_proposal: str       # 수정 제안

class CheckPoint(BaseModel):
    status: str             # ok, warning, error
    comment: str            # 평가 코멘트

class PrintCharacteristics(BaseModel):
    complexity: str         # High, Medium, Low
    difficulty: str         # Advanced, Intermediate, Beginner
    tags: List[str]         # ["Support Heavy", "Temperature Variation"]

class ExpertAssessment(BaseModel):
    quality_score: int
    quality_grade: str      # S, A, B, C, F
    print_characteristics: PrintCharacteristics
    summary_text: str       # 전체 총평 (중복 없는 단일 요약)
    check_points: Dict[str, CheckPoint] # temperature, speed, retraction, etc.
    critical_issues: List[IssueDetail]
    overall_recommendations: List[str]

# --- Final Consolidated Result ---
class GCodeAnalysisResult(BaseModel):
    basic_stats: Dict[str, Any]      # Python 통계
    expert_assessment: ExpertAssessment # LLM 정답지


# ============================================================
# Delta-based G-code Modification Models
# 델타 기반 G-code 수정 모델
# ============================================================

class DeltaAction(str, Enum):
    """델타 액션 유형"""
    MODIFY = "modify"              # 해당 라인 내용 변경
    DELETE = "delete"              # 해당 라인 삭제
    INSERT_BEFORE = "insert_before"  # 해당 라인 앞에 삽입
    INSERT_AFTER = "insert_after"    # 해당 라인 뒤에 삽입


class LineDelta(BaseModel):
    """
    단일 라인 변경사항 (델타)

    클라이언트에서 사용자가 수정한 변경사항을 표현
    서버에서 원본 G-code와 병합하여 최종 파일 생성

    Examples:
        - 수정: {"lineIndex": 42, "action": "modify", "newContent": "M104 S210"}
        - 삭제: {"lineIndex": 100, "action": "delete"}
        - 앞에 추가: {"lineIndex": 50, "action": "insert_before", "newContent": "G4 P500"}
        - 뒤에 추가: {"lineIndex": 50, "action": "insert_after", "newContent": "M106 S255"}
    """
    line_index: int = Field(..., alias="lineIndex")  # 원본 기준 라인 인덱스 (0-based)
    action: DeltaAction                               # 액션 유형
    original_content: Optional[str] = Field(None, alias="originalContent")  # modify/delete 시 원본
    new_content: Optional[str] = Field(None, alias="newContent")            # modify/insert 시 새 내용
    reason: Optional[str] = None                      # 변경 이유 (선택적, 이력 추적용)
    patch_id: Optional[str] = Field(None, alias="patchId")  # 연결된 패치 ID (선택적)

    model_config = {"use_enum_values": True, "populate_by_name": True}


class DeltaExportRequest(BaseModel):
    """
    델타 기반 G-code 내보내기 요청

    클라이언트에서 수정한 델타 목록을 서버로 전송하여
    원본 G-code와 병합한 최종 파일을 다운로드
    """
    analysis_id: str                        # 분석 ID (원본 파일 참조)
    deltas: List[LineDelta]                 # 변경사항 목록
    filename: Optional[str] = None          # 출력 파일명 (없으면 자동 생성)
    include_header_comment: bool = Field(True, alias="includeComments")  # 수정 이력 헤더 주석 포함 여부

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "analysis_id": "abc123",
                "deltas": [
                    {"lineIndex": 42, "action": "modify", "newContent": "M109 S220"},
                    {"lineIndex": 100, "action": "delete"},
                    {"lineIndex": 50, "action": "insert_after", "newContent": "M190 S65"}
                ],
                "filename": "my_model_modified.gcode",
                "includeComments": True
            }
        }
    }


class DeltaExportResponse(BaseModel):
    """델타 내보내기 응답 (메타데이터)"""
    success: bool
    filename: str
    total_lines: int                        # 최종 파일 라인 수
    applied_deltas: int                     # 적용된 델타 수
    skipped_deltas: int                     # 스킵된 델타 수 (검증 실패 등)
    warnings: List[str] = []                # 경고 메시지
