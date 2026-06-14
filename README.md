# Chappy: The Agentic Companion Robot

`Chappy` is an advanced, emotionally intelligent, and autonomous desktop companion robot. Powered of Local Large Language Models (LLMs), Computer Vision, and Speech processing, Chappy doesn't just respond to commands, it recognizes you, reads your emotional state, initiates conversations, performs agentic web tasks, and offers physical gestures of comfort like hugs and pats.

`Chappy` is designed with a decoupled architecture: a heavy "Main Brain" running on a host laptop/PC (Python) and a lightweight hardware layer that supports both Arduino (Serial) and ESP32 (Wi-Fi WebSockets, Camera, Audio).

---

## Key Features

### Local AI & Agentic Tools (Ollama)
- **Local LLM Integration:** Powered by local models like `phi4-mini` or `llama3.2:3b` via Ollama for fast, private, and contextual conversations.
- **Tool Calling / Agentic Behavior:** Chappy can autonomously use tools to help you:
    - Web Search & Wikipedia Lookups
    - Send Emails
    - Set Reminders (stored persistently)
    - Check Weather & News (Top headlines or topics)
    - Perform Math Calculations
    - Tell Jokes & check Time/Date

### Emotional Intelligence & Persona

- **Distress tracking:** Monitors your emotional state over time. If it detects sadness or crisis (via vision or speech), it enters a special "Support Mode" to ground and comfort you.
- **Dynamic Personas: ** You can change Chappy's personality on the fly (Warm, Energetic, Calm, Witty, Nurturing, Professional).
- **Relationship Mapping:**Remembers if you are its owner, a family member, a friend, or a guest, and adjusts its greeting and "love level" accordingly.
- **Proactive Check-ins:** If you look sad for a prolonged period, Chappy will autonomously initiate a conversation to ask if you're okay.

### Computer Vision & Hearing
- **Face Recognition:** Learns and remembers faces using MediaPipe and DeepFace.
- **Emotion Detection:** Analyzes facial expressions to adapt its tone and gestures.
- **Speech-to-Text:** Listens using OpenAI's Whisper model (local).
- **Text-to-Speech:** Responds vocally using pyttsx3 or CoquiTTS with dynamically adjusted speech rates and volumes based on its current emotion.
- Expressive Gestures
    - Driven by 4 servos (Head Pan/Tilt, Left/Right Arms).
    - **Gestures:** Wave, Handshake, Nod, Shake, Happy (Celebrate), Sad(Droop), Surprised, Point.
    - **Smart Hugs:** Context-aware hugs depending on the user's height and distress level:
        - `hug_leg`: For children or extreme comfort.
        - `hug_waist`: For seated users or moderate comfort.
        - `hug_reach`: High reach for tall individuals.
        - `comfort_pat`: A gentle arm pat for minor distress.

---

## Hardware Architecture
Chappy's firmware supports two microcontroller platforms. You can build Chappy using either.

### Option 1: Arduino (Wired)
- **Communication:** Serial USB (`115200` baud).
- **Sensors:** HC-SR04 (Ultrasonic distance), PIR (Presence detection), TTP223 (Capacitive Touch).
- **Actuators:** 4x Servos, 1x Status LED.

### Option 2: ESP32-CAM (Wireless)
- **Communication:** Wi-Fi via WebSockets.
- **Sensors:** Ultrasonic, PIR, Touch.
- **Advanced I/O:** *OV2640 Camera (Streams JPEG frames over WebSocket).
    - INMP441 I2S Microphone (Streams Base64 encoded audio).
    - MAX98357A I2S Speaker (Plays audio streamed from the laptop).
- **Actuators:** 4x Servos, WS2812 NeoPixel for state indication (e.g., Blue pulse = Thinking).

### Circuit, PCB & Wiring Guides
To make building Chappy easier, we provide full schematics, custom PCB layouts, and step-by-step wiring instructions.
- **Wiring Guide:** Start here if you are building Chappy on a breadboard or perfboard. Detailed pin-to-pin connection instructions for both Arduino and ESP32 can be found in our [Wiring Guide (wiring.md)](docs/wiring.md).
- **Schematics (.kicad_sch):** The logical circuit design for the robot's hardware. [View ESP32 Schematic](esp32/esp32.kicad_sch) | [View Arduino Schematic](arduino/arduino.kicad_sch).
- **PCB Layouts (.kicad_pcb):** Ready-to-manufacture printed circuit board files designed in KiCad. [View ESP32 PCB](esp32/esp32.kicad_pcb) | [View Arduino PCB](arduino/arduino.kicad_pcb).

(Note: You will need [KiCad](https://www.kicad.org/) installed to view and edit the `.kicad_sch` and `.kicad_pcb` files).*

---

## Software Architecture (Main Brain)
The `main_brain` is a modular Python application handling the heavy lifting:
- `RobotBrain`: The central state machine
- `SerialBridge`: Managed communication with the hardware
- `VisionModule`: OpenCV + MediaPipe (Detection) + DeepFace (Recognition & Emotion).
- `SpeechModule`: Audio capture, Whisper STT, TTS.
- `MemoryModule`: SQLite DB persisting users, interaction history, and reminders.
- `LLMEngine` & `AgentRunner`: Handles Ollama inference and function calling.

---

## Installation & Setup
1. Prerequisites
    - Python 3.9+ (Preffered 3.11)
    - [Ollama](https://ollama.com/) installed locally
    - Pull your preferred model: `ollama pull phi4-mini` (or update `config/settings.py`)
    - Arduino IDE (for flashing firmware).
1. Hardware Setup
    - **Wiring:** Before uploading code, assemble the hardware by following the Wiring Guide or fabricating the provided KiCad PCB files.
        - **Arduino: ** [Arduino Wiring Guide](docs/arduino_wiring.md)
        - **ESP32: ** [ESP32 Wiring Guide](docs/esp32_wiring.md)
    - **Arduino:** Flash `arduino/robo_firmware.ino`. Connect via USB.
    - **ESP32:** Flash `esp32/robo_firmware.ino`. Update `WIFI_SSID`, `WIFI_PASSWORD`, and `LAPTOP_IP` in the code before uploading.
1. Software Setup
Clone the repo and install dependencies:
``` bash
git clone https://github.com/aks-1904/chappy.git
cd chappy/main_brain
pip install -r requirements.txt
```
(Note: Ensure you have PyAudio prerequisites installed on you OS).

Configure `config/settings.py` to match your environment (API keys for Weather/News, Email SMTP credentials, COM port, etc.).

---

## Usage
Chappy uses a clean command-line interface to switch between hardware modes and utilities.

**1. Start the Robot (Arduino USB Mode):**
Run the brain and connect to the Arduino via USB.
```bash
# Auto-detect the Arduino serial port and start
python main.py arduino

# Specify a custom serial port manually (e.g., COM3 or /dev/ttyUSB0)
python main.py arduino --port COM3
```

**2. Start the Robot (ESP32 WiFi Mode):**
Run the brain and connect to the ESP32 wirelessly over your local network.
``` bash
# Start with ESP32 via WiFi
python main.py esp32

# Run in headless mode
python main.py esp32 --headless
```

**3. Register a New Face**
Teach Chappy to recognize you! Stand in front of the camera and follow the on-screen prompts (Press `SPACE` to capture or `A` for a 3-second timer).
``` bash
# Register using the default USB webcam (captures 3 photos by default)
python main.py register --name "Your Name"

# Capture a specific number of photos
python main.py register --name "Your Name" --photos 5

# Register a face using the ESP32 wireless camera instead of the laptop webcam
python main.py register --name "Your Name" --wireless
```

---

## Future Scope
Chappy is evolving from a physical companion into a seamless bridge between the physical world and your digital workspace. The next major updates include:

### Desktop UI Dashboard
- **Companion App:** A sleek desktop application (built with PyQt or Electron) to easily monitor Chappy's status.
- ** Configuration Hub:** Easily change API keys, configure email settings, adjust persona traits, and manage stored relationships/memory without touching the code.
- **Live Telemetry:** View live camera feeds, emotion charts, sensor data, and LLM reasoning logs in real-time.

### Screen-Aware Agentic Assistant
- **Screen Integration:** Giving Chappy permission to "see" your laptop screen.
- **Contextual Summarization:** Ask Chappy, "Can you summarize the article I'm reading?" and it will read your active browser window and explain it to you.
- **Paired Programming Buddy:** Ask Chappy to "Look at the code on my screen and find the bug" or "Write a unit test for this function," allowing it to act as an embodied coding assistant.
- **Seamless Task Execution:** Combining its physical presence with desktop control to seamlessly book meetings on your calendar or draft emails based on documents open on your screen.