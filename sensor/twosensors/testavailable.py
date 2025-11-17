#!/usr/bin/env python3
"""
Complete address change with LPn control
"""

import time
import RPi.GPIO as GPIO
from vl53l5cx_ctypes import VL53L5CX

print("=" * 80)
print("ADDRESS CHANGE WITH LPN CONTROL")
print("=" * 80)

# Setup GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.OUT)
GPIO.setup(27, GPIO.OUT)

# Disable BOTH sensors
print("\nDisabling both sensors...")
GPIO.output(17, GPIO.LOW)
GPIO.output(27, GPIO.LOW)
time.sleep(1)

# Enable GPIO 17's sensor only
print("Enabling GPIO 17 sensor only...")
GPIO.output(17, GPIO.HIGH)
GPIO.output(27, GPIO.LOW)
time.sleep(2)

# Verify it's at 0x29
print("\nChecking sensor at 0x29...")
try:
    s1 = VL53L5CX(i2c_addr=0x29)
    print("✅ Sensor found at 0x29")
except Exception as e:
    print(f"❌ Failed: {e}")
    GPIO.cleanup()
    exit(1)

# Change address
print("\nChanging address to 0x30...")
try:
    s1.set_i2c_address(0x30)
    time.sleep(1)
    print("✅ Address change command sent")
except Exception as e:
    print(f"❌ Failed: {e}")
    GPIO.cleanup()
    exit(1)

# Verify new address
print("\nVerifying sensor at 0x30...")
try:
    s1_new = VL53L5CX(i2c_addr=0x30)
    s1_new.set_resolution(4*4)
    print("✅ Sensor responding at 0x30")
except Exception as e:
    print(f"❌ Failed: {e}")
    GPIO.cleanup()
    exit(1)

# Enable second sensor
print("\nEnabling second sensor (GPIO 27)...")
GPIO.output(27, GPIO.HIGH)
time.sleep(2)

# Verify both sensors
print("\nVerifying both sensors...")
print("  Checking 0x29...")
try:
    s2 = VL53L5CX(i2c_addr=0x29)
    print("  ✅ Sensor at 0x29 (GPIO 27)")
except:
    print("  ❌ No sensor at 0x29")

print("  Checking 0x30...")
try:
    s1_check = VL53L5CX(i2c_addr=0x30)
    print("  ✅ Sensor at 0x30 (GPIO 17)")
except:
    print("  ❌ No sensor at 0x30")

print("\n" + "=" * 80)
print("DONE! Run i2cdetect -y 1 to verify")
print("=" * 80)

GPIO.cleanup()
