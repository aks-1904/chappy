#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <driver/i2s.h>
#include "mbedtls/base64.h"
#include "esp_camera.h"
#include <Adafruit_NeoPixel.h>

const char *WIFI_SSID = "WIFI_SSID";         // Change to real SSID
const char *WIFI_PASSWORD = "WIFI_PASSWORD"; // Change to real wifi password
const char *LAPTOP_IP = "192.168.1.100";     // Laptop local IP
const char *WS_PATH = "/robot";
const uint16_t WS_PORT = 8765;

// Sensor Pins
#define TRIG_PIN 12  // HC-SR04 trigger  (GPIO12)
#define ECHO_PIN 13  // HC-SR04 echo     (GPIO13)
#define PIR_PIN 14   // PIR sensor OUT   (GPIO14)
#define TOUCH_PIN 15 // TTP223 touch     (GPIO15)

// Servo Pins
#define SERVO_HEAD_PAN_PIN 2   // GPIO2  — Head left/right
#define SERVO_HEAD_TILT_PIN 4  // GPIO4  — Head up/down
#define SERVO_LEFT_ARM_PIN 16  // GPIO16 — Left arm
#define SERVO_RIGHT_ARM_PIN 17 // GPIO17 — Right arm

// I2S Microphone (INMP441)
// INMP441 pin map:
//    DB (data) -> GPI034 (input only)
//    SCK (clock) -> GPI026
//    WS (word select / LR clock) -> GPI025
//    L/R -> GND (left channel)
//    VDD -> 3.3V, GND -> GND
#define I2S_MIC_PORT I2S_NUM_1
#define I2S_MIC_SCK 26
#define I2S_MIC_WS 25
#define I2S_MIC_SD 34
#define MIC_SAMPLE_RATE 16000
#define MIC_CHUNK_MS 100                                        // send audio every 100ms
#define MIC_BUF_SAMPLES (MIC_SAMPLE_RATE * MIC_CHUNK_MS / 1000) // 1600 samples

// I2S Speaker (MAX98357A)
// MAX98357A pin map:
//    DIN (data) -> GPIO22
//    BCLK (clock) -> GPIO27
//    LRC (LR) -> GPIO23
//    SD (shutdown/gain) -> 3.3V (always on, 9dB gain)
//    VIN -> 5V, GND -> GND
#define I2S_SPK_PORT I2S_NUM_0
#define I2S_SPK_BCLK 27
#define I2S_SPK_LRC 23
#define I2S_SPK_DIN 22

// Camera (OV2640 on ESP32-CAM AI-Thinker)
#define CAM_PIN_PWDN 32
#define CAM_PIN_RESET -1 // not connected
#define CAM_PIN_XCLK 0
#define CAM_PIN_SIOD 26
#define CAM_PIN_SIOC 27
#define CAM_PIN_D7 35
#define CAM_PIN_D6 34
#define CAM_PIN_D5 39
#define CAM_PIN_D4 36
#define CAM_PIN_D3 21
#define CAM_PIN_D2 19
#define CAM_PIN_D1 18
#define CAM_PIN_D0 5
#define CAM_PIN_VSYNC 25
#define CAM_PIN_HREF 23
#define CAM_PIN_PCLK 22
#define FRAME_INTERVAL_MS 100 // send frame every 100ms (10fps)

// NeoPixel
#define NEO_PIN 33  // GPIO33
#define NEO_COUNT 1 // single RGB LED

WebSocketsClient ws;
bool wsConnected = false;

// JSON doc sizes
StaticJsonDocument<1024> rxDoc; // Incoming commands
StaticJsonDocument<256> txDoc;  // Outgoing events
char txBuf[512];

// Sensor State
unsigned long lastSensorMs = 0;
const int SENSOR_EVERY = 300; // ms
bool pirState = false, pirPrev = false;
bool touchState = false, touchPrev = false;
float distCm = 0.0f;

// Servos
Servo headPan, headTilt, leftArm, rightArm;

#define HEAD_PAN_NEUTRAL 90
#define HEAD_TILT_NEUTRAL 80
#define LEFT_ARM_NEUTRAL 10
#define RIGHT_ARM_NEUTRAL 170

enum RobotState
{
  S_IDLE,
  S_THINKING,
  S_SPEAKING,
  S_GESTURE
};
RobotState robotState = S_IDLE;

// NeoPixel
#define NEO_PIN 33  // GPI033
#define NEO_COUNT 1 // Single RGB LED
Adafruit_NeoPixel neo(
    NEO_COUNT,
    NEO_PIN,
    NEO_GRB + NEO_KHZ800);

unsigned long thinkStartMs = 0;
float thinkPhase = 0.0f;

unsigned long lastFrameMs = 0;
bool cameraOk = false;

bool spkBusy = false;

void setup()
{
  Serial.begin(115200);

  // Servos
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  headPan.setPeriodHertz(50);
  headPan.attach(SERVO_HEAD_PAN_PIN, 500, 2400);

  headTilt.setPeriodHertz(50);
  headTilt.attach(SERVO_HEAD_TILT_PIN, 500, 2400);

  leftArm.setPeriodHertz(50);
  leftArm.attach(SERVO_HEAD_TILT_PIN, 500, 2400);

  rightArm.setPeriodHertz(50);
  rightArm.attach(SERVO_HEAD_TILT_PIN, 500, 2400);

  // Sensor pins
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(PIR_PIN, INPUT);
  pinMode(TOUCH_PIN, INPUT);

  // NeoPixel
  neo.begin();
  setLED(50, 50, 50); // Dim white = booting

  // Camera
  cameraOk = initCamera();
  if (!cameraOk)
    Serial.println("[CAM] Init failed - Camera disabled");

  // I2S Mic
  initMic();

  // I2S Speaker
  initSpeaker();

  // WiFi
  connectWifi();

  // WebSocket
  ws.begin(LAPTOP_IP, WS_PORT, WS_PATH);
  ws.onEvent(onWsEvent);
  ws.setReconnectInterval(3000);
  ws.enableHeartbeat(15000, 3000, 2);

  setLED(0, 0, 100); // blue = waiting for laptop connection
  Serial.println("[ESP32] Setup complete, connecting to laptop...");
}

float readUltrasonic()
{
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long dur = pulseIn(ECHO_PIN, HIGH, 30000);
  if (dur == 0)
    return 400.0f;

  return dur * 0.0343f / 2.0f;
}

void loop()
{
  ws.loop();
  updateSensors();
  updateThinking();
  streamCamera();
  streamMic();
}

void streamCamera()
{
  if (!wsConnected || !cameraOk)
    return;
  unsigned long now = millis();
  if (now - lastFrameMs < FRAME_INTERVAL_MS)
    return;
  lastFrameMs = now;

  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb)
    return;

  // Base64 encode JPEG
  size_t b64Len = 0;
  size_t b64BufSize = (fb->len * 4 / 3) + 8;
  uint8_t *b64Data = (uint8_t *)malloc(b64BufSize);
  if (!b64Data)
  {
    esp_camera_fb_return(fb);
    return;
  }

  mbedtls_base64_encode(b64Data, b64BufSize, &b64Len, fb->buf, fb->len);

  // Build JSON frame message
  size_t jsonSize = b64Len + 80;
  char *jsonBuf = (char *)malloc(jsonSize);
  if (jsonBuf)
  {
    snprintf(jsonBuf, jsonSize,
             "{\"type\":\"frame\",\"data\":\"%.*s\",\"w\":%zu,\"h\":%zu}", (int)b64Len, b64Data, fb->width, fb->height);
    ws.sendTXT(jsonBuf);
    free(jsonBuf);
  }
  free(b64Data);
  esp_camera_fb_return(fb);
}

// Raw 16-bit PCM buffer
static int16_t micBuf[MIC_BUF_SAMPLES];
// Base64 output (ceil(N*2 * 4/3) + 4)
static char b64Buf[((MIC_BUF_SAMPLES * 2) * 4 / 3) + 8];

void streamMic()
{
  if (!wsConnected)
    return;
  if (robotState == S_SPEAKING)
    return; // don't stream while playing audio

  size_t bytesRead = 0;
  esp_err_t ret = i2s_read(I2S_MIC_PORT, micBuf, MIC_BUF_SAMPLES * sizeof(int16_t), &bytesRead, 0); // non-blocking (0ms timeout)
  if (ret != ESP_OK || bytesRead == 0)
    return;

  // Base64 encode raw PCM
  size_t b64Len = 0;
  mbedtls_base64_encode((unsigned char *)b64Buf, sizeof(b64Buf), &b64Len, (const unsigned char *)micBuf, bytesRead);
  b64Buf[b64Len] = '\0';

  // Build JSON with preallocated buffer to avoid heap fragmentation
  // {"type":"audio","data":"<b64>","sr":16000,"bytes":NNNN}
  // Use a static large buffer - audio frames are big
  static char audioBuf[((MIC_BUF_SAMPLES * 2) * 4 / 3) + 128];
  snprintf(audioBuf, sizeof(audioBuf), "{\"type\":\"audio\",\"data\":\"%s\",\"sr\":%d,\"bytes\":%zu}", b64Buf, MIC_SAMPLE_RATE, bytesRead);
  ws.sendTXT(audioBuf);
}

void updateThinking()
{
  if (robotState != S_THINKING)
    return;
  thinkPhase += 0.08f;
  float tri = (sinf(thinkPhase) + 1.0f) / 2.0f;
  int angle = HEAD_PAN_NEUTRAL - 12 + (int)(tri * 24);
  headPan.write(angle);

  // Pulse LED brightness
  int bright = (int)(80 + 120 * ((sinf(thinkPhase) + 1.0f) / 2.0f));
  setLED(0, (int)(bright * 0.4f), bright);
  delay(20);
}

void updateSensors()
{
  unsigned long now = millis();
  if (now - lastSensorMs < SENSOR_EVERY)
    return;
  lastSensorMs = now;

  pirState = digitalRead(PIR_PIN);
  touchState = digitalRead(TOUCH_PIN);
  distCm = readUltrasonic();

  // Fire change events
  if (pirState && !pirPrev)
    sendEvent("presence_detected", "{}");
  if (touchState && !touchPrev)
    sendEvent("touch_detected", "{}");
  pirPrev = pirState;
  touchPrev = touchState;

  // Send sensor bundle
  txDoc.clear();
  txDoc["type"] = "sensors";
  txDoc["dist_cm"] = (int)distCm;
  txDoc["pir"] = pirState;
  txDoc["touch"] = touchState;
  serializeJson(txDoc, txBuf);
  sendJson(txBuf);
}

void connectWifi()
{
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40)
  {
    delay(500);
    Serial.print(".");
    tries++;
  }
  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.printf("\n[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
    setLED(0, 100, 0); // green = wifi ok
  }
  else
  {
    Serial.println("\n[WiFi] Failed! Will retry in loop.");
    setLED(100, 0, 0); // red = wifi fail
  }
}

void initSpeaker()
{
  i2s_config_t cfg = {
      .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
      .sample_rate = 16000,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
      .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 8,
      .dma_buf_len = 512,
      .use_apll = true,
      .tx_desc_auto_clear = true,
      .fixed_mclk = 0,
  };
  i2s_pin_config_t pins = {
      .bck_io_num = I2S_SPK_BCLK,
      .ws_io_num = I2S_SPK_LRC,
      .data_out_num = I2S_SPK_DIN,
      .data_in_num = I2S_PIN_NO_CHANGE,
  };

  i2s_driver_install(I2S_SPK_PORT, &cfg, 0, NULL);
  i2s_set_pin(I2S_SPK_PORT, &pins);
  Serial.println("[SPK] I2S speaker ready");
}

void initMic()
{
  i2s_config_t cfg = {
      .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = MIC_SAMPLE_RATE,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
      .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 4,
      .dma_buf_len = 256,
      .use_apll = false,
      .tx_desc_auto_clear = false,
      .fixed_mclk = 0,
  };
  i2s_pin_config_t pins = {
      .bck_io_num = I2S_MIC_SCK,
      .ws_io_num = I2S_MIC_WS,
      .data_out_num = I2S_PIN_NO_CHANGE,
      .data_in_num = I2S_MIC_SD,
  };

  i2s_driver_install(I2S_MIC_PORT, &cfg, 0, NULL);
  i2s_set_pin(I2S_MIC_PORT, &pins);
  i2s_zero_dma_buffer(I2S_MIC_PORT);

  Serial.println("[MIC] I2S mic ready");
}

void sendJson(const char *jsonStr)
{
  if (wsConnected)
    ws.sendTXT(jsonStr);
}

void sendEvent(const char *eventName, const char *dataJson)
{
  char buf[256];
  snprintf(buf, sizeof(buf),
           "{\"type\":\"event\",\"event\":\"%s\",\"data\":%s}",
           eventName, dataJson);
  sendJson(buf);
}

void startThinking()
{
  robotState = S_THINKING;
  thinkStartMs = millis();
  thinkPhase = 0.0f;
  setLED(0, 80, 200); // blue pulse = thinking
}

void stopThinking()
{
  robotState = S_IDLE;
  setNeutral();
  setLED(0, 200, 50);
}

void updateThinking()
{
  if (robotState != S_THINKING)
    return;
  thinkPhase += 0.08f;
  float tri = (sinf(thinkPhase) + 1.0f) / 2.0f;
  int angle = HEAD_PAN_NEUTRAL - 12 + (int)(tri * 24);
  headPan.write(angle);
  // Pulse LED brightness
  int bright = (int)(80 + 120 * ((sinf(thinkPhase) + 1.0f) / 2.0f));

  setLED(0, (int)(bright * 0.4f), bright);
  delay(20);
}

void gestureWave()
{
  moveServoSlow(rightArm, RIGHT_ARM_NEUTRAL, 90, 8);
  for (int i = 0; i < 3; i++)
  {
    moveServoSlow(rightArm, 90, 60, 6);
    moveServoSlow(rightArm, 60, 120, 6);
  }
  moveServoSlow(rightArm, 90, RIGHT_ARM_NEUTRAL, 8);
  finishGesture("wave");
}

void gestureHandshake()
{
  moveServoSlow(rightArm, RIGHT_ARM_NEUTRAL, 90, 6);
  delay(800);
  headTilt.write(HEAD_TILT_NEUTRAL - 10);
  delay(600);
  headTilt.write(HEAD_TILT_NEUTRAL);
  delay(400);
  moveServoSlow(rightArm, 90, RIGHT_ARM_NEUTRAL, 6);
  finishGesture("handshake");
}

void gestureNod()
{
  for (int i = 0; i < 2; i++)
  {
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL - 20, 5);
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL - 20, HEAD_TILT_NEUTRAL + 10, 5);
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL + 10, HEAD_TILT_NEUTRAL, 5);
  }
  finishGesture("nod");
}

void gestureShake()
{
  for (int i = 0; i < 2; i++)
  {
    moveServoSlow(headPan, HEAD_PAN_NEUTRAL, HEAD_PAN_NEUTRAL - 25, 5);
    moveServoSlow(headPan, HEAD_PAN_NEUTRAL - 25, HEAD_PAN_NEUTRAL + 25, 5);
    moveServoSlow(headPan, HEAD_PAN_NEUTRAL + 25, HEAD_PAN_NEUTRAL, 5);
  }
  finishGesture("shake");
}

void gestureHappy()
{
  moveArmsBoth(90, 90, 6);
  headTilt.write(HEAD_TILT_NEUTRAL - 15);
  delay(700);
  for (int i = 0; i < 2; i++)
  {
    leftArm.write(70);
    rightArm.write(110);
    delay(200);
    leftArm.write(90);
    rightArm.write(90);
    delay(200);
  }
  delay(300);
  moveArmsBoth(LEFT_ARM_NEUTRAL, RIGHT_ARM_NEUTRAL, 6);
  finishGesture("happy");
}

void gestureSad()
{
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL + 20, 5);
  delay(1200);
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL + 20, HEAD_TILT_NEUTRAL, 5);
  finishGesture("sad");
}

void gestureSurprised()
{
  headTilt.write(HEAD_TILT_NEUTRAL - 30);
  leftArm.write(90);
  rightArm.write(90);
  delay(600);
  headTilt.write(HEAD_TILT_NEUTRAL);
  moveArmsBoth(LEFT_ARM_NEUTRAL, RIGHT_ARM_NEUTRAL, 8);
  finishGesture("surprised");
}

void gesturePointForward()
{
  moveServoSlow(rightArm, RIGHT_ARM_NEUTRAL, 90, 6);
  delay(1000);
  moveServoSlow(rightArm, 90, RIGHT_ARM_NEUTRAL, 6);
  finishGesture("point");
}

void finishGesture(const char *name)
{
  setNeutral();
  robotState = S_IDLE;
  setLED(0, 200, 50);
  char buf[64];
  snprintf(buf, sizeof(buf), "{\"gesture\":\"%s\"}", name);
  sendEvent("gesture_done", buf);
}

void playAudio(JsonDocument &doc)
{
  const char *b64data = doc["data"] | "";
  int sr = doc["sr"] | 16000;

  size_t b64Len = strlen(b64data);
  if (b64Len == 0)
    return;

  // Decode
  size_t pcmBufSize = (b64Len * 3 / 4) + 4;
  uint8_t *pcmBuf = (uint8_t *)malloc(pcmBufSize);
  if (!pcmBuf)
    return;

  size_t pcmLen = 0;
  mbedtls_base64_decode(pcmBuf, pcmBufSize, &pcmLen, (const unsigned char *)b64data, b64Len);

  // Update sample rate if changed
  i2s_set_sample_rates(I2S_SPK_PORT, sr);

  // Write to DMA (blocks until queued)
  spkBusy = true;
  size_t written = 0;
  i2s_write(I2S_SPK_PORT, pcmBuf, pcmLen, &written, portMAX_DELAY);
  spkBusy = false;

  free(pcmBuf);
  sendEvent("audio_done", "{}");
}

void setNeutral()
{
  headPan.write(HEAD_PAN_NEUTRAL);
  headTilt.write(HEAD_TILT_NEUTRAL);
  leftArm.write(LEFT_ARM_NEUTRAL);
  rightArm.write(RIGHT_ARM_NEUTRAL);
}

void moveServoSlow(Servo &s, int from, int to, int stepMs)
{
  int step = (to > from) ? 1 : -1;
  for (int p = from; p != to; p += step)
  {
    s.write(p);
    delay(stepMs);
  }
  s.write(to);
}

void moveArmsBoth(int lTarget, int rTarget, int stepMs)
{
  int lNow = leftArm.read(), rNow = rightArm.read();
  int steps = max(abs(lTarget - lNow), abs(rTarget - rNow));
  for (int i = 1; i <= steps; i++)
  {
    float t = (float)i / steps;
    leftArm.write(lNow + (int)((lTarget - lNow) * t));
    rightArm.write(rNow + (int)((rTarget - rNow) * t));
    delay(stepMs);
  }
  leftArm.write(lTarget);
  rightArm.write(rTarget);
}

void gestureHugLeg()
{
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL + 25, 6);
  moveArmsBoth(45, 135, 7);
  delay(200);
  moveArmsBoth(75, 105, 5);
  delay(300);
  moveArmsBoth(82, 98, 4);
  delay(1500);
  moveArmsBoth(60, 120, 6);
  delay(200);
  moveArmsBoth(LEFT_ARM_NEUTRAL, RIGHT_ARM_NEUTRAL, 7);
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL + 25, HEAD_TILT_NEUTRAL - 5, 6);
  delay(300);
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL - 5, HEAD_TILT_NEUTRAL, 5);
  finishGesture("hug_leg");
}

void gestureHugWaist()
{
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL + 15, 6);
  moveArmsBoth(60, 120, 7);
  delay(150);
  moveArmsBoth(35, 145, 6);
  delay(300);
  moveArmsBoth(72, 108, 5);
  delay(300);
  moveArmsBoth(80, 100, 4);
  delay(1800);
  for (int i = 0; i < 3; i++)
  {
    rightArm.write(95);
    delay(200);
    rightArm.write(100);
    delay(200);
  }
  moveArmsBoth(50, 130, 7);
  delay(200);
  moveArmsBoth(LEFT_ARM_NEUTRAL, RIGHT_ARM_NEUTRAL, 8);
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL + 15, HEAD_TILT_NEUTRAL, 5);
  finishGesture("hug_waist");
}

void gestureHugReach()
{
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL - 20, 6);
  moveArmsBoth(70, 110, 6);
  delay(100);
  moveArmsBoth(88, 92, 5);
  delay(400);
  moveArmsBoth(83, 97, 4);
  delay(2000);
  for (int i = 0; i < 2; i++)
  {
    moveArmsBoth(80, 100, 5);
    delay(300);
    moveArmsBoth(84, 96, 5);
    delay(300);
  }
  moveArmsBoth(70, 110, 6);
  delay(200);
  moveArmsBoth(50, 130, 7);
  delay(200);
  moveArmsBoth(LEFT_ARM_NEUTRAL, RIGHT_ARM_NEUTRAL, 8);
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL - 20, HEAD_TILT_NEUTRAL - 10, 5);
  delay(300);
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL - 10, HEAD_TILT_NEUTRAL, 5);
  finishGesture("hug_reach");
}

void gestureComfortPat()
{
  moveServoSlow(headPan, HEAD_PAN_NEUTRAL, HEAD_PAN_NEUTRAL + 12, 6);
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL + 10, 6);
  moveServoSlow(rightArm, RIGHT_ARM_NEUTRAL, 105, 7);
  delay(300);
  for (int i = 0; i < 5; i++)
  {
    moveServoSlow(rightArm, 105, 98, 4);
    delay(100);
    moveServoSlow(rightArm, 98, 105, 4);
    delay(180);
  }
  delay(600);
  moveServoSlow(rightArm, 105, RIGHT_ARM_NEUTRAL, 8);
  moveServoSlow(headPan, HEAD_PAN_NEUTRAL + 12, HEAD_PAN_NEUTRAL, 6);
  moveServoSlow(headTilt, HEAD_TILT_NEUTRAL + 10, HEAD_TILT_NEUTRAL, 6);
  finishGesture("comfort_pat");
}

void handleCommand(const char *raw)
{
  DeserializationError err = deserializeJson(rxDoc, raw);
  if (err)
  {
    sendEvent("error", "{\"msg\":\"bad_json\"}");
    return;
  }

  const char *cmd = rxDoc["cmd"] | "";

  if (!strcmp(cmd, "gesture_wave"))
  {
    robotState = S_GESTURE;
    gestureWave();
  }
  else if (!strcmp(cmd, "gesture_handshake"))
  {
    robotState = S_GESTURE;
    gestureHandshake();
  }
  else if (!strcmp(cmd, "gesture_nod"))
  {
    robotState = S_GESTURE;
    gestureNod();
  }
  else if (!strcmp(cmd, "gesture_shake"))
  {
    robotState = S_GESTURE;
    gestureShake();
  }
  else if (!strcmp(cmd, "gesture_happy"))
  {
    robotState = S_GESTURE;
    gestureHappy();
  }
  else if (!strcmp(cmd, "gesture_sad"))
  {
    robotState = S_GESTURE;
    gestureSad();
  }
  else if (!strcmp(cmd, "gesture_surprised"))
  {
    robotState = S_GESTURE;
    gestureSurprised();
  }
  else if (!strcmp(cmd, "gesture_point"))
  {
    robotState = S_GESTURE;
    gesturePointForward();
  }
  // Hug gestures
  else if (!strcmp(cmd, "gesture_hug_leg"))
  {
    robotState = S_GESTURE;
    gestureHugLeg();
  }
  else if (!strcmp(cmd, "gesture_hug_waist"))
  {
    robotState = S_GESTURE;
    gestureHugWaist();
  }
  else if (!strcmp(cmd, "gesture_hug_reach"))
  {
    robotState = S_GESTURE;
    gestureHugReach();
  }
  else if (!strcmp(cmd, "gesture_comfort_pat"))
  {
    robotState = S_GESTURE;
    gestureComfortPat();
  }
  else if (!strcmp(cmd, "thinking_start"))
  {
    startThinking();
  }
  else if (!strcmp(cmd, "thinking_stop"))
  {
    stopThinking();
  }
  else if (!strcmp(cmd, "speaking_start"))
  {
    robotState = S_SPEAKING;
    setLED(0, 200, 50);
  }
  else if (!strcmp(cmd, "speaking_stop"))
  {
    robotState = S_IDLE;
    setNeutral();
    setLED(0, 200, 50);
  }
  else if (!strcmp(cmd, "neutral"))
  {
    robotState = S_IDLE;
    setNeutral();
  }
  else if (!strcmp(cmd, "ping"))
  {
    sendEvent("pong", "{}");
    return;
  }
  // Audio playback
  else if (!strcmp(cmd, "audio_play"))
  {
    playAudio(rxDoc);
    return;
  }
  // LED override
  else if (!strcmp(cmd, "set_led"))
  {
    setLED(rxDoc["r"] | 0, rxDoc["g"] | 0, rxDoc["b"] | 0);
    return;
  }
  else
  {
    sendEvent("error", "{\"msg\":\"unknown_cmd\"}");
    return;
  }

  sendEvent("ack", "{}");
}

void onWsEvent(WStype_t type, uint8_t *payload, size_t length)
{
  switch (type)
  {
  case WStype_CONNECTED:
    wsConnected = true;
    Serial.println("[WS] Connected to laptop");
    setLED(0, 200, 50); // teal = fully connected
    sendEvent("ready", "{}");
    break;

  case WStype_DISCONNECTED:
    wsConnected = false;
    Serial.println("[WS] Disconnected — reconnecting...");
    setLED(100, 50, 0); // orange = disconnected
    break;

  case WStype_TEXT:
    handleCommand((char *)payload);
    break;

  case WStype_ERROR:
    Serial.printf("[WS] Error: %s\n", payload);
    break;

  default:
    break;
  }
}

// OV2640 Camera -> JPEG Stream to Laptop
bool initCamera()
{
  camera_config_t config;

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = CAM_PIN_D0;
  config.pin_d1 = CAM_PIN_D1;
  config.pin_d2 = CAM_PIN_D2;
  config.pin_d3 = CAM_PIN_D3;
  config.pin_d4 = CAM_PIN_D4;
  config.pin_d5 = CAM_PIN_D5;
  config.pin_d6 = CAM_PIN_D6;
  config.pin_d7 = CAM_PIN_D7;
  config.pin_xclk = CAM_PIN_XCLK;
  config.pin_pclk = CAM_PIN_PCLK;
  config.pin_vsync = CAM_PIN_VSYNC;
  config.pin_href = CAM_PIN_HREF;
  config.pin_sscb_sda = CAM_PIN_SIOD;
  config.pin_sscb_scl = CAM_PIN_SIOC;
  config.pin_pwdn = CAM_PIN_PWDN;
  config.pin_reset = CAM_PIN_RESET;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // QVHA = 320 * 240
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 15; // 0-63 (lower = better Quality)
  config.fb_count = 2;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK)
  {
    Serial.printf("[CAM] Init error 0x%x\n", err);
    return false;
  }

  Serial.println("[CAM] OV2640 ready - QVGA JPEG");
  return true;
}

void setLED(uint8_t r, uint8_t g, uint8_t b)
{
  neo.setPixelColor(0, neo.Color(r, g, b));
  neo.show();
}