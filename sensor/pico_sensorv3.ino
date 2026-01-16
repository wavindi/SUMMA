/*
 * VL53L5CX Sensor Bridge - GPIO 2/3 (I2C1)
 * KEY CHANGES:
 * - Uses Wire1 (I2C1) instead of Wire (I2C0)
 * - Explicitly passes Wire1 to sensor.begin()
 * - 100kHz I2C speed (more reliable than 400kHz)
 */

#include <Wire.h>
#include <SparkFun_VL53L5CX_Library.h>

SparkFun_VL53L5CX sensor;
VL53L5CX_ResultsData measurementData;

// I2C Configuration - GPIO 2/3 on I2C1
#define I2C_SDA 2            // GPIO 2 -> Sensor SDA
#define I2C_SCL 3            // GPIO 3 -> Sensor SCL
#define I2C_FREQ 100000      // 100kHz (more reliable)

// UART Configuration
#define UART_BAUD 57600

// Sensor Configuration
#define RESOLUTION 16        // 4x4 mode
#define RANGING_FREQ 15      // 15Hz

uint32_t frame_count = 0;
uint32_t error_count = 0;

void setup() {
  Serial.begin(115200);
  delay(2000);
  
  Serial.println("╔════════════════════════════════════════════╗");
  Serial.println("║  VL53L5CX Sensor Bridge - GPIO 2/3 (I2C1) ║");
  Serial.println("╚════════════════════════════════════════════╝");
  
  // UART
  Serial1.setTX(0);
  Serial1.setRX(1);
  Serial1.begin(UART_BAUD);
  delay(100);
  
  Serial.print("CONFIG: UART at ");
  Serial.print(UART_BAUD);
  Serial.println(" baud");
  
  // I2C1 on GPIO 2/3
  Wire1.setSDA(I2C_SDA);
  Wire1.setSCL(I2C_SCL);
  Wire1.begin();
  Wire1.setClock(I2C_FREQ);
  
  Serial.print("CONFIG: I2C1 on GPIO ");
  Serial.print(I2C_SDA);
  Serial.print("/");
  Serial.print(I2C_SCL);
  Serial.print(" at ");
  Serial.print(I2C_FREQ / 1000);
  Serial.println(" kHz");
  
  delay(100);
  
  // Initialize sensor with Wire1
  Serial.println("CONFIG: Initializing VL53L5CX sensor...");
  
  if (sensor.begin(0x29, Wire1) == false) {  // ← MUST specify Wire1!
    Serial.println("ERROR: VL53L5CX sensor initialization failed!");
    Serial.println("ERROR: Check I2C connections:");
    Serial.println("ERROR:   GPIO 2 = SDA");
    Serial.println("ERROR:   GPIO 3 = SCL");
    Serial.println("ERROR:   3.3V power connected?");
    Serial.println("ERROR:   GND connected?");
    Serial.println();
    Serial.println("TROUBLESHOOTING:");
    Serial.println("  1. Verify 3.3V power (NOT 5V!)");
    Serial.println("  2. Check wire connections");
    Serial.println("  3. Add 4.7kΩ pull-up resistors");
    Serial.println("  4. Run I2C scanner");
    
    while(1) {
      delay(1000);
      Serial.println("ERROR: Sensor not detected. Retrying...");
    }
  }
  
  Serial.println("CONFIG: Sensor detected successfully!");
  
  sensor.setResolution(RESOLUTION);
  Serial.print("CONFIG: Resolution: 4x4 (");
  Serial.print(RESOLUTION);
  Serial.println(" zones)");
  
  sensor.setRangingFrequency(RANGING_FREQ);
  Serial.print("CONFIG: Frequency: ");
  Serial.print(RANGING_FREQ);
  Serial.println(" Hz");
  
  sensor.startRanging();
  Serial.println("CONFIG: Ranging started");
  Serial.println("READY: Sensor streaming data");
  Serial.println("═══════════════════════════════════════════");
  
  Serial1.println("PICO_READY");
  delay(100);
}

void loop() {
  if (sensor.isDataReady()) {
    if (sensor.getRangingData(&measurementData)) {
      
      frame_count++;
      
      // USB Serial (human readable)
      Serial.println("DATA_START");
      Serial.print("Frame #");
      Serial.print(frame_count);
      Serial.println(" - 4x4 Grid:");
      
      for (int row = 0; row < 4; row++) {
        for (int col = 0; col < 4; col++) {
          int zone = row * 4 + col;
          Serial.print(measurementData.distance_mm[zone]);
          Serial.print("mm ");
        }
        Serial.println();
      }
      
      Serial.println("DATA_END");
      Serial.println("---");
      
      // UART to Pi (machine readable)
      Serial1.println("DATA_START");
      for (int i = 0; i < RESOLUTION; i++) {
        Serial1.print(measurementData.distance_mm[i]);
        Serial1.print(",");
        Serial1.println(measurementData.target_status[i]);
      }
      Serial1.println("DATA_END");
      
      if (frame_count % 100 == 0) {
        Serial.print("STATUS: Frame ");
        Serial.print(frame_count);
        Serial.print(" | Errors: ");
        Serial.println(error_count);
      }
    } else {
      error_count++;
    }
  }
  delay(5);
}
