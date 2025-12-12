import time
import RPi.GPIO as GPIO
from smbus2 import SMBus, i2c_msg

I2C_BUS = 1
DEFAULT_ADDR = 0x29
NEW_ADDR_1 = 0x39  # ← FIXED: Change sensor 1 to 0x39
# NEW_ADDR_2 = 0x29  # Not needed - sensor 2 stays at default

LPn_1 = 17
LPn_2 = 27

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(LPn_1, GPIO.OUT)
GPIO.setup(LPn_2, GPIO.OUT)

def power_off_sensors():
    GPIO.output(LPn_1, GPIO.LOW)
    GPIO.output(LPn_2, GPIO.LOW)
    time.sleep(0.2)

def power_on_sensor(lp_pin):
    GPIO.output(lp_pin, GPIO.HIGH)
    time.sleep(1.0)

def check_sensor(bus, addr):
    try:
        msg = i2c_msg.write(addr, [0x00])
        bus.i2c_rdwr(msg)
        read = i2c_msg.read(addr, 1)
        bus.i2c_rdwr(read)
        return True
    except Exception:
        return False

def write_i2c_block(bus, addr, reg16, data):
    reg_hi = (reg16 >> 8) & 0xFF
    reg_lo = reg16 & 0xFF
    msg = i2c_msg.write(addr, [reg_hi, reg_lo] + data)
    bus.i2c_rdwr(msg)

def write_byte(bus, addr, reg16, value):
    write_i2c_block(bus, addr, reg16, [value])

def change_address(bus, old_addr, new_addr):
    if not check_sensor(bus, old_addr):
        raise Exception(f"Sensor not responding at address 0x{old_addr:02X}")

    print(f"Unlocking address change on 0x{old_addr:02X}")
    write_byte(bus, old_addr, 0x7FFF, 0x00)
    time.sleep(0.3)

    print(f"Writing new I2C address 0x{new_addr:02X} to sensor at 0x{old_addr:02X}")
    write_byte(bus, old_addr, 0x0004, new_addr)
    time.sleep(0.3)

    if not check_sensor(bus, new_addr):
        raise Exception(f"Sensor not responding at new address 0x{new_addr:02X}")

    print(f"Locking address change on 0x{new_addr:02X}")
    write_byte(bus, new_addr, 0x7FFF, 0x02)
    time.sleep(0.3)

    print(f"Address changed successfully from 0x{old_addr:02X} to 0x{new_addr:02X}")

def main():
    bus = SMBus(I2C_BUS)
    try:
        # Start with both sensors off
        power_off_sensors()

        # Power on ONLY sensor 1 and change its address to 0x39
        print("\n=== Configuring Sensor 1 (GPIO 17) ===")
        power_on_sensor(LPn_1)
        GPIO.output(LPn_2, GPIO.LOW)  # Keep sensor 2 OFF
        change_address(bus, DEFAULT_ADDR, NEW_ADDR_1)
        # DO NOT power off sensor 1!

        # Now power on sensor 2 (stays at 0x29)
        print("\n=== Powering on Sensor 2 (GPIO 27) ===")
        GPIO.output(LPn_2, GPIO.HIGH)
        time.sleep(1.0)

        print("\n✅ Both sensors initialized:")
        print(f"   Sensor 1 (GPIO 17): 0x{NEW_ADDR_1:02X}")
        print(f"   Sensor 2 (GPIO 27): 0x{DEFAULT_ADDR:02X}")
        print("\n⚠️  IMPORTANT: Sensors must remain powered!")
        print("   Do NOT run this script again while sensors are in use.")

    except Exception as e:
        print(f"❌ Error: {e}")
        # Only cleanup on error
        GPIO.cleanup()

    finally:
        bus.close()
        # DO NOT call GPIO.cleanup() here!
        # Sensors must stay powered to keep addresses

if __name__ == "__main__":
    main()
