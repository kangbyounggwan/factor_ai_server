"""
G-code Comprehensive Summary Analyzer

10만줄 이상의 G-code 파일에서 핵심 정보를 추출하여
LLM에 전달하기 전 요약 정보를 생성합니다.

추출 정보:
- 온도 프로파일 (노즐/베드 온도 변화, 평균, 변화율)
- 피드레이트 정보 (속도 분포, 평균, 최대/최소)
- 서포트/제품 출력 비율
- 예상 출력 시간
- 익스트루전 이벤트
- 레이어별 통계
- 리트랙션 정보
- 팬 제어 이벤트
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import re
from .models import GCodeLine


@dataclass
class TemperatureProfile:
    """온도 프로파일 정보"""
    # 노즐 온도
    nozzle_temps: List[float] = field(default_factory=list)
    nozzle_min: float = 0.0
    nozzle_max: float = 0.0
    nozzle_avg: float = 0.0
    nozzle_changes: int = 0  # 온도 변경 횟수
    nozzle_change_rate: float = 0.0  # 평균 변화율 (도/분)

    # 베드 온도
    bed_temps: List[float] = field(default_factory=list)
    bed_min: float = 0.0
    bed_max: float = 0.0
    bed_avg: float = 0.0
    bed_changes: int = 0

    # 온도 이벤트 타임라인
    temp_events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FeedRateProfile:
    """피드레이트(속도) 프로파일"""
    all_speeds: List[float] = field(default_factory=list)
    min_speed: float = 0.0
    max_speed: float = 0.0
    avg_speed: float = 0.0

    # 속도 구간별 분포
    speed_distribution: Dict[str, int] = field(default_factory=dict)
    # 예: {"0-1000": 1234, "1000-2000": 5678, ...}

    # 이동 타입별 속도
    travel_speed_avg: float = 0.0  # G0 (비출력 이동)
    print_speed_avg: float = 0.0   # G1 (출력 이동)


@dataclass
class ExtrusionProfile:
    """익스트루전 정보"""
    total_extrusion: float = 0.0  # 총 익스트루전 길이 (mm)
    total_filament_used: float = 0.0  # 필라멘트 사용량 (m)
    extrusion_moves: int = 0  # E 값 포함 이동 수

    # 리트랙션 정보
    retraction_count: int = 0
    retraction_distances: List[float] = field(default_factory=list)
    avg_retraction: float = 0.0
    max_retraction: float = 0.0


@dataclass
class LayerProfile:
    """레이어 정보"""
    total_layers: int = 0
    layer_heights: List[float] = field(default_factory=list)
    avg_layer_height: float = 0.0
    first_layer_height: float = 0.0

    # 레이어별 통계
    layer_times: Dict[int, float] = field(default_factory=dict)  # 레이어별 예상 시간
    layer_extrusion: Dict[int, float] = field(default_factory=dict)  # 레이어별 익스트루전


@dataclass
class SupportProfile:
    """서포트 정보"""
    has_support: bool = False
    support_extrusion: float = 0.0  # 서포트 익스트루전 양
    model_extrusion: float = 0.0    # 모델 익스트루전 양
    support_ratio: float = 0.0       # 서포트 비율 (%)
    support_layers: int = 0          # 서포트가 있는 레이어 수


@dataclass
class FanProfile:
    """팬 제어 정보"""
    fan_events: List[Dict[str, Any]] = field(default_factory=list)
    max_fan_speed: int = 0
    fan_on_layer: int = 0  # 팬이 처음 켜지는 레이어


@dataclass
class PrintTimeEstimate:
    """출력 시간 예상"""
    estimated_seconds: int = 0
    estimated_minutes: float = 0.0
    estimated_hours: float = 0.0
    formatted_time: str = "00:00:00"

    # 시간 분포
    travel_time: float = 0.0   # 비출력 이동 시간
    print_time: float = 0.0    # 출력 시간
    heating_time: float = 0.0  # 예열 시간 (추정)


@dataclass
class GCodeComprehensiveSummary:
    """종합 G-code 요약"""
    # 기본 정보
    file_name: str = ""
    total_lines: int = 0
    file_size_kb: float = 0.0
    slicer_info: Optional[str] = None
    filament_type: Optional[str] = None

    # 상세 프로파일
    temperature: TemperatureProfile = field(default_factory=TemperatureProfile)
    feed_rate: FeedRateProfile = field(default_factory=FeedRateProfile)
    extrusion: ExtrusionProfile = field(default_factory=ExtrusionProfile)
    layer: LayerProfile = field(default_factory=LayerProfile)
    support: SupportProfile = field(default_factory=SupportProfile)
    fan: FanProfile = field(default_factory=FanProfile)
    print_time: PrintTimeEstimate = field(default_factory=PrintTimeEstimate)

    # 구간 정보
    start_gcode_lines: int = 0
    end_gcode_lines: int = 0
    body_lines: int = 0

    # 이벤트 요약
    total_temp_changes: int = 0
    total_fan_changes: int = 0
    total_retractions: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return asdict(self)

    def to_llm_summary(self) -> str:
        """LLM에 전달할 요약 텍스트 생성"""
        lines = [
            "=== G-code 출력 요약 ===",
            f"파일: {self.file_name}",
            f"총 라인 수: {self.total_lines:,}줄",
            f"슬라이서: {self.slicer_info or '알 수 없음'}",
            f"필라멘트: {self.filament_type or '알 수 없음'}",
            "",
            "--- 온도 설정 ---",
            f"노즐 온도: {self.temperature.nozzle_min}°C ~ {self.temperature.nozzle_max}°C (평균: {self.temperature.nozzle_avg:.1f}°C)",
            f"베드 온도: {self.temperature.bed_min}°C ~ {self.temperature.bed_max}°C (평균: {self.temperature.bed_avg:.1f}°C)",
            f"온도 변경 횟수: {self.temperature.nozzle_changes}회",
            "",
            "--- 속도 설정 ---",
            f"출력 속도: {self.feed_rate.min_speed:.0f} ~ {self.feed_rate.max_speed:.0f} mm/min",
            f"평균 속도: {self.feed_rate.avg_speed:.0f} mm/min",
            f"이동 속도 평균: {self.feed_rate.travel_speed_avg:.0f} mm/min",
            f"출력 속도 평균: {self.feed_rate.print_speed_avg:.0f} mm/min",
            "",
            "--- 레이어 정보 ---",
            f"총 레이어: {self.layer.total_layers}층",
            f"레이어 높이: {self.layer.avg_layer_height:.2f}mm (첫 레이어: {self.layer.first_layer_height:.2f}mm)",
            "",
            "--- 익스트루전 ---",
            f"총 익스트루전: {self.extrusion.total_extrusion:.2f}mm",
            f"필라멘트 사용량: {self.extrusion.total_filament_used:.2f}m",
            f"리트랙션 횟수: {self.extrusion.retraction_count}회",
            f"평균 리트랙션: {self.extrusion.avg_retraction:.2f}mm",
            "",
            "--- 서포트 ---",
            f"서포트 사용: {'예' if self.support.has_support else '아니오'}",
        ]

        if self.support.has_support:
            lines.extend([
                f"서포트 비율: {self.support.support_ratio:.1f}%",
                f"서포트 레이어: {self.support.support_layers}층",
            ])

        lines.extend([
            "",
            "--- 예상 출력 시간 ---",
            f"총 시간: {self.print_time.formatted_time}",
            f"출력 시간: {self.print_time.print_time:.1f}분",
            f"이동 시간: {self.print_time.travel_time:.1f}분",
            "",
            "--- 구간 정보 ---",
            f"시작 G-code: {self.start_gcode_lines}줄",
            f"본문 (출력): {self.body_lines}줄",
            f"종료 G-code: {self.end_gcode_lines}줄",
        ])

        return "\n".join(lines)


class GCodeSummaryAnalyzer:
    """G-code 종합 요약 분석기"""

    def __init__(self, lines: List[GCodeLine], file_path: str = ""):
        self.lines = lines
        self.file_path = file_path
        self.summary = GCodeComprehensiveSummary()

        # 상태 추적 변수
        self._current_e = 0.0
        self._prev_e = 0.0
        self._current_z = 0.0
        self._current_layer = 0
        self._is_relative_e = False
        self._in_support = False

    def analyze(self) -> GCodeComprehensiveSummary:
        """전체 분석 실행"""
        self._analyze_basic_info()
        self._analyze_temperature()
        self._analyze_feed_rate()
        self._analyze_extrusion()
        self._analyze_layers()
        self._analyze_support()
        self._analyze_fan()
        self._estimate_print_time()
        self._analyze_sections()

        return self.summary

    def _analyze_basic_info(self):
        """기본 정보 분석"""
        import os

        self.summary.total_lines = len(self.lines)

        if self.file_path:
            self.summary.file_name = os.path.basename(self.file_path)
            try:
                self.summary.file_size_kb = os.path.getsize(self.file_path) / 1024
            except:
                pass

        # 슬라이서 및 필라멘트 정보 감지
        for line in self.lines[:200]:
            if line.comment:
                comment = line.comment.strip()

                # 슬라이서 감지
                if not self.summary.slicer_info:
                    if "Cura" in comment or "CURA" in comment:
                        self.summary.slicer_info = "Ultimaker Cura"
                    elif "PrusaSlicer" in comment:
                        self.summary.slicer_info = "PrusaSlicer"
                    elif "Simplify3D" in comment:
                        self.summary.slicer_info = "Simplify3D"
                    elif "Slic3r" in comment:
                        self.summary.slicer_info = "Slic3r"
                    elif "ideaMaker" in comment:
                        self.summary.slicer_info = "ideaMaker"
                    elif "Generated by" in comment:
                        self.summary.slicer_info = comment.replace("Generated by", "").strip()

                # 필라멘트 타입 감지
                if not self.summary.filament_type:
                    comment_upper = comment.upper()
                    for ftype in ["PLA", "ABS", "PETG", "TPU", "NYLON", "ASA", "PC"]:
                        if ftype in comment_upper:
                            # 더 정확한 매칭을 위해 단어 경계 확인
                            if re.search(rf'\b{ftype}\b', comment_upper):
                                self.summary.filament_type = ftype
                                break

    def _analyze_temperature(self):
        """온도 프로파일 분석"""
        temp_profile = self.summary.temperature
        nozzle_temps = []
        bed_temps = []

        prev_nozzle = 0.0
        prev_bed = 0.0

        for line in self.lines:
            # 노즐 온도 (M104: 설정, M109: 설정 및 대기)
            if line.cmd in ["M104", "M109"]:
                if "S" in line.params:
                    temp = line.params["S"]
                    if temp > 0:  # 0 제외 (끄기 명령)
                        nozzle_temps.append(temp)

                        # 변화 감지
                        if prev_nozzle != 0 and abs(temp - prev_nozzle) > 1:
                            temp_profile.nozzle_changes += 1
                        prev_nozzle = temp

                        temp_profile.temp_events.append({
                            "line": line.index,
                            "type": "nozzle",
                            "cmd": line.cmd,
                            "temp": temp
                        })

            # 베드 온도 (M140: 설정, M190: 설정 및 대기)
            elif line.cmd in ["M140", "M190"]:
                if "S" in line.params:
                    temp = line.params["S"]
                    if temp > 0:
                        bed_temps.append(temp)

                        if prev_bed != 0 and abs(temp - prev_bed) > 1:
                            temp_profile.bed_changes += 1
                        prev_bed = temp

                        temp_profile.temp_events.append({
                            "line": line.index,
                            "type": "bed",
                            "cmd": line.cmd,
                            "temp": temp
                        })

        # 통계 계산
        if nozzle_temps:
            temp_profile.nozzle_temps = nozzle_temps
            temp_profile.nozzle_min = min(nozzle_temps)
            temp_profile.nozzle_max = max(nozzle_temps)
            temp_profile.nozzle_avg = sum(nozzle_temps) / len(nozzle_temps)

        if bed_temps:
            temp_profile.bed_temps = bed_temps
            temp_profile.bed_min = min(bed_temps)
            temp_profile.bed_max = max(bed_temps)
            temp_profile.bed_avg = sum(bed_temps) / len(bed_temps)

    def _analyze_feed_rate(self):
        """피드레이트 분석"""
        feed_profile = self.summary.feed_rate
        all_speeds = []
        travel_speeds = []
        print_speeds = []

        speed_buckets = defaultdict(int)
        bucket_size = 1000  # 1000 mm/min 단위

        for line in self.lines:
            if line.cmd in ["G0", "G1"]:
                if "F" in line.params:
                    speed = line.params["F"]
                    all_speeds.append(speed)

                    # 버킷 분류
                    bucket = int(speed // bucket_size) * bucket_size
                    bucket_key = f"{bucket}-{bucket + bucket_size}"
                    speed_buckets[bucket_key] += 1

                    # 이동 타입 분류
                    if line.cmd == "G0":
                        travel_speeds.append(speed)
                    elif "E" in line.params:
                        print_speeds.append(speed)

        if all_speeds:
            feed_profile.all_speeds = all_speeds
            feed_profile.min_speed = min(all_speeds)
            feed_profile.max_speed = max(all_speeds)
            feed_profile.avg_speed = sum(all_speeds) / len(all_speeds)
            feed_profile.speed_distribution = dict(speed_buckets)

        if travel_speeds:
            feed_profile.travel_speed_avg = sum(travel_speeds) / len(travel_speeds)

        if print_speeds:
            feed_profile.print_speed_avg = sum(print_speeds) / len(print_speeds)

    def _analyze_extrusion(self):
        """익스트루전 분석"""
        ext_profile = self.summary.extrusion

        prev_e = 0.0
        total_positive_e = 0.0
        retractions = []
        extrusion_moves = 0

        for line in self.lines:
            # 상대/절대 익스트루전 모드 확인
            if line.cmd == "M82":
                self._is_relative_e = False
            elif line.cmd == "M83":
                self._is_relative_e = True
            elif line.cmd == "G92" and "E" in line.params:
                # E 리셋
                prev_e = line.params["E"]

            # 익스트루전 이동 분석
            if line.cmd == "G1" and "E" in line.params:
                e_val = line.params["E"]
                extrusion_moves += 1

                if self._is_relative_e:
                    delta_e = e_val
                else:
                    delta_e = e_val - prev_e
                    prev_e = e_val

                if delta_e > 0:
                    total_positive_e += delta_e
                elif delta_e < 0:
                    # 리트랙션
                    retractions.append(abs(delta_e))

        ext_profile.total_extrusion = total_positive_e
        ext_profile.total_filament_used = total_positive_e / 1000  # mm -> m
        ext_profile.extrusion_moves = extrusion_moves
        ext_profile.retraction_count = len(retractions)
        ext_profile.retraction_distances = retractions

        if retractions:
            ext_profile.avg_retraction = sum(retractions) / len(retractions)
            ext_profile.max_retraction = max(retractions)

    def _analyze_layers(self):
        """레이어 분석"""
        layer_profile = self.summary.layer

        z_values = []
        layer_count = 0

        for line in self.lines:
            # 레이어 주석 감지
            if line.comment:
                comment = line.comment.strip().upper()
                if comment.startswith("LAYER:"):
                    try:
                        layer_num = int(comment.replace("LAYER:", "").strip())
                        layer_count = max(layer_count, layer_num + 1)
                    except ValueError:
                        pass

            # Z 값 추적
            if line.cmd in ["G0", "G1"] and "Z" in line.params:
                z = line.params["Z"]
                if z > 0:
                    z_values.append(z)

        # 레이어 높이 계산
        if z_values:
            unique_z = sorted(set(z_values))
            if len(unique_z) > 1:
                # Z 값 차이로 레이어 높이 추정
                diffs = [unique_z[i+1] - unique_z[i] for i in range(len(unique_z)-1)]
                valid_diffs = [d for d in diffs if 0.05 < d < 1.0]  # 합리적인 범위

                if valid_diffs:
                    layer_profile.avg_layer_height = sum(valid_diffs) / len(valid_diffs)
                    layer_profile.first_layer_height = valid_diffs[0] if valid_diffs else 0.2

                # 레이어 수 추정
                if not layer_count:
                    layer_count = len(unique_z)

        layer_profile.total_layers = layer_count
        layer_profile.layer_heights = z_values[:100] if z_values else []  # 처음 100개만

    def _analyze_support(self):
        """서포트 분석"""
        support_profile = self.summary.support

        support_extrusion = 0.0
        model_extrusion = 0.0
        in_support = False
        support_layer_set = set()
        current_layer = 0
        prev_e = 0.0

        for line in self.lines:
            # 레이어 추적
            if line.comment:
                comment = line.comment.strip().upper()
                if comment.startswith("LAYER:"):
                    try:
                        current_layer = int(comment.replace("LAYER:", "").strip())
                    except ValueError:
                        pass

                # 서포트 구간 감지 (다양한 슬라이서 포맷)
                if any(kw in comment for kw in ["TYPE:SUPPORT", "SUPPORT-MATERIAL", ";SUPPORT", "FEATURE:SUPPORT"]):
                    in_support = True
                elif any(kw in comment for kw in ["TYPE:WALL", "TYPE:SKIN", "TYPE:FILL", "TYPE:PERIMETER", "FEATURE:INNER"]):
                    in_support = False

            # 익스트루전 추적
            if line.cmd == "G92" and "E" in line.params:
                prev_e = line.params["E"]

            if line.cmd == "G1" and "E" in line.params:
                e_val = line.params["E"]
                delta_e = e_val - prev_e
                prev_e = e_val

                if delta_e > 0:
                    if in_support:
                        support_extrusion += delta_e
                        support_layer_set.add(current_layer)
                    else:
                        model_extrusion += delta_e

        support_profile.support_extrusion = support_extrusion
        support_profile.model_extrusion = model_extrusion
        support_profile.has_support = support_extrusion > 0
        support_profile.support_layers = len(support_layer_set)

        total = support_extrusion + model_extrusion
        if total > 0:
            support_profile.support_ratio = (support_extrusion / total) * 100

    def _analyze_fan(self):
        """팬 제어 분석"""
        fan_profile = self.summary.fan

        current_layer = 0
        fan_first_on_layer = -1

        for line in self.lines:
            # 레이어 추적
            if line.comment and "LAYER:" in line.comment.upper():
                try:
                    current_layer = int(line.comment.upper().replace("LAYER:", "").strip())
                except ValueError:
                    pass

            # 팬 제어 (M106: 켜기, M107: 끄기)
            if line.cmd == "M106":
                speed = line.params.get("S", 255)
                fan_profile.fan_events.append({
                    "line": line.index,
                    "layer": current_layer,
                    "action": "on",
                    "speed": speed
                })
                fan_profile.max_fan_speed = max(fan_profile.max_fan_speed, int(speed))

                if fan_first_on_layer < 0 and speed > 0:
                    fan_first_on_layer = current_layer

            elif line.cmd == "M107":
                fan_profile.fan_events.append({
                    "line": line.index,
                    "layer": current_layer,
                    "action": "off",
                    "speed": 0
                })

        fan_profile.fan_on_layer = fan_first_on_layer if fan_first_on_layer >= 0 else 0
        self.summary.total_fan_changes = len(fan_profile.fan_events)

    def _estimate_print_time(self):
        """출력 시간 추정 - G-code 직접 시뮬레이션"""
        time_estimate = self.summary.print_time

        # 직접 계산 방식 (헤더 주석 무시)
        total_time_sec = 0.0
        calc_travel_time_sec = 0.0
        calc_print_time_sec = 0.0

        last_x = last_y = last_z = None
        current_f = 1800.0  # mm/min 기본값 (= 30 mm/s)

        for line in self.lines:
            if line.cmd not in ["G0", "G1"]:
                continue

            # 피드레이트 업데이트
            if "F" in line.params:
                current_f = line.params["F"]

            # 좌표 추출
            x = line.params.get("X")
            y = line.params.get("Y")
            z = line.params.get("Z")

            # 첫 번째 좌표는 기준점 설정만
            if last_x is None:
                last_x = x if x is not None else 0.0
                last_y = y if y is not None else 0.0
                last_z = z if z is not None else 0.0
                continue

            # 현재 좌표 (없으면 이전 값 유지)
            curr_x = x if x is not None else last_x
            curr_y = y if y is not None else last_y
            curr_z = z if z is not None else last_z

            # 거리 계산
            dx = curr_x - last_x
            dy = curr_y - last_y
            dz = curr_z - last_z
            distance = (dx*dx + dy*dy + dz*dz) ** 0.5

            # 시간 계산 (F는 mm/min이므로 mm/s로 변환)
            speed_mm_s = current_f / 60.0
            if speed_mm_s > 0 and distance > 0:
                move_time = distance / speed_mm_s
                total_time_sec += move_time

                # Travel vs Print 구분
                if line.cmd == "G0" or "E" not in line.params:
                    calc_travel_time_sec += move_time
                else:
                    calc_print_time_sec += move_time

            # 좌표 업데이트
            last_x, last_y, last_z = curr_x, curr_y, curr_z

        # 결과 저장
        time_estimate.estimated_seconds = int(total_time_sec)
        time_estimate.travel_time = calc_travel_time_sec / 60.0  # 분 단위로 저장
        time_estimate.print_time = calc_print_time_sec / 60.0    # 분 단위로 저장

        # 시간 포맷팅
        seconds = time_estimate.estimated_seconds
        time_estimate.estimated_minutes = seconds / 60
        time_estimate.estimated_hours = seconds / 3600

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        time_estimate.formatted_time = f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _analyze_sections(self):
        """구간 분석 (START/BODY/END)"""
        start_end = 0
        body_end = len(self.lines)

        # START 끝 찾기: 첫 번째 LAYER:0 또는 실제 출력 시작
        for i, line in enumerate(self.lines):
            if line.comment and "LAYER:0" in line.comment.upper():
                start_end = i
                break
            # Z 이동 + 익스트루전 조합 감지
            if line.cmd == "G1" and "E" in line.params and "X" in line.params:
                if i > 50:  # 최소 50줄 이상 지나야 시작 구간 끝
                    start_end = i
                    break

        if start_end == 0:
            start_end = min(100, len(self.lines))

        # END 시작 찾기: 마지막 LAYER 또는 온도 끄기
        for i in range(len(self.lines) - 1, max(0, len(self.lines) - 500), -1):
            line = self.lines[i]
            if line.cmd in ["M104", "M140"] and line.params.get("S", 0) == 0:
                body_end = i
                break
            if line.comment and "END" in line.comment.upper():
                body_end = i
                break

        self.summary.start_gcode_lines = start_end
        self.summary.end_gcode_lines = len(self.lines) - body_end
        self.summary.body_lines = body_end - start_end

        # 총 이벤트 수
        self.summary.total_temp_changes = (
            self.summary.temperature.nozzle_changes +
            self.summary.temperature.bed_changes
        )
        self.summary.total_retractions = self.summary.extrusion.retraction_count


def analyze_gcode_summary(
    lines: List[GCodeLine],
    file_path: str = ""
) -> GCodeComprehensiveSummary:
    """G-code 종합 요약 분석 실행"""
    analyzer = GCodeSummaryAnalyzer(lines, file_path)
    return analyzer.analyze()
