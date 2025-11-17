#!/usr/bin/env python3
"""
VL53L5CX OPTIMIZED for Padel Ball Detection Through Glass
- Improved filtering parameters
- Auto-reset logic for stuck filters
- Zone selection (ignore noisy zones)
- Better calibration spike rejection
"""

import time
import collections
import statistics
from vl53l5cx_ctypes import VL53L5CX

# ============================================================================
# OPTIMIZED PARAMETERS - TUNED FOR YOUR APPLICATION
# ============================================================================
CALIBRATION_SAMPLES = 60       # More samples for stable baseline
MEDIAN_WINDOW = 3               # Fast spike rejection
MOVING_AVG_WINDOW = 1           # Quick response
OUTLIER_THRESHOLD = 100          # Allow return to baseline, block huge spikes

# Calibration limits
MAX_VALID_CALIBRATION = 50      # Reject >50mm during calibration
MIN_VALID_CALIBRATION = 3       # Minimum valid distance

# Detection
DETECTION_THRESHOLD = 10        # Object if >15mm above baseline
MIN_ZONES_FOR_DETECTION = 3     # Need 3+ zones

# Zone configuration - USE ONLY GOOD ZONES
GOOD_ZONES = [0, 5, 6, 9, 10, 11, 12, 13]  # Stable, low-noise zones
IGNORE_ZONES = [1, 2, 3, 4, 7, 8, 14, 15]  # High noise/crosstalk

# Auto-reset parameters
AUTO_RESET_THRESHOLD = 80       # If filter >80mm but raw <20mm, reset
AUTO_RESET_RAW_LIMIT = 20       # Raw reading limit for reset trigger

def median_filter(window, new_value):
    window.append(new_value)
    if len(window) < 2:  # Need at least 2 values
        return new_value
    return statistics.median(window)

def moving_average(window, new_value):
    window.append(new_value)
    return sum(window) / len(window)

def main():
    print("=" * 80)
    print("VL53L5CX OPTIMIZED DETECTION SYSTEM")
    print("=" * 80)
    print("\nInitializing sensor...")
    
    try:
        sensor = VL53L5CX()
        sensor.set_resolution(4 * 4)
        sensor.set_ranging_frequency_hz(15)
        print("✅ Sensor initialized")
    except RuntimeError as e:
        print(f"❌ Initialization failed: {e}")
        return
    
    sensor.start_ranging()
    time.sleep(2.0)
    
    filename = time.strftime("gen7_%Y_%m_%d_wa9t_%H_%M_%S.txt")
    start_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"\n📝 Logging to: {filename}")
    print(f"🔧 Configuration:")
    print(f"   - Median window: {MEDIAN_WINDOW}")
    print(f"   - Moving avg window: {MOVING_AVG_WINDOW}")
    print(f"   - Outlier threshold: {OUTLIER_THRESHOLD}mm")
    print(f"   - Using zones: {GOOD_ZONES}")
    print(f"   - Ignoring zones: {IGNORE_ZONES}")
    
    # Column headers for good zones only
    zone_headers = " | ".join([f"Z{z:2d}  " for z in range(16)])
    header = f"Time     | {zone_headers}| Detect |"
    
    with open(filename, "w") as log_file:
        log_file.write(f"Using VL53L5CX - Optimized Configuration\n")
        log_file.write(f"Start time: {start_time_str}\n")
        log_file.write(f"Config: MEDIAN={MEDIAN_WINDOW}, AVG={MOVING_AVG_WINDOW}, OUTLIER={OUTLIER_THRESHOLD}mm\n")
        log_file.write(f"Good zones: {GOOD_ZONES}\n")
        log_file.write(f"Ignored zones: {IGNORE_ZONES}\n\n")
        
        log_file.write("=== CALIBRATION PHASE ===\n")
        log_file.write(header + "\n")
        log_file.write("-" * len(header) + "\n")
        
        print(f"\n{'=' * 80}")
        print("CALIBRATION PHASE - Keep area clear!")
        print(f"Collecting {CALIBRATION_SAMPLES} samples...")
        print(f"{'=' * 80}")
        print(header)
        print("-" * len(header))
        
        # Calibration with spike rejection
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
                    
                    # Spike rejection during calibration
                    if MIN_VALID_CALIBRATION < val < MAX_VALID_CALIBRATION:
                        calibration_samples[i].append(val)
                    elif val >= MAX_VALID_CALIBRATION:
                        valid_sample = False  # Spike detected
                
                if valid_sample:
                    collected += 1
                    line = f"{timestamp} | " + " | ".join(f"{v:4d}" for v in sample_values) + " |      |"
                    print(line)
                    log_file.write(line + "\n")
                else:
                    rejected += 1
                    if rejected % 10 == 0:
                        print(f"⚠️  Rejected {rejected} spike samples so far...")
                
                log_file.flush()
            
            time.sleep(0.02)
        
        # Calculate baselines (median of clean samples)
        baseline = {}
        for i in range(16):
            if len(calibration_samples[i]) > 0:
                baseline[i] = statistics.median(calibration_samples[i])
            else:
                baseline[i] = 0
        
        # Log baseline
        log_file.write("\n=== CALIBRATION BASELINE ===\n")
        baseline_line = "Baseline | " + " | ".join(f"{baseline[i]:4.0f}" for i in range(16)) + " |\n"
        log_file.write(baseline_line)
        log_file.write(f"Rejected {rejected} spike samples during calibration\n\n")
        log_file.flush()
        
        print("\n" + "=" * 80)
        print("CALIBRATION COMPLETE")
        print("=" * 80)
        print(baseline_line)
        print(f"Rejected {rejected} spike samples")
        print(f"Good zones baseline range: {min([baseline[z] for z in GOOD_ZONES]):.0f}-{max([baseline[z] for z in GOOD_ZONES]):.0f}mm")
        print("=" * 80)
        
        # Initialize filters
        median_windows = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
        moving_avg_windows = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
        last_valid = {i: None for i in range(16)}
        reset_count = {i: 0 for i in range(16)}  # Track auto-resets
        
        print("\n🚀 STARTING LIVE DETECTION...")
        log_file.write("=== LIVE DETECTION (Corrected & Filtered) ===\n")
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
                        
                        # Subtract baseline
                        corrected = raw_dist - baseline[i]
                        
                        # AUTO-RESET LOGIC - Critical for stuck filter recovery
                        if last_valid[i] is not None:
                            # If filter output is high but raw reading is low = STUCK
                            if last_valid[i] > AUTO_RESET_THRESHOLD and corrected < AUTO_RESET_RAW_LIMIT:
                                # RESET THIS ZONE'S FILTERS
                                median_windows[i].clear()
                                moving_avg_windows[i].clear()
                                last_valid[i] = corrected
                                reset_count[i] += 1
                                smooth_val = max(corrected, 0)
                                results.append(int(round(smooth_val)))
                                continue  # Skip normal filtering
                        
                        # Outlier rejection
                        if last_valid[i] is not None and abs(corrected - last_valid[i]) > OUTLIER_THRESHOLD:
                            corrected = last_valid[i]  # Use last valid instead of spike
                        
                        # Median filter
                        median_val = median_filter(median_windows[i], corrected)
                        
                        # Moving average
                        smooth_val = moving_average(moving_avg_windows[i], median_val)
                        last_valid[i] = smooth_val
                        
                        # Clamp to positive
                        smooth_val = max(smooth_val, 0)
                        
                        results.append(int(round(smooth_val)))
                        
                        # Count zones above detection threshold (only good zones)
                        if i in GOOD_ZONES and smooth_val > DETECTION_THRESHOLD:
                            zones_above_threshold += 1
                    
                    # Detection logic
                    object_detected = zones_above_threshold >= MIN_ZONES_FOR_DETECTION
                    detect_str = "  YES" if object_detected else "   NO"
                    
                    line = f"{timestamp} | " + " | ".join(f"{v:4d}" for v in results) + f" | {detect_str} |"
                    print(line)
                    log_file.write(line + "\n")
                    log_file.flush()
                
                time.sleep(0.01)
        
        except KeyboardInterrupt:
            print("\n\n⏹️  Stopped by user")
            print(f"\nAuto-reset statistics (times filters were cleared):")
            for zone in GOOD_ZONES:
                if reset_count[zone] > 0:
                    print(f"   Zone {zone:2d}: {reset_count[zone]} resets")
        
        finally:
            sensor.stop_ranging()
            print("✅ Sensor stopped\n")

if __name__ == "__main__":
    main()

