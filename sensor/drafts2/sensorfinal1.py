#!/usr/bin/env python3
"""
VL53L5CX Dual Sensors Detection - LOCAL (I2C) + REMOTE (Pico UART)
COMPLETE WORKING VERSION
"""

import time
import collections
import statistics
import requests
import RPi.GPIO as GPIO
import sys
import atexit
import serial
import threading
from vl53l5cx_ctypes import VL53L5CX

# ============================================================================
# CONFIGURATION
# ============================================================================

SERVER_URL = 'http://localhost:5000'
ADD_POINT_URL = f'{SERVER_URL}/add_point'
SUBTRACT_POINT_URL = f'{SERVER_URL}/subtract_point'
RESET_MATCH_URL = f'{SERVER_URL}/reset_match'

UART_PORT = '/dev/serial0'
UART_BAUD = 57600

CALIBRATION_SAMPLES = 60
MEDIAN_WINDOW = 3
MOVING_AVG_WINDOW = 1
OUTLIER_THRESHOLD = 100
MAX_VALID_CALIBRATION = 50
MIN_VALID_CALIBRATION = 3

DETECTION_THRESHOLD = 8
MIN_ZONES_FOR_DETECTION = 3
GOOD_ZONES = [0, 5, 6, 9, 10, 11, 12, 13]

AUTO_RESET_THRESHOLD = 80
AUTO_RESET_RAW_LIMIT = 20

ADD_POINT_WINDOW = (0.2, 3.0)
SUBTRACT_POINT_WINDOW = (3.5, 10.0)
RESET_MATCH_WINDOW = (10.5, 15.0)
LED_ACTIVATION_THRESHOLD = 0.2
MAX_DETECTION_TIMEOUT = 15.5

BLACK_TEAM = 'black'
YELLOW_TEAM = 'yellow'
LOCAL_SENSOR_ADDR = 0x29

# ============================================================================
# GPIO SETUP (with warnings disabled)
# ============================================================================

GPIO.setwarnings(False)  # Disable GPIO warnings

try:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(18, GPIO.OUT)
    GPIO.setup(23, GPIO.OUT)
    black_led = GPIO.PWM(18, 100)
    yellow_led = GPIO.PWM(23, 100)
    black_led.start(0)
    yellow_led.start(0)
    GPIO_AVAILABLE = True
except Exception as e:
    print(f"⚠️ GPIO setup failed: {e}")
    black_led = yellow_led = None
    GPIO_AVAILABLE = False

def led_green_on(led_pwm, brightness=80):
    if GPIO_AVAILABLE and led_pwm:
        try:
            led_pwm.ChangeDutyCycle(brightness)
        except:
            pass

def led_green_off(led_pwm):
    if GPIO_AVAILABLE and led_pwm:
        try:
            led_pwm.ChangeDutyCycle(0)
        except:
            pass

def cleanup_leds():
    if GPIO_AVAILABLE:
        try:
            led_green_off(black_led)
            led_green_off(yellow_led)
            if black_led:
                black_led.stop()
            if yellow_led:
                yellow_led.stop()
            GPIO.cleanup()
        except:
            pass

atexit.register(cleanup_leds)

# ============================================================================
# REMOTE SENSOR DATA
# ============================================================================

remote_sensor_lock = threading.Lock()
remote_sensor_data = {
    'distances': [0] * 16,
    'last_update': 0,
    'frame_count': 0,
    'data_ready': False
}

# ============================================================================
# HTTP FUNCTIONS
# ============================================================================

def send_action_http(team, action, detection_time):
    if action == 'add':
        url = ADD_POINT_URL
        payload = {'team': team, 'action_type': 'add_point', 'detection_time': detection_time}
        action_text = "Add point"
    elif action == 'subtract':
        url = SUBTRACT_POINT_URL
        payload = {'team': team, 'action_type': 'subtract_point', 'detection_time': detection_time}
        action_text = "Subtract point"
    elif action == 'reset':
        url = RESET_MATCH_URL
        payload = {'action': 'reset_match', 'triggered_by': team, 'detection_time': detection_time}
        action_text = "Reset match"
    else:
        return False

    try:
        print(f"📤 {action_text} for {team.upper()} ({detection_time:.2f}s)")
        response = requests.post(url, json=payload, timeout=3)
        if response.status_code == 200 and response.json().get('success'):
            print(f"✅ Confirmed")
            return True
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def determine_action(detection_duration):
    if ADD_POINT_WINDOW[0] <= detection_duration <= ADD_POINT_WINDOW[1]:
        return 'add'
    elif SUBTRACT_POINT_WINDOW[0] <= detection_duration <= SUBTRACT_POINT_WINDOW[1]:
        return 'subtract'
    elif RESET_MATCH_WINDOW[0] <= detection_duration <= RESET_MATCH_WINDOW[1]:
        return 'reset'
    return None

# ============================================================================
# FILTERING
# ============================================================================

def median_filter(window, value):
    window.append(value)
    return statistics.median(window) if len(window) >= 2 else value

def moving_average(window, value):
    window.append(value)
    return sum(window) / len(window)

# ============================================================================
# CALIBRATION
# ============================================================================

def calibrate_baseline(sensor, name):
    print(f"📊 Calibrating {name}...")
    samples = {i: [] for i in range(16)}
    collected = 0
    timeout = time.time() + 10  # 10 second timeout

    while collected < CALIBRATION_SAMPLES and time.time() < timeout:
        try:
            if sensor.data_ready():
                data = sensor.get_data()
                zone_readings = []

                for i in range(16):
                    try:
                        val = int(data.distance_mm[0][i])
                        if MIN_VALID_CALIBRATION < val < MAX_VALID_CALIBRATION:
                            zone_readings.append((i, val))
                    except:
                        pass

                if len(zone_readings) > 12:
                    for zone_idx, val in zone_readings:
                        samples[zone_idx].append(val)
                    collected += 1
                    if collected % 10 == 0:
                        print(f"  Progress: {collected}/{CALIBRATION_SAMPLES}")

            time.sleep(0.02)
        except Exception as e:
            print(f"  ⚠️ Calibration error: {e}")
            time.sleep(0.1)

    baseline = {i: (statistics.median(samples[i]) if samples[i] else 20) for i in range(16)}
    print(f"✅ {name} calibrated ({collected} samples)")
    return baseline

def calibrate_remote_baseline(name):
    print(f"📊 Calibrating {name} (remote)...")
    samples = {i: [] for i in range(16)}
    collected = 0
    timeout = time.time() + 10

    while collected < CALIBRATION_SAMPLES and time.time() < timeout:
        with remote_sensor_lock:
            if remote_sensor_data['data_ready']:
                distances = remote_sensor_data['distances'].copy()
            else:
                time.sleep(0.05)
                continue
        
        zone_readings = []
        for i in range(16):
            val = distances[i]
            if MIN_VALID_CALIBRATION < val < MAX_VALID_CALIBRATION:
                zone_readings.append((i, val))
        
        if len(zone_readings) > 12:
            for zone_idx, val in zone_readings:
                samples[zone_idx].append(val)
            collected += 1
            if collected % 10 == 0:
                print(f"  Progress: {collected}/{CALIBRATION_SAMPLES}")
        
        time.sleep(0.05)
    
    baseline = {i: (statistics.median(samples[i]) if samples[i] else 20) for i in range(16)}
    print(f"✅ {name} calibrated ({collected} samples)")
    return baseline

# ============================================================================
# SENSOR PROCESSING
# ============================================================================

def process_sensor(sensor, baseline, median_windows, movavg_windows, last_valid):
    if not sensor.data_ready():
        return None, None

    try:
        data = sensor.get_data()
        results = []
        zones_above_thresh = 0

        for i in range(16):
            try:
                raw_dist = int(data.distance_mm[0][i])
            except:
                raw_dist = 0

            corrected = raw_dist - baseline.get(i, 0)

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
    except Exception as e:
        print(f"⚠️ Sensor processing error: {e}")
        return None, None

def process_remote_sensor(baseline, median_windows, movavg_windows, last_valid):
    with remote_sensor_lock:
        if not remote_sensor_data['data_ready']:
            return None, None
        distances = remote_sensor_data['distances'].copy()
    
    try:
        results = []
        zones_above_thresh = 0

        for i in range(16):
            raw_dist = distances[i]
            corrected = raw_dist - baseline.get(i, 0)

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
    except Exception as e:
        print(f"⚠️ Remote sensor error: {e}")
        return None, None

# ============================================================================
# UART THREAD
# ============================================================================

def uart_reader_thread(serial_port):
    print(f"🔌 UART thread started")
    reading_data = False
    data_buffer = []
    
    while True:
        try:
            if serial_port.in_waiting > 0:
                line = serial_port.readline().decode('utf-8', errors='ignore').strip()
                
                if line == "DATA_START":
                    reading_data = True
                    data_buffer = []
                elif line == "DATA_END":
                    reading_data = False
                    distances = []
                    for data_line in data_buffer:
                        if ',' in data_line:
                            try:
                                dist = int(data_line.split(',')[0])
                                distances.append(dist)
                            except:
                                pass
                    
                    if len(distances) == 16:
                        with remote_sensor_lock:
                            remote_sensor_data['distances'] = distances
                            remote_sensor_data['last_update'] = time.time()
                            remote_sensor_data['frame_count'] += 1
                            remote_sensor_data['data_ready'] = True
                
                elif reading_data:
                    data_buffer.append(line)
                elif line and (line.startswith("PICO") or line.startswith("CONFIG") or line.startswith("READY")):
                    print(f"  [PICO] {line}")
            else:
                time.sleep(0.001)
        except Exception as e:
            print(f"⚠️ UART error: {e}")
            time.sleep(0.1)

# ============================================================================
# DETECTION STATE
# ============================================================================

def process_single_sensor(state, detected, current_time, timestamp, team_info):
    team = team_info['team']
    led_pwm = team_info['led']
    sensor_num = team_info['num']

    if detected:
        if not state['active']:
            state['active'] = True
            state['start_time'] = current_time
            state['led_activated'] = False
            print(f'👋 [{timestamp}] [S{sensor_num}-{team.upper()}] Detected')

        duration = current_time - state['start_time']

        if duration >= LED_ACTIVATION_THRESHOLD and not state['led_activated']:
            led_green_on(led_pwm)
            state['led_activated'] = True
            print(f"🟢 [{timestamp}] [{team.upper()}] LED ON")

        if duration > MAX_DETECTION_TIMEOUT:
            led_green_off(led_pwm)
            action = determine_action(duration)
            if action:
                send_action_http(team, action, duration)
            state['active'] = False
            state['start_time'] = None
            state['led_activated'] = False

    else:
        if state['active']:
            total_duration = current_time - state['start_time']
            led_green_off(led_pwm)
            print(f'✋ [{timestamp}] [{team.upper()}] Ended ({total_duration:.2f}s)')

            action = determine_action(total_duration)
            if action:
                send_action_http(team, action, total_duration)

            state['active'] = False
            state['start_time'] = None
            state['led_activated'] = False

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("="*70)
    print("🏓 Padel Scoreboard - Dual Sensors")
    print("="*70)

    # UART
    print(f"\n🔌 Connecting to Pico...")
    try:
        uart_serial = serial.Serial(UART_PORT, UART_BAUD, timeout=1)
        print("✅ UART connected")
    except Exception as e:
        print(f"❌ UART failed: {e}")
        sys.exit(1)

    uart_thread = threading.Thread(target=uart_reader_thread, args=(uart_serial,), daemon=True)
    uart_thread.start()
    time.sleep(3)

    # Local sensor
    print(f"\n🔧 Initializing local sensor...")
    try:
        sensor1 = VL53L5CX(i2c_addr=LOCAL_SENSOR_ADDR)
        sensor1.set_resolution(4*4)
        sensor1.set_ranging_frequency_hz(15)
        sensor1.start_ranging()
        time.sleep(2)
        print("✅ Local sensor ready")
    except Exception as e:
        print(f"❌ Local sensor failed: {e}")
        sys.exit(1)

    print("\n"+"="*70)
    print("🎯 Calibrating...")
    print("="*70)

    baseline1 = calibrate_baseline(sensor1, 'LOCAL (Black)')
    baseline2 = calibrate_remote_baseline('REMOTE (Yellow)')

    print("\n"+"="*70)

    # Init filtering
    median_windows1 = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
    movavg_windows1 = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
    last_valid1 = {i: None for i in range(16)}

    median_windows2 = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
    movavg_windows2 = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
    last_valid2 = {i: None for i in range(16)}

    detection_states = {
        'sensor1': {'active': False, 'start_time': None, 'led_activated': False},
        'sensor2': {'active': False, 'start_time': None, 'led_activated': False}
    }

    team_info = {
        'sensor1': {'team': BLACK_TEAM, 'led': black_led, 'num': 1},
        'sensor2': {'team': YELLOW_TEAM, 'led': yellow_led, 'num': 2}
    }

    print("🚀 System Ready!")
    print("  • Sensor 1 (BLACK): Local I2C")
    print("  • Sensor 2 (YELLOW): Remote Pico")
    print("="*70)
    print()

    try:
        while True:
            current_time = time.time()
            timestamp = time.strftime('%H:%M:%S')

            # Local
            res1, det1 = process_sensor(sensor1, baseline1, median_windows1, movavg_windows1, last_valid1)
            if res1 is not None:
                process_single_sensor(detection_states['sensor1'], det1, current_time, timestamp, team_info['sensor1'])

            # Remote
            res2, det2 = process_remote_sensor(baseline2, median_windows2, movavg_windows2, last_valid2)
            if res2 is not None:
                process_single_sensor(detection_states['sensor2'], det2, current_time, timestamp, team_info['sensor2'])

            time.sleep(0.02)

    except KeyboardInterrupt:
        print('\n'+'='*70)
        print('🛑 Stopping...')
    finally:
        led_green_off(black_led)
        led_green_off(yellow_led)
        sensor1.stop_ranging()
        uart_serial.close()
        cleanup_leds()
        print('✅ Stopped')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal: {e}")
        import traceback
        traceback.print_exc()
        cleanup_leds()
        sys.exit(1)
