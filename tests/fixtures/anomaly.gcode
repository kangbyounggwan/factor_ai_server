;FLAVOR:Marlin
;TIME:6623
;LAYER:0
M107
M190 S60
M109 S200
G28
G1 Z5 F5000
; Cold Extrusion Trigger (S0 then E move)
M104 S0 ; Set temp to 0
G4 P1000 ; Wait a bit (simulation)
G1 E10 F100 ; Extrude while cold! (Should trigger COLD_EXTRUSION)

; Reset temp
M104 S200
G4 P100 ; Wait...

; Early Temp Off Trigger
; Print continues...
G1 X10 Y10 E20
M104 S0 ; Temp OFF early! (Should trigger EARLY_TEMP_OFF)

; More printing after temp off
G1 X20 Y20 E25 ; Extrusion continues
G1 X30 Y30 E30

M84 ; End
