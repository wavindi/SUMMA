#!/usr/bin/env python3
"""
VL53L5CX Dual Sensor - WITH 40-SAMPLE CALIBRATION - COMPACT DISPLAY
"""

import time
import collections
import statistics
from vl53l5cx_ctypes import VL53L5CX

# Sensor addresses
SENSOR1_ADDRESS = 0x29
SENSOR2_ADDRESS = 0x39

# Filter parameters
MEDIAN_WINDOW = 3
MOVING_AVG_WINDOW = 2

# Calibration parameters
CALIBRATION_SAMPLES = 40

def median_filter(window, new_value):
    """Apply median filter with window size 3"""
    window.append(new_value)
    if len(window) < window.maxlen:
        return new_value
    return statistics.median(window)

def moving_average(window, new_value):
    """Apply moving average with window size 2"""
    window.append(new_value)
    return sum(window) / len(window)

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

def calibrate_sensors(sensor1, sensor2):
    """Calibrate both sensors with 40 samples each"""
    print("\n" + "="*100)
    print("CALIBRATION PHASE - 40 SAMPLES")
    print("="*100)
    
    # Storage for calibration samples
    calib_s1_raw = {zone: [] for zone in range(16)}
    calib_s1_filtered = {zone: [] for zone in range(16)}
    calib_s2_raw = {zone: [] for zone in range(16)}
    calib_s2_filtered = {zone: [] for zone in range(16)}
    
    # Filter windows for calibration
    median_windows_s1 = {zone: collections.deque(maxlen=MEDIAN_WINDOW) for zone in range(16)}
    moving_avg_windows_s1 = {zone: collections.deque(maxlen=MOVING_AVG_WINDOW) for zone in range(16)}
    
    median_windows_s2 = {zone: collections.deque(maxlen=MEDIAN_WINDOW) for zone in range(16)}
    moving_avg_windows_s2 = {zone: collections.deque(maxlen=MOVING_AVG_WINDOW) for zone in range(16)}
    
    collected = 0
    start_time = time.time()
    
    print(f"\nCollecting {CALIBRATION_SAMPLES} samples from each sensor...")
    print("(Glass should be clear of objects)\n")
    
    while collected < CALIBRATION_SAMPLES:
        elapsed = time.time() - start_time
        
        # Timeout after 2 minutes
        if elapsed > 120:
            print(f"\n⚠ Calibration timeout after {elapsed:.1f}s")
            print(f"Collected: {collected}/{CALIBRATION_SAMPLES} samples")
            break
        
        # Read Sensor 1
        if sensor1.data_ready():
            try:
                data1 = sensor1.get_data()
                for zone in range(16):
                    try:
                        raw_dist = int(data1.distance_mm[0][zone])
                        calib_s1_raw[zone].append(raw_dist)
                        
                        # Apply filters
                        med = median_filter(median_windows_s1[zone], raw_dist)
                        filtered = moving_average(moving_avg_windows_s1[zone], med)
                        calib_s1_filtered[zone].append(filtered)
                    except:
                        pass
            except:
                pass
        
        # Read Sensor 2
        if sensor2.data_ready():
            try:
                data2 = sensor2.get_data()
                for zone in range(16):
                    try:
                        raw_dist = int(data2.distance_mm[0][zone])
                        calib_s2_raw[zone].append(raw_dist)
                        
                        # Apply filters
                        med = median_filter(median_windows_s2[zone], raw_dist)
                        filtered = moving_average(moving_avg_windows_s2[zone], med)
                        calib_s2_filtered[zone].append(filtered)
                    except:
                        pass
            except:
                pass
        
        # Check if we have collected data from both sensors
        if calib_s1_raw[0] and calib_s2_raw[0]:
            collected = min(len(calib_s1_raw[0]), len(calib_s2_raw[0]))
            if collected % 5 == 0 and collected > 0:
                print(f"  ✓ {collected}/{CALIBRATION_SAMPLES} samples collected")
        
        time.sleep(0.1)
    
    # Calculate baselines (median of filtered values)
    baseline_s1 = {}
    baseline_s2 = {}
    
    print("\nCalculating baselines from filtered values...")
    
    for zone in range(16):
        if calib_s1_filtered[zone]:
            baseline_s1[zone] = statistics.median(calib_s1_filtered[zone])
        else:
            baseline_s1[zone] = 0
        
        if calib_s2_filtered[zone]:
            baseline_s2[zone] = statistics.median(calib_s2_filtered[zone])
        else:
            baseline_s2[zone] = 0
    
    avg_baseline_s1 = sum(baseline_s1.values()) / len(baseline_s1)
    avg_baseline_s2 = sum(baseline_s2.values()) / len(baseline_s2)
    
    print(f"\n✓ Calibration complete ({collected} samples)")
    print(f"  Sensor 1 baseline (avg): {avg_baseline_s1:.1f}mm")
    print(f"  Sensor 2 baseline (avg): {avg_baseline_s2:.1f}mm")
    
    return baseline_s1, baseline_s2, collected

def main():
    filename = time.strftime("gen5_%Y_%m_%d_wa9t_%H_%M_%S.txt")
    start_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"Log file: {filename}\n")
    
    print("="*100)
    print("VL53L5CX DUAL SENSOR - CALIBRATED - COMPACT DISPLAY")
    print("="*100)
    print(f"Format: Z0:S1/S2 | Z1:S1/S2 | ... (compact, all on one line)\n")
    
    sensor1, sensor2 = initialize_sensors()
    
    if sensor1 is None or sensor2 is None:
        print("\n✗ Sensor initialization failed")
        return
    
    if not start_sensors_with_warmup(sensor1, sensor2):
        print("\n✗ Failed to start sensors")
        return
    
    # CALIBRATION PHASE
    baseline_s1, baseline_s2, calib_samples = calibrate_sensors(sensor1, sensor2)
    
    # LIVE MEASUREMENT PHASE
    print("\n" + "="*100)
    print("LIVE MEASUREMENT PHASE - COMPACT DISPLAY")
    print("="*100 + "\n")
    
    # Create COMPACT header
    header = "Time    |"
    for zone in range(16):
        header += f"Z{zone:2d}:|"
    
    with open(filename, "w") as log_file:
        log_file.write(f"VL53L5CX Dual Sensor - Calibrated - {start_time_str}\n")
        log_file.write(f"Sensor 1: 0x{SENSOR1_ADDRESS:02x}, Sensor 2: 0x{SENSOR2_ADDRESS:02x}\n")
        log_file.write(f"Calibration: {CALIBRATION_SAMPLES} samples\n")
        log_file.write(f"Format: Z#:S1/S2 (compact display)\n\n")
        log_file.write("CALIBRATION BASELINES:\n")
        log_file.write(f"Sensor 1 (0x{SENSOR1_ADDRESS:02x}): {[baseline_s1[z] for z in range(16)]}\n")
        log_file.write(f"Sensor 2 (0x{SENSOR2_ADDRESS:02x}): {[baseline_s2[z] for z in range(16)]}\n")
        log_file.write("\n" + "="*100 + "\n")
        log_file.write("LIVE MEASUREMENTS (corrected):\n")
        log_file.write(header + "\n")
        log_file.write("-" * len(header) + "\n")
        log_file.flush()
        
        print(header)
        print("-" * len(header))
        
        # Create filter windows for live measurements
        median_windows_s1 = {zone: collections.deque(maxlen=MEDIAN_WINDOW) for zone in range(16)}
        moving_avg_windows_s1 = {zone: collections.deque(maxlen=MOVING_AVG_WINDOW) for zone in range(16)}
        
        median_windows_s2 = {zone: collections.deque(maxlen=MEDIAN_WINDOW) for zone in range(16)}
        moving_avg_windows_s2 = {zone: collections.deque(maxlen=MOVING_AVG_WINDOW) for zone in range(16)}
        
        try:
            while True:
                timestamp = time.strftime("%H:%M:%S")
                
                s1_corrected = [0] * 16
                s2_corrected = [0] * 16
                
                # Read Sensor 1 - CORRECTED
                if sensor1.data_ready():
                    try:
                        data1 = sensor1.get_data()
                        for zone in range(16):
                            try:
                                raw_dist = int(data1.distance_mm[0][zone])
                                
                                # Apply filters
                                med = median_filter(median_windows_s1[zone], raw_dist)
                                filtered = moving_average(moving_avg_windows_s1[zone], med)
                                
                                # Subtract baseline (corrected value)
                                corrected = filtered - baseline_s1[zone]
                                s1_corrected[zone] = int(max(corrected, 0))
                            except:
                                s1_corrected[zone] = 0
                    except Exception as e:
                        pass
                
                # Read Sensor 2 - CORRECTED
                if sensor2.data_ready():
                    try:
                        data2 = sensor2.get_data()
                        for zone in range(16):
                            try:
                                raw_dist = int(data2.distance_mm[0][zone])
                                
                                # Apply filters
                                med = median_filter(median_windows_s2[zone], raw_dist)
                                filtered = moving_average(moving_avg_windows_s2[zone], med)
                                
                                # Subtract baseline (corrected value)
                                corrected = filtered - baseline_s2[zone]
                                s2_corrected[zone] = int(max(corrected, 0))
                            except:
                                s2_corrected[zone] = 0
                    except Exception as e:
                        pass
                
                # Build COMPACT output line: Z#:S1/S2|Z#:S1/S2|...
                line = f"{timestamp}|"
                for zone in range(16):
                    line += f"{s1_corrected[zone]:3d}/{s2_corrected[zone]:3d}|"
                
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
