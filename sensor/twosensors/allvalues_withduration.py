#!/usr/bin/env python3
"""
VL53L5CX Dual Sensors Detection with Event Duration & Exact Duration Logging
- Logs live zone readings and detection status per sensor
- Prints live detection duration on console
- Logs a separate line to the file immediately when detection ends, with exact duration
"""

import time
import collections
import statistics
from vl53l5cx_ctypes import VL53L5CX

CALIBRATION_SAMPLES = 60
MEDIAN_WINDOW = 3
MOVING_AVG_WINDOW = 1
OUTLIER_THRESHOLD = 100
MAX_VALID_CALIBRATION = 50
MIN_VALID_CALIBRATION = 3
DETECTION_THRESHOLD = 10
MIN_ZONES_FOR_DETECTION = 3
GOOD_ZONES = [0, 5, 6, 9, 10, 11, 12, 13]
AUTO_RESET_THRESHOLD = 80
AUTO_RESET_RAW_LIMIT = 20

SENSOR1_ADDR = 0x29
SENSOR2_ADDR = 0x39

def median_filter(window, value):
    window.append(value)
    if len(window) < 2:
        return value
    return statistics.median(window)

def moving_average(window, value):
    window.append(value)
    return sum(window) / len(window)

def check_outlier(curr, last, threshold):
    if last is None:
        return False
    return abs(curr - last) > threshold

def calibrate_baseline(sensor, name):
    print(f"Calibrating {name} with {CALIBRATION_SAMPLES} samples...")
    samples = {i: [] for i in range(16)}
    collected = 0
    rejected = 0
    while collected < CALIBRATION_SAMPLES:
        if sensor.data_ready():
            data = sensor.get_data()
            valid_sample = True
            for i in range(16):
                try:
                    val = int(data.distance_mm[0][i])
                except:
                    val = 0
                if MIN_VALID_CALIBRATION < val < MAX_VALID_CALIBRATION:
                    samples[i].append(val)
                elif val >= MAX_VALID_CALIBRATION:
                    valid_sample = False
            if valid_sample:
                collected += 1
            else:
                rejected += 1
                if rejected % 10 == 0:
                    print(f"{name}: Rejected {rejected} spike samples...")
        time.sleep(0.02)
    baseline = {}
    for i in range(16):
        baseline[i] = statistics.median(samples[i]) if samples[i] else 0
    print(f"{name} calibration complete, rejected {rejected} spikes")
    return baseline

def process_sensor(sensor, baseline, median_windows, movavg_windows, last_valid):
    if not sensor.data_ready():
        return None, None
    data = sensor.get_data()
    results = []
    zones_above_thresh = 0
    for i in range(16):
        try:
            raw_dist = int(data.distance_mm[0][i])
        except:
            raw_dist = 0
        corrected = raw_dist - baseline[i]
        if last_valid[i] is not None:
            if last_valid[i] > AUTO_RESET_THRESHOLD and corrected < AUTO_RESET_RAW_LIMIT:
                median_windows[i].clear()
                movavg_windows[i].clear()
                last_valid[i] = corrected
            elif abs(corrected - last_valid[i]) > OUTLIER_THRESHOLD:
                corrected = last_valid[i]

        med_val = median_filter(median_windows[i], corrected)
        smooth_val = moving_average(movavg_windows[i], med_val)
        smooth_val = max(smooth_val, 0)
        last_valid[i] = smooth_val
        results.append(int(round(smooth_val)))
        if i in GOOD_ZONES and smooth_val > DETECTION_THRESHOLD:
            zones_above_thresh += 1
    detected = zones_above_thresh >= MIN_ZONES_FOR_DETECTION
    return results, detected

def main():
    sensor1 = VL53L5CX(i2c_addr=SENSOR1_ADDR)
    sensor2 = VL53L5CX(i2c_addr=SENSOR2_ADDR)
    sensor1.set_resolution(4*4)
    sensor2.set_resolution(4*4)
    sensor1.set_ranging_frequency_hz(15)
    sensor2.set_ranging_frequency_hz(15)
    sensor1.start_ranging()
    sensor2.start_ranging()
    time.sleep(2)
    baseline1 = calibrate_baseline(sensor1, "Sensor 1")
    baseline2 = calibrate_baseline(sensor2, "Sensor 2")

    median_windows1 = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
    movavg_windows1 = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
    last_valid1 = {i: None for i in range(16)}

    median_windows2 = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
    movavg_windows2 = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
    last_valid2 = {i: None for i in range(16)}

    filename = time.strftime("gen_dual_%Y_%m_%d_wa9t_%H_%M_%S.txt")
    with open(filename, "w") as log_file:
        header = "Time     | Sensor1 Zones (16)                            | Detect | Duration(s) | Sensor2 Zones (16)                            | Detect | Duration(s) |"
        log_file.write(f"VL53L5CX Dual Sensor Log started at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write(header + "\n")
        log_file.write("-"*len(header) + "\n")
        print(header)
        print("-"*len(header))

        detect_start_time1 = None
        detect_start_time2 = None
        detection_active1 = False
        detection_active2 = False

        try:
            while True:
                res1, det1 = process_sensor(sensor1, baseline1, median_windows1, movavg_windows1, last_valid1)
                res2, det2 = process_sensor(sensor2, baseline2, median_windows2, movavg_windows2, last_valid2)

                if res1 is None or res2 is None:
                    time.sleep(0.01)
                    continue

                timestamp = time.strftime("%H:%M:%S")
                s1_str = " ".join(f"{v:3d}" for v in res1)
                s2_str = " ".join(f"{v:3d}" for v in res2)
                det1_str = "YES" if det1 else "NO "
                det2_str = "YES" if det2 else "NO "

                # Manage detection timing for sensor 1
                duration1_log_line = ""
                if det1:
                    if not detection_active1:
                        detect_start_time1 = time.time()
                        detection_active1 = True
                        print(f"Object detected by Sensor 1 at {timestamp}")
                    duration1_live = time.time() - detect_start_time1
                else:
                    if detection_active1:
                        duration = time.time() - detect_start_time1
                        print(f"Object detection ended Sensor 1 at {timestamp}, Duration: {duration:.2f}s")
                        duration1_log_line = f"DETECTION ENDED Sensor 1 at {timestamp}, Duration: {duration:.2f}s\n"
                        detect_start_time1 = None
                    detection_active1 = False
                    duration1_live = 0

                # Manage detection timing for sensor 2
                duration2_log_line = ""
                if det2:
                    if not detection_active2:
                        detect_start_time2 = time.time()
                        detection_active2 = True
                        print(f"Object detected by Sensor 2 at {timestamp}")
                    duration2_live = time.time() - detect_start_time2
                else:
                    if detection_active2:
                        duration = time.time() - detect_start_time2
                        print(f"Object detection ended Sensor 2 at {timestamp}, Duration: {duration:.2f}s")
                        duration2_log_line = f"DETECTION ENDED Sensor 2 at {timestamp}, Duration: {duration:.2f}s\n"
                        detect_start_time2 = None
                    detection_active2 = False
                    duration2_live = 0

                log_line = f"{timestamp} | {s1_str:<48} | {det1_str} | {duration1_live:10.2f} | {s2_str:<48} | {det2_str} | {duration2_live:10.2f} |"
                log_file.write(log_line + "\n")

                # Log detection end durations immediately
                if duration1_log_line:
                    log_file.write(duration1_log_line)
                if duration2_log_line:
                    log_file.write(duration2_log_line)
                
                log_file.flush()
                time.sleep(0.05)

        except KeyboardInterrupt:
            print("\nStopped by user")
        finally:
            sensor1.stop_ranging()
            sensor2.stop_ranging()
            print("Sensors stopped.")
            log_file.write(f"Sensors stopped at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

if __name__ == "__main__":
    main()
