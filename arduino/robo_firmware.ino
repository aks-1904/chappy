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
