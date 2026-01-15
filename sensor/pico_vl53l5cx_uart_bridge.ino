/*
 * Raspberry Pi Pico - VL53L5CX UART Bridge for SUMMA Padel Scoring
 * Version: 3.0 - OPTIMIZED for 40m Cable Transmission
 * 
 * UPLOAD THIS SAME CODE TO BOTH PICO BOARDS
 * 
 * Hardware Connections:
 * - I2C1: GPIO 2 (SDA), GPIO 3 (SCL) -> VL53L5CX sensor
 * - UART0: GPIO 0 (TX ONLY) -> Raspberry Pi 3B GPIO 23 or 24
 * - GND -> Raspberry Pi 3B GND (CRITICAL for 40m cable)
 * - Power: 5V USB or external 5V supply
 * 
 * Board Manager: "Raspberry Pi Pico/RP2040" by Earle F. Philhower
 * Library: "SparkFun VL53L5CX Arduino Library" by SparkFun Electronics
 * 
 * Pico 1 (Black team): TX (GPIO 0) -> Pi GPIO 23
 * Pico 2 (Yellow team): TX (GPIO 0) -> Pi GPIO 24
 */

#include <Wire.h>
#include <SparkFun_VL53L5CX_Library.h>

// ============================================================================
// CONFIGURATION - TUNED FOR 40M CABLE TRANSMISSION
// ============================================================================

// I2C Configuration (Wire1 = I2C1, custom pins)
#define I2C_SDA 2            // GPIO 2 -> Sensor SDA
#define I2C_SCL 3            // GPIO 3 -> Sensor SCL
#define I2C_FREQ 400000      // 400kHz Fast Mode

// UART Configuration (Serial1 = UART0)
#define UART_TX 0            // GPIO 0 -> Pi GPIO 23 or 24 (via 40m cable)
#define UART_RX 1            // GPIO 1 (configured but not used)
#define UART_BAUD 57600      // MUST MATCH Pi script (optimal for 40m)

// Sensor Configuration
#define RESOLUTION 16        // 4x4 mode = 16 zones
#define RANGING_FREQ 15      // 15Hz (good balance for 40m transmission)

// Transmission Settings
#define LOOP_DELAY_MS 5      // Match Pi polling rate (200 Hz)
#define STATUS_INTERVAL 100  // Print status every N frames
#define NEWLINE_DELAY_US 200 // Microsecond delay between lines (for cable stability)

// ============================================================================
// GLOBAL VARIABLES
// ============================================================================

SparkFun_VL53L5CX sensor;
bool sensor_ready = false;
uint32_t frame_count = 0;
uint32_t error_count = 0;
uint32_t last_status_frame = 0;

// ============================================================================
// SETUP
// ============================================================================

void setup() {
  // Initialize USB Serial for debugging (optional, view via USB)
  Serial.begin(115200);
  delay(1000);

  Serial.println("╔═══════════════════════════════════════════════════════════╗");
  Serial.println("║  Raspberry Pi Pico - VL53L5CX UART Bridge v3.0           ║");
  Serial.println("║  SUMMA Padel Scoring System - 40m Cable Optimized        ║");
  Serial.println("╚═══════════════════════════════════════════════════════════╝");

  // Initialize UART0 (Serial1) - TX ONLY for Pi communication
  Serial1.setTX(UART_TX);
  Serial1.setRX(UART_RX);
  Serial1.begin(UART_BAUD);
  delay(100);

  Serial.println("[CONFIG] UART0 initialized");
  Serial.print("[CONFIG]   TX Pin: GPIO");
  Serial.println(UART_TX);
  Serial.print("[CONFIG]   Baud Rate: ");
  Serial.println(UART_BAUD);
  Serial.println("[CONFIG]   Mode: TX only -> Raspberry Pi 3B");

  // Initialize I2C1 on custom pins GPIO 2/3
  Wire1.setSDA(I2C_SDA);
  Wire1.setSCL(I2C_SCL);
  Wire1.begin();
  Wire1.setClock(I2C_FREQ);

  Serial.println("[CONFIG] I2C1 initialized");
  Serial.print("[CONFIG]   SDA: GPIO");
  Serial.println(I2C_SDA);
  Serial.print("[CONFIG]   SCL: GPIO");
  Serial.println(I2C_SCL);
  Serial.print("[CONFIG]   Frequency: ");
  Serial.print(I2C_FREQ / 1000);
  Serial.println(" kHz");

  // Wait for sensor power stabilization
  delay(200);

  // Initialize VL53L5CX sensor on Wire1 (I2C1)
  Serial.println("[INIT] Initializing VL53L5CX sensor...");

  uint8_t retry_count = 0;
  const uint8_t MAX_RETRIES = 5;

  while (!sensor.begin(0x29, Wire1) && retry_count < MAX_RETRIES) {
    retry_count++;
    Serial.print("[ERROR] Sensor init failed (attempt ");
    Serial.print(retry_count);
    Serial.print("/");
    Serial.print(MAX_RETRIES);
    Serial.println(")");
    Serial.print("[ERROR] Check I2C wiring: GPIO");
    Serial.print(I2C_SDA);
    Serial.print("(SDA), GPIO");
    Serial.print(I2C_SCL);
    Serial.println("(SCL)");

    // Send error to Pi
    Serial1.println("ERROR: Sensor init failed!");

    delay(2000);
  }

  if (retry_count >= MAX_RETRIES) {
    Serial.println("[FATAL] Sensor initialization failed after max retries!");
    Serial.println("[FATAL] System halted. Check sensor connections.");
    Serial1.println("FATAL: Sensor not detected!");
    while(1) {
      delay(5000);
      Serial.println("[FATAL] Waiting for sensor...");
    }
  }

  Serial.println("[OK] Sensor detected and initialized");

  // Configure sensor
  sensor.setResolution(RESOLUTION);
  Serial.print("[CONFIG] Resolution: 4x4 (");
  Serial.print(RESOLUTION);
  Serial.println(" zones)");

  sensor.setRangingFrequency(RANGING_FREQ);
  Serial.print("[CONFIG] Ranging frequency: ");
  Serial.print(RANGING_FREQ);
  Serial.println(" Hz");

  // Start ranging
  sensor.startRanging();
  Serial.println("[OK] Ranging started");

  // Send ready signal to Pi
  Serial1.println("PICO_READY");
  Serial1.println("CONFIG: 4x4 mode, 15Hz");

  Serial.println("[READY] Transmitting data to Raspberry Pi 3B via UART0");
  Serial.println("[READY] GPIO 0 (TX) -> Pi GPIO 23 or 24");
  Serial.println("════════════════════════════════════════════════════════════");

  sensor_ready = true;
  delay(100);
}

// ============================================================================
// MAIN LOOP - OPTIMIZED FOR RELIABLE 40M TRANSMISSION
// ============================================================================

void loop() {
  if (!sensor_ready) {
    delay(100);
    return;
  }

  // Check if new sensor data is available
  if (sensor.isDataReady()) {
    VL53L5CX_ResultsData measurementData;

    // Attempt to get ranging data
    if (sensor.getRangingData(&measurementData)) {

      // ═══════════════════════════════════════════════════════════════
      // TRANSMIT DATA TO RASPBERRY PI VIA UART (40M CABLE)
      // ═══════════════════════════════════════════════════════════════

      // Protocol start marker
      Serial1.println("DATA_START");
      delayMicroseconds(NEWLINE_DELAY_US);  // Small delay for cable stability

      // Send all 16 zones (4x4 grid)
      // Format: distance_mm,target_status
      for (int i = 0; i < RESOLUTION; i++) {
        int distance_mm = measurementData.distance_mm[i];
        uint8_t status = measurementData.target_status[i];

        // Send formatted data: "distance,status\n"
        Serial1.print(distance_mm);
        Serial1.print(",");
        Serial1.println(status);

        // Tiny delay between lines for long cable reliability
        delayMicroseconds(NEWLINE_DELAY_US);
      }

      // Protocol end marker
      Serial1.println("DATA_END");

      frame_count++;

      // ═══════════════════════════════════════════════════════════════
      // PERIODIC STATUS UPDATE (USB SERIAL DEBUG)
      // ═══════════════════════════════════════════════════════════════

      if (frame_count - last_status_frame >= STATUS_INTERVAL) {
        last_status_frame = frame_count;

        Serial.print("[FRAME ");
        Serial.print(frame_count);
        Serial.print("] Errors: ");
        Serial.print(error_count);
        Serial.print(" | Zone 0: ");
        Serial.print(measurementData.distance_mm[0]);
        Serial.print("mm | Zone 7: ");
        Serial.print(measurementData.distance_mm[7]);
        Serial.println("mm");

        // Show error rate if any
        if (error_count > 0) {
          float error_rate = (float)error_count / (float)frame_count * 100.0;
          Serial.print("[STATUS] Error rate: ");
          Serial.print(error_rate, 2);
          Serial.println("%");
        }
      }

    } else {
      // Failed to get data
      error_count++;

      if (error_count % 50 == 0) {
        Serial.print("[WARNING] Data read failures: ");
        Serial.println(error_count);
      }
    }
  }

  // Loop delay to match Pi polling rate (200 Hz = 5ms)
  delay(LOOP_DELAY_MS);
}

// ============================================================================
// HELPER FUNCTIONS (IF NEEDED IN FUTURE)
// ============================================================================

// Optional: Function to flush UART buffer (not currently used)
void flushUART() {
  Serial1.flush();
}

// Optional: Health check function
void sendHealthCheck() {
  Serial1.print("HEALTH: Frames=");
  Serial1.print(frame_count);
  Serial1.print(", Errors=");
  Serial1.println(error_count);
}
