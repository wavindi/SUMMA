import time
import RPi.GPIO as GPIO
import subprocess
from smbus2 import SMBus, i2c_msg

# GPIO pins controlling LPn (power enable) of sensors
LPn_1 = 17
LPn_2 = 27

# I2C bus number on Raspberry Pi
I2C_BUS = 1

# New desired I2C address for first sensor
NEW_ADDR_1 = 0x39  # In 7-bit format; must be between 0x03 and 0x77

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(LPn_1, GPIO.OUT)
GPIO.setup(LPn_2, GPIO.OUT)

def power_off_all():
    GPIO.output(LPn_1, GPIO.LOW)
    GPIO.output(LPn_2, GPIO.LOW)
    time.sleep(0.2)

def power_on_sensor(lp_pin):
    GPIO.output(lp_pin, GPIO.HIGH)
    time.sleep(1.0)  # Wait for sensor boot

def scan_i2c():
    """Scan I2C bus for device addresses"""
    result = subprocess.run(['i2cdetect', '-y', str(I2C_BUS)], capture_output=True, text=True)
    lines = result.stdout.strip().split('\n')[1:]
    addresses = []
    for line in lines:
        parts = line.split()[1:]
        for part in parts:
            if part != '--':
                try:
                    addresses.append(int(part, 16))
                except ValueError:
                    continue
    return addresses

def write_i2c_block(bus, addr, reg16, data):
    reg_hi = (reg16 >> 8) & 0xFF
    reg_lo = reg16 & 0xFF
    msg = i2c_msg.write(addr, [reg_hi, reg_lo] + data)
    bus.i2c_rdwr(msg)

def write_byte(bus, addr, reg16, value):
    write_i2c_block(bus, addr, reg16, [value])

def check_sensor(bus, addr):
    try:
        # Read any register (0x00) to check presence
        write_i2c_block(bus, addr, 0x0000, [])
        return True
    except Exception:
        return False

def change_address(bus, old_addr, new_addr):
    if not check_sensor(bus, old_addr):
        raise Exception(f"Sensor not found at address 0x{old_addr:02X}")

    print(f"Unlocking address change on sensor at 0x{old_addr:02X}...")
    write_byte(bus, old_addr, 0x7FFF, 0x00)
    time.sleep(0.3)

    print(f"Writing new address 0x{new_addr:02X}...")
    write_byte(bus, old_addr, 0x0004, new_addr)
    time.sleep(0.3)

    if not check_sensor(bus, new_addr):
        raise Exception(f"Sensor not responding at new address 0x{new_addr:02X}")

    print(f"Locking address change on sensor at 0x{new_addr:02X}...")
    write_byte(bus, new_addr, 0x7FFF, 0x02)
    time.sleep(0.3)

    print(f"Successfully changed address from 0x{old_addr:02X} to 0x{new_addr:02X}.")

def main():
    bus = SMBus(I2C_BUS)
    try:
        power_off_all()

        # Power on only first sensor to detect current address(es)
        power_on_sensor(LPn_1)
        detected_addrs = scan_i2c()
        print(f"Detected addresses with sensor 1 powered: {[hex(a) for a in detected_addrs]}")

        # Assume default address 0x29 if found, else use first detected
        old_addr = 0x29 if 0x29 in detected_addrs else (detected_addrs[0] if detected_addrs else None)
        if old_addr is None:
            raise Exception("No sensor detected at default address or any address")

        # Change first sensor I2C address
        change_address(bus, old_addr, NEW_ADDR_1)
        GPIO.output(LPn_1, GPIO.LOW)
        time.sleep(0.3)

        print("Done.")

    finally:
        bus.close()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
