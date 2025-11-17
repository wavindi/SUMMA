#!/usr/bin/env python3
"""
VL53L5CX Dual Sensors Detection emitting point add to backend
- Sensor 1 = black team
- Sensor 2 = yellow team
- Emits 'sensor_point_scored' with action 'add_point' when detection lasts >1s
- Uses your backend event naming and frontend expectations
"""

import time
import collections
import statistics
from vl53l5cx_ctypes import VL53L5CX
import socketio

sio = socketio.Client(logger=False, engineio_logger=False)
SERVER_URL = 'http://localhost:5000'

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

BLACK_TEAM = 'black'
YELLOW_TEAM = 'yellow'

SENSOR1_ADDR = 0x29
SENSOR2_ADDR = 0x39

@sio.event
def connect():
    print(f"✅ Connected to server: {SERVER_URL}")

@sio.event
def disconnect():
    print("❌ Disconnected from server")

def connect_socket():
    if not sio.connected:
        try:
            sio.connect(SERVER_URL, wait_timeout=10)
            return True
        except Exception as e:
            print(f"Failed to connect socket.io server: {e}")
            return False
    return True

def emit_point_scored(team):
    if not sio.connected:
        print(f"⚠️ Offline: cannot send add_point for {team}")
        return False
    try:
        data = {'team': team, 'action': 'add_point', 'timestamp': time.time()}
        sio.emit('sensor_point_scored', data)
        print(f"📡 Sent add_point for {team}")
        return True
    except Exception as e:
        print(f"Emit failed: {e}")
        return False

def median_filter(window, value):
    window.append(value)
    if len(window) < 2:
        return value
    return statistics.median(window)

def moving_average(window, value):
    window.append(value)
    return sum(window) / len(window)

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
    if not connect_socket():
        print("⚠️ Running offline - no server connection")

    sensor1 = VL53L5CX(i2c_addr=SENSOR1_ADDR)
    sensor2 = VL53L5CX(i2c_addr=SENSOR2_ADDR)
    sensor1.set_resolution(4*4)
    sensor2.set_resolution(4*4)
    sensor1.set_ranging_frequency_hz(15)
    sensor2.set_ranging_frequency_hz(15)
    sensor1.start_ranging()
    sensor2.start_ranging()
    time.sleep(2)
    baseline1 = calibrate_baseline(sensor1, 'Sensor 1')
    baseline2 = calibrate_baseline(sensor2, 'Sensor 2')

    median_windows1 = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
    movavg_windows1 = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
    last_valid1 = {i: None for i in range(16)}

    median_windows2 = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
    movavg_windows2 = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
    last_valid2 = {i: None for i in range(16)}

    detect_start_time1 = None
    detect_start_time2 = None
    detection_active1 = False
    detection_active2 = False
    event_emitted1 = False
    event_emitted2 = False

    try:
        while True:
            res1, det1 = process_sensor(sensor1, baseline1, median_windows1, movavg_windows1, last_valid1)
            res2, det2 = process_sensor(sensor2, baseline2, median_windows2, movavg_windows2, last_valid2)
            if res1 is None or res2 is None:
                time.sleep(0.01)
                continue

            timestamp = time.strftime('%H:%M:%S')

            # Sensor 1 detection and point emit logic
            if det1:
                if not detection_active1:
                    detect_start_time1 = time.time()
                    detection_active1 = True
                    event_emitted1 = False
                    print(f'Object detected by Sensor 1 at {timestamp}')
                duration1 = time.time() - detect_start_time1
                if sio.connected and duration1 > 1.0 and not event_emitted1:
                    emit_point_scored(BLACK_TEAM)
                    event_emitted1 = True
            else:
                if detection_active1:
                    duration = time.time() - detect_start_time1
                    print(f'Object detection ended Sensor 1 at {timestamp}, Duration: {duration:.2f}s')
                detection_active1 = False
                duration1 = 0
                event_emitted1 = False

            # Sensor 2 detection and point emit logic
            if det2:
                if not detection_active2:
                    detect_start_time2 = time.time()
                    detection_active2 = True
                    event_emitted2 = False
                    print(f'Object detected by Sensor 2 at {timestamp}')
                duration2 = time.time() - detect_start_time2
                if sio.connected and duration2 > 1.0 and not event_emitted2:
                    emit_point_scored(YELLOW_TEAM)
                    event_emitted2 = True
            else:
                if detection_active2:
                    duration = time.time() - detect_start_time2
                    print(f'Object detection ended Sensor 2 at {timestamp}, Duration: {duration:.2f}s')
                detection_active2 = False
                duration2 = 0
                event_emitted2 = False

            time.sleep(0.05)

    except KeyboardInterrupt:
        print('\nExiting...')
    finally:
        try:
            sio.disconnect()
        except Exception:
            pass
        sensor1.stop_ranging()
        sensor2.stop_ranging()
        print('Sensors stopped.')

if __name__ == '__main__':
    main()
