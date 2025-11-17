#!/usr/bin/env python3
"""
VL53L5CX All Zones Live Output
Prints one line per reading with timestamp and all 16 zones (0-15)
"""

import time
from vl53l5cx_ctypes import VL53L5CX

def main():
    print("Initializing VL53L5CX sensor...")
    
    try:
        sensor = VL53L5CX()
        sensor.set_resolution(4 * 4)  # 4x4 mode = 16 zones
        sensor.set_ranging_frequency_hz(15)  # 15 readings per second
        print("Sensor initialized\n")
    except RuntimeError as e:
        print(f"Failed: {e}")
        return
    
    sensor.start_ranging()
    time.sleep(2.0)
    
    print("Zone layout (4x4 grid):")
    print("┌─────┬─────┬─────┬─────┐")
    print("│  0  │  1  │  2  │  3  │")
    print("├─────┼─────┼─────┼─────┤")
    print("│  4  │  5  │  6  │  7  │")
    print("├─────┼─────┼─────┼─────┤")
    print("│  8  │  9  │ 10  │ 11  │")
    print("├─────┼─────┼─────┼─────┤")
    print("│ 12  │ 13  │ 14  │ 15  │")
    print("└─────┴─────┴─────┴─────┘\n")
    
    print("Time     | All 16 Zones (mm) - Row format: [0,1,2,3] [4,5,6,7] [8,9,10,11] [12,13,14,15]")
    print("-" * 120)
    
    try:
        while True:
            if sensor.data_ready():
                data = sensor.get_data()
                
                # Get timestamp
                timestamp = time.strftime("%H:%M:%S")
                
                # Read all 16 zones
                zones = []
                for i in range(16):
                    try:
                        zone_value = int(data.distance_mm[0][i])
                        zones.append(zone_value)
                    except:
                        zones.append(0)  # Default to 0 if reading fails
                
                # Format as grouped rows for better readability
                row1 = f"[{zones[0]:4d},{zones[1]:4d},{zones[2]:4d},{zones[3]:4d}]"
                row2 = f"[{zones[4]:4d},{zones[5]:4d},{zones[6]:4d},{zones[7]:4d}]"
                row3 = f"[{zones[8]:4d},{zones[9]:4d},{zones[10]:4d},{zones[11]:4d}]"
                row4 = f"[{zones[12]:4d},{zones[13]:4d},{zones[14]:4d},{zones[15]:4d}]"
                
                # Print single line with all zones grouped by rows
                print(f"{timestamp} | {row1} {row2} {row3} {row4}")
            
            time.sleep(0.01)  # Small delay to not overwhelm output
            
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        sensor.stop_ranging()

if __name__ == "__main__":
    main()
