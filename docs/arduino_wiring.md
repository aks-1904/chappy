# Arduino Wiring Guide

## Servo Power - IMPORTANT
**Never power servos from the Arduino 5V pin.**
MG996R draws up to 2.5A each under load. Use a separate 5V/3A+ supply.

```
External 5V Supply - Servo VCC (red wired) [ALL 4 servos]
External GND - Servo GND (black/brown)
External GND - Arduino GND [common ground]
```

---

## Servo Connections

| Arduino Pin | Servo | Wire Color (signal) |
| --- | --- | --- |
| D3 | Head Pan | Yellow / Orange |
| D5 | Head Tilt | Yellow / Orange |
| D6 | Left Arm | Yellow / Orange |
| D9 | Right Arm | Yellow / Orange |

Servo connector pinout (left to right looking at plug):
```
[GND] [VCC] [SIGNAL]
Black Red Yellow
```

---

## HC-SR04 Ultrasonic Distance Sensor

| HC-SR04 Pin | Arduino Pin |
| --- | --- |
| VCC | 5V | 
| GND | GND |
| TRIG | D10 |
| ECHO | D11 |

--- 

## PIR Motion Sensor (HC-SR501)

| PIR Pin | Arduino Pin |
| --- | --- |
| VCC | 5V |
| GND | GND |
| OUT | D4 |

Adjust sensitivity and delay ports on the PIR module:
- **Sensitivity** (left pot): turn clockwise = farther range
- **Delay** (right pot): turn counter-clockwise = shorter trigger hold

--- 

## Touch Sensor (TTP223 Capacitive)

| Touch Pin | Arduino Pin |
| --- | --- |
| VCC | 3.3 or 5V |
| GND | GND |
| SIG / OUT | D7 |

---

## Servo ranges in firmware

- Head Pan: 45° - 135° (neutral: 90°)
- Head Tilt: 60° - 100° (neutral: 80°)
- Left Arm: 10° - 90° (neutral: 10° = down)
- Right Arm: 90° - 170° (neutral: 170° = down mirrored)

---

## PCB & Schemantic Design

You can also check the PCB & Schemantic Design for connecting hardwares with Arduino accordingly
- **PCB:** [PCB Design Arduino](../ardiono/arduino.kicad_pcb)
- **Schemantic**: [Schemantic Design Arduino](../arduino/arduino.kicad_sch) 
