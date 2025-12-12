#!/usr/bin/env python3
"""
VL53L5CX Auto-Configuration and Validation Script
Automatically configures two sensors at boot and validates the setup
"""

import time
import subprocess
import RPi.GPIO as GPIO
from smbus2 import SMBus, i2c_msg

# Configuration
I2C_BUS = 1
DEFAULT_ADDR = 0x29
NEW_ADDR = 0x39

# GPIO pins for LPn (power control)
LPn_1 = 17
LPn_2 = 27

# Setup GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(LPn_1, GPIO.OUT)
GPIO.setup(LPn_2, GPIO.OUT)

def scan_i2c_bus(bus):
    """Scan I2C bus and return list of detected addresses."""
    devices = []
    for addr in range(0x03, 0x78):
        try:
            msg = i2c_msg.write(addr, [0x00])
            bus.i2c_rdwr(msg)
            devices.append(addr)
        except Exception:
            pass
    return devices

def run_i2cdetect():
    """Run i2cdetect command and return detected addresses."""
    try:
        result = subprocess.run(['i2cdetect', '-y', '1'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        print("\n" + result.stdout)
        return result.stdout
    except Exception as e:
        print(f"   ⚠️  Could not run i2cdetect: {e}")
        return None

def check_sensor(bus, addr):
    """Check if sensor responds at given address."""
    try:
        msg = i2c_msg.write(addr, [0x00])
        bus.i2c_rdwr(msg)
        read = i2c_msg.read(addr, 1)
        bus.i2c_rdwr(read)
        return True
    except Exception:
        return False

def write_i2c_block(bus, addr, reg16, data):
    """Write data to 16-bit register address."""
    reg_hi = (reg16 >> 8) & 0xFF
    reg_lo = reg16 & 0xFF
    msg = i2c_msg.write(addr, [reg_hi, reg_lo] + data)
    bus.i2c_rdwr(msg)

def write_byte(bus, addr, reg16, value):
    """Write single byte to 16-bit register."""
    write_i2c_block(bus, addr, reg16, [value])

def change_address(bus, old_addr, new_addr):
    """Change VL53L5CX I2C address."""
    if not check_sensor(bus, old_addr):
        raise Exception(f"Sensor not responding at address 0x{old_addr:02X}")
    
    print(f"   → Unlocking address change...")
    write_byte(bus, old_addr, 0x7FFF, 0x00)
    time.sleep(0.3)
    
    print(f"   → Writing new address 0x{new_addr:02X}...")
    write_byte(bus, old_addr, 0x0004, new_addr)
    time.sleep(0.3)
    
    if not check_sensor(bus, new_addr):
        raise Exception(f"Sensor not responding at new address 0x{new_addr:02X}")
    
    print(f"   → Locking address change...")
    write_byte(bus, new_addr, 0x7FFF, 0x02)
    time.sleep(0.3)
    
    print(f"   ✓ Address changed: 0x{old_addr:02X} → 0x{new_addr:02X}")

def configure_sensors(bus):
    """Configure sensors: check addresses and change if needed."""
    print("\n" + "="*60)
    print("🔧 SENSOR CONFIGURATION")
    print("="*60)
    
    # Step 1: Power on both sensors
    print("\n[Step 1] Powering on both sensors...")
    GPIO.output(LPn_1, GPIO.HIGH)
    GPIO.output(LPn_2, GPIO.HIGH)
    time.sleep(1.0)
    
    # Step 2: Check current addresses
    print("\n[Step 2] Scanning for current addresses...")
    devices = scan_i2c_bus(bus)
    print(f"   Detected: {[hex(d) for d in devices]}")
    
    has_default = DEFAULT_ADDR in devices
    has_new = NEW_ADDR in devices
    
    # Step 3: Determine action needed
    if has_default and has_new:
        print("\n✅ Both sensors already at correct addresses!")
        print(f"   Sensor 1: 0x{NEW_ADDR:02X}")
        print(f"   Sensor 2: 0x{DEFAULT_ADDR:02X}")
        print("   → No configuration needed")
        return True
    
    elif has_default and not has_new:
        print("\n⚠️  Both sensors at same address (0x29) - need to reconfigure")
        print("\n[Step 3] Reconfiguring addresses...")
        
        # Power cycle to start fresh
        GPIO.output(LPn_1, GPIO.LOW)
        GPIO.output(LPn_2, GPIO.LOW)
        time.sleep(0.5)
        
        # Power on sensor 1 only and change its address
        print("\n[Step 4] Configuring Sensor 1 (GPIO 17) → 0x39...")
        GPIO.output(LPn_1, GPIO.HIGH)
        GPIO.output(LPn_2, GPIO.LOW)
        time.sleep(1.0)
        
        if check_sensor(bus, DEFAULT_ADDR):
            change_address(bus, DEFAULT_ADDR, NEW_ADDR)
        else:
            raise Exception("Sensor 1 not responding")
        
        # Power on sensor 2
        print("\n[Step 5] Powering on Sensor 2 (GPIO 27) → 0x29...")
        GPIO.output(LPn_2, GPIO.HIGH)
        time.sleep(1.0)
        
        if not check_sensor(bus, DEFAULT_ADDR):
            raise Exception("Sensor 2 not responding at 0x29")
        
        print("\n✅ Address configuration complete!")
        return True
    
    else:
        raise Exception(f"Unexpected sensor configuration: {[hex(d) for d in devices]}")

def run_validation_tests(bus):
    """Run comprehensive validation tests."""
    print("\n" + "="*60)
    print("🧪 VALIDATION TESTS")
    print("="*60)
    
    test_results = []
    
    # TEST 1: Turn off both sensors
    print("\n[TEST 1] Both sensors OFF")
    GPIO.output(LPn_1, GPIO.LOW)
    GPIO.output(LPn_2, GPIO.LOW)
    time.sleep(0.5)
    
    print("   i2cdetect output:")
    run_i2cdetect()
    
    devices = scan_i2c_bus(bus)
    print(f"   Result: {[hex(d) for d in devices] if devices else 'No devices'}")
    test_results.append(("Both OFF", len(devices) == 0))
    time.sleep(1)
    
    # TEST 2: GPIO 17 ON, GPIO 27 OFF
    print("\n[TEST 2] GPIO 17 ON, GPIO 27 OFF")
    GPIO.output(LPn_1, GPIO.HIGH)
    GPIO.output(LPn_2, GPIO.LOW)
    time.sleep(1.0)
    
    print("   i2cdetect output:")
    run_i2cdetect()
    
    devices = scan_i2c_bus(bus)
    sensor1_addr = devices[0] if devices else None
    print(f"   Sensor 1 address: {hex(sensor1_addr) if sensor1_addr else 'Not detected'}")
    test_results.append(("Sensor 1 only", sensor1_addr == NEW_ADDR))
    time.sleep(1)
    
    # TEST 3: GPIO 17 OFF, GPIO 27 ON
    print("\n[TEST 3] GPIO 17 OFF, GPIO 27 ON")
    GPIO.output(LPn_1, GPIO.LOW)
    GPIO.output(LPn_2, GPIO.HIGH)
    time.sleep(1.0)
    
    print("   i2cdetect output:")
    run_i2cdetect()
    
    devices = scan_i2c_bus(bus)
    sensor2_addr = devices[0] if devices else None
    print(f"   Sensor 2 address: {hex(sensor2_addr) if sensor2_addr else 'Not detected'}")
    test_results.append(("Sensor 2 only", sensor2_addr == DEFAULT_ADDR))
    time.sleep(1)
    
    # TEST 4: Both sensors ON (final check)
    print("\n[TEST 4] Both sensors ON - Final Check")
    GPIO.output(LPn_1, GPIO.HIGH)
    GPIO.output(LPn_2, GPIO.HIGH)
    time.sleep(1.0)
    
    print("   i2cdetect output:")
    run_i2cdetect()
    
    devices = scan_i2c_bus(bus)
    print(f"   Detected addresses: {[hex(d) for d in devices]}")
    
    has_both = (DEFAULT_ADDR in devices and NEW_ADDR in devices)
    are_different = len(devices) == 2
    test_results.append(("Both sensors different addresses", has_both and are_different))
    
    # Final validation
    print("\n" + "="*60)
    print("📊 TEST RESULTS SUMMARY")
    print("="*60)
    
    for test_name, passed in test_results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    print("\n" + "="*60)
    
    all_passed = all(result[1] for result in test_results)
    
    if all_passed and has_both and are_different:
        print("🎉 FINAL RESULT: VALID")
        print("="*60)
        print(f"   ✅ Sensor 1 (GPIO {LPn_1}): 0x{NEW_ADDR:02X}")
        print(f"   ✅ Sensor 2 (GPIO {LPn_2}): 0x{DEFAULT_ADDR:02X}")
        print("   ✅ Both sensors operational with different addresses")
        print("="*60 + "\n")
        return True
    else:
        print("❌ FINAL RESULT: FALSE")
        print("="*60)
        print("   Configuration failed - sensors not properly configured")
        print("="*60 + "\n")
        return False

def main():
    """Main execution function."""
    bus = SMBus(I2C_BUS)
    
    try:
        print("\n" + "="*60)
        print("🚀 VL53L5CX Auto-Configuration & Validation")
        print("="*60)
        print(f"   I2C Bus: {I2C_BUS}")
        print(f"   Target Addresses: 0x{DEFAULT_ADDR:02X}, 0x{NEW_ADDR:02X}")
        print(f"   GPIO Pins: {LPn_1}, {LPn_2}")
        print("="*60)
        
        # Phase 1: Configure sensors
        config_success = configure_sensors(bus)
        
        if not config_success:
            print("\n❌ Configuration failed!")
            return False
        
        # Phase 2: Run validation tests
        validation_success = run_validation_tests(bus)
        
        return validation_success
    
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Always leave sensors powered on
        GPIO.output(LPn_1, GPIO.HIGH)
        GPIO.output(LPn_2, GPIO.HIGH)
        bus.close()

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
