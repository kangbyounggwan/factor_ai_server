"""
프린터 제조사/모델 데이터베이스
공식 문서 URL, 커뮤니티 URL 등 관리
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class PrinterSeries:
    """프린터 시리즈 정보"""
    name: str
    models: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ManufacturerInfo:
    """제조사 정보"""
    name: str
    official_support_url: str
    official_docs_url: Optional[str] = None
    firmware_type: str = "marlin"  # marlin, klipper, custom
    community_urls: List[str] = field(default_factory=list)
    reddit_subs: List[str] = field(default_factory=list)
    youtube_channels: List[str] = field(default_factory=list)
    series: List[PrinterSeries] = field(default_factory=list)
    search_keywords: List[str] = field(default_factory=list)


# 제조사 데이터베이스
MANUFACTURERS: Dict[str, ManufacturerInfo] = {
    "creality": ManufacturerInfo(
        name="Creality",
        official_support_url="https://www.creality.com/pages/download",
        official_docs_url="https://www.creality.com/pages/support",
        firmware_type="marlin",
        community_urls=[
            "https://www.reddit.com/r/ender3/",
            "https://www.reddit.com/r/CR10/",
            "https://www.reddit.com/r/Creality/",
        ],
        reddit_subs=["ender3", "CR10", "Creality", "ender3v2"],
        youtube_channels=["Teaching Tech", "CHEP", "Maker's Muse"],
        series=[
            PrinterSeries(
                name="Ender",
                models=["Ender 3", "Ender 3 Pro", "Ender 3 V2", "Ender 3 V3", "Ender 3 S1", "Ender 3 S1 Pro", "Ender 5", "Ender 5 Plus", "Ender 5 S1"],
                description="FDM 입문용 프린터"
            ),
            PrinterSeries(
                name="CR",
                models=["CR-10", "CR-10 S", "CR-10 V2", "CR-10 V3", "CR-10 Smart", "CR-10 Max"],
                description="대형 FDM 프린터"
            ),
            PrinterSeries(
                name="K1",
                models=["K1", "K1 Max", "K1C"],
                description="고속 Core XY 프린터"
            ),
        ],
        search_keywords=["Creality", "Ender", "CR-10", "K1"]
    ),

    "bambulab": ManufacturerInfo(
        name="Bambu Lab",
        official_support_url="https://wiki.bambulab.com",
        official_docs_url="https://wiki.bambulab.com/en/general",
        firmware_type="custom",
        community_urls=[
            "https://www.reddit.com/r/BambuLab/",
            "https://forum.bambulab.com/",
        ],
        reddit_subs=["BambuLab"],
        youtube_channels=["Bambu Lab"],
        series=[
            PrinterSeries(
                name="X1",
                models=["X1", "X1 Carbon", "X1E"],
                description="플래그십 Core XY"
            ),
            PrinterSeries(
                name="P1",
                models=["P1P", "P1S"],
                description="미드레인지 Core XY"
            ),
            PrinterSeries(
                name="A1",
                models=["A1", "A1 Mini"],
                description="베드슬링어 입문용"
            ),
        ],
        search_keywords=["Bambu Lab", "X1 Carbon", "P1S", "A1"]
    ),

    "prusa": ManufacturerInfo(
        name="Prusa Research",
        official_support_url="https://help.prusa3d.com",
        official_docs_url="https://help.prusa3d.com/category/original-prusa-i3-mk3s",
        firmware_type="marlin",
        community_urls=[
            "https://forum.prusa3d.com/",
            "https://www.reddit.com/r/prusa3d/",
        ],
        reddit_subs=["prusa3d", "prusa"],
        youtube_channels=["Prusa 3D"],
        series=[
            PrinterSeries(
                name="MK",
                models=["MK3S+", "MK4", "MK4S"],
                description="베드슬링어 프린터"
            ),
            PrinterSeries(
                name="Mini",
                models=["Mini", "Mini+"],
                description="소형 프린터"
            ),
            PrinterSeries(
                name="XL",
                models=["XL"],
                description="대형 Core XY"
            ),
        ],
        search_keywords=["Prusa", "MK3S", "MK4", "Prusa Mini"]
    ),

    "voron": ManufacturerInfo(
        name="Voron Design",
        official_support_url="https://docs.vorondesign.com",
        official_docs_url="https://docs.vorondesign.com",
        firmware_type="klipper",
        community_urls=[
            "https://www.reddit.com/r/VORONDesign/",
            "https://discord.gg/voron",
        ],
        reddit_subs=["VORONDesign", "voroncorexy"],
        youtube_channels=["Nero 3D", "Steve Builds"],
        series=[
            PrinterSeries(
                name="Voron",
                models=["V0", "V0.2", "Trident", "V2.4", "V2.4r2"],
                description="DIY Core XY 키트"
            ),
        ],
        search_keywords=["Voron", "V2.4", "Trident", "Klipper"]
    ),

    "anycubic": ManufacturerInfo(
        name="Anycubic",
        official_support_url="https://www.anycubic.com/pages/support",
        official_docs_url="https://www.anycubic.com/pages/firmware-software",
        firmware_type="marlin",
        community_urls=[
            "https://www.reddit.com/r/AnycubicPhoton/",
            "https://www.reddit.com/r/anycubic/",
        ],
        reddit_subs=["AnycubicPhoton", "anycubic"],
        youtube_channels=[],
        series=[
            PrinterSeries(
                name="Kobra",
                models=["Kobra", "Kobra 2", "Kobra 2 Pro", "Kobra 2 Max", "Kobra 3"],
                description="베드슬링어 FDM"
            ),
            PrinterSeries(
                name="Vyper",
                models=["Vyper"],
                description="자동 레벨링 FDM"
            ),
            PrinterSeries(
                name="Photon",
                models=["Photon", "Photon Mono", "Photon Mono X", "Photon M3"],
                description="레진 프린터"
            ),
        ],
        search_keywords=["Anycubic", "Kobra", "Vyper", "Photon"]
    ),

    "elegoo": ManufacturerInfo(
        name="Elegoo",
        official_support_url="https://www.elegoo.com/pages/3d-printing-user-support",
        official_docs_url="https://www.elegoo.com/pages/3d-printing-user-support",
        firmware_type="marlin",
        community_urls=[
            "https://www.reddit.com/r/ElegooMars/",
            "https://www.reddit.com/r/ElegooNeptune3/",
        ],
        reddit_subs=["ElegooMars", "ElegooNeptune3", "elegoo"],
        youtube_channels=[],
        series=[
            PrinterSeries(
                name="Neptune",
                models=["Neptune 3", "Neptune 3 Pro", "Neptune 3 Plus", "Neptune 3 Max", "Neptune 4", "Neptune 4 Pro"],
                description="베드슬링어 FDM"
            ),
            PrinterSeries(
                name="Mars",
                models=["Mars", "Mars 2", "Mars 3", "Mars 4"],
                description="레진 프린터"
            ),
            PrinterSeries(
                name="Saturn",
                models=["Saturn", "Saturn 2", "Saturn 3"],
                description="대형 레진 프린터"
            ),
        ],
        search_keywords=["Elegoo", "Neptune", "Mars", "Saturn"]
    ),

    "artillery": ManufacturerInfo(
        name="Artillery",
        official_support_url="https://www.artillery3d.com/pages/downloads",
        official_docs_url="https://www.artillery3d.com/pages/downloads",
        firmware_type="marlin",
        community_urls=[
            "https://www.reddit.com/r/Artillery3D/",
        ],
        reddit_subs=["Artillery3D", "artillerygenius"],
        youtube_channels=[],
        series=[
            PrinterSeries(
                name="Sidewinder",
                models=["Sidewinder X1", "Sidewinder X2", "Sidewinder X3 Pro"],
                description="대형 직접 구동 FDM"
            ),
            PrinterSeries(
                name="Genius",
                models=["Genius", "Genius Pro"],
                description="컴팩트 FDM"
            ),
        ],
        search_keywords=["Artillery", "Sidewinder", "Genius"]
    ),

    "sovol": ManufacturerInfo(
        name="Sovol",
        official_support_url="https://sovol3d.com/pages/download",
        official_docs_url="https://sovol3d.com/pages/download",
        firmware_type="marlin",
        community_urls=[
            "https://www.reddit.com/r/Sovol/",
        ],
        reddit_subs=["Sovol"],
        youtube_channels=[],
        series=[
            PrinterSeries(
                name="SV",
                models=["SV01", "SV01 Pro", "SV03", "SV04", "SV05", "SV06", "SV06 Plus", "SV07", "SV07 Plus"],
                description="FDM 프린터"
            ),
        ],
        search_keywords=["Sovol", "SV06", "SV07"]
    ),

    "flashforge": ManufacturerInfo(
        name="FlashForge",
        official_support_url="https://www.flashforge.com/download-center",
        official_docs_url="https://www.flashforge.com/download-center",
        firmware_type="custom",
        community_urls=[
            "https://www.reddit.com/r/FlashForge/",
        ],
        reddit_subs=["FlashForge"],
        youtube_channels=[],
        series=[
            PrinterSeries(
                name="Adventurer",
                models=["Adventurer 3", "Adventurer 4", "Adventurer 5M", "Adventurer 5M Pro"],
                description="밀폐형 FDM"
            ),
            PrinterSeries(
                name="Creator",
                models=["Creator Pro", "Creator Pro 2", "Creator 3"],
                description="듀얼 익스트루더 FDM"
            ),
        ],
        search_keywords=["FlashForge", "Adventurer", "Creator"]
    ),

    "ultimaker": ManufacturerInfo(
        name="Ultimaker",
        official_support_url="https://support.ultimaker.com",
        official_docs_url="https://support.ultimaker.com",
        firmware_type="custom",
        community_urls=[
            "https://community.ultimaker.com/",
        ],
        reddit_subs=["ultimaker"],
        youtube_channels=["Ultimaker"],
        series=[
            PrinterSeries(
                name="S-Line",
                models=["S3", "S5", "S7"],
                description="전문가용 FDM"
            ),
        ],
        search_keywords=["Ultimaker", "S5", "S7"]
    ),
}


def get_manufacturer(name: str) -> Optional[ManufacturerInfo]:
    """제조사 정보 조회"""
    key = name.lower().replace(" ", "").replace("-", "")
    return MANUFACTURERS.get(key)


def get_all_manufacturers() -> List[str]:
    """모든 제조사 이름 목록"""
    return [info.name for info in MANUFACTURERS.values()]


def get_series_for_manufacturer(manufacturer: str) -> List[PrinterSeries]:
    """제조사의 시리즈 목록"""
    info = get_manufacturer(manufacturer)
    if info:
        return info.series
    return []


def get_models_for_series(manufacturer: str, series: str) -> List[str]:
    """시리즈의 모델 목록"""
    info = get_manufacturer(manufacturer)
    if info:
        for s in info.series:
            if s.name.lower() == series.lower():
                return s.models
    return []


def get_search_context(manufacturer: str, model: Optional[str] = None) -> Dict[str, Any]:
    """
    검색에 필요한 컨텍스트 정보 반환

    Returns:
        {
            "manufacturer": "Creality",
            "model": "Ender 3 V2",
            "official_url": "https://...",
            "reddit_subs": ["ender3", "Creality"],
            "search_keywords": ["Creality", "Ender 3 V2"],
            "firmware_type": "marlin"
        }
    """
    info = get_manufacturer(manufacturer)
    if not info:
        return {
            "manufacturer": manufacturer,
            "model": model,
            "official_url": None,
            "reddit_subs": [],
            "search_keywords": [manufacturer, model] if model else [manufacturer],
            "firmware_type": "unknown"
        }

    keywords = list(info.search_keywords)
    if model:
        keywords.append(model)

    return {
        "manufacturer": info.name,
        "model": model,
        "official_url": info.official_support_url,
        "official_docs_url": info.official_docs_url,
        "reddit_subs": info.reddit_subs,
        "community_urls": info.community_urls,
        "search_keywords": keywords,
        "firmware_type": info.firmware_type
    }


def find_manufacturer_by_model(model: str) -> Optional[ManufacturerInfo]:
    """모델명으로 제조사 찾기"""
    model_lower = model.lower()
    for info in MANUFACTURERS.values():
        for series in info.series:
            for m in series.models:
                if m.lower() in model_lower or model_lower in m.lower():
                    return info
    return None
