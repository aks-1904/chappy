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
char txBug[512];

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

void loop()
{
  // put your main code here, to run repeatedly:
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

void handleCommand(const char *raw)
{
  DeserializationError err = deserializeJson(rxDoc, raw);
  if (err)
  {
    sendEvent("error", "{\"msg\":\"bad_json\"}");
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
