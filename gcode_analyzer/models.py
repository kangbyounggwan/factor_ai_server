from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

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

class Anomaly(BaseModel):
    type: AnomalyType
    line_index: int
    severity: str  # low, medium, high
    temp_before: Optional[float] = None
    temp_after: Optional[float] = None
    message: str
    context: Dict[str, Any] = {}

# --- New: Expert Assessment (The Answer Sheet) ---
class IssueDetail(BaseModel):
    id: str                 # 식별자 (ISSUE-001)
    line: int               # 발생 라인
    type: str               # 문제 유형
    severity: str           # high, medium, low
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
