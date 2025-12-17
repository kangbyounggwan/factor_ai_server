"""
고장 진단 API 데이터 모델
"""
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class ProblemType(str, Enum):
    """문제 유형 분류"""
    # 출력 품질 문제
    BED_ADHESION = "bed_adhesion"  # 첫 레이어 접착 불량
    STRINGING = "stringing"  # 스트링/거미줄
    WARPING = "warping"  # 뒤틀림/휨
    LAYER_SHIFTING = "layer_shifting"  # 레이어 쉬프트
    UNDER_EXTRUSION = "under_extrusion"  # 압출 부족
    OVER_EXTRUSION = "over_extrusion"  # 과압출
    GHOSTING = "ghosting"  # 고스팅/링잉
    Z_BANDING = "z_banding"  # Z 밴딩
    BLOB = "blob"  # 블롭/얼룩
    CLOGGING = "clogging"  # 노즐 막힘
    LAYER_SEPARATION = "layer_separation"  # 레이어 분리
    ELEPHANT_FOOT = "elephant_foot"  # 엘리펀트 풋
    BRIDGING_ISSUE = "bridging_issue"  # 브릿징 문제
    OVERHANG_ISSUE = "overhang_issue"  # 오버행 문제
    SURFACE_QUALITY = "surface_quality"  # 표면 품질 문제

    # 기계 문제
    BED_LEVELING = "bed_leveling"  # 베드 레벨링
    NOZZLE_DAMAGE = "nozzle_damage"  # 노즐 손상
    EXTRUDER_SKIP = "extruder_skip"  # 익스트루더 스킵
    HEATING_FAILURE = "heating_failure"  # 가열 실패
    MOTOR_ISSUE = "motor_issue"  # 모터 문제
    BELT_TENSION = "belt_tension"  # 벨트 텐션
    FILAMENT_JAM = "filament_jam"  # 필라멘트 걸림

    # 소프트웨어 문제
    SLICER_SETTINGS = "slicer_settings"  # 슬라이서 설정
    GCODE_ERROR = "gcode_error"  # G-code 오류
    FIRMWARE_ISSUE = "firmware_issue"  # 펌웨어 문제

    # 기타
    UNKNOWN = "unknown"  # 알 수 없음
    OTHER = "other"  # 기타


class Difficulty(str, Enum):
    """해결 난이도"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


class UserPlan(str, Enum):
    """사용자 플랜"""
    FREE = "free"          # 무료 - DuckDuckGo + Wikipedia
    BASIC = "basic"        # 기본 유료 - Tavily basic
    PRO = "pro"            # 프로 - Tavily advanced + 더 많은 결과
    ENTERPRISE = "enterprise"  # 기업용 - 모든 기능


# ============================================================
# Request Models
# ============================================================
class DiagnoseRequest(BaseModel):
    """진단 요청"""
    manufacturer: Optional[str] = Field(None, description="프린터 제조사 (예: Creality, Bambu Lab)")
    series: Optional[str] = Field(None, description="프린터 시리즈 (예: Ender, X1)")
    model: Optional[str] = Field(None, description="프린터 모델 (예: Ender 3 V2, X1 Carbon)")
    symptom_text: str = Field(..., min_length=5, description="증상 설명 텍스트")
    images: Optional[List[str]] = Field(None, description="문제 이미지 (base64 인코딩)")
    language: str = Field("ko", description="응답 언어 (ko, en)")
    filament_type: Optional[str] = Field(None, description="필라멘트 종류 (PLA, ABS, PETG 등)")
    additional_context: Optional[str] = Field(None, description="추가 컨텍스트 정보")
    user_plan: UserPlan = Field(UserPlan.FREE, description="사용자 플랜 (free, basic, pro, enterprise)")


# ============================================================
# Response Models
# ============================================================
class Problem(BaseModel):
    """진단된 문제"""
    type: ProblemType = Field(..., description="문제 유형")
    confidence: float = Field(..., ge=0, le=1, description="확신도 (0~1)")
    description: str = Field(..., description="문제 설명")
    detected_from: str = Field("text", description="감지 출처 (text, image, both)")


class Solution(BaseModel):
    """해결책"""
    priority: int = Field(..., ge=1, description="우선순위 (1이 가장 높음)")
    title: str = Field(..., description="해결책 제목")
    steps: List[str] = Field(..., description="단계별 해결 방법")
    difficulty: Difficulty = Field(Difficulty.EASY, description="난이도")
    estimated_time: Optional[str] = Field(None, description="예상 소요 시간")
    tools_needed: Optional[List[str]] = Field(None, description="필요한 도구")
    warnings: Optional[List[str]] = Field(None, description="주의사항")


class Reference(BaseModel):
    """참조 자료"""
    title: str = Field(..., description="자료 제목")
    url: str = Field(..., description="URL")
    source: str = Field(..., description="출처 (official, reddit, youtube 등)")
    relevance: float = Field(..., ge=0, le=1, description="관련성 점수")
    snippet: Optional[str] = Field(None, description="내용 요약")


class ExpertOpinion(BaseModel):
    """전문가 의견"""
    summary: str = Field(..., description="종합 의견")
    prevention_tips: List[str] = Field(default_factory=list, description="예방 팁")
    when_to_seek_help: Optional[str] = Field(None, description="전문가 도움이 필요한 경우")
    related_issues: Optional[List[str]] = Field(None, description="관련될 수 있는 다른 문제들")


class TokenUsage(BaseModel):
    """토큰 사용량"""
    image_analysis: int = Field(0, description="이미지 분석 토큰")
    search_query: int = Field(0, description="검색 쿼리 생성 토큰")
    search_summary: int = Field(0, description="검색 결과 요약 토큰")
    solution_generation: int = Field(0, description="솔루션 생성 토큰")
    total: int = Field(0, description="총 토큰")


class DiagnoseResponse(BaseModel):
    """진단 응답"""
    diagnosis_id: str = Field(..., description="진단 ID")
    problem: Problem = Field(..., description="진단된 문제")
    solutions: List[Solution] = Field(..., description="해결책 목록")
    references: List[Reference] = Field(default_factory=list, description="참조 자료")
    expert_opinion: ExpertOpinion = Field(..., description="전문가 의견")
    printer_info: Dict[str, Any] = Field(default_factory=dict, description="프린터 정보")
    token_usage: TokenUsage = Field(default_factory=TokenUsage, description="토큰 사용량")


# ============================================================
# Internal Models
# ============================================================
class ImageAnalysisResult(BaseModel):
    """이미지 분석 결과 (내부용)"""
    detected_problems: List[ProblemType] = Field(default_factory=list)
    confidence_scores: Dict[str, float] = Field(default_factory=dict)
    description: str = Field("")
    visual_evidence: List[str] = Field(default_factory=list)
    tokens_used: int = Field(0)


class SearchResult(BaseModel):
    """검색 결과 (내부용)"""
    query: str
    results: List[Reference] = Field(default_factory=list)
    tokens_used: int = Field(0)


class SearchQueries(BaseModel):
    """생성된 검색 쿼리 (내부용)"""
    official_query: str = Field(..., description="공식 문서 검색 쿼리")
    community_query: str = Field(..., description="커뮤니티 검색 쿼리")
    general_query: str = Field(..., description="일반 웹 검색 쿼리")
    tokens_used: int = Field(0)
