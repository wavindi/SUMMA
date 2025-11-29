#include <Wire.h>
#include <SparkFun_VL53L5CX_Library.h>

SparkFun_VL53L5CX sensor;

#define RANGING_FREQ 15

#define SDA_PIN 4
#define SCL_PIN 5

void setup() {
  // UART to Raspberry Pi
  Serial1.setTX(0);
  Serial1.setRX(1);
  Serial1.begin(57600);
  delay(1000);
  
  Serial1.println("PICO_BRIDGE_START");
  
  // I2C to sensor
  Wire.setSDA(SDA_PIN);
  Wire.setSCL(SCL_PIN);
  Wire.begin();
  Wire.setClock(400000);
  
  delay(100);
  Serial1.println("INIT_SENSOR");
  
  if (sensor.begin() == false) {
    Serial1.println("ERROR:SENSOR_INIT_FAILED");
    while (1) {
      delay(5000);
      Serial1.println("ERROR:SENSOR_NOT_RESPONDING");
    }
  }
  
  Serial1.println("SENSOR_FOUND");
  
  // Set 4x4 mode (16 zones)
  sensor.setResolution(4*4);  // ← 4x4 mode (16 zones)
  Serial1.println("CONFIG:4x4_MODE");
  
  sensor.setRangingFrequency(RANGING_FREQ);
  Serial1.print("CONFIG:FREQ_");
  Serial1.println(RANGING_FREQ);
  
  sensor.startRanging();
  Serial1.println("READY");
}

void loop() {
  if (sensor.isDataReady()) {
    VL53L5CX_ResultsData data;
    
    if (sensor.getRangingData(&data)) {
      Serial1.println("DATA_START");
      
      // Send 16 zones (4x4)
      for (int i = 0; i < 16; i++) {
        Serial1.print(data.distance_mm[i]);
        Serial1.print(",");
        Serial1.println(data.target_status[i]);
      }
      
      Serial1.println("DATA_END");
    }
  }
  
  delay(10);
}
