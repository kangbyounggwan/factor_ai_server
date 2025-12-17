"""
G-code Segment Extractor
레이어별 압출 세그먼트와 이동 세그먼트를 추출하는 모듈
다양한 슬라이서 지원: OrcaSlicer, BambuStudio, Cura, PrusaSlicer, Simplify3D
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from .parser import parse_gcode, ParseResult
from .models import GCodeLine
import re
import time
import base64
import struct


class EncodingError(Exception):
    """인코딩 오류로 파일 파싱 실패"""
    pass


def segments_to_float32_base64(segments: List[List[float]]) -> str:
    """
    세그먼트 배열을 Float32Array로 변환 후 Base64 인코딩

    Args:
        segments: [[x1,y1,z1,x2,y2,z2], ...] 형태의 세그먼트 리스트

    Returns:
        Base64 인코딩된 Float32 바이너리 문자열
    """
    if not segments:
        return ""

    # Flatten: [[x1,y1,z1,x2,y2,z2], ...] -> [x1,y1,z1,x2,y2,z2,...]
    flat = []
    for seg in segments:
        flat.extend(seg)

    # Pack as Float32 (little-endian)
    packed = struct.pack(f'<{len(flat)}f', *flat)
    return base64.b64encode(packed).decode('ascii')


class SlicerType(Enum):
    """지원되는 슬라이서 타입"""
    UNKNOWN = "unknown"
    ORCASLICER = "orcaslicer"
    BAMBUSTUDIO = "bambustudio"
    CURA = "cura"
    PRUSASLICER = "prusaslicer"
    SIMPLIFY3D = "simplify3d"
    IDEAMAKER = "ideamaker"


class FirmwareType(Enum):
    """프린터 펌웨어 타입"""
    UNKNOWN = "unknown"
    MARLIN = "marlin"
    KLIPPER = "klipper"
    REPRAPFIRMWARE = "reprapfirmware"
    SMOOTHIEWARE = "smoothieware"


class EquipmentType(Enum):
    """프린터 설비/브랜드 타입"""
    UNKNOWN = "unknown"
    BAMBULAB = "bambulab"      # Bambu Lab (X1, P1, A1 series)
    CREALITY = "creality"      # Creality (Ender, CR series)
    PRUSA = "prusa"            # Prusa (MK3, MK4, Mini)
    VORON = "voron"            # Voron (0, 1, 2, Trident)
    RATRIG = "ratrig"          # RatRig (V-Core, V-Minion)
    ELEGOO = "elegoo"          # Elegoo (Neptune series)
    ANYCUBIC = "anycubic"      # Anycubic (Kobra, Vyper)
    ARTILLERY = "artillery"    # Artillery (Sidewinder, Genius)
    SOVOL = "sovol"            # Sovol (SV series)
    KLIPPER_GENERIC = "klipper_generic"  # Generic Klipper setup


@dataclass
class LayerTemperature:
    """레이어별 온도 데이터"""
    layer: int
    nozzleTemp: float = 0.0
    bedTemp: float = 0.0


@dataclass
class LayerData:
    """단일 레이어 데이터"""
    layerNum: int
    z: float
    extrusions: List[List[float]] = field(default_factory=list)
    travels: List[List[float]] = field(default_factory=list)
    wipes: List[List[float]] = field(default_factory=list)  # WIPE 세그먼트 (리트랙션하며 이동)
    supports: List[List[float]] = field(default_factory=list)  # 서포트 세그먼트
    nozzleTemp: float = 0.0  # 해당 레이어에서의 노즐 온도
    bedTemp: float = 0.0     # 해당 레이어에서의 베드 온도


@dataclass
class BoundingBox:
    """3D 바운딩 박스"""
    minX: float = float('inf')
    maxX: float = float('-inf')
    minY: float = float('inf')
    maxY: float = float('-inf')
    minZ: float = float('inf')
    maxZ: float = float('-inf')

    def update(self, x: float, y: float, z: float):
        self.minX = min(self.minX, x)
        self.maxX = max(self.maxX, x)
        self.minY = min(self.minY, y)
        self.maxY = max(self.maxY, y)
        self.minZ = min(self.minZ, z)
        self.maxZ = max(self.maxZ, z)

    def to_dict(self) -> Dict[str, float]:
        return {
            "minX": round(self.minX, 3) if self.minX != float('inf') else 0,
            "maxX": round(self.maxX, 3) if self.maxX != float('-inf') else 0,
            "minY": round(self.minY, 3) if self.minY != float('inf') else 0,
            "maxY": round(self.maxY, 3) if self.maxY != float('-inf') else 0,
            "minZ": round(self.minZ, 3) if self.minZ != float('inf') else 0,
            "maxZ": round(self.maxZ, 3) if self.maxZ != float('-inf') else 0
        }


@dataclass
class Metadata:
    """메타데이터"""
    boundingBox: BoundingBox = field(default_factory=BoundingBox)
    layerCount: int = 0
    totalFilament: float = 0.0  # mm
    printTime: int = 0  # seconds
    layerHeight: float = 0.0
    firstLayerHeight: float = 0.0
    estimatedTime: Optional[str] = None
    filamentType: Optional[str] = None
    slicer: Optional[str] = None
    slicerVersion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "boundingBox": self.boundingBox.to_dict(),
            "layerCount": self.layerCount,
            "totalFilament": round(self.totalFilament, 2),
            "printTime": self.printTime,
            "layerHeight": round(self.layerHeight, 3),
            "firstLayerHeight": round(self.firstLayerHeight, 3),
            "estimatedTime": self.estimatedTime,
            "filamentType": self.filamentType,
            "slicer": self.slicer,
            "slicerVersion": self.slicerVersion
        }


@dataclass
class SegmentExtractionResult:
    """최종 추출 결과"""
    layers: List[LayerData] = field(default_factory=list)
    metadata: Metadata = field(default_factory=Metadata)

    def to_dict(self) -> Dict[str, Any]:
        """기존 JSON 배열 형식으로 반환"""
        # 레이어별 온도 데이터 생성
        temperatures = [
            {
                "layer": layer.layerNum,
                "nozzleTemp": layer.nozzleTemp,
                "bedTemp": layer.bedTemp
            }
            for layer in self.layers
            if layer.nozzleTemp > 0 or layer.bedTemp > 0
        ]

        return {
            "layers": [
                {
                    "layerNum": layer.layerNum,
                    "z": round(layer.z, 3),
                    "extrusions": layer.extrusions,
                    "travels": layer.travels,
                    "wipes": layer.wipes,
                    "supports": layer.supports
                }
                for layer in self.layers
            ],
            "metadata": self.metadata.to_dict(),
            "temperatures": temperatures
        }

    def to_binary_dict(self) -> Dict[str, Any]:
        """
        Float32Array + Base64 최적화 형식으로 반환

        Returns:
            {
                "layers": [
                    {
                        "layerNum": 0,
                        "z": 0.2,
                        "extrusionData": "base64...",  # Float32Array
                        "travelData": "base64...",
                        "wipeData": "base64...",
                        "supportData": "base64...",
                        "extrusionCount": 1234,
                        "travelCount": 567,
                        "wipeCount": 89,
                        "supportCount": 456
                    },
                    ...
                ],
                "metadata": { ... },
                "temperatures": [
                    {"layer": 0, "nozzleTemp": 200, "bedTemp": 60},
                    ...
                ]
            }
        """
        # 레이어별 온도 데이터 생성
        temperatures = [
            {
                "layer": layer.layerNum,
                "nozzleTemp": layer.nozzleTemp,
                "bedTemp": layer.bedTemp
            }
            for layer in self.layers
            if layer.nozzleTemp > 0 or layer.bedTemp > 0
        ]

        return {
            "layers": [
                {
                    "layerNum": layer.layerNum,
                    "z": round(layer.z, 3),
                    "extrusionData": segments_to_float32_base64(layer.extrusions),
                    "travelData": segments_to_float32_base64(layer.travels),
                    "wipeData": segments_to_float32_base64(layer.wipes),
                    "supportData": segments_to_float32_base64(layer.supports),
                    "extrusionCount": len(layer.extrusions),
                    "travelCount": len(layer.travels),
                    "wipeCount": len(layer.wipes),
                    "supportCount": len(layer.supports)
                }
                for layer in self.layers
            ],
            "metadata": self.metadata.to_dict(),
            "temperatures": temperatures
        }


class SlicerDetector:
    """슬라이서 자동 감지"""

    SLICER_PATTERNS = {
        SlicerType.ORCASLICER: [
            re.compile(r'generated by OrcaSlicer\s*([\d.]+)?', re.IGNORECASE),
            re.compile(r'; OrcaSlicer', re.IGNORECASE),
        ],
        SlicerType.BAMBUSTUDIO: [
            re.compile(r'BambuStudio\s*([\d.]+)?', re.IGNORECASE),
            re.compile(r'; Bambu Lab', re.IGNORECASE),
        ],
        SlicerType.CURA: [
            re.compile(r'Generated with Cura_SteamEngine\s*([\d.]+)?', re.IGNORECASE),
            re.compile(r';FLAVOR:Marlin', re.IGNORECASE),
            re.compile(r'Ultimaker Cura', re.IGNORECASE),
        ],
        SlicerType.PRUSASLICER: [
            re.compile(r'generated by PrusaSlicer\s*([\d.]+)?', re.IGNORECASE),
            re.compile(r'; PrusaSlicer', re.IGNORECASE),
        ],
        SlicerType.SIMPLIFY3D: [
            re.compile(r'Simplify3D', re.IGNORECASE),
        ],
        SlicerType.IDEAMAKER: [
            re.compile(r'ideaMaker', re.IGNORECASE),
        ],
    }

    @classmethod
    def detect(cls, lines: List[GCodeLine], max_lines: int = 100) -> Tuple[SlicerType, Optional[str]]:
        """
        G-code 파일의 처음 부분을 분석하여 슬라이서 감지
        Returns: (SlicerType, version string or None)
        """
        for line in lines[:max_lines]:
            raw = line.raw or ""
            for slicer_type, patterns in cls.SLICER_PATTERNS.items():
                for pattern in patterns:
                    match = pattern.search(raw)
                    if match:
                        version = match.group(1) if match.groups() else None
                        return slicer_type, version
        return SlicerType.UNKNOWN, None


class FirmwareDetector:
    """펌웨어/프린터 타입 자동 감지 (Klipper 매크로 등)"""

    # Klipper 매크로 패턴들
    KLIPPER_MACRO_PATTERNS = [
        # 시작/종료 매크로
        re.compile(r'\bSTART_PRINT\b', re.IGNORECASE),
        re.compile(r'\bPRINT_START\b', re.IGNORECASE),
        re.compile(r'\bEND_PRINT\b', re.IGNORECASE),
        re.compile(r'\bPRINT_END\b', re.IGNORECASE),
        # 온도 파라미터가 포함된 매크로 호출
        re.compile(r'(?:START_PRINT|PRINT_START)\s+.*(?:EXTRUDER(?:_TEMP)?|BED(?:_TEMP)?)\s*=', re.IGNORECASE),
        # Klipper 전용 명령어
        re.compile(r'\bSET_PRESSURE_ADVANCE\b', re.IGNORECASE),
        re.compile(r'\bSET_VELOCITY_LIMIT\b', re.IGNORECASE),
        re.compile(r'\bSET_RETRACTION\b', re.IGNORECASE),
        re.compile(r'\bSET_GCODE_OFFSET\b', re.IGNORECASE),
        re.compile(r'\bBED_MESH_CALIBRATE\b', re.IGNORECASE),
        re.compile(r'\bBED_MESH_PROFILE\b', re.IGNORECASE),
        re.compile(r'\bQUAD_GANTRY_LEVEL\b', re.IGNORECASE),
        re.compile(r'\bZ_TILT_ADJUST\b', re.IGNORECASE),
        re.compile(r'\bG32\b'),  # Klipper 커스텀 호밍
        re.compile(r'\bRESPOND\b', re.IGNORECASE),  # Klipper 콘솔 출력
        re.compile(r'\bEXCLUDE_OBJECT\b', re.IGNORECASE),  # Klipper 객체 제외
        re.compile(r'\bSET_HEATER_TEMPERATURE\b', re.IGNORECASE),
        re.compile(r'\bTURN_OFF_HEATERS\b', re.IGNORECASE),
    ]

    # RepRapFirmware 패턴
    REPRAP_PATTERNS = [
        re.compile(r'; generated by RepRapFirmware', re.IGNORECASE),
        re.compile(r'M98\s+P.*\.g', re.IGNORECASE),  # 매크로 파일 호출
        re.compile(r'M929', re.IGNORECASE),  # 로깅 명령
    ]

    # Smoothieware 패턴
    SMOOTHIE_PATTERNS = [
        re.compile(r'; generated by Smoothieware', re.IGNORECASE),
        re.compile(r'M500\s+; save', re.IGNORECASE),  # Smoothie 특유 저장
    ]

    @classmethod
    def detect(cls, lines: List[GCodeLine], max_lines: int = 200) -> Tuple[FirmwareType, Optional[Dict[str, Any]]]:
        """
        G-code 파일의 처음 부분을 분석하여 펌웨어/프린터 타입 감지

        Returns:
            (FirmwareType, metadata_dict or None)
            metadata_dict는 Klipper의 경우 매크로 파라미터 등 포함
        """
        klipper_evidence = []
        klipper_metadata = {}

        for line in lines[:max_lines]:
            raw = line.raw or ""

            # Klipper 매크로 패턴 확인
            for pattern in cls.KLIPPER_MACRO_PATTERNS:
                if pattern.search(raw):
                    klipper_evidence.append(raw.strip())

                    # START_PRINT/PRINT_START 파라미터 추출
                    if 'START_PRINT' in raw.upper() or 'PRINT_START' in raw.upper():
                        # EXTRUDER_TEMP, BED_TEMP, EXTRUDER, BED 등 파라미터 추출
                        temp_match = re.search(
                            r'(?:EXTRUDER(?:_TEMP)?)\s*=\s*(\d+(?:\.\d+)?)',
                            raw, re.IGNORECASE
                        )
                        if temp_match:
                            klipper_metadata['extruder_temp'] = float(temp_match.group(1))

                        bed_match = re.search(
                            r'(?:BED(?:_TEMP)?)\s*=\s*(\d+(?:\.\d+)?)',
                            raw, re.IGNORECASE
                        )
                        if bed_match:
                            klipper_metadata['bed_temp'] = float(bed_match.group(1))

                        klipper_metadata['start_macro'] = raw.strip()
                    break

            # RepRapFirmware 확인
            for pattern in cls.REPRAP_PATTERNS:
                if pattern.search(raw):
                    return FirmwareType.REPRAPFIRMWARE, None

            # Smoothieware 확인
            for pattern in cls.SMOOTHIE_PATTERNS:
                if pattern.search(raw):
                    return FirmwareType.SMOOTHIEWARE, None

        # Klipper 증거가 충분하면 (2개 이상의 패턴 매치)
        if len(klipper_evidence) >= 1:
            klipper_metadata['detected_macros'] = klipper_evidence[:5]  # 최대 5개까지만 저장
            return FirmwareType.KLIPPER, klipper_metadata

        # Marlin 확인 (기본 G-code만 사용하고 특수 매크로 없음)
        # Marlin은 보통 기본 G-code만 사용하므로, 특별한 패턴 없으면 Marlin로 추정
        has_standard_gcode = any(
            line.cmd in ['G28', 'G29', 'M104', 'M109', 'M140', 'M190']
            for line in lines[:max_lines] if line.cmd
        )
        if has_standard_gcode and not klipper_evidence:
            return FirmwareType.MARLIN, None

        return FirmwareType.UNKNOWN, None

    @classmethod
    def is_klipper(cls, lines: List[GCodeLine], max_lines: int = 200) -> bool:
        """Klipper 펌웨어인지 빠르게 확인"""
        firmware_type, _ = cls.detect(lines, max_lines)
        return firmware_type == FirmwareType.KLIPPER

    @classmethod
    def get_klipper_start_temps(cls, lines: List[GCodeLine], max_lines: int = 200) -> Optional[Dict[str, float]]:
        """
        Klipper START_PRINT/PRINT_START 매크로에서 설정된 온도 추출

        Returns:
            {"extruder_temp": 210.0, "bed_temp": 60.0} 또는 None
        """
        firmware_type, metadata = cls.detect(lines, max_lines)
        if firmware_type != FirmwareType.KLIPPER or not metadata:
            return None

        temps = {}
        if 'extruder_temp' in metadata:
            temps['extruder_temp'] = metadata['extruder_temp']
        if 'bed_temp' in metadata:
            temps['bed_temp'] = metadata['bed_temp']

        return temps if temps else None


class EquipmentDetector:
    """프린터 설비/브랜드 자동 감지"""

    EQUIPMENT_PATTERNS = {
        EquipmentType.BAMBULAB: [
            re.compile(r'Bambu\s*Lab', re.IGNORECASE),
            re.compile(r'; printer_model\s*[:=]\s*(?:X1|P1|A1)', re.IGNORECASE),
            re.compile(r'BambuStudio', re.IGNORECASE),
            re.compile(r'G9111\s+.*(?:bedTemp|extruderTemp)\s*=', re.IGNORECASE),  # Bambu Lab 전용 온도 명령어
            re.compile(r'M10[49]\s+S\d+\s+H[1-9]', re.IGNORECASE),  # Bambu Lab H 파라미터 (멀티 노즐)
        ],
        EquipmentType.CREALITY: [
            re.compile(r'Creality', re.IGNORECASE),
            re.compile(r'\bEnder[\s-]?\d', re.IGNORECASE),  # word boundary로 시작
            re.compile(r'\bCR-\d{1,2}\b', re.IGNORECASE),  # CR-10 형태만 (하이픈 필수)
            re.compile(r'; printer_model\s*[:=]\s*Ender', re.IGNORECASE),
        ],
        EquipmentType.PRUSA: [
            re.compile(r'Prusa(?:Slicer)?', re.IGNORECASE),
            re.compile(r'MK\d[Ss]?\+?', re.IGNORECASE),
            re.compile(r'; printer_model\s*[:=]\s*(?:MK|Mini|XL)', re.IGNORECASE),
        ],
        EquipmentType.VORON: [
            re.compile(r'\bVoron\b', re.IGNORECASE),
            re.compile(r'\bV0\b', re.IGNORECASE),
            re.compile(r'\bV1\b', re.IGNORECASE),
            re.compile(r'\bV2\b', re.IGNORECASE),
            re.compile(r'\bTrident\b', re.IGNORECASE),
        ],
        EquipmentType.RATRIG: [
            re.compile(r'RatRig', re.IGNORECASE),
            re.compile(r'V-Core', re.IGNORECASE),
            re.compile(r'V-Minion', re.IGNORECASE),
        ],
        EquipmentType.ELEGOO: [
            re.compile(r'Elegoo', re.IGNORECASE),
            re.compile(r'Neptune', re.IGNORECASE),
        ],
        EquipmentType.ANYCUBIC: [
            re.compile(r'Anycubic', re.IGNORECASE),
            re.compile(r'Kobra', re.IGNORECASE),
            re.compile(r'Vyper', re.IGNORECASE),
        ],
        EquipmentType.ARTILLERY: [
            re.compile(r'Artillery', re.IGNORECASE),
            re.compile(r'Sidewinder', re.IGNORECASE),
            re.compile(r'Genius', re.IGNORECASE),
        ],
        EquipmentType.SOVOL: [
            re.compile(r'Sovol', re.IGNORECASE),
            re.compile(r'SV0[1-9]', re.IGNORECASE),
        ],
    }

    @classmethod
    def detect(cls, lines: List[GCodeLine], max_lines: int = 200) -> Tuple[EquipmentType, Optional[str]]:
        """
        G-code 파일에서 프린터 설비/브랜드 감지

        Returns:
            (EquipmentType, model_name or None)
        """
        for line in lines[:max_lines]:
            raw = line.raw or ""

            for equipment_type, patterns in cls.EQUIPMENT_PATTERNS.items():
                for pattern in patterns:
                    match = pattern.search(raw)
                    if match:
                        # 모델명 추출 시도
                        model_name = None
                        model_match = re.search(r'printer_model\s*[:=]\s*(\S+)', raw, re.IGNORECASE)
                        if model_match:
                            model_name = model_match.group(1)
                        return equipment_type, model_name

        return EquipmentType.UNKNOWN, None


@dataclass
class PrinterContext:
    """프린터 환경 컨텍스트 (슬라이서 + 설비 + 펌웨어)"""
    # 슬라이서 정보
    slicer_type: SlicerType = SlicerType.UNKNOWN
    slicer_version: Optional[str] = None

    # 설비/프린터 정보
    equipment_type: EquipmentType = EquipmentType.UNKNOWN
    equipment_model: Optional[str] = None

    # 펌웨어 정보
    firmware_type: FirmwareType = FirmwareType.UNKNOWN
    firmware_metadata: Optional[Dict[str, Any]] = None

    # Klipper 전용 메타데이터
    klipper_start_temps: Optional[Dict[str, float]] = None  # {'extruder_temp': 210, 'bed_temp': 60}
    klipper_macros: Optional[List[str]] = None  # 감지된 Klipper 매크로 목록

    def is_klipper(self) -> bool:
        """Klipper 펌웨어인지 확인"""
        return self.firmware_type == FirmwareType.KLIPPER

    def is_bambulab(self) -> bool:
        """Bambu Lab 프린터인지 확인"""
        return self.equipment_type == EquipmentType.BAMBULAB

    def has_klipper_temps(self) -> bool:
        """Klipper 매크로에서 온도가 설정되었는지 확인"""
        return bool(self.klipper_start_temps)

    def get_expected_temps(self) -> Optional[Dict[str, float]]:
        """Klipper 매크로에서 설정된 예상 온도 반환"""
        return self.klipper_start_temps

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "slicer": {
                "type": self.slicer_type.value,
                "version": self.slicer_version
            },
            "equipment": {
                "type": self.equipment_type.value,
                "model": self.equipment_model
            },
            "firmware": {
                "type": self.firmware_type.value,
                "is_klipper": self.is_klipper(),
                "klipper_temps": self.klipper_start_temps,
                "klipper_macros": self.klipper_macros
            }
        }


def detect_printer_context(lines: List[GCodeLine], max_lines: int = 2000) -> PrinterContext:
    """
    G-code 파일에서 프린터 컨텍스트 전체 감지
    (슬라이서 + 설비 + 펌웨어 3가지 모두 시도)

    Args:
        lines: 파싱된 G-code 라인들
        max_lines: 검사할 최대 라인 수 (기본 2000 - START 매크로가 뒤에 있을 수 있음)

    Returns:
        PrinterContext 객체
    """
    # 1. 슬라이서 감지 (보통 파일 앞부분 주석에 있음)
    slicer_type, slicer_version = SlicerDetector.detect(lines, min(max_lines, 200))

    # 2. 설비 감지 (보통 파일 앞부분 주석에 있음)
    equipment_type, equipment_model = EquipmentDetector.detect(lines, min(max_lines, 500))

    # 3. 펌웨어 감지 (START_PRINT 등 매크로가 뒤에 있을 수 있음)
    firmware_type, firmware_metadata = FirmwareDetector.detect(lines, max_lines)

    # Klipper 전용 정보 추출
    klipper_start_temps = None
    klipper_macros = None

    if firmware_type == FirmwareType.KLIPPER and firmware_metadata:
        klipper_start_temps = {}
        if 'extruder_temp' in firmware_metadata:
            klipper_start_temps['extruder_temp'] = firmware_metadata['extruder_temp']
        if 'bed_temp' in firmware_metadata:
            klipper_start_temps['bed_temp'] = firmware_metadata['bed_temp']
        if not klipper_start_temps:
            klipper_start_temps = None

        klipper_macros = firmware_metadata.get('detected_macros')

        # Klipper + unknown equipment → klipper_generic로 설정
        if equipment_type == EquipmentType.UNKNOWN:
            equipment_type = EquipmentType.KLIPPER_GENERIC

    return PrinterContext(
        slicer_type=slicer_type,
        slicer_version=slicer_version,
        equipment_type=equipment_type,
        equipment_model=equipment_model,
        firmware_type=firmware_type,
        firmware_metadata=firmware_metadata,
        klipper_start_temps=klipper_start_temps,
        klipper_macros=klipper_macros
    )


class GCodeSegmentExtractor:
    """G-code에서 레이어별 세그먼트를 추출하는 클래스"""

    def __init__(self):
        self._reset_state()

    def _reset_state(self):
        """상태 초기화"""
        # 현재 위치 상태
        self.current_x: float = 0.0
        self.current_y: float = 0.0
        self.current_z: float = 0.0
        self.current_e: float = 0.0
        self.current_f: float = 0.0

        # 상대/절대 모드
        self.absolute_xyz: bool = True  # G90/G91
        self.absolute_e: bool = True    # M82/M83

        # 레이어 추적
        self.current_layer: int = -1
        self.layer_z_map: Dict[int, float] = {}
        self.layers: Dict[int, LayerData] = {}
        self.pending_layer_change: bool = False
        self.last_z_for_layer: float = 0.0

        # 슬라이서 정보
        self.slicer_type: SlicerType = SlicerType.UNKNOWN
        self.slicer_version: Optional[str] = None

        # 메타데이터
        self.bounding_box = BoundingBox()
        self.total_filament: float = 0.0
        self.estimated_time: Optional[str] = None
        self.filament_type: Optional[str] = None
        self.total_layers_hint: Optional[int] = None

        # 온도 추적
        self.current_nozzle_temp: float = 0.0
        self.current_bed_temp: float = 0.0
        self.layer_temperatures: List[LayerTemperature] = []

        # WIPE 상태 추적
        self.in_wipe: bool = False

        # 서포트 상태 추적
        self.in_support: bool = False

        # 슬라이서별 레이어 감지 패턴
        self._setup_patterns()

    def _setup_patterns(self):
        """슬라이서별 패턴 설정"""
        # OrcaSlicer / PrusaSlicer 패턴
        self.orca_layer_change = re.compile(r';LAYER_CHANGE', re.IGNORECASE)
        self.orca_z_marker = re.compile(r';Z:([\d.]+)', re.IGNORECASE)
        self.orca_height = re.compile(r';HEIGHT:([\d.]+)', re.IGNORECASE)

        # Cura 패턴
        self.cura_layer = re.compile(r';LAYER:(\d+)', re.IGNORECASE)
        self.cura_layer_count = re.compile(r';LAYER_COUNT:(\d+)', re.IGNORECASE)

        # BambuStudio 패턴
        self.bambu_layer = re.compile(r'; layer num/total_layer_count:\s*(\d+)/(\d+)', re.IGNORECASE)
        self.bambu_m73_layer = re.compile(r'^M73\s+L(\d+)', re.IGNORECASE)

        # Simplify3D 패턴
        self.s3d_layer = re.compile(r'; layer\s+(\d+)', re.IGNORECASE)

        # 공통 메타데이터 패턴
        self.time_patterns = [
            re.compile(r';TIME:(\d+)', re.IGNORECASE),
            re.compile(r'; model printing time:\s*([\d\w\s:]+)', re.IGNORECASE),
            re.compile(r'; estimated printing time.*?=\s*([\d\w\s]+)', re.IGNORECASE),  # OrcaSlicer
            re.compile(r';estimated printing time.*?=\s*([\d:dhms\s]+)', re.IGNORECASE),
            re.compile(r';Print time:\s*([\d:]+)', re.IGNORECASE),
        ]

        self.filament_length_patterns = [
            re.compile(r'; total filament length \[mm\]\s*:\s*([\d.]+)', re.IGNORECASE),
            re.compile(r';Filament used:\s*([\d.]+)m', re.IGNORECASE),
        ]

        self.filament_type_patterns = [
            re.compile(r'; filament_type\s*=\s*(\w+)', re.IGNORECASE),
            re.compile(r';Filament type\s*=\s*(\w+)', re.IGNORECASE),
            re.compile(r';TYPE:(\w+).*filament', re.IGNORECASE),
        ]

        self.total_layers_patterns = [
            re.compile(r'; total layer number:\s*(\d+)', re.IGNORECASE),
            re.compile(r';LAYER_COUNT:(\d+)', re.IGNORECASE),
        ]

        self.layer_height_patterns = [
            re.compile(r'; layer_height\s*=\s*([\d.]+)', re.IGNORECASE),
            re.compile(r';Layer height:\s*([\d.]+)', re.IGNORECASE),
        ]

    def _detect_layer_from_line(self, line: GCodeLine) -> Optional[int]:
        """라인에서 레이어 번호 감지 (슬라이서별 처리)"""
        raw = line.raw or ""

        # Cura 스타일: ;LAYER:N
        match = self.cura_layer.search(raw)
        if match:
            return int(match.group(1))

        # BambuStudio 스타일: ; layer num/total_layer_count: N/M
        match = self.bambu_layer.search(raw)
        if match:
            layer_num = int(match.group(1))
            # BambuStudio는 1부터 시작하므로 0-indexed로 변환
            return layer_num - 1

        # BambuStudio M73 L 명령
        match = self.bambu_m73_layer.match(raw)
        if match:
            layer_num = int(match.group(1))
            return layer_num - 1  # 0-indexed로 변환

        # OrcaSlicer/PrusaSlicer 스타일: ;LAYER_CHANGE
        if self.orca_layer_change.search(raw):
            self.pending_layer_change = True
            return None  # Z 변경 시 적용

        # Simplify3D 스타일: ; layer N
        match = self.s3d_layer.search(raw)
        if match:
            return int(match.group(1))

        return None

    def _extract_metadata_from_line(self, line: GCodeLine):
        """라인에서 메타데이터 추출"""
        raw = line.raw or ""

        # 시간 추출
        if not self.estimated_time:
            for pattern in self.time_patterns:
                match = pattern.search(raw)
                if match:
                    self.estimated_time = match.group(1).strip()
                    break

        # 필라멘트 타입 추출
        if not self.filament_type:
            for pattern in self.filament_type_patterns:
                match = pattern.search(raw)
                if match:
                    self.filament_type = match.group(1).upper()
                    break

        # 총 레이어 수 힌트
        if not self.total_layers_hint:
            for pattern in self.total_layers_patterns:
                match = pattern.search(raw)
                if match:
                    self.total_layers_hint = int(match.group(1))
                    break

        # 필라멘트 길이 (미리 파싱)
        for pattern in self.filament_length_patterns:
            match = pattern.search(raw)
            if match:
                try:
                    length = float(match.group(1))
                    # m 단위면 mm로 변환
                    if 'Filament used' in raw and 'm' in raw:
                        length *= 1000
                    if length > self.total_filament:
                        self.total_filament = length
                except ValueError:
                    pass

    def _get_or_create_layer(self, layer_num: int, z: float) -> LayerData:
        """레이어 데이터 가져오거나 생성"""
        if layer_num not in self.layers:
            self.layers[layer_num] = LayerData(
                layerNum=layer_num,
                z=z,
                nozzleTemp=self.current_nozzle_temp,
                bedTemp=self.current_bed_temp
            )
            self.layer_z_map[layer_num] = z
        else:
            # Z 값 업데이트 (더 정확한 값으로)
            if z > 0 and (self.layers[layer_num].z == 0 or abs(z - self.layers[layer_num].z) < 0.01):
                self.layers[layer_num].z = z
            # 온도가 0이면 현재 온도로 업데이트
            if self.layers[layer_num].nozzleTemp == 0 and self.current_nozzle_temp > 0:
                self.layers[layer_num].nozzleTemp = self.current_nozzle_temp
            if self.layers[layer_num].bedTemp == 0 and self.current_bed_temp > 0:
                self.layers[layer_num].bedTemp = self.current_bed_temp
        return self.layers[layer_num]

    def _process_move(self, line: GCodeLine, is_rapid: bool = False):
        """G0/G1 이동 명령 처리"""
        params = line.params

        # 새 위치 계산
        new_x = self.current_x
        new_y = self.current_y
        new_z = self.current_z
        new_e = self.current_e

        if 'X' in params:
            new_x = params['X'] if self.absolute_xyz else self.current_x + params['X']
        if 'Y' in params:
            new_y = params['Y'] if self.absolute_xyz else self.current_y + params['Y']
        if 'Z' in params:
            new_z = params['Z'] if self.absolute_xyz else self.current_z + params['Z']
        if 'E' in params:
            new_e = params['E'] if self.absolute_e else self.current_e + params['E']
        if 'F' in params:
            self.current_f = params['F']

        # Z 변경 감지 -> 레이어 변경 (OrcaSlicer LAYER_CHANGE 처리)
        z_changed = abs(new_z - self.current_z) > 0.001 and new_z > 0

        if z_changed:
            if self.pending_layer_change:
                # LAYER_CHANGE 신호 후 Z 변경 -> 새 레이어
                self.current_layer += 1
                self.pending_layer_change = False
                self.last_z_for_layer = new_z
            elif self.current_layer < 0:
                # 첫 레이어 시작
                self.current_layer = 0
                self.last_z_for_layer = new_z
            elif new_z > self.last_z_for_layer + 0.05:
                # 명시적 레이어 마커 없이 Z가 크게 증가 (폴백)
                if self.slicer_type == SlicerType.UNKNOWN:
                    self.current_layer += 1
                    self.last_z_for_layer = new_z

        # 세그먼트 생성 (실제 XY 이동이 있을 때만)
        has_xy_move = ('X' in params or 'Y' in params)

        if has_xy_move and self.current_layer >= 0:
            effective_z = new_z if new_z > 0 else self.current_z
            layer = self._get_or_create_layer(self.current_layer, effective_z)

            segment = [
                round(self.current_x, 3),
                round(self.current_y, 3),
                round(self.current_z if self.current_z > 0 else effective_z, 3),
                round(new_x, 3),
                round(new_y, 3),
                round(effective_z, 3)
            ]

            # 압출 여부 판단
            e_delta = new_e - self.current_e

            if e_delta > 0.001 and not is_rapid:
                # 양의 E 변화 = 압출 세그먼트
                if self.in_support:
                    # 서포트 구간 압출 = supports 세그먼트
                    layer.supports.append(segment)
                else:
                    # 일반 압출 = extrusions 세그먼트
                    layer.extrusions.append(segment)
                # 상대 E 모드에서만 필라멘트 누적
                if not self.absolute_e:
                    self.total_filament += e_delta
            elif self.in_wipe:
                # WIPE 상태에서의 이동 (리트랙션하며 이동) = wipe 세그먼트
                layer.wipes.append(segment)
            else:
                # E 변화 없거나 음수(리트랙션) = 이동 세그먼트
                layer.travels.append(segment)

            # 바운딩 박스 업데이트
            self.bounding_box.update(new_x, new_y, effective_z)

        # 상태 업데이트
        self.current_x = new_x
        self.current_y = new_y
        self.current_z = new_z
        self.current_e = new_e

    def _process_line(self, line: GCodeLine):
        """단일 G-code 라인 처리"""
        cmd = line.cmd.upper() if line.cmd else ""
        raw = line.raw or ""
        comment = line.comment or ""

        # WIPE 상태 감지 (BambuStudio/OrcaSlicer)
        if 'WIPE_START' in raw or 'WIPE_START' in comment:
            self.in_wipe = True
        elif 'WIPE_END' in raw or 'WIPE_END' in comment:
            self.in_wipe = False

        # 서포트 상태 감지 (다양한 슬라이서 지원)
        comment_upper = comment.upper()
        raw_upper = raw.upper()

        # 서포트 시작 키워드
        # - Cura: ;TYPE:SUPPORT, ;TYPE:SUPPORT-INTERFACE
        # - BambuStudio/OrcaSlicer: ; FEATURE: Support, ; FEATURE: Support interface
        # - PrusaSlicer: ;TYPE:SUPPORT, SUPPORT-MATERIAL
        support_start_keywords = [
            'TYPE:SUPPORT', 'TYPE: SUPPORT',
            'SUPPORT-MATERIAL',
            'TYPE:SUPPORT-INTERFACE', 'TYPE: SUPPORT-INTERFACE',
            # BambuStudio/OrcaSlicer FEATURE 스타일 (공백 포함)
            'FEATURE: SUPPORT', 'FEATURE:SUPPORT',
            'FEATURE: SUPPORT INTERFACE', 'FEATURE:SUPPORT INTERFACE',
            'FEATURE: SUPPORT TRANSITION', 'FEATURE:SUPPORT TRANSITION',
        ]

        if any(kw in comment_upper or kw in raw_upper for kw in support_start_keywords):
            self.in_support = True
        # 서포트 종료 (다른 TYPE/FEATURE로 전환)
        elif any(kw in comment_upper or kw in raw_upper for kw in [
            # Cura TYPE 스타일
            'TYPE:WALL', 'TYPE: WALL', 'TYPE:OUTER', 'TYPE: OUTER',
            'TYPE:INNER', 'TYPE: INNER', 'TYPE:SKIN', 'TYPE: SKIN',
            'TYPE:FILL', 'TYPE: FILL', 'TYPE:PERIMETER',
            'TYPE:SOLID', 'TYPE: SOLID', 'TYPE:SPARSE', 'TYPE: SPARSE',
            'TYPE:TOP', 'TYPE: TOP', 'TYPE:BOTTOM', 'TYPE: BOTTOM',
            'TYPE:BRIDGE', 'TYPE: BRIDGE', 'TYPE:OVERHANG',
            'TYPE:SKIRT', 'TYPE: SKIRT', 'TYPE:BRIM', 'TYPE: BRIM',
            'TYPE:PRIME', 'TYPE: PRIME', 'TYPE:CUSTOM', 'TYPE: CUSTOM',
            'TYPE:EXTERNAL', 'TYPE: EXTERNAL', 'TYPE:INTERNAL', 'TYPE: INTERNAL',
            # BambuStudio/OrcaSlicer FEATURE 스타일
            'FEATURE: OUTER WALL', 'FEATURE:OUTER WALL',
            'FEATURE: INNER WALL', 'FEATURE:INNER WALL',
            'FEATURE: OVERHANG WALL', 'FEATURE:OVERHANG WALL',
            'FEATURE: SPARSE INFILL', 'FEATURE:SPARSE INFILL',
            'FEATURE: INTERNAL SOLID INFILL', 'FEATURE:INTERNAL SOLID INFILL',
            'FEATURE: SOLID INFILL', 'FEATURE:SOLID INFILL',
            'FEATURE: TOP SURFACE', 'FEATURE:TOP SURFACE',
            'FEATURE: BOTTOM SURFACE', 'FEATURE:BOTTOM SURFACE',
            'FEATURE: IRONING', 'FEATURE:IRONING',
            'FEATURE: BRIDGE', 'FEATURE:BRIDGE',
            'FEATURE: SKIRT', 'FEATURE:SKIRT',
            'FEATURE: BRIM', 'FEATURE:BRIM',
            'FEATURE: PRIME TOWER', 'FEATURE:PRIME TOWER',
            'FEATURE: CUSTOM', 'FEATURE:CUSTOM',
        ]):
            self.in_support = False

        # 메타데이터 추출
        self._extract_metadata_from_line(line)

        # 레이어 마커 감지
        layer_num = self._detect_layer_from_line(line)
        if layer_num is not None and layer_num >= 0:
            self.current_layer = layer_num
            self.pending_layer_change = False

        # 명령어 처리
        if cmd == 'G0':
            self._process_move(line, is_rapid=True)
        elif cmd == 'G1':
            self._process_move(line, is_rapid=False)
        elif cmd == 'G28':
            # 홈 복귀
            params = line.params
            if not params or 'X' in params:
                self.current_x = 0
            if not params or 'Y' in params:
                self.current_y = 0
            if not params or 'Z' in params:
                self.current_z = 0
        elif cmd == 'G90':
            self.absolute_xyz = True
        elif cmd == 'G91':
            self.absolute_xyz = False
        elif cmd == 'M82':
            self.absolute_e = True
        elif cmd == 'M83':
            self.absolute_e = False
        elif cmd == 'G92':
            # 위치 리셋
            if 'X' in line.params:
                self.current_x = line.params['X']
            if 'Y' in line.params:
                self.current_y = line.params['Y']
            if 'Z' in line.params:
                self.current_z = line.params['Z']
            if 'E' in line.params:
                # E 리셋 시 절대 모드에서 필라멘트 계산
                if self.absolute_e and self.current_e > 0:
                    self.total_filament += self.current_e
                self.current_e = line.params['E']
        # 온도 명령어 처리
        elif cmd in ('M104', 'M109'):
            # M104: 노즐 온도 설정 (대기 안함)
            # M109: 노즐 온도 설정 (대기)
            if 'S' in line.params:
                self.current_nozzle_temp = line.params['S']
                # 현재 레이어에 온도 기록
                if self.current_layer >= 0 and self.current_layer in self.layers:
                    self.layers[self.current_layer].nozzleTemp = self.current_nozzle_temp
        elif cmd in ('M140', 'M190'):
            # M140: 베드 온도 설정 (대기 안함)
            # M190: 베드 온도 설정 (대기)
            if 'S' in line.params:
                self.current_bed_temp = line.params['S']
                # 현재 레이어에 온도 기록
                if self.current_layer >= 0 and self.current_layer in self.layers:
                    self.layers[self.current_layer].bedTemp = self.current_bed_temp
        elif cmd == 'G9111':
            # OrcaSlicer/BambuStudio 특수 온도 명령어
            # G9111 bedTemp=55 extruderTemp=220
            raw = line.raw or ""
            bed_match = re.search(r'bedTemp\s*=\s*(\d+(?:\.\d+)?)', raw, re.IGNORECASE)
            ext_match = re.search(r'extruderTemp\s*=\s*(\d+(?:\.\d+)?)', raw, re.IGNORECASE)
            if bed_match:
                self.current_bed_temp = float(bed_match.group(1))
            if ext_match:
                self.current_nozzle_temp = float(ext_match.group(1))

    def _calculate_layer_height(self) -> float:
        """레이어 높이 계산"""
        if len(self.layers) < 2:
            return 0.2  # 기본값

        sorted_layers = sorted(self.layers.values(), key=lambda x: x.layerNum)

        heights = []
        for i in range(1, min(len(sorted_layers), 20)):  # 처음 20개 레이어만 분석
            h = sorted_layers[i].z - sorted_layers[i-1].z
            if 0.04 <= h <= 0.5:  # 합리적인 범위
                heights.append(h)

        if heights:
            # 최빈값에 가까운 평균 계산
            heights.sort()
            mid_start = len(heights) // 4
            mid_end = len(heights) - mid_start if mid_start > 0 else len(heights)
            return sum(heights[mid_start:mid_end]) / (mid_end - mid_start)
        return 0.2

    def _parse_time_to_seconds(self, time_str: str) -> int:
        """시간 문자열을 초로 변환"""
        if not time_str:
            return 0

        # 순수 숫자 (초)
        try:
            return int(time_str)
        except ValueError:
            pass

        # "1h 23m 45s" 또는 "2h 10m 43s" 형식
        total = 0
        patterns = [
            (r'(\d+)\s*h', 3600),
            (r'(\d+)\s*m(?!s)', 60),  # ms 아닌 m만
            (r'(\d+)\s*s', 1),
            (r'(\d+)\s*d', 86400),
        ]
        for pattern, multiplier in patterns:
            match = re.search(pattern, time_str, re.IGNORECASE)
            if match:
                total += int(match.group(1)) * multiplier

        if total > 0:
            return total

        # "HH:MM:SS" 형식
        parts = time_str.split(':')
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass

        return 0

    def _finalize_filament_calculation(self):
        """최종 필라멘트 사용량 계산"""
        # 절대 모드에서 마지막 E 값이 총 사용량
        if self.absolute_e and self.current_e > self.total_filament:
            self.total_filament = self.current_e

    def extract(self, file_path: str) -> SegmentExtractionResult:
        """G-code 파일에서 세그먼트 추출

        Raises:
            EncodingError: 인코딩 오류로 파일을 제대로 파싱할 수 없는 경우
        """
        # 상태 초기화
        self._reset_state()

        # 파싱
        parse_result = parse_gcode(file_path)
        lines = parse_result.lines

        # 슬라이서 감지
        self.slicer_type, self.slicer_version = SlicerDetector.detect(lines)

        # 인코딩 폴백 + unknown 슬라이서 = 인코딩 에러로 판단
        if parse_result.is_fallback and self.slicer_type == SlicerType.UNKNOWN:
            raise EncodingError(
                f"Failed to decode file with supported encodings (utf-8, cp949, euc-kr). "
                f"File may be corrupted or use an unsupported encoding. "
                f"Fallback encoding: {parse_result.encoding}"
            )

        # 모든 라인 처리
        for line in lines:
            self._process_line(line)

        # 최종 필라멘트 계산
        self._finalize_filament_calculation()

        # 결과 정리
        sorted_layers = sorted(self.layers.values(), key=lambda x: x.layerNum)

        # 빈 레이어 필터링 (압출이 없는 레이어)
        sorted_layers = [l for l in sorted_layers if l.extrusions or l.travels]

        # 레이어 번호 재정렬
        for i, layer in enumerate(sorted_layers):
            layer.layerNum = i

        # 레이어 높이 계산
        layer_height = self._calculate_layer_height()

        # 첫 레이어 높이 결정 (비정상적으로 큰 값 필터링)
        first_layer_height = 0.2
        if sorted_layers:
            first_z = sorted_layers[0].z
            # 첫 레이어가 비정상적으로 크면 (스타트 코드 Z 이동) 다음 레이어로 추정
            if first_z > 1.0 and len(sorted_layers) > 1:
                first_layer_height = sorted_layers[1].z
            elif first_z > 0:
                first_layer_height = first_z

        # 메타데이터 구성
        metadata = Metadata(
            boundingBox=self.bounding_box,
            layerCount=len(sorted_layers),
            totalFilament=self.total_filament,
            printTime=self._parse_time_to_seconds(self.estimated_time or ""),
            layerHeight=layer_height,
            firstLayerHeight=first_layer_height,
            estimatedTime=self.estimated_time,
            filamentType=self.filament_type,
            slicer=self.slicer_type.value,
            slicerVersion=self.slicer_version
        )

        return SegmentExtractionResult(
            layers=sorted_layers,
            metadata=metadata
        )


def extract_segments(file_path: str, binary_format: bool = False) -> Dict[str, Any]:
    """
    G-code 파일에서 레이어별 세그먼트 추출

    Args:
        file_path: G-code 파일 경로
        binary_format: True면 Float32Array+Base64 형식, False면 JSON 배열 형식

    Returns:
        레이어별 세그먼트 데이터 딕셔너리
    """
    extractor = GCodeSegmentExtractor()
    result = extractor.extract(file_path)
    return result.to_binary_dict() if binary_format else result.to_dict()


def extract_segments_binary(file_path: str) -> Dict[str, Any]:
    """
    G-code 파일에서 레이어별 세그먼트 추출 (Float32Array + Base64 형식)

    클라이언트에서 효율적으로 처리할 수 있는 바이너리 형식으로 반환.
    JavaScript에서 디코딩 예시:
        const binary = atob(layer.extrusionData);
        const buffer = new ArrayBuffer(binary.length);
        const view = new Uint8Array(buffer);
        for (let i = 0; i < binary.length; i++) view[i] = binary.charCodeAt(i);
        const floats = new Float32Array(buffer);
        // floats: [x1, y1, z1, x2, y2, z2, ...] 형태

    Args:
        file_path: G-code 파일 경로

    Returns:
        Float32Array + Base64 형식의 세그먼트 데이터
    """
    return extract_segments(file_path, binary_format=True)


def extract_segments_batch(file_paths: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    여러 G-code 파일에서 세그먼트 일괄 추출

    Args:
        file_paths: G-code 파일 경로 리스트

    Returns:
        파일명을 키로 하는 결과 딕셔너리
    """
    import os
    results = {}
    for path in file_paths:
        try:
            result = extract_segments(path)
            filename = os.path.basename(path)
            results[filename] = result
        except Exception as e:
            import os
            filename = os.path.basename(path)
            results[filename] = {"error": str(e)}
    return results


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python segment_extractor.py <gcode_file> [output_json]")
        print("\nSupported slicers: OrcaSlicer, BambuStudio, Cura, PrusaSlicer, Simplify3D")
        sys.exit(1)

    file_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Processing: {file_path}")
    start_time = time.time()

    result = extract_segments(file_path)

    elapsed = time.time() - start_time
    print(f"\n=== Results ===")
    print(f"Slicer: {result['metadata']['slicer']} {result['metadata'].get('slicerVersion', '')}")
    print(f"Processed in {elapsed:.2f}s")
    print(f"Layers: {result['metadata']['layerCount']}")
    print(f"Filament: {result['metadata']['totalFilament']:.2f}mm")
    print(f"Print time: {result['metadata']['printTime']}s ({result['metadata'].get('estimatedTime', 'N/A')})")
    print(f"Layer height: {result['metadata']['layerHeight']}mm")
    print(f"First layer: {result['metadata']['firstLayerHeight']}mm")
    print(f"Bounding box: {result['metadata']['boundingBox']}")

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved to: {output_path}")
    else:
        # 첫 3개 레이어만 샘플 출력
        if result['layers']:
            print(f"\n=== Sample (first 3 layers) ===")
            for layer in result['layers'][:3]:
                print(f"Layer {layer['layerNum']}: z={layer['z']}mm, "
                      f"extrusions={len(layer['extrusions'])}, travels={len(layer['travels'])}, "
                      f"wipes={len(layer['wipes'])}, supports={len(layer['supports'])}")
