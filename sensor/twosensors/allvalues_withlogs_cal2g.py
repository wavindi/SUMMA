#!/usr/bin/env python3
"""
VL53L5CX Object Detection behind 12mm Glass
Calibrates glass baseline, logs glass thickness, and reads corrected distance
"""

import time
import collections
import statistics
from vl53l5cx_ctypes import VL53L5CX

# Parameters
CALIBRATION_SAMPLES = 60
MEDIAN_WINDOW = 5
MOVING_AVG_WINDOW = 3
OUTLIER_THRESHOLD = 200  # Max jump in mm to reject

def median_filter(window, new_value):
    window.append(new_value)
    if len(window) < window.maxlen:
        return new_value
    return statistics.median(window)

def moving_average(window, new_value):
    window.append(new_value)
    return sum(window) / len(window)

def main():
    print("Initializing VL53L5CX sensor...")
    try:
        sensor = VL53L5CX()
        sensor.set_resolution(4 * 4)
        sensor.set_ranging_frequency_hz(15)
        print("Sensor initialized\n")
    except RuntimeError as e:
        print(f"Initialization failed: {e}")
        return
    
    sensor.start_ranging()
    time.sleep(2.0)
    
    filename = time.strftime("gen3_%Y_%m_%d_wa9t_%H_%M_%S.txt")
    start_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"Logging to file: {filename}")
    
    header = "Time     | Zone 5  | Zone 6  | Zone 9  | Zone 10 | Avg Dist |"
    
    with open(filename, "w") as log_file:
        # Write intro info
        log_file.write(f"Using VL53L5CX, calibration at {start_time_str}\n")
        log_file.write("Glass thickness baseline values logged. Measurement after calibration includes object detection at 10cm behind glass.\n\n")
        log_file.write(header + "\n")
        log_file.write("-" * len(header) + "\n")
        
        print(header)
        print("-" * len(header))
        
        # Calibration: Collect baseline with only glass, no object behind
        baseline_samples = {zone: [] for zone in [5,6,9,10]}
        collected = 0
        
        while collected < CALIBRATION_SAMPLES:
            if sensor.data_ready():
                data = sensor.get_data()
                timestamp = time.strftime("%H:%M:%S.%f")[:-3]
                
                # Collect valid zone distances >10 mm (ignore invalid/noisy)
                valid = True
                for zone in baseline_samples:
                    try:
                        dist = int(data.distance_mm[0][zone])
                        if dist < 10 or dist > 4000:
                            valid = False
                            break
                        baseline_samples[zone].append(dist)
                    except:
                        valid = False
                        break
                
                if valid:
                    collected += 1
                    # Log calibration line (optional)
                    line = f"{timestamp} | " + " | ".join(f"{baseline_samples[z][-1]:7d}" for z in baseline_samples) + " |"
                    log_file.write(line + "\n")
                
            time.sleep(0.02)
        
        # Calculate baseline median per zone (glass thickness effect)
        baseline = {z: int(statistics.median(baseline_samples[z])) for z in baseline_samples}
        avg_baseline = sum(baseline.values()) / len(baseline)
        
        # Log baseline summary (glass thickness baseline)
        log_file.write("\nCalibration baseline (glass thickness approx in mm):\n")
        bl_line = "Baseline | " + " | ".join(f"{baseline[z]:7d}" for z in baseline) + f" | Avg: {avg_baseline:.1f} mm\n\n"
        log_file.write(bl_line)
        log_file.flush()
        print("\nCalibration baseline distances (glass thickness approx):")
        print(bl_line)
        
        # Prepare filters
        median_windows = {z: collections.deque(maxlen=MEDIAN_WINDOW) for z in baseline_samples}
        moving_avg_windows = {z: collections.deque(maxlen=MOVING_AVG_WINDOW) for z in baseline_samples}
        last_valid = {z: None for z in baseline_samples}
        
        print("Starting measurement with object behind the glass (10cm target)...\n")
        log_file.write("Live measurements (corrected for glass thickness baseline):\n")
        log_file.write(header + "\n")
        log_file.write("-" * len(header) + "\n")
        log_file.flush()
        
        try:
            while True:
                if sensor.data_ready():
                    data = sensor.get_data()
                    timestamp = time.strftime("%H:%M:%S")
                    
                    results = []
                    for zone in baseline_samples:
                        try:
                            raw_dist = int(data.distance_mm[0][zone])
                        except:
                            raw_dist = 0
                        
                        # Subtract glass thickness baseline (crosstalk)
                        corrected = raw_dist - baseline[zone]
                        
                        # Outlier rejection
                        if last_valid[zone] is not None and abs(corrected - last_valid[zone]) > OUTLIER_THRESHOLD:
                            corrected = last_valid[zone]
                        
                        # Median and moving average filtering
                        med_val = median_filter(median_windows[zone], corrected)
                        smooth_val = moving_average(moving_avg_windows[zone], med_val)
                        last_valid[zone] = smooth_val
                        
                        smooth_val = max(smooth_val, 0)
                        
                        results.append(int(round(smooth_val)))
                    
                    # Average of the 4 zones for overall object distance
                    avg_distance = sum(results) / len(results)
                    
                    line = f"{timestamp} | " + " | ".join(f"{v:7d}" for v in results) + f" | {avg_distance:8.1f} |"
                    print(line)
                    log_file.write(line + "\n")
                    log_file.flush()
                
                time.sleep(0.01)
        
        except KeyboardInterrupt:
            print("\nMeasurement stopped by user.")
        finally:
            sensor.stop_ranging()
            print("Sensor stopped.")

if __name__ == "__main__":
    main()
