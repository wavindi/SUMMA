#!/usr/bin/env python3
"""
VL53L5CX Master Setup Script
- Verifies sensor connectivity
- Detects number of sensors
- Auto-configures addresses if needed
- Validates final setup
"""

import time
import sys
import subprocess
import RPi.GPIO as GPIO
from smbus2 import SMBus, i2c_msg

# ============================================================================
# CONFIGURATION
# ============================================================================
I2C_BUS = 1
DEFAULT_ADDR = 0x29
NEW_ADDR = 0x39

# GPIO pins for LPn (power control)
LPn_1 = 17
LPn_2 = 27

# ============================================================================
# GPIO SETUP
# ============================================================================
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(LPn_1, GPIO.OUT)
GPIO.setup(LPn_2, GPIO.OUT)

# ============================================================================
# I2C UTILITY FUNCTIONS
# ============================================================================
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
    """Run i2cdetect command for visual bus inspection."""
    try:
        result = subprocess.run(['i2cdetect', '-y', '1'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        print(result.stdout)
    except Exception as e:
        print(f"   ⚠️  Could not run i2cdetect: {e}")

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

# ============================================================================
# PHASE 1: INITIAL VERIFICATION
# ============================================================================
def phase1_initial_verification(bus):
    """Verify I2C bus and detect how many sensors are present."""
    print("\n" + "="*70)
    print("🔍 PHASE 1: INITIAL SENSOR VERIFICATION")
    print("="*70)
    
    # Check I2C bus
    print("\n[Step 1] Checking I2C bus availability...")
    try:
        test_scan = scan_i2c_bus(bus)
        print("   ✅ I2C bus accessible")
    except Exception as e:
        print(f"   ❌ I2C bus not working: {e}")
        print("\n   Fix: Check /boot/config.txt:")
        print("   dtparam=i2c_arm=on")
        print("   dtparam=i2c_baudrate=100000")
        return None
    
    # Power on both sensors to detect them
    print("\n[Step 2] Powering on all sensors...")
    GPIO.output(LPn_1, GPIO.HIGH)
    GPIO.output(LPn_2, GPIO.HIGH)
    time.sleep(1.5)
    
    # Scan for sensors
    print("\n[Step 3] Scanning I2C bus...")
    print("   i2cdetect output:")
    run_i2cdetect()
    
    devices = scan_i2c_bus(bus)
    sensor_count = len([d for d in devices if d in [DEFAULT_ADDR, NEW_ADDR]])
    
    print(f"\n   Detected addresses: {[hex(d) for d in devices]}")
    print(f"   VL53L5CX sensors found: {sensor_count}")
    
    # Analyze sensor configuration
    has_default = DEFAULT_ADDR in devices
    has_new = NEW_ADDR in devices
    
    if sensor_count == 0:
        print("\n   ❌ No sensors detected!")
        print("   Check wiring:")
        print("      - SDA → Pi GPIO 2")
        print("      - SCL → Pi GPIO 3")
        print("      - VCC → Pi 3.3V (NOT 5V!)")
        print("      - GND → Pi GND")
        return None
    
    elif sensor_count == 1:
        addr = DEFAULT_ADDR if has_default else NEW_ADDR
        print(f"\n   ℹ️  Only 1 sensor detected at 0x{addr:02X}")
        return {'count': 1, 'address': addr}
    
    elif sensor_count == 2:
        if has_default and has_new:
            print(f"\n   ✅ 2 sensors at different addresses: 0x{DEFAULT_ADDR:02X}, 0x{NEW_ADDR:02X}")
            return {'count': 2, 'configured': True}
        elif has_default and not has_new:
            print(f"\n   ⚠️  2 sensors both at 0x{DEFAULT_ADDR:02X} - need address change")
            return {'count': 2, 'configured': False}
        else:
            print(f"\n   ⚠️  Unexpected configuration: {[hex(d) for d in devices]}")
            return None
    
    else:
        print(f"\n   ⚠️  Unexpected number of sensors: {sensor_count}")
        return None

# ============================================================================
# PHASE 1B: SINGLE SENSOR DISPLAY
# ============================================================================
def phase1b_single_sensor_display(sensor_info):
    """Display information when only 1 sensor is detected."""
    print("\n" + "="*70)
    print("ℹ️  PHASE 1B: SINGLE SENSOR DETECTED")
    print("="*70)
    
    addr = sensor_info['address']
    
    print(f"\n   Sensor detected at address: 0x{addr:02X}")
    print(f"   Total sensors found: 1")
    print("\n   System status: Single sensor mode")
    
    # Determine which GPIO it's connected to
    if addr == NEW_ADDR:
        print(f"   Connected to: GPIO {LPn_1} (Sensor 1)")
    else:
        print(f"   Connected to: GPIO {LPn_1} or {LPn_2}")
    
    print("\n" + "="*70)
    print("   Note: This system is designed for 2 sensors.")
    print("   Currently operating with 1 sensor only.")
    print("="*70 + "\n")

# ============================================================================
# PHASE 2: ADDRESS CONFIGURATION
# ============================================================================
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
    
    print(f"   ✅ Address changed: 0x{old_addr:02X} → 0x{new_addr:02X}")

def phase2_configure_addresses(bus):
    """Configure sensors to different addresses."""
    print("\n" + "="*70)
    print("🔧 PHASE 2: ADDRESS CONFIGURATION")
    print("="*70)
    
    try:
        # Power cycle to start fresh
        print("\n[Step 1] Power cycling sensors...")
        GPIO.output(LPn_1, GPIO.LOW)
        GPIO.output(LPn_2, GPIO.LOW)
        time.sleep(0.5)
        
        # Power on sensor 1 only and change its address
        print("\n[Step 2] Configuring Sensor 1 (GPIO 17) → 0x39...")
        GPIO.output(LPn_1, GPIO.HIGH)
        GPIO.output(LPn_2, GPIO.LOW)
        time.sleep(1.2)
        
        if not check_sensor(bus, DEFAULT_ADDR):
            raise Exception("Sensor 1 not responding at 0x29")
        
        change_address(bus, DEFAULT_ADDR, NEW_ADDR)
        
        # Power on sensor 2
        print("\n[Step 3] Powering on Sensor 2 (GPIO 27) → 0x29...")
        GPIO.output(LPn_2, GPIO.HIGH)
        time.sleep(1.2)
        
        if not check_sensor(bus, DEFAULT_ADDR):
            raise Exception("Sensor 2 not responding at 0x29")
        
        print("\n   ✅ Address configuration complete!")
        print(f"      Sensor 1 (GPIO {LPn_1}): 0x{NEW_ADDR:02X}")
        print(f"      Sensor 2 (GPIO {LPn_2}): 0x{DEFAULT_ADDR:02X}")
        
        return True
        
    except Exception as e:
        print(f"\n   ❌ Configuration failed: {e}")
        return False

# ============================================================================
# PHASE 3: FINAL VALIDATION
# ============================================================================
def phase3_final_validation(bus):
    """Validate final sensor setup with individual tests."""
    print("\n" + "="*70)
    print("✅ PHASE 3: FINAL VALIDATION")
    print("="*70)
    
    test_results = []
    
    # Test 1: Both OFF
    print("\n[Test 1] Both sensors OFF...")
    GPIO.output(LPn_1, GPIO.LOW)
    GPIO.output(LPn_2, GPIO.LOW)
    time.sleep(0.5)
    
    devices = scan_i2c_bus(bus)
    sensor_devices = [d for d in devices if d in [DEFAULT_ADDR, NEW_ADDR]]
    no_sensors = len(sensor_devices) == 0
    print(f"   Result: {[hex(d) for d in sensor_devices] if sensor_devices else 'No sensors'}")
    print(f"   {'✅ PASS' if no_sensors else '❌ FAIL'}")
    test_results.append(("Both OFF", no_sensors))
    time.sleep(0.5)
    
    # Test 2: Sensor 1 ON only (should be 0x39)
    print("\n[Test 2] Sensor 1 ON (GPIO 17) only...")
    GPIO.output(LPn_1, GPIO.HIGH)
    GPIO.output(LPn_2, GPIO.LOW)
    time.sleep(1.0)
    
    devices = scan_i2c_bus(bus)
    sensor1_correct = NEW_ADDR in devices and DEFAULT_ADDR not in devices
    print(f"   Detected: {[hex(d) for d in devices if d in [DEFAULT_ADDR, NEW_ADDR]]}")
    print(f"   Expected: [0x{NEW_ADDR:02X}]")
    print(f"   {'✅ PASS' if sensor1_correct else '❌ FAIL'}")
    test_results.append(("Sensor 1 at 0x39", sensor1_correct))
    time.sleep(0.5)
    
    # Test 3: Sensor 2 ON only (should be 0x29)
    print("\n[Test 3] Sensor 2 ON (GPIO 27) only...")
    GPIO.output(LPn_1, GPIO.LOW)
    GPIO.output(LPn_2, GPIO.HIGH)
    time.sleep(1.0)
    
    devices = scan_i2c_bus(bus)
    sensor2_correct = DEFAULT_ADDR in devices and NEW_ADDR not in devices
    print(f"   Detected: {[hex(d) for d in devices if d in [DEFAULT_ADDR, NEW_ADDR]]}")
    print(f"   Expected: [0x{DEFAULT_ADDR:02X}]")
    print(f"   {'✅ PASS' if sensor2_correct else '❌ FAIL'}")
    test_results.append(("Sensor 2 at 0x29", sensor2_correct))
    time.sleep(0.5)
    
    # Test 4: Both ON (final check)
    print("\n[Test 4] Both sensors ON...")
    GPIO.output(LPn_1, GPIO.HIGH)
    GPIO.output(LPn_2, GPIO.HIGH)
    time.sleep(1.0)
    
    print("   i2cdetect output:")
    run_i2cdetect()
    
    devices = scan_i2c_bus(bus)
    both_present = DEFAULT_ADDR in devices and NEW_ADDR in devices
    print(f"   Detected: {[hex(d) for d in devices if d in [DEFAULT_ADDR, NEW_ADDR]]}")
    print(f"   Expected: [0x{DEFAULT_ADDR:02X}, 0x{NEW_ADDR:02X}]")
    print(f"   {'✅ PASS' if both_present else '❌ FAIL'}")
    test_results.append(("Both sensors different addresses", both_present))
    
    # Summary
    print("\n" + "="*70)
    print("📊 VALIDATION SUMMARY")
    print("="*70)
    
    for test_name, passed in test_results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name:.<50} {status}")
    
    all_passed = all(result[1] for result in test_results)
    
    print("\n" + "="*70)
    if all_passed:
        print("🎉 VALIDATION RESULT: ✅ SUCCESS")
        print("="*70)
        print(f"   Sensor 1 (GPIO {LPn_1}): 0x{NEW_ADDR:02X}")
        print(f"   Sensor 2 (GPIO {LPn_2}): 0x{DEFAULT_ADDR:02X}")
        print("   System ready for padel scoreboard!")
    else:
        print("❌ VALIDATION RESULT: ❌ FAILED")
        print("="*70)
        print("   Some tests failed - check wiring and connections")
    print("="*70 + "\n")
    
    return all_passed

# ============================================================================
# MAIN EXECUTION
# ============================================================================
def main():
    """Main execution flow."""
    bus = SMBus(I2C_BUS)
    
    try:
        print("\n" + "="*70)
        print("🚀 VL53L5CX MASTER SENSOR SETUP")
        print("="*70)
        print(f"   I2C Bus: {I2C_BUS}")
        print(f"   Target Addresses: 0x{DEFAULT_ADDR:02X}, 0x{NEW_ADDR:02X}")
        print(f"   GPIO Control Pins: {LPn_1}, {LPn_2}")
        print("="*70)
        
        # PHASE 1: Initial verification
        verification_result = phase1_initial_verification(bus)
        
        if verification_result is None:
            print("\n❌ ABORTED: Initial verification failed")
            return False
        
        # PHASE 1B: Handle single sensor case (just display, don't fail)
        if verification_result['count'] == 1:
            phase1b_single_sensor_display(verification_result)
            return True  # Exit cleanly with success code
        
        # Handle dual sensor case
        if verification_result['count'] == 2:
            # Already configured correctly
            if verification_result.get('configured'):
                print("\n" + "="*70)
                print("✅ SENSORS ALREADY CONFIGURED")
                print("="*70)
                print(f"   Sensor 1: 0x{NEW_ADDR:02X}")
                print(f"   Sensor 2: 0x{DEFAULT_ADDR:02X}")
                print("   Skipping address configuration...")
                print("="*70)
                
                # Go straight to validation
                return phase3_final_validation(bus)
            
            # Need to configure addresses
            else:
                # PHASE 2: Configure addresses
                config_success = phase2_configure_addresses(bus)
                
                if not config_success:
                    print("\n❌ ABORTED: Address configuration failed")
                    return False
                
                # PHASE 3: Final validation
                return phase3_final_validation(bus)
        
        return False
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Always leave sensors powered on for operation
        GPIO.output(LPn_1, GPIO.HIGH)
        GPIO.output(LPn_2, GPIO.HIGH)
        bus.close()
        print("   Sensors remain powered for operation\n")

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
