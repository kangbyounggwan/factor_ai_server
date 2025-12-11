"""
G-code Analyzer Configuration
하드코딩 제거를 위한 설정 파일
"""
from pydantic import BaseModel
from typing import Optional

class AnalysisConfig(BaseModel):
    """분석 설정"""
    snippet_window: int = 50  # 온도 이벤트 앞뒤로 추출할 라인 수
    llm_model: str = "gemini-2.5-flash-lite"  # Gemini 2.5 Flash Lite
    max_concurrent_llm_calls: int = 5  # 병렬 LLM 호출 제한
    
class FilamentConfig(BaseModel):
    """필라멘트별 권장 온도 (DB에서 가져올 수도 있음)"""
    name: str
    min_nozzle_temp: float
    max_nozzle_temp: float
    min_bed_temp: float
    max_bed_temp: float

# 기본 필라멘트 설정 (DB 연동 전까지 사용)
DEFAULT_FILAMENTS = {
    "PLA": FilamentConfig(name="PLA", min_nozzle_temp=180, max_nozzle_temp=220, min_bed_temp=50, max_bed_temp=70),
    "ABS": FilamentConfig(name="ABS", min_nozzle_temp=230, max_nozzle_temp=260, min_bed_temp=90, max_bed_temp=110),
    "PETG": FilamentConfig(name="PETG", min_nozzle_temp=220, max_nozzle_temp=250, min_bed_temp=70, max_bed_temp=90),
    "TPU": FilamentConfig(name="TPU", min_nozzle_temp=210, max_nozzle_temp=230, min_bed_temp=30, max_bed_temp=60),
}

def get_default_config() -> AnalysisConfig:
    return AnalysisConfig()
