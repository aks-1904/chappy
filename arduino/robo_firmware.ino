#include <Arduino.h>
#include <Servo.h>
#include <ArduinoJson.h> // By Benoit Blanchon

#define SERIAL_BAUD 115200 // Serial baud rate of laptop

#define LED_PIN 13

// Head Servos
#define SERVO_HEAD_PAN_PIN 3  // Left-Right
#define SERVO_HEAD_TILT_PIN 5 // Up-Down

// Arm Servos
#define SERVO_LEFT_ARM_PIN 6
#define SERVO_RIGHT_ARM_PIN 9

Servo headPan;
Servo headTilt;
Servo leftArm;
Servo rightArm;

// Neutral (resting) positions in degrees
#define HEAD_PAN_NEUTRAL 90
#define HEAD_TILT_NEUTRAL 80
#define LEFT_ARM_NEUTRAL 10   // Arms down
#define RIGHT_ARM_NEUTRAL 170 // Arms down (mirrored)

// HC-SR04 Ultrasonic
#define TRIG_PIN 10
#define ECHO_PIN 11

// PIR Presence sensor
#define PIR_PIN 4

// Touch sensor (capacitive/digital)
#define TOUCH_PIN 7

// Sampling interval
#define SENSOR_INTERVAL_MS 300

unsigned long lastSensorTime = 0;
bool pirState = false;
bool pirPrevState = false;
bool touchState = false;
bool touchPrevState = false;
float distanceCm = 0.0f;

enum RobotState
{
    STATE_IDLE,
    STATE_THINKING,
    STATE_SPEAKING,
    STATE_GESTURE
};

RobotState robotState = STATE_IDLE;

// Thinking animation: subtle head oscillation
unsigned long thinkingStartMs = 0;
const int THINK_OSCILLATE_RANGE = 15;  // degrees
const int THINK_OSCILLATE_SPEED = 800; // ms per cycle

// JSON buffers
StaticJsonDocument<256> inDoc;
StaticJsonDocument<256> outDoc;

// Functions prototype
void blinkLED(int);
void readSerial();
void setNeutral();
void sendEvent(const char *, const char *) void handleCommand(const char *);
void updateSensors();
float readUltrasonic();
void handleCommand(const char *);
void setGestureState();
void updateThinkingAnimation();

// Gestures
void gestureWave();
void gestureHandshake();
void moveServoSlow(Servo &, int, int, int)

    void setup()
{
    Serial.begin(SERIAL_BAUD);
    while (!Serial)
    {
        ;
    }

    pinMode(LED_PIN, OUTPUT);
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
    pinMode(PIR_PIN, INPUT);
    pinMode(TOUCH_PIN, INPUT);

    // Attach servos
    headPan.attach(SERVO_HEAD_PAN_PIN);
    headTilt.attach(SERVO_HEAD_TILT_PIN);
    leftArm.attach(SERVO_LEFT_ARM_PIN);
    rightArm.attach(SERVO_RIGHT_ARM_PIN);

    setNeutral();

    delay(500);

    // Sending signal to laptop when robot setup is done
    sendEvent("ready", "{}");

    blinkLED(3); // To confirm everything works fine
}

void loop()
{
    readSerial();
    updateSensors();
    updateThinkingAnimation();
}

void moveServoSlow(Servo &s, int from, int to, int stepDelayMs)
{
    int step = (to > from) ? 1 : -1;
    for (int pos = from; pos != to; pos += step)
    {
        s.write(pos);
        delay(stepDelayMs);
    }
    s.write(to);
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
    setNeutral();
    robotState = STATE_IDLE;

    digitalWrite(LED_PIN, LOW);
    
    sendEvent("gesture_done", "{\"gesture\":\"wave\"}");
}

void gestureHandshake()
{
    moveServoSlow(rightArm, RIGHT_ARM_NEUTRAL, 90, 6);
    delay(800);

    // Simulate grip: slight tilt
    headTilt.write(HEAD_TILT_NEUTRAL - 10)
        delay(600);
    headTilt.write(HEAD_TILT_NEUTRAL);
    delay(400);
    moveServoSlow(rightArm, 90, RIGHT_ARM_NEUTRAL, 6);
    setNeutral();
    robotState = STATE_IDLE;
    digitalWrite(LED_PIN, LOW);

    sendEvent("gesture_done", "{\"gesture\":\"handshake\"}");
}

void updateThinkingAnimation()
{
    if (robotState != STATE_THINKING)
        return;

    // Gentle side-to-side head bob using sine approximation
    unsigned long elapsed = millis() - thinkingStartMs;
    float phase = (float)(elapsed % THINK_OSCILLATE_SPEED) / THINK_OSCILLATE_SPEED;

    // Single trangle wave: 0 -> 1 -> 0
    float tri = (phase < 0.5f) ? (phase * 2.0f) : ((1.0f - phase) * 2.0f);
    int angle = HEAD_PAN_NEUTRAL - THINK_OSCILLATE_RANGE + (int)(tri * THINK_OSCILLATE_RANGE * 2);
    headPan.write(angle);
}

void updateSensors()
{
    unsigned long now = millis();
    if (now - lastSensorTime < SENSOR_INTERVAL_MS)
        return;
    lastSensorTime = now;

    // PIR
    pirState = digitalRead(PIR_PIN);
    if (pirState && !pirPrevState)
    {
        sendEvent("presence_detected", "{}")
    }
    pirPrevState = pirState;

    // Touch
    touchState = digitalRead(TOUCH_PIN);
    if (touchState && !touchPrevState)
    {
        sendEvent("touch_detected", "{}");
    }
    touchPrevState = touchState;

    // Ultrasonic distance
    distanceCm = readUltrasonic();

    // Send sensor bundle every cycle
    outDoc.clear();
    outDoc["event"] = "sensors";
    outDoc["pir"] = pirState;
    outDoc["touch"] = touchState;
    outDoc["dist_cm"] = (int)distanceCm;
    serializeJson(outDoc, txBuffer);

    Serial.println(txBuffer);
}

float readUltrasonic()
{
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);
    long duration = pulseIn(ECHO_PIN, HIGH, 30000); // 30ms timeout
    if (duration == 0)
        return 400.0f; // No echo = far
    return duration * 0.0343f / 2.0f;
}

void sendEvent(const char *evt, const char *payloadJson)
{
    // Inline merge: {"event":"...","data":{...}}
    Serial.print("{\"event\":\"");
    Serial.print(evt);
    Serial.print("\",\"data\":");
    Serial.print(payloadJson);
    Serial.println("}");
}

void setNeutral()
{
    headPan.write(HEAD_PAN_NEUTRAL);
    headTilt.write(HEAD_TILT_NEUTRAL);
    leftArm.write(LEFT_ARM_NEUTRAL);
    rightArm.write(RIGHT_ARM_NEUTRAL);
}

void blinkLED(int times)
{
    for (int i = 0; i < times; ++i)
    {
        digitalWrite(LED_PIN, HIGH);
        delay(150);
        digitalWrite(LED_PIN, LOW);
        delay(150);
    }
}

void readSerial()
{
    if (!Serial.available())
        return;

    String line = Serial.readStringUntil('\n'); // Reads string until new line comes
    line.trim();
    if (line.length() == 0)
        return;

    DeserializationError err = deserializeJson(inDoc, line);
    if (err)
    {
        sendEvent("error", "{\"msg\":\"bad_json\"}");
        return;
    }

    const char *cmd = inDoc["cmd"] | "";
    handleCommand(cmd); // To be implement later
}

// State Helpers
void setGestureState()
{
    robotState = STATE_GESTURE;
    digitalWrite(LED_PIN, HIGH);
}

void handleCommand(const char *cmd)
{
    if (strcmp(cmd, "gesture_wave") == 0)
    {
        setGestureState();
        gestureWave();
    }
    else if (strcmp(cmd, "gesture_handshake") == 0)
    {
        setGestureState();
        gestureHandshake();
    }
    else if (strcmp(cmd, "gesture_nod") == 0)
    {
        setGestureState();
        gestureNod();
    }
    else if (strcmp(cmd, "gesture_shake") == 0)
    {
        setGestureState();
        gestureShake();
    }
    else if (strcmp(cmd, "gesture_happy") == 0)
    {
        setGestureState();
        gestureHappy();
    }
    else if (strcmp(cmd, "gesture_sad") == 0)
    {
        setGestureState();
        gestureSad();
    }
    else if (strcmp(cmd, "gesture_surprised") == 0)
    {
        setGestureState();
        gestureSurprised();
    }
    else if (strcmp(cmd, "gesture_point") == 0)
    {
        setGestureState();
        gesturePointForward();
    }
    else if (strcmp(cmd, "thinking_start") == 0)
    {
        startThinking();
    }
    else if (strcmp(cmd, "thinking_stop") == 0)
    {
        stopThinking();
    }
    else if (strcmp(cmd, "speaking_start") == 0)
    {
        robotState = STATE_SPEAKING;
    }
    else if (strcmp(cmd, "speaking_stop") == 0)
    {
        robotState = STATE_IDLE;
        setNeutral();
    }
    else if (strcmp(cmd, "neutral") == 0)
    {
        robotState = STATE_IDLE;
        setNeutral();
    }
    else if (strcmp(cmd, "ping") == 0)
    {
        sendEvent("pong", "{}");
    }
    else if (strcmp(cmd, "gesture_hug_leg") == 0)
    {
        setGestureState();
        gestureHugLeg();
    }
    else if (strcmp(cmd, "gesture_hug_waist") == 0)
    {
        setGestureState();
        gestureHugWaist();
    }
    else if (strcmp(cmd, "gesture_hug_reach") == 0)
    {
        setGestureState();
        gestureHugReach();
    }
    else if (strcmp(cmd, "gesture_comfort_pat") == 0)
    {
        setGestureState();
        gestureComfortPat();
    }
    else
    {
        sendEvent("error", "{\"msg\":\"unknown_cmd\"}");
        return;
    }
    sendEvent("ack", "{}");
}