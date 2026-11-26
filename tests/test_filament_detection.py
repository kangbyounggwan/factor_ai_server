"""재질 자동감지 회귀시험 (bdd3d24)

슬라이서가 거의 모든 파일에 넣는 'absolute ...' 주석의 ABS 를
필라멘트 ABS 로 오판하지 않는지, 실제 재질 선언은 그대로 잡는지 확인한다.

실행 (저장소 루트에서):
    python -m unittest tests.test_filament_detection -v
"""
import unittest

from gcode_analyzer.data_preparer import detect_filament_from_gcode
from gcode_analyzer.parser import parse_gcode_from_string
from gcode_analyzer.summary import summarize_gcode

BODY = "\n".join([
    "M104 S205", "M140 S60", "G28", "G1 Z0.2 F3000",
    "G1 X10 Y10 E1 F1500", "G1 X20 Y10 E2", "G1 Z0.4", "G1 X10 Y20 E3",
])


def detect(header: str):
    """(summary.py 감지값, data_preparer.py 감지값)"""
    lines = parse_gcode_from_string(header + "\n" + BODY).lines
    return summarize_gcode(lines).filament_type, detect_filament_from_gcode(lines)


class FilamentDetectionTest(unittest.TestCase):
    # 수정 전에는 summary.py 가 아래 세 경우를 ABS 로 판정했다
    def test_absolute_extrusion_comment_is_not_abs(self):
        self.assertEqual(detect("M82 ;absolute extrusion mode"), (None, None))

    def test_absolute_coordinates_comment_is_not_abs(self):
        self.assertEqual(detect("G90 ; use absolute coordinates"), (None, None))

    def test_absolute_positioning_without_space_is_not_abs(self):
        self.assertEqual(detect("G90;absolute positioning"), (None, None))

    # 실제 재질 선언은 계속 잡아야 한다
    def test_cura_style_pla(self):
        self.assertEqual(detect(";filament_type = PLA"), ("PLA", "PLA"))

    def test_prusa_style_petg(self):
        self.assertEqual(detect("; FILAMENT_TYPE:PETG"), ("PETG", "PETG"))

    def test_absolute_comment_and_pla_declaration(self):
        self.assertEqual(detect("M82 ;absolute extrusion mode\n;filament_type = PLA"), ("PLA", "PLA"))

    def test_real_abs_is_still_detected(self):
        self.assertEqual(detect(";filament_type = ABS"), ("ABS", "ABS"))

    def test_simple_comment_pattern(self):
        self.assertEqual(detect("; ABS"), ("ABS", "ABS"))


if __name__ == "__main__":
    unittest.main()
