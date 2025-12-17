#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "DHT.h"

// === KONFIGURASI WIFI & SERVER ===
const char *ssid = "SAHABATKOPI .CO_5G";
const char *password = "akukeren";
const char *serverName = "http://192.168.1.50:5000/api/readings"; // IP Laptop
const char *device_id = "ESP32_REAL_01";

// === PIN SETUP ===
#define DHTPIN 4
#define DHTTYPE DHT22
#define MQ135_PIN 34
#define SDA_PIN 21
#define SCL_PIN 22
#define S0 26
#define S1 25
#define S2 33
#define S3 32
#define OUT 27

DHT dht(DHTPIN, DHTTYPE);
LiquidCrystal_I2C lcd(0x27, 16, 2);

bool systemActive = true;
float baselineFixed = 0;
bool isCalibrated = false;
unsigned long startCalib = 0;
unsigned long lastMsg = 0;
unsigned long lastLCDUpdate = 0;

// Variabel Sensor
float suhuFiltered = 0;
float humidFiltered = 0;
int gasValueFiltered = 0;
int redVal = 0, greenVal = 0, blueVal = 0;
String serverStatus = "Init...";

// === FUNGSI FILTER ===
float filter(float newValue, float oldValue, float alpha = 0.2)
{
    return (alpha * newValue) + ((1 - alpha) * oldValue);
}

// === FUNGSI BACA WARNA  ===
void bacaWarna()
{
    if (!systemActive)
        return;

    digitalWrite(S2, LOW);
    digitalWrite(S3, LOW);
    delay(10);
    redVal = pulseIn(OUT, LOW);

    digitalWrite(S2, HIGH);
    digitalWrite(S3, HIGH);
    delay(10);
    greenVal = pulseIn(OUT, LOW);

    digitalWrite(S2, LOW);
    digitalWrite(S3, HIGH);
    delay(10);
    blueVal = pulseIn(OUT, LOW);
}

String getWarnaDominan()
{
    if (redVal == 0 || greenVal == 0 || blueVal == 0)
        return "-";

    int avg = (redVal + greenVal + blueVal) / 3;

    if (redVal < greenVal && redVal < blueVal)
        return "MRH";
    if (greenVal < redVal && greenVal < blueVal)
        return "HJU";
    if (blueVal < redVal && blueVal < greenVal)
        return "BRU";
    return "UNK";
}

// === LOGIKA SENSOR ===
void prosesSensor()
{
    if (!systemActive)
        return;

    float suhu = dht.readTemperature();
    float humid = dht.readHumidity();
    int rawGas = analogRead(MQ135_PIN);

    if (!isnan(suhu) && !isnan(humid))
    {
        suhuFiltered = filter(suhu, suhuFiltered);
        humidFiltered = filter(humid, humidFiltered);
        gasValueFiltered = (int)filter(rawGas, gasValueFiltered);
    }
    bacaWarna();

    // Mode Kalibrasi
    if (!isCalibrated)
    {
        unsigned long elapsed = millis() - startCalib;
        if (elapsed < 60000)
        {
            baselineFixed = gasValueFiltered;
            int countdown = 60 - (elapsed / 1000);
            lcd.setCursor(0, 0);
            lcd.print("Kalibrasi Udara ");
            lcd.setCursor(0, 1);
            lcd.printf("Tunggu: %2d dtk ", countdown);
            return;
        }
        isCalibrated = true;
        lcd.clear();
        lcd.print("Siap Digunakan!");
        delay(1000);
        lcd.clear();
    }
}

// === UPDATE LCD ===
void updateLCD()
{
    if (!systemActive)
    {
        lcd.noBacklight();
        lcd.clear();
        return;
    }

    lcd.backlight();
    lcd.setCursor(0, 0);
    lcd.printf("T:%.0f H:%.0f G:%d  ", suhuFiltered, humidFiltered, gasValueFiltered);

    lcd.setCursor(0, 1);
    String line2 = serverStatus;
    if (line2.length() > 9)
        line2 = line2.substring(0, 9);
    while (line2.length() < 10)
        line2 += " ";
    lcd.print(line2);
    lcd.print(" W:");
    lcd.print(getWarnaDominan());
}

// === KOMUNIKASI SERVER ===
void kirimDataHTTP()
{
    if (WiFi.status() != WL_CONNECTED)
        return;

    StaticJsonDocument<400> doc;
    doc["device_id"] = device_id;

    if (!systemActive)
    {
        doc["mq135"] = 0;
        doc["temp"] = 0;
        doc["humidity"] = 0;
        doc["r"] = 0;
        doc["g"] = 0;
        doc["b"] = 0;
    }
    else
    {
        doc["mq135"] = gasValueFiltered;
        doc["temp"] = suhuFiltered;
        doc["humidity"] = humidFiltered;
        doc["r"] = redVal;
        doc["g"] = greenVal;
        doc["b"] = blueVal;
    }

    String requestBody;
    serializeJson(doc, requestBody);

    HTTPClient http;
    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");

    int httpResponseCode = http.POST(requestBody);

    if (httpResponseCode > 0)
    {
        String response = http.getString();
        StaticJsonDocument<512> resDoc;
        deserializeJson(resDoc, response);

        const char *command = resDoc["command"];

        // Cek Perintah ON/OFF
        if (strcmp(command, "OFF") == 0)
        {
            if (systemActive)
            {
                systemActive = false;
                lcd.clear();
                lcd.noBacklight();
            }
        }
        else
        {
            if (!systemActive)
            {
                systemActive = true;
                lcd.backlight();
            }
        }

        const char *statusSvr = resDoc["status"];
        if (statusSvr)
            serverStatus = String(statusSvr);
    }
    else
    {
        Serial.print("Error: ");
        Serial.println(httpResponseCode);
    }
    http.end();
}

void setup()
{
    Serial.begin(115200);
    Wire.begin(SDA_PIN, SCL_PIN);
    lcd.init();
    lcd.backlight();
    lcd.print("WiFi Init...");

    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
        Serial.print(".");
    }

    lcd.clear();
    lcd.print("Connected!");
    delay(1000);
    lcd.clear();

    analogReadResolution(12);
    pinMode(S0, OUTPUT);
    pinMode(S1, OUTPUT);
    pinMode(S2, OUTPUT);
    pinMode(S3, OUTPUT);
    pinMode(OUT, INPUT);

    digitalWrite(S0, HIGH);
    digitalWrite(S1, LOW);

    dht.begin();
    startCalib = millis();
}

void loop()
{
    prosesSensor();

    unsigned long now = millis();

    if (now - lastLCDUpdate > 1000)
    {
        lastLCDUpdate = now;
        updateLCD();
    }

    int interval = systemActive ? 3000 : 5000;

    if (now - lastMsg > interval)
    {
        if (isCalibrated)
        {
            kirimDataHTTP();
        }
        lastMsg = now;
    }
}