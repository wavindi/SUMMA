#!/usr/bin/env python3
"""
VL53L5CX Dual Sensor - RAW VALUES ONLY
Displays raw distance values (no filtering, no baseline subtraction)
"""

import time
from vl53l5cx_ctypes import VL53L5CX

# Sensor addresses
SENSOR1_ADDRESS = 0x29
SENSOR2_ADDRESS = 0x39

def initialize_sensors():
    """Initialize both sensors"""
    print("Initializing sensors...\n")
    
    try:
        print(f"[1] Sensor 1 at 0x{SENSOR1_ADDRESS:02x}...")
        sensor1 = VL53L5CX(i2c_addr=SENSOR1_ADDRESS)
        sensor1.set_resolution(4 * 4)
        sensor1.set_ranging_frequency_hz(15)
        print(f"    ✓ Sensor 1 initialized")
    except Exception as e:
        print(f"    ✗ Sensor 1 failed: {e}")
        return None, None
    
    try:
        print(f"[2] Sensor 2 at 0x{SENSOR2_ADDRESS:02x}...")
        sensor2 = VL53L5CX(i2c_addr=SENSOR2_ADDRESS)
        sensor2.set_resolution(4 * 4)
        sensor2.set_ranging_frequency_hz(15)
        print(f"    ✓ Sensor 2 initialized")
    except Exception as e:
        print(f"    ✗ Sensor 2 failed: {e}")
        try:
            sensor1.stop_ranging()
        except:
            pass
        return None, None
    
    return sensor1, sensor2

def start_sensors_with_warmup(sensor1, sensor2):
    """Start both sensors with extended warmup time"""
    print("\n[3] Starting sensors with firmware upload...")
    try:
        sensor1.start_ranging()
        print("    Sensor 1: Starting ranging...")
        
        sensor2.start_ranging()
        print("    Sensor 2: Starting ranging...")
        
        print("    Waiting for sensors to stabilize (15 seconds)...")
        for i in range(15):
            time.sleep(1)
            print(f"    {i+1}/15 seconds...")
        
        print("    ✓ Sensors ready")
        return True
    except Exception as e:
        print(f"    ✗ Failed to start: {e}")
        return False

def main():
    filename = time.strftime("gen5_%Y_%m_%d_wa9t_%H_%M_%S.txt")
    start_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"Log file: {filename}\n")
    
    print("="*70)
    print("VL53L5CX RAW VALUES - ALL 16 ZONES")
    print("="*70)
    
    sensor1, sensor2 = initialize_sensors()
    
    if sensor1 is None or sensor2 is None:
        print("\n✗ Sensor initialization failed")
        return
    
    if not start_sensors_with_warmup(sensor1, sensor2):
        print("\n✗ Failed to start sensors")
        return
    
    print("\n" + "="*70)
    print("READING RAW VALUES")
    print("="*70 + "\n")
    
    # Create header
    header = "Time     | "
    for zone in range(16):
        header += f"Z{zone:2d}(S1/S2) | "
    
    with open(filename, "w") as log_file:
        log_file.write(f"Raw VL53L5CX Dual Sensor Values - {start_time_str}\n")
        log_file.write(f"Sensor 1: 0x{SENSOR1_ADDRESS:02x}, Sensor 2: 0x{SENSOR2_ADDRESS:02x}\n")
        log_file.write(f"Raw distance values in mm (no filtering, no baseline subtraction)\n\n")
        log_file.write(header + "\n")
        log_file.write("-" * len(header) + "\n")
        log_file.flush()
        
        print(header)
        print("-" * len(header))
        
        try:
            while True:
                timestamp = time.strftime("%H:%M:%S")
                
                s1_data = [0] * 16
                s2_data = [0] * 16
                
                # Read Sensor 1 - RAW VALUES
                if sensor1.data_ready():
                    try:
                        data1 = sensor1.get_data()
                        for zone in range(16):
                            try:
                                raw_dist = int(data1.distance_mm[0][zone])
                                s1_data[zone] = raw_dist
                            except:
                                s1_data[zone] = 0
                    except Exception as e:
                        pass
                
                # Read Sensor 2 - RAW VALUES
                if sensor2.data_ready():
                    try:
                        data2 = sensor2.get_data()
                        for zone in range(16):
                            try:
                                raw_dist = int(data2.distance_mm[0][zone])
                                s2_data[zone] = raw_dist
                            except:
                                s2_data[zone] = 0
                    except Exception as e:
                        pass
                
                # Build output line
                line = f"{timestamp} | "
                for zone in range(16):
                    line += f"{s1_data[zone]:4d}/{s2_data[zone]:4d} | "
                
                print(line)
                log_file.write(line + "\n")
                log_file.flush()
                
                time.sleep(0.1)
        
        except KeyboardInterrupt:
            print("\n\n✓ Stopped by user")
            log_file.write("\n\nStopped by user.\n")
        
        finally:
            sensor1.stop_ranging()
            sensor2.stop_ranging()
            print("Sensors stopped.")

if __name__ == "__main__":
    main()
