#!/usr/bin/env python3

"""
VL53L5CX Dual Sensor - Robust I2C with Error Recovery
- Handles OSError 5 issues
- Proper power-on sequence
- Second sensor troubleshooting
"""

import time
import smbus2
import sys
import os

from vl53l5cx_ctypes import VL53L5CX

# Check I2C first
def check_i2c():
    try:
        i2c_bus = smbus2.SMBus(1)
        print("I2C bus accessible")
        return i2c_bus
    except:
        print("❌ I2C bus not available")
        return None

def robust_sensor_init(address, name):
    """Initialize VL53L5CX with robust error handling"""
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            print(f"🔄 Initializing {name} (addr 0x{address:02x}) - Attempt {attempt + 1}")
            sensor = VL53L5CX(i2c_addr=address)
            
            # Power cycle delay
            time.sleep(0.1)
            
            # Basic config
            sensor.set_resolution(4*4)
            time.sleep(0.1)
            
            # Lower I2C frequency in code
            sensor.set_ranging_frequency_hz(10)  # Slower for stability
            time.sleep(0.1)
            
            sensor.start_ranging()
            time.sleep(0.3)
            
            # Test read
            if sensor.data_ready():
                data = sensor.get_data()
                distance = data.distance_mm[0][0]
                print(f"✅ {name} initialized - Sample reading: {distance}mm")
                return sensor
            else:
                print(f"⚠️  {name} not ready yet...")
                sensor.stop_ranging()
                time.sleep(0.2)
                
        except Exception as e:
            print(f"⚠️  {name} init attempt {attempt + 1} failed: {e}")
            time.sleep(0.5)
    
    print(f"❌ FAILED to initialize {name}")
    return None

def main():
    print("🔧 VL53L5CX I2C Troubleshooting")
    print("=" * 40)
    
    # Check I2C first
    i2c_bus = check_i2c()
    if not i2c_bus:
        print("❌ I2C not working. Check /boot/config.txt:")
        print("   dtparam=i2c_arm=on")
        print("   dtparam=i2c_baudrate=100000")
        print("   sudo reboot")
        sys.exit(1)
    
    # Try to initialize sensors
    sensor1 = robust_sensor_init(0x29, "Sensor 1")
    sensor2 = robust_sensor_init(0x39, "Sensor 2")
    
    if sensor1:
        print(f"✅ Sensor 1 (0x29) ready")
        # Test reading
        for i in range(5):
            if sensor1.data_ready():
                data = sensor1.get_data()
                dist = data.distance_mm[0][0]
                print(f"  Reading {i+1}: {dist}mm")
            time.sleep(0.1)
    else:
        print("❌ Sensor 1 failed - check wiring:")
        print("   SDA → Pi GPIO 2 (SDA)")
        print("   SCL → Pi GPIO 3 (SCL)")
        print("   VCC → Pi 3.3V (NOT 5V!)")
        print("   GND → Pi GND")
    
    if sensor2:
        print(f"✅ Sensor 2 (0x39) ready")
        for i in range(5):
            if sensor2.data_ready():
                data = sensor2.get_data()
                dist = data.distance_mm[0][0]
                print(f"  Reading {i+1}: {dist}mm")
            time.sleep(0.1)
    else:
        print("❌ Sensor 2 failed - only 1 sensor detected at 0x29")
        print("   Check second sensor wiring and power")
    
    if sensor1:
        sensor1.stop_ranging()
    if sensor2:
        sensor2.stop_ranging()

if __name__ == '__main__':
    main()
