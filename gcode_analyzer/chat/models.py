"""
통합 챗봇 API 데이터 모델
"""
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class AttachmentType(str, Enum):
    """첨부 파일 타입"""
    GCODE = "gcode"
    IMAGE = "image"
    STL = "stl"
    TEXT = "text"


class ChatIntent(str, Enum):
    """사용자 의도"""
    # 도구 사용
    GCODE_ANALYSIS = "gcode_analysis"       # G-code 분석 요청 (도구 선택 → 리포트 생성)
    GCODE_GENERAL = "gcode_general"         # G-code 일반 질문 (제너럴 모드 → 텍스트 답변만)
    GCODE_ISSUE_RESOLVE = "gcode_issue_resolve"  # G-code 이슈 해결 (AI 해결하기)
    TROUBLESHOOT = "troubleshoot"           # 프린터 문제 진단
    MODELLING_TEXT = "modelling_text"       # Text-to-3D 요청
    MODELLING_IMAGE = "modelling_image"     # Image-to-3D 요청
    PRICE_COMPARISON = "price_comparison"   # 가격비교 요청

    # 일반 대화
    GENERAL_QUESTION = "general_question"   # 3D 프린팅 관련 질문
    GREETING = "greeting"                   # 인사
    HELP = "help"                           # 도움말 요청

    # 컨텍스트 기반
    FOLLOW_UP = "follow_up"                 # 이전 대화 후속 질문
    CLARIFICATION = "clarification"         # 추가 정보 제공


class UserPlan(str, Enum):
    """사용자 플랜"""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class LLMModel(str, Enum):
    """지원하는 LLM 모델"""
    # Gemini 모델 (Google)
    GEMINI_FLASH_LITE = "gemini-2.5-flash-lite"  # 무료 - 빠르고 효율적
    GEMINI_FLASH = "gemini-2.5-flash"            # 유료 - 빠른 응답

    # OpenAI 모델
    GPT_4O_MINI = "gpt-4o-mini"                  # 무료 - 빠르고 효율적
    GPT_4O = "gpt-4o"                            # 유료 - 가장 강력한 모델


# 모델별 프로바이더 매핑
MODEL_PROVIDER_MAP = {
    LLMModel.GEMINI_FLASH_LITE: "gemini",
    LLMModel.GEMINI_FLASH: "gemini",
    LLMModel.GPT_4O_MINI: "openai",
    LLMModel.GPT_4O: "openai",
}


# 무료 모델 목록
FREE_MODELS = {LLMModel.GEMINI_FLASH_LITE, LLMModel.GPT_4O_MINI}


# ============================================================
# Request Models
# ============================================================
class ConversationHistoryItem(BaseModel):
    """대화 히스토리 아이템"""
    role: str = Field(..., description="역할 (user | assistant)")
    content: str = Field(..., description="메시지 내용")


class Attachment(BaseModel):
    """첨부 파일"""
    type: AttachmentType = Field(..., description="파일 타입")
    content: str = Field(..., description="base64 인코딩된 콘텐츠 또는 URL")
    filename: Optional[str] = Field(None, description="파일명")
    mime_type: Optional[str] = Field(None, description="MIME 타입")


class ChatRequest(BaseModel):
    """챗봇 요청"""
    # 사용자 정보
    user_id: str = Field(..., description="사용자 ID (비로그인 시 프론트에서 anon_xxx 생성)")
    user_plan: UserPlan = Field(UserPlan.FREE, description="사용자 플랜")

    # 메시지
    message: str = Field(..., min_length=1, description="사용자 메시지")
    conversation_id: Optional[str] = Field(None, description="대화 세션 ID")
    conversation_history: Optional[List[ConversationHistoryItem]] = Field(
        None, description="이전 대화 히스토리 (컨텍스트 윈도우용)"
    )

    # 첨부 파일
    attachments: Optional[List[Attachment]] = Field(None, description="첨부 파일 목록")

    # 추가 컨텍스트 (UI에서 선택한 도구 정보 등)
    selected_tool: Optional[str] = Field(None, description="UI에서 선택한 도구 (troubleshoot, gcode, modelling, resolve_issue)")
    selected_model: Optional[str] = Field(None, description="UI에서 선택한 LLM 모델")
    printer_info: Optional[Dict[str, Any]] = Field(None, description="프린터 정보")
    filament_type: Optional[str] = Field(None, description="필라멘트 타입")

    # G-code 이슈 해결용 (AI 해결하기)
    analysis_id: Optional[str] = Field(None, description="G-code 분석 ID (이슈 해결 시 필요)")
    issue_to_resolve: Optional[Dict[str, Any]] = Field(None, description="해결할 이슈 정보")

    # 가격비교 옵션
    price_comparison_options: Optional[Dict[str, Any]] = Field(
        None,
        description="가격비교 옵션 (marketplaces, min_price, max_price, sort_by, max_results, category, in_stock_only)"
    )

    # 설정
    language: str = Field("ko", description="응답 언어")


# ============================================================
# Response Models
# ============================================================
class SuggestedAction(BaseModel):
    """추천 액션"""
    label: str = Field(..., description="버튼 레이블")
    action: str = Field(..., description="액션 ID")
    data: Optional[Dict[str, Any]] = Field(None, description="액션 데이터")


class ToolResult(BaseModel):
    """도구 실행 결과"""
    tool_name: str = Field(..., description="사용된 도구명")
    success: bool = Field(True, description="성공 여부")
    data: Optional[Dict[str, Any]] = Field(None, description="결과 데이터")
    error: Optional[str] = Field(None, description="에러 메시지")

    # G-code 분석 전용 필드 (편의를 위해 최상위 레벨에도 노출)
    analysis_id: Optional[str] = Field(None, description="G-code 분석 ID")
    segments: Optional[Dict[str, Any]] = Field(None, description="G-code 세그먼트 데이터")


class TokenUsage(BaseModel):
    """토큰 사용량"""
    intent_classification: int = Field(0, description="의도 분류 토큰")
    tool_execution: int = Field(0, description="도구 실행 토큰")
    response_generation: int = Field(0, description="응답 생성 토큰")
    total: int = Field(0, description="총 토큰")


class ChatResponse(BaseModel):
    """챗봇 응답"""
    # 메타
    conversation_id: str = Field(..., description="대화 세션 ID")
    message_id: str = Field(..., description="메시지 ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="타임스탬프")

    # 라우팅 결과
    intent: ChatIntent = Field(..., description="감지된 의도")
    confidence: float = Field(1.0, description="의도 확신도")

    # 응답
    response: str = Field(..., description="AI 응답 텍스트")

    # 도구 결과
    tool_result: Optional[ToolResult] = Field(None, description="도구 실행 결과")

    # 후속 액션
    suggested_actions: List[SuggestedAction] = Field(
        default_factory=list,
        description="추천 액션 목록"
    )

    # 토큰 사용량
    token_usage: TokenUsage = Field(default_factory=TokenUsage, description="토큰 사용량")

    # G-code 분석 전용 필드 (최상위 레벨에서 빠르게 접근 가능)
    analysis_id: Optional[str] = Field(None, description="G-code 분석 ID")


# ============================================================
# Internal Models
# ============================================================
class IntentResult(BaseModel):
    """의도 분류 결과 (내부용)"""
    intent: ChatIntent
    confidence: float = 1.0
    extracted_params: Dict[str, Any] = Field(default_factory=dict)
    reasoning: Optional[str] = None


class ConversationMessage(BaseModel):
    """대화 메시지 (내부용)"""
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    intent: Optional[ChatIntent] = None
    tool_result: Optional[Dict[str, Any]] = None


class ConversationSession(BaseModel):
    """대화 세션 (내부용)"""
    conversation_id: str
    user_id: str
    messages: List[ConversationMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
    context: Dict[str, Any] = Field(default_factory=dict)  # 이전 분석 결과 등


# ============================================================
# Tool-specific Parameter Models
# ============================================================
class GCodeAnalysisParams(BaseModel):
    """G-code 분석 파라미터"""
    gcode_content: str
    printer_info: Optional[Dict[str, Any]] = None
    filament_type: Optional[str] = None
    analysis_mode: str = "full"  # "summary_only" | "full"
    language: str = "ko"


class TroubleshootParams(BaseModel):
    """문제 진단 파라미터"""
    symptom_text: str
    images: Optional[List[str]] = None  # base64 이미지
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    filament_type: Optional[str] = None
    language: str = "ko"


class ModellingParams(BaseModel):
    """3D 모델링 파라미터"""
    prompt: str
    image_url: Optional[str] = None  # Image-to-3D인 경우
    task_type: str = "text_to_3d"  # "text_to_3d" | "image_to_3d"
    quality: str = "medium"  # "low" | "medium" | "high"


# ============================================================
# Price Comparison Models
# ============================================================
class PriceComparisonOptions(BaseModel):
    """가격비교 옵션"""
    marketplaces: Optional[List[str]] = Field(
        default=["naver", "coupang", "amazon", "ebay"],
        description="검색할 마켓플레이스"
    )
    min_price: Optional[int] = Field(None, description="최소 가격 (KRW)")
    max_price: Optional[int] = Field(None, description="최대 가격 (KRW)")
    sort_by: str = Field("relevance", description="정렬 기준 (price_asc, price_desc, rating, review_count, relevance)")
    max_results: int = Field(10, description="최대 결과 수")
    category: Optional[str] = Field(None, description="카테고리 (3d_printer, filament, parts, accessories)")
    in_stock_only: bool = Field(False, description="재고 있는 상품만")


class PriceComparisonProduct(BaseModel):
    """가격비교 상품"""
    id: str = Field(..., description="상품 ID")
    title: str = Field(..., description="상품명")
    price: float = Field(..., description="가격 (원래 통화)")
    currency: str = Field("KRW", description="통화")
    price_krw: int = Field(..., description="원화 가격")
    original_price: Optional[float] = Field(None, description="원래 가격 (할인 전)")
    discount_percent: Optional[int] = Field(None, description="할인율")
    marketplace: str = Field(..., description="마켓플레이스 (naver, coupang, amazon, ebay)")
    product_url: str = Field(..., description="상품 URL")
    image_url: Optional[str] = Field(None, description="상품 이미지 URL")
    rating: Optional[float] = Field(None, description="평점")
    review_count: Optional[int] = Field(None, description="리뷰 수")
    in_stock: bool = Field(True, description="재고 여부")


class PriceComparisonData(BaseModel):
    """가격비교 결과 데이터"""
    query: str = Field(..., description="검색 쿼리")
    results_count: int = Field(..., description="결과 수")
    markets_searched: List[str] = Field(..., description="검색한 마켓플레이스")
    products: List[PriceComparisonProduct] = Field(default_factory=list, description="상품 목록")


class PriceComparisonParams(BaseModel):
    """가격비교 파라미터"""
    query: str = Field(..., description="검색 쿼리")
    options: Optional[PriceComparisonOptions] = Field(default_factory=PriceComparisonOptions)
    language: str = Field("ko", description="응답 언어")
