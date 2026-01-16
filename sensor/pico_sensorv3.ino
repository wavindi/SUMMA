/*
 * VL53L5CX Sensor - GPIO 4/5 - Continuous Streaming
 */

#include <Wire.h>
#include <SparkFun_VL53L5CX_Library.h>

SparkFun_VL53L5CX sensor;
VL53L5CX_ResultsData measurementData;

#define I2C_SDA 4
#define I2C_SCL 5
#define I2C_FREQ 400000
#define UART_BAUD 57600
#define RESOLUTION 16
#define RANGING_FREQ 15

uint32_t frame_count = 0;
uint32_t error_count = 0;

void setup() {
  // USB Serial
  Serial.begin(115200);
  delay(2000);
  
  Serial.println();
  Serial.println("============================================");
  Serial.println("   VL53L5CX Sensor - Continuous Streaming");
  Serial.println("============================================");
  Serial.println();
  
  // UART to Raspberry Pi
  Serial1.setTX(0);
  Serial1.setRX(1);
  Serial1.begin(UART_BAUD);
  delay(100);
  Serial.print("OK: UART initialized at ");
  Serial.print(UART_BAUD);
  Serial.println(" baud");
  
  // I2C on GPIO 4/5
  Wire.setSDA(I2C_SDA);
  Wire.setSCL(I2C_SCL);
  Wire.begin();
  Wire.setClock(I2C_FREQ);
  Serial.print("OK: I2C on GPIO ");
  Serial.print(I2C_SDA);
  Serial.print("/");
  Serial.print(I2C_SCL);
  Serial.print(" at ");
  Serial.print(I2C_FREQ / 1000);
  Serial.println(" kHz");
  
  // Wait for sensor
  Serial.println("Waiting 500ms for sensor...");
  delay(500);
  
  // Pre-test
  Serial.print("Testing I2C at 0x29... ");
  Wire.beginTransmission(0x29);
  if (Wire.endTransmission() == 0) {
    Serial.println("OK!");
  } else {
    Serial.println("FAILED!");
    while(1) delay(5000);
  }
  
  // Initialize sensor
  Serial.println("Initializing VL53L5CX (5-10 sec)...");
  unsigned long startInit = millis();
  if (!sensor.begin()) {
    Serial.println("ERROR: Init failed!");
    while(1) delay(5000);
  }
  Serial.print("OK: Initialized in ");
  Serial.print(millis() - startInit);
  Serial.println(" ms");
  
  // Configure
  Serial.println("Configuring sensor...");
  sensor.setResolution(RESOLUTION);
  delay(100);
  sensor.setRangingFrequency(RANGING_FREQ);
  delay(100);
  Serial.print("OK: 4x4 mode at ");
  Serial.print(RANGING_FREQ);
  Serial.println(" Hz");
  
  // Start ranging
  Serial.println("Starting ranging...");
  sensor.startRanging();
  delay(500);
  Serial.println("OK: Ranging started");
  
  Serial.println();
  Serial.println("============================================");
  Serial.println("     SYSTEM READY - STREAMING DATA!");
  Serial.println("============================================");
  Serial.println();
  
  Serial1.println("PICO_READY");
  delay(100);
}

void loop() {
  if (sensor.isDataReady()) {
    if (sensor.getRangingData(&measurementData)) {
      
      frame_count++;
      
      // USB output (human-readable)
      Serial.println("DATA_START");
      Serial.print("Frame #");
      Serial.print(frame_count);
      Serial.println(" - 4x4 Grid:");
      
      for (int row = 0; row < 4; row++) {
        for (int col = 0; col < 4; col++) {
          int zone = row * 4 + col;
          int distance = measurementData.distance_mm[zone];
          
          if (distance < 10) Serial.print("   ");
          else if (distance < 100) Serial.print("  ");
          else if (distance < 1000) Serial.print(" ");
          
          Serial.print(distance);
          Serial.print("mm ");
        }
        Serial.println();
      }
      Serial.println("DATA_END");
      Serial.println("---");
      
      // UART output (to Raspberry Pi)
      Serial1.println("DATA_START");
      for (int i = 0; i < RESOLUTION; i++) {
        Serial1.print(measurementData.distance_mm[i]);
        Serial1.print(",");
        Serial1.println(measurementData.target_status[i]);
      }
      Serial1.println("DATA_END");
      
      // Status every 100 frames
      if (frame_count % 100 == 0) {
        Serial.println();
        Serial.print("STATUS: Frame ");
        Serial.print(frame_count);
        Serial.print(" | Errors: ");
        Serial.print(error_count);
        Serial.print(" | Uptime: ");
        Serial.print(millis() / 1000);
        Serial.println(" sec");
        Serial.println();
      }
      
    } else {
      error_count++;
    }
  }
  delay(5);
}
