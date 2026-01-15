/*
 * Raspberry Pi Pico - VL53L5CX UART Bridge for SUMMA Padel Scoring
 * Version: 1.0 - Arduino IDE Implementation
 * 
 * Upload this SAME code to BOTH Picos
 * 
 * Hardware Connections:
 * - I2C0: GP4 (SDA), GP5 (SCL) -> VL53L5CX sensor
 * - UART0: GP0 (TX) -> Raspberry Pi GPIO 23 or 24
 * - Power: 3.3V, GND
 * 
 * Arduino IDE Setup:
 * 1. Install board: File > Preferences > Additional Boards Manager URLs:
 *    https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json
 * 2. Tools > Board > Raspberry Pi Pico/RP2040 > Raspberry Pi Pico
 * 3. Install library: Sketch > Include Library > Manage Libraries
 *    Search and install: "SparkFun VL53L5CX" by SparkFun Electronics
 */

#include <Wire.h>
#include <SparkFun_VL53L5CX_Library.h>

// ============================================================================
// CONFIGURATION
// ============================================================================
#define UART_BAUD 57600
#define I2C_FREQ 400000      // 400kHz Fast Mode I2C
#define RESOLUTION 16        // 4x4 mode (16 zones)
#define RANGING_FREQ 15      // 15Hz update rate

// GPIO Pin Definitions (for reference - handled by Wire and Serial)
#define I2C_SDA 4            // GP4
#define I2C_SCL 5            // GP5
#define UART_TX 0            // GP0
#define UART_RX 1            // GP1

// Status reporting
#define FRAME_REPORT_INTERVAL 100

// ============================================================================
// SENSOR INSTANCE
// ============================================================================
SparkFun_VL53L5CX sensor;
VL53L5CX_ResultsData measurementData;

bool sensor_ready = false;
uint32_t frame_count = 0;
uint32_t error_count = 0;

// ============================================================================
// SETUP
// ============================================================================
void setup() {
  // Initialize UART (Serial = UART0 on GP0/GP1)
  Serial.begin(UART_BAUD);
  delay(500);
  
  Serial.println("╔════════════════════════════════════════════╗");
  Serial.println("║  Raspberry Pi Pico - VL53L5CX UART Bridge ║");
  Serial.println("║     SUMMA Padel Scoring System v1.0       ║");
  Serial.println("╚════════════════════════════════════════════╝");
  
  // Initialize I2C on GP4/GP5 (Wire = I2C0)
  Wire.setSDA(I2C_SDA);
  Wire.setSCL(I2C_SCL);
  Wire.begin();
  Wire.setClock(I2C_FREQ);
  
  Serial.println("CONFIG: I2C initialized");
  Serial.print("CONFIG: I2C Pins - SDA: GP");
  Serial.print(I2C_SDA);
  Serial.print(", SCL: GP");
  Serial.println(I2C_SCL);
  Serial.print("CONFIG: I2C Speed: ");
  Serial.print(I2C_FREQ / 1000);
  Serial.println(" kHz");
  Serial.print("CONFIG: UART: GP");
  Serial.print(UART_TX);
  Serial.print("(TX) @ ");
  Serial.print(UART_BAUD);
  Serial.println(" baud");
  
  // Small delay for sensor power-up
  delay(100);
  
  // Initialize VL53L5CX sensor
  Serial.println("CONFIG: Initializing VL53L5CX sensor...");
  
  if (sensor.begin() == false) {
    Serial.println("ERROR: VL53L5CX sensor initialization failed!");
    Serial.println("ERROR: Check I2C connections:");
    Serial.print("ERROR:   - GP");
    Serial.print(I2C_SDA);
    Serial.println(" -> VL53L5CX SDA");
    Serial.print("ERROR:   - GP");
    Serial.print(I2C_SCL);
    Serial.println(" -> VL53L5CX SCL");
    Serial.println("ERROR:   - 3.3V -> VL53L5CX VIN");
    Serial.println("ERROR:   - GND -> VL53L5CX GND");
    
    while(1) {
      delay(1000);
      Serial.println("ERROR: Sensor not detected. Retrying...");
    }
  }
  
  Serial.println("CONFIG: Sensor detected successfully");
  
  // Set resolution to 4x4 (16 zones)
  if (sensor.setResolution(RESOLUTION) == false) {
    Serial.println("ERROR: Failed to set resolution");
  } else {
    Serial.print("CONFIG: Resolution set to 4x4 (");
    Serial.print(RESOLUTION);
    Serial.println(" zones)");
  }
  
  // Set ranging frequency
  if (sensor.setRangingFrequency(RANGING_FREQ) == false) {
    Serial.println("ERROR: Failed to set ranging frequency");
  } else {
    Serial.print("CONFIG: Ranging frequency: ");
    Serial.print(RANGING_FREQ);
    Serial.println(" Hz");
  }
  
  // Start ranging
  if (sensor.startRanging() == false) {
    Serial.println("ERROR: Failed to start ranging");
    while(1) {
      delay(1000);
      Serial.println("ERROR: Cannot start ranging. Check sensor!");
    }
  }
  
  Serial.println("CONFIG: Ranging started");
  Serial.println("READY: Sensor streaming data to Raspberry Pi");
  Serial.println("═══════════════════════════════════════════");
  
  sensor_ready = true;
  delay(100);
}

// ============================================================================
// MAIN LOOP
// ============================================================================
void loop() {
  if (!sensor_ready) {
    delay(100);
    return;
  }
  
  // Check if new data is ready
  if (sensor.isDataReady() == true) {
    
    // Get ranging data
    if (sensor.getRangingData(&measurementData) == false) {
      error_count++;
      if (error_count % 100 == 0) {
        Serial.print("WARNING: Failed to get ranging data (");
        Serial.print(error_count);
        Serial.println(" errors)");
      }
      delay(10);
      return;
    }
    
    // Send data with protocol delimiters
    Serial.println("DATA_START");
    
    // Send all 16 zone distances (4x4 grid)
    for (int i = 0; i < 16; i++) {
      int distance_mm = measurementData.distance_mm[i];
      uint8_t status = measurementData.target_status[i];
      
      // Format: distance_mm,target_status
      Serial.print(distance_mm);
      Serial.print(",");
      Serial.println(status);
    }
    
    Serial.println("DATA_END");
    
    frame_count++;
    
    // Periodic status update (every 100 frames)
    if (frame_count % FRAME_REPORT_INTERVAL == 0) {
      Serial.print("PICO: Frame ");
      Serial.print(frame_count);
      Serial.print(" | Errors: ");
      Serial.println(error_count);
    }
  }
  
  // Small delay to match Pi polling rate
  delay(5);
}
