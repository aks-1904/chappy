#include <Arduino.h>
#include <Servo.h>
#include <ArduinoJson.h> // By Benoit Blanchon

#define SERIAL_BAUD 115200 // Serial baud rate of laptop

#define LED_PIN 13

// Functions prototype
void blinkLED(int);
void readSerial();

void setup()
{
    Serial.begin(SERIAL_BAUD);
    while (!Serial)
    {
        ;
    }

    pinMode(LED_PIN, OUTPUT);

    delay(500);

    // Sending signal to laptop when robot setup is done
    sendEvent("ready", "{}");

    blinkLED(3); // To confirm everything works fine
}

void loop()
{
    readSerial();
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
    if(!Serial.available()) return;

    String line = Serial.readStringUntil('\n'); // Reads string until new line comes
    line.trim();
    if(line.length() == 0) return;
}
