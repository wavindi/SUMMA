#!/usr/bin/env python3
"""
VL53L5CX with Calibration
Calibrates each zone with 60 readings, then shows difference from baseline
"""

import time
from vl53l5cx_ctypes import VL53L5CX

def main():
    print("=" * 80)
    print("VL53L5CX CALIBRATION & MONITORING")
    print("=" * 80)
    print("\nInitializing VL53L5CX sensor...")
    
    try:
        sensor = VL53L5CX()
        sensor.set_resolution(4 * 4)
        sensor.set_ranging_frequency_hz(15)  # 15 readings per second
        print("✅ Sensor initialized\n")
    except RuntimeError as e:
        print(f"❌ Failed: {e}")
        return
    
    sensor.start_ranging()
    time.sleep(2.0)
    
    # ==================== CALIBRATION PHASE ====================
    print("=" * 80)
    print("CALIBRATION PHASE - Collecting 60 baseline readings")
    print("⚠️  Keep area clear of objects during calibration!")
    print("=" * 80)
    
    # Store calibration samples for each zone
    calibration_samples = {
        5: [],
        6: [],
        9: [],
        10: []
    }
    
    readings_collected = 0
    target_readings = 60
    
    # Collect 60 readings
    while readings_collected < target_readings:
        if sensor.data_ready():
            data = sensor.get_data()
            
            # Collect distance for each zone
            try:
                calibration_samples[5].append(int(data.distance_mm[0][5]))
                calibration_samples[6].append(int(data.distance_mm[0][6]))
                calibration_samples[9].append(int(data.distance_mm[0][9]))
                calibration_samples[10].append(int(data.distance_mm[0][10]))
                
                readings_collected += 1
                
                # Show progress
                if readings_collected % 10 == 0:
                    print(f"Progress: {readings_collected}/{target_readings} readings collected...")
            
            except Exception as e:
                print(f"Error reading data: {e}")
                continue
        
        time.sleep(0.01)
    
    # Calculate baseline averages for each zone
    baselines = {}
    for zone in [5, 6, 9, 10]:
        if len(calibration_samples[zone]) > 0:
            baselines[zone] = sum(calibration_samples[zone]) / len(calibration_samples[zone])
        else:
            baselines[zone] = 0
    
    print("\n" + "=" * 80)
    print("CALIBRATION COMPLETE - Baselines established:")
    print("=" * 80)
    print(f"Zone 5:  {baselines[5]:7.1f} mm")
    print(f"Zone 6:  {baselines[6]:7.1f} mm")
    print(f"Zone 9:  {baselines[9]:7.1f} mm")
    print(f"Zone 10: {baselines[10]:7.1f} mm")
    print("=" * 80)
    print("\nNow monitoring DIFFERENCES from baseline...")
    print("Negative values = Object closer than baseline")
    print("Positive values = Object farther than baseline")
    print("=" * 80 + "\n")
    
    # Wait a moment before starting monitoring
    time.sleep(1.0)
    
    # ==================== MONITORING PHASE ====================
    print("Time     | Z5 Diff (mm) | Z6 Diff (mm) | Z9 Diff (mm) | Z10 Diff (mm) | Avg Diff")
    print("-" * 90)
    
    try:
        while True:
            if sensor.data_ready():
                data = sensor.get_data()
                
                # Get timestamp
                timestamp = time.strftime("%H:%M:%S")
                
                # Read current distances
                z5 = int(data.distance_mm[0][5])
                z6 = int(data.distance_mm[0][6])
                z9 = int(data.distance_mm[0][9])
                z10 = int(data.distance_mm[0][10])
                
                # Calculate differences from baseline
                diff_z5 = z5 - baselines[5]
                diff_z6 = z6 - baselines[6]
                diff_z9 = z9 - baselines[9]
                diff_z10 = z10 - baselines[10]
                
                # Calculate average difference
                avg_diff = (diff_z5 + diff_z6 + diff_z9 + diff_z10) / 4
                
                # Print line with differences (use + to show sign explicitly)
                print(f"{timestamp} | {diff_z5:+12.0f} | {diff_z6:+12.0f} | "
                      f"{diff_z9:+12.0f} | {diff_z10:+13.0f} | {avg_diff:+8.1f}")
            
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Monitoring stopped")
    finally:
        sensor.stop_ranging()
        print("✅ Sensor stopped\n")

if __name__ == "__main__":
    main()
