#!/usr/bin/env python3
"""
VL53L5CX Simple Live Output
Prints one line per reading with timestamp and zones 5,6,9,10
"""

import time
from vl53l5cx_ctypes import VL53L5CX

def main():
    print("Initializing VL53L5CX sensor...")
    
    try:
        sensor = VL53L5CX()
        sensor.set_resolution(4 * 4)
        sensor.set_ranging_frequency_hz(15)  # 15 readings per second
        print("Sensor initialized\n")
    except RuntimeError as e:
        print(f"Failed: {e}")
        return
    
    sensor.start_ranging()
    time.sleep(2.0)
    
    print("Time     | Zone 5 (mm) | Zone 6 (mm) | Zone 9 (mm) | Zone 10 (mm)")
    print("-" * 70)
    
    try:
        while True:
            if sensor.data_ready():
                data = sensor.get_data()
                
                # Get timestamp
                timestamp = time.strftime("%H:%M:%S")
                
                # Read zones 5, 6, 9, 10
                z5 = int(data.distance_mm[0][5])
                z6 = int(data.distance_mm[0][6])
                z9 = int(data.distance_mm[0][9])
                z10 = int(data.distance_mm[0][10])
                
                # Print line
                print(f"{timestamp} | {z5:11d} | {z6:11d} | {z9:11d} | {z10:12d}")
            
            time.sleep(0.01)  # Small delay to not overwhelm output
            
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        sensor.stop_ranging()

if __name__ == "__main__":
    main()
