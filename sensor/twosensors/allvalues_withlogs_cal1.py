#!/usr/bin/env python3
"""
VL53L5CX All Zones Logging Output with Adjustable Calibration Samples,
Filtering, and Crosstalk Baseline Subtraction
"""

import time
import collections
import statistics
from vl53l5cx_ctypes import VL53L5CX

# Parameters to configure
CALIBRATION_SAMPLES = 60  # Modify this to change calibration sample count
MEDIAN_WINDOW = 5
MOVING_AVG_WINDOW = 3
OUTLIER_THRESHOLD = 200  # Max allowed jump in mm between consecutive readings

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
        print(f"Failed: {e}")
        return
    
    sensor.start_ranging()
    time.sleep(2.0)
    
    filename = time.strftime("gen2_%Y_%m_%d_wa9t_%H_%M_%S.txt")
    start_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"Logging output to file: {filename}\n")
    
    header = "Time          | " + " | ".join([f"Z{i:2d}  " for i in range(16)]) + "|"
    
    with open(filename, "w") as log_file:
        # Write initial info
        log_file.write(f"using vl53l5cx and the time {start_time_str}\n\n")
        log_file.write("=== CALIBRATION SAMPLES (Keep area clear, with cover glass) ===\n")
        log_file.write(header + "\n")
        log_file.write("-" * len(header) + "\n")
        
        print(f"using vl53l5cx and the time {start_time_str}")
        print("=== CALIBRATION SAMPLES ===")
        print(header)
        print("-" * len(header))

        # Collect calibration samples
        calibration_samples = {i: [] for i in range(16)}
        samples_collected = 0
        
        while samples_collected < CALIBRATION_SAMPLES:
            if sensor.data_ready():
                data = sensor.get_data()
                timestamp = time.strftime("%H:%M:%S.%f")[:-3]
                
                sample_line_values = []
                for i in range(16):
                    try:
                        val = int(data.distance_mm[0][i])
                    except:
                        val = 0
                    calibration_samples[i].append(val)
                    sample_line_values.append(val)
                
                line = f"{timestamp} | " + " | ".join(f"{v:4d}" for v in sample_line_values) + " |"
                
                # Write calibration sample line
                log_file.write(line + "\n")
                log_file.flush()
                print(line)
                
                samples_collected += 1
            
            time.sleep(0.02)
        
        # Calculate baseline medians
        baseline = {}
        for i in range(16):
            if len(calibration_samples[i]) > 0:
                baseline[i] = statistics.median(calibration_samples[i])
            else:
                baseline[i] = 0
        
        # Log baseline summary line
        log_file.write("\n=== CALIBRATION BASELINE MEDIAN DISTANCES ===\n")
        baseline_line = "Baseline    | " + " | ".join(f"{baseline[i]:4.0f}" for i in range(16)) + " |"
        log_file.write(baseline_line + "\n\n")
        log_file.flush()
        
        print("\n=== CALIBRATION BASELINE MEDIAN DISTANCES ===")
        print(baseline_line)
        print("\nStarting live measurement...\n")
        
        # Log header for live measurements
        log_file.write("=== LIVE DISTANCE READINGS (Corrected & Filtered) ===\n")
        log_file.write(header + "\n")
        log_file.write("-" * len(header) + "\n")
        log_file.flush()
        
        print("=== LIVE DISTANCE READINGS ===")
        print(header)
        print("-" * len(header))
        
        # Prepare filters for live measurement
        median_windows = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
        moving_avg_windows = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
        last_valid = {i: None for i in range(16)}
        
        try:
            while True:
                if sensor.data_ready():
                    data = sensor.get_data()
                    timestamp = time.strftime("%H:%M:%S")
                    results = []
                    
                    for i in range(16):
                        try:
                            raw_dist = int(data.distance_mm[0][i])
                        except:
                            raw_dist = 0
                        
                        # Subtract calibration baseline (crosstalk)
                        corrected = raw_dist - baseline[i]
                        
                        # Outlier rejection
                        if last_valid[i] is not None and abs(corrected - last_valid[i]) > OUTLIER_THRESHOLD:
                            corrected = last_valid[i]  # Reject spike
                        
                        # Median filter
                        median_val = median_filter(median_windows[i], corrected)
                        # Moving average filter
                        smooth_val = moving_average(moving_avg_windows[i], median_val)
                        last_valid[i] = smooth_val
                        
                        # Clamp negative distances to zero
                        smooth_val = max(smooth_val, 0)
                        
                        results.append(int(round(smooth_val)))
                    
                    line = f"{timestamp} | " + " | ".join(f"{v:4d}" for v in results) + " |"
                    print(line)
                    log_file.write(line + "\n")
                    log_file.flush()
                
                time.sleep(0.01)
        
        except KeyboardInterrupt:
            print("\nStopped by user")
        finally:
            sensor.stop_ranging()

if __name__ == "__main__":
    main()
