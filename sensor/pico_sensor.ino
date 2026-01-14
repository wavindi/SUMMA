/*
 * Raspberry Pi Pico - VL53L5CX UART Bridge for SUMMA Padel Scoring
 * Version: 2.0 - Custom Pin Configuration
 * 
 * Upload this SAME code to BOTH Pico boards
 * 
 * Hardware Connections:
 * - I2C1: GPIO 2 (SDA), GPIO 3 (SCL) -> VL53L5CX sensor
 * - UART0 (Serial1): GPIO 0 (TX) -> Raspberry Pi 3B UART RX
 * - USB Serial (Serial): For debugging via USB
 * - Power: 3.3V, GND
 * 
 * Board Manager: Install "Raspberry Pi Pico/RP2040" by Earle F. Philhower
 * Library: Install "SparkFun VL53L5CX Arduino Library" by SparkFun Electronics
 */

#include <Wire.h>
#include <SparkFun_VL53L5CX_Library.h>

// ============================================================================
// CONFIGURATION
// ============================================================================
// I2C Configuration (Wire1 = I2C1)
#define I2C_SDA 2            // GPIO 2 -> Sensor SDA
#define I2C_SCL 3            // GPIO 3 -> Sensor SCL
#define I2C_FREQ 400000      // 400kHz Fast Mode

// UART Configuration (Serial1 = UART0)
#define UART_TX 0            // GPIO 0 -> Pi 3B RX
#define UART_RX 1            // GPIO 1 (not used, but configured)
#define UART_BAUD 57600

// Sensor Configuration
#define RESOLUTION 16        // 4x4 mode (16 zones)
#define RANGING_FREQ 15      // 15Hz update rate

// ============================================================================
// SENSOR INSTANCE
// ============================================================================
SparkFun_VL53L5CX sensor;
bool sensor_ready = false;
uint32_t frame_count = 0;
uint32_t error_count = 0;

// ============================================================================
// SETUP
// ============================================================================
void setup() {
  // Initialize USB Serial for debugging
  Serial.begin(115200);
  delay(2000);  // Wait for USB serial connection
  
  Serial.println("╔════════════════════════════════════════════╗");
  Serial.println("║  Raspberry Pi Pico - VL53L5CX UART Bridge ║");
  Serial.println("║  SUMMA Padel Scoring System v2.0          ║");
  Serial.println("╚════════════════════════════════════════════╝");
  
  // Initialize UART0 (Serial1) for communication with Raspberry Pi 3B
  Serial1.setTX(UART_TX);
  Serial1.setRX(UART_RX);
  Serial1.begin(UART_BAUD);
  delay(100);
  
  Serial.println("CONFIG: UART0 initialized");
  Serial.print("CONFIG: UART Pins - TX: GPIO");
  Serial.print(UART_TX);
  Serial.print(", RX: GPIO");
  Serial.println(UART_RX);
  Serial.print("CONFIG: UART Baud: ");
  Serial.println(UART_BAUD);
  
  // Initialize I2C1 on GPIO 2/3
  Wire1.setSDA(I2C_SDA);
  Wire1.setSCL(I2C_SCL);
  Wire1.begin();
  Wire1.setClock(I2C_FREQ);
  
  Serial.println("CONFIG: I2C1 initialized");
  Serial.print("CONFIG: I2C Pins - SDA: GPIO");
  Serial.print(I2C_SDA);
  Serial.print(", SCL: GPIO");
  Serial.println(I2C_SCL);
  Serial.print("CONFIG: I2C Speed: ");
  Serial.print(I2C_FREQ / 1000);
  Serial.println(" kHz");
  
  // Small delay for sensor power-up
  delay(100);
  
  // Initialize VL53L5CX sensor on Wire1 (I2C1)
  Serial.println("CONFIG: Initializing VL53L5CX sensor...");
  
  if (sensor.begin(0x29, Wire1) == false) {
    Serial.println("ERROR: VL53L5CX sensor initialization failed!");
    Serial.print("ERROR: Check I2C connections (GPIO");
    Serial.print(I2C_SDA);
    Serial.print("=SDA, GPIO");
    Serial.print(I2C_SCL);
    Serial.println("=SCL)");
    
    Serial1.println("ERROR: Sensor init failed!");
    
    while(1) {
      delay(1000);
      Serial.println("ERROR: Sensor not detected. Retrying...");
    }
  }
  
  Serial.println("CONFIG: Sensor detected successfully");
  
  // Set resolution to 4x4 (16 zones)
  sensor.setResolution(RESOLUTION);
  Serial.print("CONFIG: Resolution set to 4x4 (");
  Serial.print(RESOLUTION);
  Serial.println(" zones)");
  
  // Set ranging frequency
  sensor.setRangingFrequency(RANGING_FREQ);
  Serial.print("CONFIG: Ranging frequency: ");
  Serial.print(RANGING_FREQ);
  Serial.println(" Hz");
  
  // Start ranging
  sensor.startRanging();
  Serial.println("CONFIG: Ranging started");
  Serial.println("READY: Sensor streaming data to Raspberry Pi 3B");
  Serial.println("═══════════════════════════════════════════");
  
  // Send ready signal to Pi 3B via Serial1 (UART0)
  Serial1.println("PICO_READY");
  
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
  if (sensor.isDataReady()) {
    VL53L5CX_ResultsData measurementData;
    
    // Get ranging data
    if (sensor.getRangingData(&measurementData)) {
      
      // Send data with protocol delimiters to Pi 3B via Serial1 (UART0)
      Serial1.println("DATA_START");
      
      // Send all 16 zone distances (4x4 grid)
      for (int i = 0; i < RESOLUTION; i++) {
        int distance_mm = measurementData.distance_mm[i];
        uint8_t status = measurementData.target_status[i];
        
        // Format: distance_mm,target_status
        Serial1.print(distance_mm);
        Serial1.print(",");
        Serial1.println(status);
      }
      
      Serial1.println("DATA_END");
      
      frame_count++;
      
      // Periodic status update to USB Serial (every 100 frames)
      if (frame_count % 100 == 0) {
        Serial.print("PICO: Frame ");
        Serial.print(frame_count);
        Serial.print(" | Errors: ");
        Serial.print(error_count);
        Serial.print(" | Sample distance zone 0: ");
        Serial.print(measurementData.distance_mm[0]);
        Serial.println(" mm");
      }
    } else {
      error_count++;
      if (error_count % 100 == 0) {
        Serial.print("WARNING: Failed to get ranging data (");
        Serial.print(error_count);
        Serial.println(" errors)");
      }
    }
  }
  
  // 5ms delay matches Pi polling rate
  delay(5);
}
