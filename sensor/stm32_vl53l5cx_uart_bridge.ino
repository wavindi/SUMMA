/*
 * STM32F103C6T6 - VL53L5CX UART Bridge for SUMMA Padel Scoring
 * Version: 2.0 - Dual Hardware UART Mode
 * 
 * Upload this SAME code to BOTH STM32 boards
 * 
 * Hardware Connections:
 * - I2C1: PB8 (SCL), PB9 (SDA) -> VL53L5CX sensor
 * - USART1: PA9 (TX) -> Raspberry Pi UART RX
 * - Power: 3.3V, GND
 */

#include <Wire.h>
#include <vl53l5cx_class.h>

// ============================================================================
// CONFIGURATION
// ============================================================================
#define I2C_SDA PB9
#define I2C_SCL PB8
#define VL53L5CX_ADDRESS 0x29

#define UART_BAUD 57600
#define RESOLUTION 16        // 4x4 mode (16 zones)
#define RANGING_FREQ 15      // 15Hz update rate

// ============================================================================
// SENSOR INSTANCE
// ============================================================================
VL53L5CX sensor(&Wire, -1, -1);  // Using hardware I2C, no LPn pin control
bool sensor_ready = false;
uint32_t frame_count = 0;
uint32_t error_count = 0;

// ============================================================================
// SETUP
// ============================================================================
void setup() {
  // Initialize UART (Serial uses PA9/PA10 on STM32F103)
  Serial.begin(UART_BAUD);
  delay(500);
  
  Serial.println("╔════════════════════════════════════════════╗");
  Serial.println("║  STM32F103C6T6 - VL53L5CX UART Bridge     ║");
  Serial.println("║  SUMMA Padel Scoring System v2.0          ║");
  Serial.println("╚════════════════════════════════════════════╝");
  
  // Initialize I2C on PB8/PB9
  Wire.begin();
  Wire.setClock(400000);  // 400kHz Fast Mode I2C
  
  Serial.println("CONFIG: I2C initialized");
  Serial.print("CONFIG: I2C Pins - SCL: PB8, SDA: PB9");
  Serial.println();
  Serial.print("CONFIG: I2C Speed: 400kHz");
  Serial.println();
  
  // Small delay for sensor power-up
  delay(100);
  
  // Initialize VL53L5CX sensor
  Serial.println("CONFIG: Initializing VL53L5CX sensor...");
  
  if (sensor.begin() != VL53L5CX_STATUS_OK) {
    Serial.println("ERROR: VL53L5CX sensor initialization failed!");
    Serial.println("ERROR: Check I2C connections (PB8=SCL, PB9=SDA)");
    while(1) {
      delay(1000);
      Serial.println("ERROR: Sensor not detected. Retrying...");
    }
  }
  
  Serial.println("CONFIG: Sensor detected successfully");
  
  // Initialize sensor
  if (sensor.init() != VL53L5CX_STATUS_OK) {
    Serial.println("ERROR: Sensor init() failed!");
    while(1) delay(1000);
  }
  
  Serial.println("CONFIG: Sensor initialized");
  
  // Set resolution to 4x4 (16 zones)
  if (sensor.vl53l5cx_set_resolution(RESOLUTION) != VL53L5CX_STATUS_OK) {
    Serial.println("ERROR: Failed to set resolution");
  } else {
    Serial.print("CONFIG: Resolution set to 4x4 (");
    Serial.print(RESOLUTION);
    Serial.println(" zones)");
  }
  
  // Set ranging frequency
  if (sensor.vl53l5cx_set_ranging_frequency_hz(RANGING_FREQ) != VL53L5CX_STATUS_OK) {
    Serial.println("ERROR: Failed to set ranging frequency");
  } else {
    Serial.print("CONFIG: Ranging frequency: ");
    Serial.print(RANGING_FREQ);
    Serial.println(" Hz");
  }
  
  // Set ranging mode to continuous
  if (sensor.vl53l5cx_set_ranging_mode(VL53L5CX_RANGING_MODE_CONTINUOUS) != VL53L5CX_STATUS_OK) {
    Serial.println("ERROR: Failed to set ranging mode");
  } else {
    Serial.println("CONFIG: Ranging mode: CONTINUOUS");
  }
  
  // Start ranging
  if (sensor.vl53l5cx_start_ranging() != VL53L5CX_STATUS_OK) {
    Serial.println("ERROR: Failed to start ranging");
    while(1) delay(1000);
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
  uint8_t isReady = 0;
  if (sensor.vl53l5cx_check_data_ready(&isReady) != VL53L5CX_STATUS_OK) {
    error_count++;
    if (error_count % 100 == 0) {
      Serial.print("WARNING: Data ready check failed (");
      Serial.print(error_count);
      Serial.println(" errors)");
    }
    delay(10);
    return;
  }
  
  if (isReady) {
    VL53L5CX_ResultsData results;
    
    // Get ranging data
    if (sensor.vl53l5cx_get_ranging_data(&results) != VL53L5CX_STATUS_OK) {
      error_count++;
      Serial.println("WARNING: Failed to get ranging data");
      delay(10);
      return;
    }
    
    // Send data with protocol delimiters
    Serial.println("DATA_START");
    
    // Send all 16 zone distances (4x4 grid)
    for (int i = 0; i < 16; i++) {
      int distance_mm = results.distance_mm[i];
      uint8_t status = results.target_status[i];
      
      // Format: distance_mm,target_status
      Serial.print(distance_mm);
      Serial.print(",");
      Serial.println(status);
    }
    
    Serial.println("DATA_END");
    
    frame_count++;
    
    // Periodic status update (every 100 frames)
    if (frame_count % 100 == 0) {
      Serial.print("STM32: Frame ");
      Serial.print(frame_count);
      Serial.print(" | Errors: ");
      Serial.println(error_count);
    }
  }
  
  // 5ms delay matches Pi polling rate
  delay(5);
}
