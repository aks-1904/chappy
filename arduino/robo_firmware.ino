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

// Functions prototype
void blinkLED(int);
void readSerial();
void setNeutral();

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
}

void sendEvent(const char* evt, const char* payloadJson) {
  // Inline merge: {"event":"...","data":{...}}
  Serial.print("{\"event\":\"");
  Serial.print(evt);
  Serial.print("\",\"data\":");
  Serial.print(payloadJson);
  Serial.println("}");
}

void setNeutral() {
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
}
