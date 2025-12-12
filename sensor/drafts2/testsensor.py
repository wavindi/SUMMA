#!/usr/bin/env python3
"""
VL53L5CX Diagnostic - Find what's wrong
"""

import time
import RPi.GPIO as GPIO
import subprocess
import atexit

LPN_GPIO_17 = 17
LPN_GPIO_27 = 27

def run_i2cdetect():
    """Show I2C devices"""
    result = subprocess.run(['i2cdetect', '-y', '1'], capture_output=True, text=True)
    print(result.stdout)

def setup_gpio():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(LPN_GPIO_17, GPIO.OUT)
    GPIO.setup(LPN_GPIO_27, GPIO.OUT)

def cleanup_gpio():
    """Custom cleanup that keeps GPIO 17 and 27 HIGH"""
    print("\n🔌 Keeping GPIO 17 and 27 HIGH (sensors ON)")
    # Don't call GPIO.cleanup() as it would reset all pins
    # Instead, explicitly set the pins we want to keep high
    GPIO.output(LPN_GPIO_17, GPIO.HIGH)
    GPIO.output(LPN_GPIO_27, GPIO.HIGH)

print("=" * 80)
print("VL53L5CX DUAL SENSOR DIAGNOSTIC")
print("=" * 80)

setup_gpio()
# Register custom cleanup function to run when script exits
atexit.register(cleanup_gpio)

# Test 1: Both OFF
print("\n📋 TEST 1: Both LPn pins LOW (both sensors OFF)")
print("-" * 80)
GPIO.output(LPN_GPIO_17, GPIO.LOW)
GPIO.output(LPN_GPIO_27, GPIO.LOW)
time.sleep(1)
print("Expected: No sensors detected\n")
run_i2cdetect()

# Test 2: Only GPIO 17 ON
print("\n📋 TEST 2: GPIO 17 HIGH, GPIO 27 LOW (only Sensor 1)")
print("-" * 80)
GPIO.output(LPN_GPIO_17, GPIO.HIGH)
GPIO.output(LPN_GPIO_27, GPIO.LOW)
time.sleep(1)
print("Expected: One sensor at 0x29 or 0x30\n")
run_i2cdetect()

# Test 3: Only GPIO 27 ON
print("\n📋 TEST 3: GPIO 17 LOW, GPIO 27 HIGH (only Sensor 2)")
print("-" * 80)
GPIO.output(LPN_GPIO_17, GPIO.LOW)
GPIO.output(LPN_GPIO_27, GPIO.HIGH)
time.sleep(1)
print("Expected: One sensor at 0x29 or 0x30\n")
run_i2cdetect()

# Test 4: Both ON
print("\n📋 TEST 4: GPIO 17 HIGH, GPIO 27 HIGH (both sensors)")
print("-" * 80)
GPIO.output(LPN_GPIO_17, GPIO.HIGH)
GPIO.output(LPN_GPIO_27, GPIO.HIGH)
time.sleep(1)
print("Expected: One or two sensors (may be at same address)\n")
run_i2cdetect()

print("\n" + "=" * 80)
print("INTERPRETATION")
print("=" * 80)
print("""
If you see:
✅ TEST 1: Nothing
✅ TEST 2: One sensor
✅ TEST 3: One sensor
✅ TEST 4: Two different sensors
   → Both sensors OK! LPn control working!

If you see:
❌ TEST 2: Nothing
   → Sensor 1 not connected or broken

❌ TEST 3: Nothing
   → Sensor 2 not connected or broken

❌ TEST 2 & 3: Nothing
   → Both sensors not connected

❌ TEST 4: Only one sensor (not two)
   → Address change issue - need manual fix
""")

print("\n✅ Diagnostic complete. Both sensors remain powered ON.")
print("GPIO 17: HIGH | GPIO 27: HIGH")
print("Press Ctrl+C to exit (sensors will stay ON)")

# Keep the script running to maintain GPIO state
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nExiting... Sensors remain ON")
