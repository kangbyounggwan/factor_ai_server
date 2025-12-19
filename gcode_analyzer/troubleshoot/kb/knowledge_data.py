"""
3D 프린터 문제 Knowledge Base 데이터

주의: 이 KB는 문제 분류와 증상 매칭용입니다.
실제 솔루션과 출처는 Perplexity 검색으로 언어에 맞게 제공됩니다.
"""
from .models import (
    KnowledgeEntry, ProblemCategory, Severity
)


KNOWLEDGE_BASE: list[KnowledgeEntry] = [
    # ============================================================
    # 1. Under-Extrusion (압출 부족)
    # ============================================================
    KnowledgeEntry(
        id="under_extrusion",
        problem_name="Under-Extrusion",
        problem_name_ko="압출 부족",
        category=ProblemCategory.EXTRUSION,
        severity=Severity.MEDIUM,
        symptoms=[
            "thin walls",
            "missing layers",
            "gaps in top surface",
            "weak infill",
            "inconsistent extrusion",
            "filament not coming out",
        ],
        symptoms_ko=[
            "벽이 얇음",
            "레이어 누락",
            "상단에 갭",
            "인필 약함",
            "압출 불균일",
            "필라멘트 안나옴",
        ],
        visual_signs=[
            "gaps between walls",
            "visible infill through walls",
        ],
        causes=[
            "노즐 막힘",
            "필라멘트 직경 불일치",
            "익스트루더 텐션 부족",
            "온도 낮음",
        ],
        quick_checks=[
            "노즐 막힘 확인",
            "필라멘트 직경 측정",
            "익스트루더 기어 확인",
        ],
        solutions=[],  # 실제 솔루션은 Perplexity에서 검색
        keywords=["under extrusion", "압출부족", "노즐막힘", "안나옴"],
        printer_types=["FDM"],
        filament_types=["PLA", "PETG", "ABS"],
    ),

    # ============================================================
    # 2. Stringing (스트링)
    # ============================================================
    KnowledgeEntry(
        id="stringing",
        problem_name="Stringing",
        problem_name_ko="스트링",
        category=ProblemCategory.EXTRUSION,
        severity=Severity.LOW,
        symptoms=[
            "thin strings between parts",
            "cobweb strands",
            "hair-like strings",
            "oozing during travel",
        ],
        symptoms_ko=[
            "부품 사이 가는 실",
            "거미줄 같은 가닥",
            "머리카락 같은 실",
            "이동중 흘림",
        ],
        visual_signs=[
            "thin threads connecting parts",
            "hairy appearance",
        ],
        causes=[
            "리트랙션 부족",
            "온도 높음",
            "이동속도 느림",
        ],
        quick_checks=[
            "리트랙션 설정 확인",
            "온도 확인",
        ],
        solutions=[],
        keywords=["stringing", "oozing", "스트링", "거미줄", "실"],
        printer_types=["FDM"],
        filament_types=["PLA", "PETG", "TPU"],
    ),

    # ============================================================
    # 3. Layer Shifting (레이어 밀림)
    # ============================================================
    KnowledgeEntry(
        id="layer_shifting",
        problem_name="Layer Shifting",
        problem_name_ko="레이어 밀림",
        category=ProblemCategory.MECHANICAL,
        severity=Severity.HIGH,
        symptoms=[
            "layers misaligned",
            "shifted layers",
            "print offset",
            "staircase effect",
        ],
        symptoms_ko=[
            "레이어 어긋남",
            "층이 밀림",
            "출력 틀어짐",
            "계단식 밀림",
        ],
        visual_signs=[
            "horizontal offset",
            "layers not aligned",
        ],
        causes=[
            "벨트 느슨함",
            "모터 과열",
            "속도 너무 빠름",
            "풀리 느슨함",
        ],
        quick_checks=[
            "벨트 텐션 확인",
            "풀리 나사 확인",
            "모터 온도 확인",
        ],
        solutions=[],
        keywords=["layer shift", "밀림", "어긋남", "벨트"],
        printer_types=["FDM"],
        filament_types=["all"],
    ),

    # ============================================================
    # 4. Bed Adhesion (베드 접착)
    # ============================================================
    KnowledgeEntry(
        id="bed_adhesion",
        problem_name="Bed Adhesion",
        problem_name_ko="베드 접착 문제",
        category=ProblemCategory.ADHESION,
        severity=Severity.MEDIUM,
        symptoms=[
            "print not sticking",
            "corners lifting",
            "warping",
            "first layer peeling",
        ],
        symptoms_ko=[
            "안붙음",
            "모서리 들림",
            "뒤틀림",
            "첫레이어 박리",
        ],
        visual_signs=[
            "lifted corners",
            "print detaching",
        ],
        causes=[
            "레벨링 불량",
            "노즐 너무 높음",
            "베드 온도 낮음",
            "베드 오염",
        ],
        quick_checks=[
            "베드 레벨링 확인",
            "첫 레이어 높이 확인",
            "베드 청결 확인",
        ],
        solutions=[],
        keywords=["bed adhesion", "warping", "접착", "안붙음", "뒤틀림"],
        printer_types=["FDM"],
        filament_types=["PLA", "PETG", "ABS"],
    ),

    # ============================================================
    # 5. Z-Banding
    # ============================================================
    KnowledgeEntry(
        id="z_banding",
        problem_name="Z-Banding",
        problem_name_ko="Z축 밴딩",
        category=ProblemCategory.SURFACE,
        severity=Severity.MEDIUM,
        symptoms=[
            "horizontal lines",
            "periodic ripples",
            "z ribbing",
        ],
        symptoms_ko=[
            "수평 줄무늬",
            "주기적 물결",
            "Z축 줄",
        ],
        visual_signs=[
            "regular horizontal lines",
            "wavy surface",
        ],
        causes=[
            "리드스크류 문제",
            "Z커플러 불량",
            "레이어 높이 불일치",
        ],
        quick_checks=[
            "리드스크류 상태 확인",
            "Z커플러 조임 확인",
        ],
        solutions=[],
        keywords=["z banding", "밴딩", "줄무늬", "물결"],
        printer_types=["FDM"],
        filament_types=["all"],
    ),

    # ============================================================
    # 6. Overheating
    # ============================================================
    KnowledgeEntry(
        id="overheating",
        problem_name="Overheating",
        problem_name_ko="과열",
        category=ProblemCategory.TEMPERATURE,
        severity=Severity.MEDIUM,
        symptoms=[
            "melting",
            "loss of detail",
            "blobby surface",
            "droopy overhangs",
        ],
        symptoms_ko=[
            "녹음",
            "디테일 손실",
            "뭉툭한 표면",
            "오버행 처짐",
        ],
        visual_signs=[
            "melted features",
            "soft appearance",
        ],
        causes=[
            "온도 높음",
            "냉각 부족",
            "속도 느림",
        ],
        quick_checks=[
            "냉각 팬 작동 확인",
            "온도 확인",
        ],
        solutions=[],
        keywords=["overheating", "과열", "녹음", "처짐"],
        printer_types=["FDM"],
        filament_types=["PLA", "PETG"],
    ),

    # ============================================================
    # 7. Elephant's Foot
    # ============================================================
    KnowledgeEntry(
        id="elephants_foot",
        problem_name="Elephant's Foot",
        problem_name_ko="코끼리 발",
        category=ProblemCategory.DIMENSIONAL,
        severity=Severity.LOW,
        symptoms=[
            "first layer bulging",
            "bottom flares",
            "base too wide",
        ],
        symptoms_ko=[
            "첫 레이어 불룩",
            "바닥 벌어짐",
            "베이스 넓음",
        ],
        visual_signs=[
            "bulge at base",
        ],
        causes=[
            "첫 레이어 너무 가까움",
            "베드 온도 높음",
        ],
        quick_checks=[
            "첫 레이어 높이 확인",
            "베드 온도 확인",
        ],
        solutions=[],
        keywords=["elephant foot", "코끼리발", "첫레이어", "불룩"],
        printer_types=["FDM"],
        filament_types=["all"],
    ),

    # ============================================================
    # 8. Blobs/Zits
    # ============================================================
    KnowledgeEntry(
        id="blobs_zits",
        problem_name="Blobs and Zits",
        problem_name_ko="블롭/여드름",
        category=ProblemCategory.SURFACE,
        severity=Severity.LOW,
        symptoms=[
            "small bumps",
            "zits on surface",
            "blobs at seam",
        ],
        symptoms_ko=[
            "작은 돌기",
            "표면 여드름",
            "심에 뭉침",
        ],
        visual_signs=[
            "random bumps",
            "visible seam blobs",
        ],
        causes=[
            "리트랙션 불량",
            "심 설정 문제",
        ],
        quick_checks=[
            "심 설정 확인",
            "리트랙션 확인",
        ],
        solutions=[],
        keywords=["blobs", "zits", "블롭", "여드름", "돌기"],
        printer_types=["FDM"],
        filament_types=["all"],
    ),

    # ============================================================
    # 9. Ghosting/Ringing
    # ============================================================
    KnowledgeEntry(
        id="ghosting",
        problem_name="Ghosting",
        problem_name_ko="고스팅/링잉",
        category=ProblemCategory.SURFACE,
        severity=Severity.LOW,
        symptoms=[
            "ripples on surface",
            "echo of features",
            "ringing",
        ],
        symptoms_ko=[
            "표면 잔물결",
            "형상 잔상",
            "링잉",
        ],
        visual_signs=[
            "repeating wave pattern",
        ],
        causes=[
            "속도/가속도 높음",
            "프레임 진동",
            "벨트 텐션 불량",
        ],
        quick_checks=[
            "벨트 텐션 확인",
            "프레임 흔들림 확인",
        ],
        solutions=[],
        keywords=["ghosting", "ringing", "고스팅", "링잉", "잔상", "물결"],
        printer_types=["FDM"],
        filament_types=["all"],
    ),

    # ============================================================
    # 10. Poor Bridging
    # ============================================================
    KnowledgeEntry(
        id="poor_bridging",
        problem_name="Poor Bridging",
        problem_name_ko="브릿징 불량",
        category=ProblemCategory.SURFACE,
        severity=Severity.LOW,
        symptoms=[
            "sagging bridges",
            "droopy filament",
            "stringy bridges",
        ],
        symptoms_ko=[
            "브릿지 처짐",
            "필라멘트 늘어짐",
            "실같은 브릿지",
        ],
        visual_signs=[
            "sagging on unsupported areas",
        ],
        causes=[
            "냉각 부족",
            "브릿지 속도 느림",
            "온도 높음",
        ],
        quick_checks=[
            "냉각 팬 설정 확인",
            "브릿지 설정 확인",
        ],
        solutions=[],
        keywords=["bridging", "브릿징", "브릿지", "처짐"],
        printer_types=["FDM"],
        filament_types=["PLA", "PETG"],
    ),

    # ============================================================
    # 11. Wet Filament
    # ============================================================
    KnowledgeEntry(
        id="wet_filament",
        problem_name="Wet Filament",
        problem_name_ko="습기 찬 필라멘트",
        category=ProblemCategory.FILAMENT,
        severity=Severity.MEDIUM,
        symptoms=[
            "popping sounds",
            "bubbles",
            "rough surface",
            "weak layers",
        ],
        symptoms_ko=[
            "팝핑 소리",
            "기포",
            "거친 표면",
            "레이어 약함",
        ],
        visual_signs=[
            "holes or bubbles",
            "fuzzy texture",
        ],
        causes=[
            "습기 흡수",
            "보관 불량",
        ],
        quick_checks=[
            "필라멘트 보관 상태 확인",
            "출력 시 소리 확인",
        ],
        solutions=[],
        keywords=["wet filament", "습기", "팝핑", "기포"],
        printer_types=["FDM"],
        filament_types=["Nylon", "PETG", "PLA", "TPU"],
    ),

    # ============================================================
    # 12. Clogged Nozzle
    # ============================================================
    KnowledgeEntry(
        id="clogged_nozzle",
        problem_name="Clogged Nozzle",
        problem_name_ko="노즐 막힘",
        category=ProblemCategory.EXTRUSION,
        severity=Severity.HIGH,
        symptoms=[
            "no filament",
            "partial extrusion",
            "clicking sounds",
            "filament grinding",
        ],
        symptoms_ko=[
            "필라멘트 안나옴",
            "부분 압출",
            "클릭 소리",
            "필라멘트 갈림",
        ],
        visual_signs=[
            "empty areas",
            "thin lines",
        ],
        causes=[
            "이물질 축적",
            "탄화된 필라멘트",
            "온도 낮음",
        ],
        quick_checks=[
            "수동 압출 테스트",
            "필라멘트 상태 확인",
        ],
        solutions=[],
        keywords=["clogged nozzle", "노즐막힘", "막힘", "클릭", "안나옴"],
        printer_types=["FDM"],
        filament_types=["all"],
    ),
]


def get_all_entries() -> list[KnowledgeEntry]:
    """모든 KB 항목 반환"""
    return KNOWLEDGE_BASE


def get_entry_by_id(entry_id: str) -> KnowledgeEntry | None:
    """ID로 항목 조회"""
    for entry in KNOWLEDGE_BASE:
        if entry.id == entry_id:
            return entry
    return None


def get_entries_by_category(category: ProblemCategory) -> list[KnowledgeEntry]:
    """카테고리별 항목 조회"""
    return [e for e in KNOWLEDGE_BASE if e.category == category]
