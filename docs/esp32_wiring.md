# ESP32 Wiring Guide
All hardware connects to the **ESP32-CAM (AI-Thinker)** board.
THe laptop connects only via **WiFi** - no USB cable needed during operation.

---

## INMP441 I2S Microphone

| INMP441 Pin | ESP32-CAM GPIO | Notes |
| --- | --- | --- |
| VDD | 3.3V | 3.3V ONLY (not 5V) |
| GND | GND |
| L/R | GND | Selectc LEFT channel |
| WS | GPI025 | Word Select (LR clock) |
| SCK | GPI026 | Bit clock |
| SD | GPI034 | Serial Data (Input-only pin - correct)

---

## MAX98357A I2S Amplifier + Speaker

| MAX98357A Pin | ESP32-CAM GPIO | Notes |
| --- | --- | --- |
| VIN | 5V | Needs 5V for speaker power |
| GND | GND |
| LRC | GPIO23 | Left/Right clock (word select) |
| BCLK | GPIO27 | Bit clock
| DIN | GPIO22 | Audio data input |
| SD (SHUTDOWN) | 3.3V | HIGHT = enabled, 9dB gain, Float = 12dB, GND = shutdown |

---

## Servo Motors (MG996R * 4)

| Servo | ESP32 GPIO | External 5V PSU |
| --- | --- | --- |
| Head Pan | GPIO2 | VCC (red) + GND |
| Head Tilt | GPIO4 | VCC (red) + GND |
| Left Arm | GPIO16 | VCC (red) + GND |
Right Arm | GPIO17 | VCC (red) + GND |

**CRITICAL - External power for servos:**
```
[5V 2A+ PSU] ---- Servo VCC (all 4 red wires in parallel)
[PSU GND] ---- Servo GND (all 4 brown/black wires) + ESP32 GND

Servo Signal (orange/yellow) ---- ESP32GPIO (3.3V logic - fine for MG996R)

DO NOT connect servo VCC to ESP32 3.3V or 5V pin.
Four MG996R servoes can draw 4A+ simultaneously - will brown out ESP32.
```

**Servo connector pinout (looking at 3-pin plug):**
```
[GND]  [VCC]  [SIGNAL]
Brown  Red    Orange
Black  Red    Yellow
```

---

## HC-SR04 Ultrasonic Distance Sensor
| HC-SR04 Pin | ESP32 GPIO | Notes |
| --- | --- | --- |
| VCC | 5V | Needs 5V |
| GND | GND |
| TRIG | GPIO12 | Output from ESP32 |
| ECHO | GPIO13 | HC-SR04 outputs 5V on ECHO, Add voltage divider |

**Voltage divider for ECHO (5V -> 3.3V):**
```
HC-SR04 ECHO --- [1kΩ] ------- GPIO13 (ESP32)
                          |
                        [2kΩ]
                          |
                         GND
```
Output voltage = 5V * (2kΩ / (1kΩ + 2kΩ)) = 3.3V

---

## PIR Sensor (HC-SR501)

| HC-SR501 Pin | ESP32 GPIO | Notes |
| --- | --- | --- |
| VCC | 5V | Needs 5V to operate |
| GND | GND |
| OUT | GPIO14 | Outputs 3.3V when triggered - safe for ESP-32 |

**Adjustment pots on HC=SR501:**
**Left pot (sensitivity):** Turn clockwise for longer range (upto 7m)
**Right pot (delay):** Turn counter-clockwise for shortest hold (~3s)
**Jumper (retrigger):** Set to H (repeat trigger mode)

## TTP223 Touch Sensor

| TTP223 Pin | ESP32 GPIO | Notes |
| --- | --- | --- |
| VCC | 3.3V | Works at 3.3V |
| GND | GND |
| SIG | GPIO15 | Low - no touch, High = touched |

---

## WS2812B NeoPixel LED

| ES2812B Pin | ESP32 GPIO | Notes |
| --- | --- | --- |
| VCC | 5V | Needs 5V |
| GND | GND |
| DIN | GPIO33 | 3.3V login from ESP32 is fine Add 300Ω registor in series on DIN line |

**NeoPixel protection resisor:**
```
GPIO33 --- [300Ω] --- DIN(WS2812B)
```
Prevents signal reflection/ringing on the data line.

---

## Power Supply Recommendation

**option A - USB Power Bank (portable)**
```
USB Power Band (5V 3A+)
    |
    |--- USB-A to bare wires -> servo rail
    |--- USB-A to ESP32-CAM USB -> powers ESP32
```
Use a 20000mAh bank for 4-6 hours runtime

**Option B - Desktup regulated supply (recommended for dev)**
```
LM2596 Buck Converter (set to 5V) from 12V wall adapter
|
|--- 5V rail -> everything above
```

**Option C - 18650 Li-Ion battery pack (3.7V -> boost to 5V)**
```
2 * 18650 (7.4V) -> MT3608 boost -> 5V rail
```
Best for compact wireless robot body.

---

## Flashing ESP32-CAM (One-time Setup)
ESP32-CAM has no USB programmer build-in. Use a FTDI adapter:
```
FTDI(CP2102/FT232RL)    ESP32-CAM
5V -------------------> 5V
GND ------------------> GND
TX -------------------> RX(GPIO3)
RX <------------------- TX(GPIO1)
GND ------------------> GPIO0 <- BOOT MODE (must be GND to flash)
                        (disconnect GPIO0 after flashing)
```
**Flash steps:**
1. Wire GPIO0 to GND
1. Power on / press RESET
1. In Arduino iDE: select **AI-Thinker ESP32-CAM** board
1. Set **Upload Speed: 115200**
1. Click upload
1. When "Connecting..." appears: press and hold RESET for 1 second
1. Release RESET - upload begins
1. After "Done": disconnect GPIO0 from GND, press RESET

---

## WiFi Setup
1. Find your laptop's local IP:
    - **Windows:** `ipconfig` -> look for IPv4 under WiFi adapter
    - **Linux/Mac:** `ip addr` or `ifconfig` -> loop for `192.168.x.x`
1. Update **both** files:
    - **ESP32 firmware** (`esp32/robot_firmware.ino`)
    ``` cpp
    const char* WIFI_SSID = "YouWiFiName";
    const char* WIFI_PASSWORD = "YouPassword";
    const char* LAPTOP_IP = "192.168.x.x"; // <- You Laptop IP
    ```
    - **Laptop settings** (`main_brain/config/settings.py`)
    ``` py
    WIRELESS = {
        "enabled": True,
        "laptop_ip": "192.168.x.x", # <- same IP
        "ws_port": 8765,
    }
    ```

1. Make sure both laptop and ESP32 are on the **same WiFi network**
1. **Firewall:** Allow port 8765 on laptop:
    - Windows: `netsh advfirewall firewall and rule name="Robot WS" dir=in action=allow protocol=TCP loaclport=8765`
    - Linux: `sudo ufw allow 8765/tcp`

## Quick Connection Test

**On laptop (run first):**
``` py
python main.py --wireless
# Should show: "[WS] Listening on ws://0.0.0.0:8765/robot"
```

**On ESP32(after flashing):**
``` txt
Open Arduino Serial Monitor at 115200 baud.
Expected output:
    [WiFi] Connected! IP: 192.168.x.x
    [WS] Connected to laptop
    [ESP32] Setup complete
```

---

## NeoPixel LED Status Colors

| Color | Meaning |
| --- | --- |
| Dim white | Booting |
| Green | WiFi connected |
| Red | WiFi failed |
| Blue (pulsing) | Thinking / processing |
| Teal | ESP32 <-> Laptop connected, idle |
| Orange | Disconnected from laptop |
| Bright green | Speaking |

---

##  Schemantic Design

You can also check the Schemantic Design for connecting hardwares with ESP32 accordingly

- **Schemantic**: [Schemantic Design ESP32](../esp32/ESP32_SCM.kicad_sch) 
