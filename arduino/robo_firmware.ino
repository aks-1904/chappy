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
char txBuffer[256];

// Functions prototype
void blinkLED(int);
void readSerial();
void setNeutral();
void sendEvent(const char *, const char *);
void handleCommand(const char *);
void updateSensors();
float readUltrasonic();
void setGestureState();
void updateThinkingAnimation();
void startThinking();
void stopThinking();

// Gestures
void gestureWave();
void gestureHandshake();
void gestureNod();
void gestureShake();
void gestureHappy();
void gestureSad();
void gestureSurprised();
void gesturePointForward();
void gestureHugLeg();
void gestureComfortPat();
void gestureHugWaist();
void gestureHugReach();
void moveServoSlow(Servo &, int, int, int);
void moveServoBoth(int, int, int);

void setup()
{
    Serial.begin(SERIAL_BAUD);
    #ifdef USBCON
        while (!Serial)
            ;
    #endif

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

void startThinking()
{
    robotState = STATE_THINKING;
    thinkingStartMs = millis();
    digitalWrite(LED_PIN, HIGH);
}

void stopThinking()
{
    robotState = STATE_IDLE;
    setNeutral();
    digitalWrite(LED_PIN, LOW);
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

// Wave right arm
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

// Extend right arm for handshake, then retract
void gestureHandshake()
{
    moveServoSlow(rightArm, RIGHT_ARM_NEUTRAL, 90, 6);
    delay(800);

    // Simulate grip: slight tilt
    headTilt.write(HEAD_TILT_NEUTRAL - 10);
    delay(600);
    headTilt.write(HEAD_TILT_NEUTRAL);
    delay(400);
    moveServoSlow(rightArm, 90, RIGHT_ARM_NEUTRAL, 6);
    setNeutral();
    robotState = STATE_IDLE;
    digitalWrite(LED_PIN, LOW);

    sendEvent("gesture_done", "{\"gesture\":\"handshake\"}");
}

// Nod head up-down (agreement)
void gestureNod()
{
    for (int i = 0; i < 2; i++)
    {
        moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL - 20, 5);
        moveServoSlow(headTilt, HEAD_TILT_NEUTRAL - 20, HEAD_TILT_NEUTRAL + 10, 5);
        moveServoSlow(headTilt, HEAD_TILT_NEUTRAL + 10, HEAD_TILT_NEUTRAL, 5);
    }
    setNeutral();
    robotState = STATE_IDLE;
    digitalWrite(LED_PIN, LOW);
    sendEvent("gesture_done", "{\"gesture\":\"nod\"}");
}

// Head shake left-right (disagreement / no)
void gestureShake()
{
    for (int i = 0; i < 2; i++)
    {
        moveServoSlow(headPan, HEAD_PAN_NEUTRAL, HEAD_PAN_NEUTRAL - 25, 5);
        moveServoSlow(headPan, HEAD_PAN_NEUTRAL - 25, HEAD_PAN_NEUTRAL + 25, 5);
        moveServoSlow(headPan, HEAD_PAN_NEUTRAL + 25, HEAD_PAN_NEUTRAL, 5);
    }
    setNeutral();
    robotState = STATE_IDLE;
    digitalWrite(LED_PIN, LOW);
    sendEvent("gesture_done", "{\"gesture\":\"shake\"}");
}

// Happy: both arms up + head tilt
void gestureHappy()
{
    moveServoSlow(leftArm, LEFT_ARM_NEUTRAL, 90, 6);
    moveServoSlow(rightArm, RIGHT_ARM_NEUTRAL, 90, 6);
    headTilt.write(HEAD_TILT_NEUTRAL - 15);
    delay(700);

    // Celebrate bounce
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
    moveServoSlow(leftArm, 90, LEFT_ARM_NEUTRAL, 6);
    moveServoSlow(rightArm, 90, RIGHT_ARM_NEUTRAL, 6);

    setNeutral();
    robotState = STATE_IDLE;

    digitalWrite(LED_PIN, LOW);
    sendEvent("gesture_done", "{\"gesture\":\"happy\"}");
}

// Sad: arms droop, head tilts down
void gestureSad()
{
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL + 20, 5);
    delay(1200);
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL + 20, HEAD_TILT_NEUTRAL, 5);
    setNeutral();
    robotState = STATE_IDLE;
    digitalWrite(LED_PIN, LOW);
    sendEvent("gesture_done", "{\"gesture\":\"sad\"}");
}

// Surprised: head snaps up, arms fling up
void gestureSurprised()
{
    headTilt.write(HEAD_TILT_NEUTRAL - 30);
    leftArm.write(90);
    rightArm.write(90);
    delay(600);
    headTilt.write(HEAD_TILT_NEUTRAL);
    moveServoSlow(leftArm, 90, LEFT_ARM_NEUTRAL, 8);
    moveServoSlow(rightArm, 90, RIGHT_ARM_NEUTRAL, 8);
    setNeutral();
    robotState = STATE_IDLE;
    digitalWrite(LED_PIN, LOW);
    sendEvent("gesture_done", "{\"gesture\":\"surprised\"}");
}

// Point forward with right arm
void gesturePointForward()
{
    moveServoSlow(rightArm, RIGHT_ARM_NEUTRAL, 90, 6);
    headPan.write(HEAD_PAN_NEUTRAL);
    delay(1000);
    moveServoSlow(rightArm, 90, RIGHT_ARM_NEUTRAL, 6);
    setNeutral();
    robotState = STATE_IDLE;
    digitalWrite(LED_PIN, LOW);
    sendEvent("gesture_done", "{\"gesture\":\"point\"}");
}

// Move both arms simultaneously toward targets (Helper)
void moveServoBoth(int leftTarget, int rightTarget, int stepDelay)
{
    int lCurrent = leftArm.read();
    int rCurrent = rightArm.read();
    int steps = max(abs(leftTarget - lCurrent), abs(rightTarget - rCurrent));
    for (int i = 1; i <= steps; i++)
    {
        float t = (float)i / steps;
        leftArm.write(lCurrent + (int)((leftTarget - lCurrent) * t));
        rightArm.write(rCurrent + (int)((rightTarget - rCurrent) * t));
        delay(stepDelay);
    }
    leftArm.write(leftTarget);
    rightArm.write(rightTarget);
}

void gestureHugLeg()
{
    // Lean head forward and down
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL + 25, 6);

    // Both arms sweep outward
    moveServoBoth(45, 135, 7);
    delay(200);

    // Arms wrap inward
    moveServoBoth(75, 105, 5); // close in
    delay(300);
    moveServoBoth(82, 98, 4); // Squeeze
    delay(1500);              // Hold the hug

    // Release slowly
    moveServoBoth(60, 120, 6);
    delay(200);
    moveServoBoth(LEFT_ARM_NEUTRAL, RIGHT_ARM_NEUTRAL, 7);

    // Head back up with a gentle tilt
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL + 25, HEAD_TILT_NEUTRAL - 5, 6);
    delay(300);
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL - 5, HEAD_TILT_NEUTRAL, 5);

    setNeutral();
    robotState = STATE_IDLE;
    digitalWrite(LED_PIN, LOW);
    sendEvent("gesture_done", "{\"gesture\":\"hug_leg\"}");
}

void gestureHugWaist()
{
    // Head tilts forward
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL + 15, 6);

    // Arms rise to mid position
    moveServoBoth(60, 120, 7);
    delay(150);

    // Arms open wide
    moveServoBoth(35, 145, 6);
    delay(300);

    // Arms wrap in firmly
    moveServoBoth(72, 108, 5);
    delay(300);
    moveServoBoth(80, 100, 4); // tight hug
    delay(1800);               // hold

    // Gentle pat during hold (right arm only)
    for (int i = 0; i < 3; ++i)
    {
        rightArm.write(95);
        delay(200);
        rightArm.write(100);
        delay(200);
    }

    // Release
    moveServoBoth(50, 130, 7);
    delay(200);
    moveServoBoth(LEFT_ARM_NEUTRAL, RIGHT_ARM_NEUTRAL, 8);
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL + 15, HEAD_TILT_NEUTRAL, 5);

    setNeutral();
    robotState = STATE_IDLE;
    digitalWrite(LED_PIN, LOW);
    sendEvent("gesture_done", "{\"gesture\":\"hug_waist\"}");
}

void gestureHugReach()
{
    // Head tilts back slightly
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL - 20, 6);

    // Both arms sweep up high
    moveServoBoth(LEFT_ARM_NEUTRAL, RIGHT_ARM_NEUTRAL, 8); // ensure start
    delay(100);
    moveServoBoth(70, 110, 6); // mid
    delay(100);
    moveServoBoth(88, 92, 5); // reaching up

    delay(400);

    // Wrap inward - hugging around their head/shoulders
    moveServoBoth(83, 97, 4); // slight close
    delay(2000);              // long warm hold

    // Gentle rhythmic squeeze
    for (int i = 0; i < 2; i++)
    {
        moveServoBoth(80, 100, 5);
        delay(300);
        moveServoBoth(84, 96, 5);
        delay(300);
    }

    // Release - arms slide down gently
    moveServoBoth(70, 110, 6);
    delay(200);
    moveServoBoth(50, 130, 7);
    delay(200);
    moveServoBoth(LEFT_ARM_NEUTRAL, RIGHT_ARM_NEUTRAL, 8);

    // Head returns, slight warm nod
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL - 20, HEAD_TILT_NEUTRAL - 10, 5);
    delay(300);
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL - 10, HEAD_TILT_NEUTRAL, 5);

    setNeutral();
    robotState = STATE_IDLE;
    digitalWrite(LED_PIN, LOW);
    sendEvent("gesture_done", "{\"gesture\":\"hug_reach\"}");
}

void gestureComfortPat()
{
    // Head tilts gently to one side
    moveServoSlow(headPan, HEAD_PAN_NEUTRAL, HEAD_PAN_NEUTRAL + 12, 6);
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL, HEAD_TILT_NEUTRAL + 10, 6);

    // Right arm extends to comfortable reach
    moveServoSlow(rightArm, RIGHT_ARM_NEUTRAL, 105, 7);
    delay(300);

    // Gentle rhythmic pats (5 pats)
    for (int i = 0; i < 5; i++)
    {
        moveServoSlow(rightArm, 105, 98, 4); // forward
        delay(100);
        moveServoSlow(rightArm, 98, 105, 4); // back
        delay(180);
    }

    // Hold at gentle position
    delay(600);

    // Arm slowly retreats
    moveServoSlow(rightArm, 105, RIGHT_ARM_NEUTRAL, 8);

    // Head returns softly
    moveServoSlow(headPan, HEAD_PAN_NEUTRAL + 12, HEAD_PAN_NEUTRAL, 6);
    moveServoSlow(headTilt, HEAD_TILT_NEUTRAL + 10, HEAD_TILT_NEUTRAL, 6);

    setNeutral();
    robotState = STATE_IDLE;
    digitalWrite(LED_PIN, LOW);
    sendEvent("gesture_done", "{\"gesture\":\"comfort_pat\"}");
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
        sendEvent("presence_detected", "{}");
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
    handleCommand(cmd);
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