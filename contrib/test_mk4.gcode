M73 P0 R30
M73 Q0 S32
M201 X4000 Y4000 Z200 E2500 ; sets maximum accelerations, mm/sec^2
M203 X300 Y300 Z40 E100 ; sets maximum feedrates, mm / sec
M204 P4000 R2500 T4000 ; sets acceleration (P, T) and retract acceleration (R), mm/sec^2
M205 X8.00 Y8.00 Z2.00 E10.00 ; sets the jerk limits, mm/sec
M205 S0 T0 ; sets the minimum extruding and travel feed rate, mm/sec

M486 S0
M486 ACali-Dragon_v1.stl
M486 S-1

;TYPE:Custom
M17 ; enable steppers
M862.1 P0.4 A0 F0 ; nozzle check
M862.3 P "MK4" ; printer model check
M862.5 P2 ; g-code level check
M862.6 P"Input shaper" ; FW feature check
M115 U6.4.0+11974

M555 X113.174 Y91.4842 W32 H25.5751

G90 ; use absolute coordinates
M83 ; extruder relative mode

G28 ; home all without mesh bed level

G1 X42 Y-4 Z5 F4800

M84 E ; turn off E motor

G29 P9 X10 Y-4 W32 H4

M106 S100

G0 Z40 F10000

M107

;
; MBL
;
M84 E ; turn off E motor
G29 P1 ; invalidate mbl & probe print area
G29 P1 X0 Y0 W50 H20 C ; probe near purge place
G29 P3.2 ; interpolate mbl probes
G29 P3.13 ; extrapolate mbl outside probe area
G29 A ; activate mbl

G21 ; set units to millimeters
G90 ; use absolute coordinates
M83 ; use relative distances for extrusion

M572 S0.036 ; Pressure advance


G1 Z40.8 F720 ; Move print head up
M104 S0 ; turn off temperature
M140 S0 ; turn off heatbed
M107 ; turn off fan
G1 X241 Y170 F3600 ; park
G1 Z62.8 F300 ; Move print head up
G4 ; wait
M572 S0 ; reset PA
M593 X T2 F0 ; disable IS
M593 Y T2 F0 ; disable IS
M84 X Y E ; disable motors
; max_layer_z = 39.8
M73 P100 R0
M73 Q100 S0
