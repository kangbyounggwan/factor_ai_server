;FLAVOR:Marlin
;TIME:6623
;Filament used: 1.25368m
;LAYER:0
M107
M190 S60 ; Set bed temperature
M104 S200 ; Set nozzle temperature
M109 S200 ; Wait for nozzle temperature
G28 ; Home all axes
G1 Z5 F5000 ; Lift nozzle
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
M104 S0 ; Turn off nozzle
M140 S0 ; Turn off bed
M84 ; Disable motors
