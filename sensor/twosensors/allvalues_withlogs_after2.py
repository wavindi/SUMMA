#!/usr/bin/env python3
"""
VL53L5CX - FINAL OPTIMIZED VERSION
Based on comprehensive analysis of gen2, gen3, gen4 logs
All 12 modifications applied
"""

import time
import collections
import statistics
from vl53l5cx_ctypes import VL53L5CX

# ============================================================================
# OPTIMIZED PARAMETERS (Based on Log Analysis)
# ============================================================================

# Filtering - Modified #2, #3, #4
MEDIAN_WINDOW = 3               # Was 5 - faster flush
MOVING_AVG_WINDOW = 2           # Was 3 - quicker response
OUTLIER_THRESHOLD = 40          # Was 200 - CRITICAL FIX

# Calibration - Modified #5, #6
CALIBRATION_SAMPLES = 100
MAX_VALID_CALIBRATION = 30      # Was 4000 - block huge spikes
MIN_VALID_CALIBRATION = 3       # Was 10 - accept more valid data

# Detection - Modified #9, #10
DETECTION_THRESHOLD = 12        # Was 15 - more sensitive
MIN_ZONES_FOR_DETECTION = 2     # Was 3 - lower requirement

# Auto-reset - Modified #7, #8
AUTO_RESET_THRESHOLD = 50       # Was 80 - detect stuck sooner
AUTO_RESET_RAW_LIMIT = 15       # Was 20 - tighter limit

# Zone selection - Modified #1
GOOD_ZONES = [0, 10, 11, 12, 13]  # Was [0,5,9,10,11,12,13]
IGNORE_ZONES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 14, 15]

# Spike rejection - Modified #11
MAX_VALID_LIVE_READING = 500    # NEW: Reject >500mm spikes

def median_filter(window, new_value):
    window.append(new_value)
    if len(window) < 2:
        return new_value
    return statistics.median(window)

def moving_average(window, new_value):
    window.append(new_value)
    return sum(window) / len(window)

def main():
    print("=" * 80)
    print("VL53L5CX - OPTIMIZED DETECTION (Based on Log Analysis)")
    print("=" * 80)
    print("\nInitializing sensor...")
    
    try:
        sensor = VL53L5CX()
        sensor.set_resolution(4 * 4)
        sensor.set_ranging_frequency_hz(15)
        print("✅ Sensor initialized")
    except RuntimeError as e:
        print(f"❌ Failed: {e}")
        return
    
    sensor.start_ranging()
    time.sleep(2.0)
    
    filename = time.strftime("gen5_optimized_%Y_%m_%d_wa9t_%H_%M_%S.txt")
    start_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"\n📝 Logging to: {filename}")
    print(f"\n🔧 Applied Modifications:")
    print(f"   #1: GOOD_ZONES = {GOOD_ZONES}")
    print(f"   #2: MEDIAN_WINDOW = {MEDIAN_WINDOW} (was 5)")
    print(f"   #3: MOVING_AVG_WINDOW = {MOVING_AVG_WINDOW} (was 3)")
    print(f"   #4: OUTLIER_THRESHOLD = {OUTLIER_THRESHOLD}mm (was 200) 🔥 CRITICAL")
    print(f"   #5: MAX_VALID_CALIBRATION = {MAX_VALID_CALIBRATION}mm (was 4000)")
    print(f"   #11: Spike rejection = >{MAX_VALID_LIVE_READING}mm blocked 🔥 CRITICAL")
    
    zone_headers = " | ".join([f"Z{z:2d}  " for z in range(16)])
    header = f"Time     | {zone_headers}| Det |"
    
    with open(filename, "w") as log_file:
        log_file.write(f"VL53L5CX - OPTIMIZED (12 Modifications Applied)\n")
        log_file.write(f"Start: {start_time_str}\n")
        log_file.write(f"Config: MED={MEDIAN_WINDOW}, AVG={MOVING_AVG_WINDOW}, OUTLIER={OUTLIER_THRESHOLD}, ZONES={GOOD_ZONES}\n\n")
        
        log_file.write("=== CALIBRATION ===\n")
        log_file.write(header + "\n")
        log_file.write("-" * len(header) + "\n")
        
        print("\n" + "=" * 80)
        print(f"CALIBRATION - Collecting {CALIBRATION_SAMPLES} samples")
        print("=" * 80)
        print(header)
        print("-" * len(header))
        
        # Calibration with strict spike rejection
        calibration_samples = {i: [] for i in range(16)}
        collected = 0
        rejected = 0
        
        while collected < CALIBRATION_SAMPLES:
            if sensor.data_ready():
                data = sensor.get_data()
                timestamp = time.strftime("%H:%M:%S")
                
                valid_sample = True
                sample_values = []
                
                for i in range(16):
                    try:
                        val = int(data.distance_mm[0][i])
                    except:
                        val = 0
                    
                    sample_values.append(val)
                    
                    # Strict calibration filtering (Modification #5, #6)
                    if MIN_VALID_CALIBRATION <= val <= MAX_VALID_CALIBRATION:
                        calibration_samples[i].append(val)
                    elif val > MAX_VALID_CALIBRATION:
                        valid_sample = False
                
                if valid_sample:
                    collected += 1
                    line = f"{timestamp} | " + " | ".join(f"{v:4d}" for v in sample_values) + " |     |"
                    if collected % 10 == 0:
                        print(line)
                    log_file.write(line + "\n")
                else:
                    rejected += 1
                
                log_file.flush()
            
            time.sleep(0.02)
        
        # Calculate baseline
        baseline = {}
        for i in range(16):
            if len(calibration_samples[i]) > 0:
                baseline[i] = statistics.median(calibration_samples[i])
            else:
                baseline[i] = 0
        
        # Log baseline
        log_file.write("\n=== BASELINE ===\n")
        baseline_line = "Baseline | " + " | ".join(f"{baseline[i]:4.0f}" for i in range(16)) + " |\n"
        log_file.write(baseline_line)
        log_file.write(f"Rejected {rejected} spikes (>{MAX_VALID_CALIBRATION}mm)\n")
        log_file.write(f"Good zones baseline: {[baseline[z] for z in GOOD_ZONES]}\n\n")
        log_file.flush()
        
        print("\n" + "=" * 80)
        print("CALIBRATION COMPLETE")
        print("=" * 80)
        print(baseline_line)
        print(f"Rejected {rejected} spike samples")
        print(f"Good zones: {GOOD_ZONES}")
        print(f"Baselines: {[f'{baseline[z]:.0f}mm' for z in GOOD_ZONES]}")
        print("=" * 80)
        
        # Initialize filters
        median_windows = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
        moving_avg_windows = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
        last_valid = {i: None for i in range(16)}
        reset_count = {i: 0 for i in range(16)}
        spike_count = {i: 0 for i in range(16)}
        
        print("\n🚀 LIVE DETECTION STARTING...\n")
        log_file.write("=== LIVE DETECTION ===\n")
        log_file.write(header + "\n")
        log_file.write("-" * len(header) + "\n")
        log_file.flush()
        
        print(header)
        print("-" * len(header))
        
        try:
            while True:
                if sensor.data_ready():
                    data = sensor.get_data()
                    timestamp = time.strftime("%H:%M:%S")
                    
                    results = []
                    zones_above_threshold = 0
                    
                    for i in range(16):
                        try:
                            raw_dist = int(data.distance_mm[0][i])
                        except:
                            raw_dist = 0
                        
                        # Modification #11: Spike rejection in live loop
                        if raw_dist > MAX_VALID_LIVE_READING or raw_dist < 0:
                            spike_count[i] += 1
                            raw_dist = last_valid[i] if last_valid[i] is not None else baseline[i]
                        
                        # Subtract baseline
                        corrected = raw_dist - baseline[i]
                        
                        # Modification #7, #8: Auto-reset logic (improved thresholds)
                        if last_valid[i] is not None:
                            if last_valid[i] > AUTO_RESET_THRESHOLD and corrected < AUTO_RESET_RAW_LIMIT:
                                median_windows[i].clear()
                                moving_avg_windows[i].clear()
                                last_valid[i] = corrected
                                reset_count[i] += 1
                                smooth_val = max(corrected, 0)
                                results.append(int(round(smooth_val)))
                                continue
                        
                        # Modification #4: Outlier rejection (40mm threshold)
                        if last_valid[i] is not None and abs(corrected - last_valid[i]) > OUTLIER_THRESHOLD:
                            corrected = last_valid[i]
                        
                        # Modification #2: Median filter (window=3)
                        median_val = median_filter(median_windows[i], corrected)
                        
                        # Modification #3: Moving average (window=2)
                        smooth_val = moving_average(moving_avg_windows[i], median_val)
                        last_valid[i] = smooth_val
                        
                        smooth_val = max(smooth_val, 0)
                        results.append(int(round(smooth_val)))
                        
                        # Modification #9, #10: Detection (threshold=12mm, 2+ zones)
                        if i in GOOD_ZONES and smooth_val > DETECTION_THRESHOLD:
                            zones_above_threshold += 1
                    
                    # Detection decision
                    object_detected = zones_above_threshold >= MIN_ZONES_FOR_DETECTION
                    detect_str = " YES" if object_detected else "  NO"
                    
                    line = f"{timestamp} | " + " | ".join(f"{v:4d}" for v in results) + f" | {detect_str} |"
                    print(line)
                    log_file.write(line + "\n")
                    log_file.flush()
                
                time.sleep(0.01)
        
        except KeyboardInterrupt:
            print("\n\n⏹️  Stopped")
            print(f"\n📊 Statistics:")
            print(f"   Auto-resets: {sum(reset_count.values())} total")
            for z in GOOD_ZONES:
                if reset_count[z] > 0 or spike_count[z] > 0:
                    print(f"   Zone {z:2d}: {reset_count[z]} resets, {spike_count[z]} spikes blocked")
        
        finally:
            sensor.stop_ranging()
            print("✅ Sensor stopped\n")

if __name__ == "__main__":
    main()
