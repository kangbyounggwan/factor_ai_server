;FLAVOR:Marlin
;TIME:6623
;Filament used: 1.25368m
;LAYER:0
M107
M190 S60
M109 S200
G28
G1 Z5 F5000
;LAYER:1
G0 F6000 X10 Y10 Z0.2
G1 F1200 E0
G1 X20 Y10 E0.5
G1 X20 Y20 E1.0
;LAYER:2
G0 F6000 X10 Y10 Z0.4
G1 F1200 E1.0
G1 X20 Y10 E1.5
G1 X20 Y20 E2.0

; ===== TEST: Early Temperature Off =====
; 출력 중간에 온도를 0으로 설정 (문제!)
M104 S0 ; 노즐 온도 끄기

; 하지만 출력이 계속됨 (문제!)
G1 X30 Y30 E3.0
G1 X40 Y40 E4.0
G1 X50 Y50 E5.0 F1500
G1 X60 Y60 E6.0

; ===== TEST: Resume then off again =====
M104 S200 ; 다시 가열
G4 P5000 ; 대기
G1 X70 Y70 E7.0
G1 X80 Y80 E8.0

; 또 다시 끄기 (급격한 온도 변화)
M104 S0

; 끝
M84
