"""
Knowledge Base 모델 정의

3D 프린터 문제-해결책 데이터 구조
"""
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from enum import Enum


class ProblemCategory(str, Enum):
    """문제 카테고리"""
    EXTRUSION = "extrusion"           # 압출 문제
    ADHESION = "adhesion"             # 접착 문제
    SURFACE = "surface"               # 표면 품질
    DIMENSIONAL = "dimensional"       # 치수 정확도
    MECHANICAL = "mechanical"         # 기계적 문제
    TEMPERATURE = "temperature"       # 온도 관련
    FILAMENT = "filament"             # 필라멘트 문제
    CALIBRATION = "calibration"       # 캘리브레이션
    FIRMWARE = "firmware"             # 펌웨어/소프트웨어
    OTHER = "other"


class Severity(str, Enum):
    """문제 심각도"""
    LOW = "low"           # 출력 가능, 품질 저하
    MEDIUM = "medium"     # 출력 어려움
    HIGH = "high"         # 출력 불가
    CRITICAL = "critical" # 프린터 손상 위험


class SolutionStep(BaseModel):
    """해결책 단계"""
    action: str = Field(..., description="수행할 작업")
    detail: Optional[str] = Field(None, description="상세 설명 (선택)")


class Solution(BaseModel):
    """해결책"""
    title: str = Field(..., description="해결책 제목")
    steps: List[str] = Field(..., description="간단한 단계 목록")
    difficulty: str = Field("easy", description="난이도: easy, medium, hard")
    source_url: str = Field(..., description="출처 URL (필수)")
    source_title: str = Field("", description="출처 제목")


class KnowledgeEntry(BaseModel):
    """Knowledge Base 항목"""
    id: str = Field(..., description="고유 ID")

    # 문제 정의
    problem_name: str = Field(..., description="문제 이름 (영문)")
    problem_name_ko: str = Field(..., description="문제 이름 (한글)")
    category: ProblemCategory = Field(..., description="문제 카테고리")
    severity: Severity = Field(Severity.MEDIUM, description="심각도")

    # 증상 (검색용)
    symptoms: List[str] = Field(..., description="증상 목록 (영문, 검색용)")
    symptoms_ko: List[str] = Field(..., description="증상 목록 (한글)")
    visual_signs: List[str] = Field(default_factory=list, description="시각적 징후")

    # 원인
    causes: List[str] = Field(..., description="가능한 원인")

    # 즉시 확인 사항
    quick_checks: List[str] = Field(..., description="즉시 확인할 사항")

    # 해결책 (URL 포함 필수)
    solutions: List[Solution] = Field(..., description="해결책 목록")

    # 관련 키워드 (검색 최적화)
    keywords: List[str] = Field(default_factory=list, description="관련 키워드")

    # 메타데이터
    printer_types: List[str] = Field(default_factory=list, description="관련 프린터 유형")
    filament_types: List[str] = Field(default_factory=list, description="관련 필라멘트")


class KBSearchResult(BaseModel):
    """KB 검색 결과"""
    entry: KnowledgeEntry
    similarity_score: float = Field(..., description="유사도 점수 (0-1)")
    matched_symptoms: List[str] = Field(default_factory=list, description="매칭된 증상")


class KBSearchResponse(BaseModel):
    """KB 검색 응답"""
    query: str = Field(..., description="검색 쿼리")
    results: List[KBSearchResult] = Field(default_factory=list)
    total_found: int = Field(0)
    search_method: str = Field("vector", description="검색 방법: vector, keyword, hybrid")
