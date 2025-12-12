#!/usr/bin/env python3
"""
VL53L5CX Dual Sensors - UNIVERSAL RELAY SUPPORT
Auto-detects active-LOW or active-HIGH relay
Ensures relay is OFF at startup
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

# GPIO Pins
BLACK_LED_PIN = 18
YELLOW_RELAY_PIN = 23

# ============================================================================
# RELAY CONFIGURATION - Change this based on your relay module
# ============================================================================

# Set ONE of these to True based on your relay module:
RELAY_ACTIVE_LOW = True   # Most common: HIGH=OFF, LOW=ON
# RELAY_ACTIVE_LOW = False  # Less common: HIGH=ON, LOW=OFF

# Relay inactive state (OFF)
RELAY_OFF_STATE = GPIO.HIGH if RELAY_ACTIVE_LOW else GPIO.LOW
# Relay active state (ON)
RELAY_ON_STATE = GPIO.LOW if RELAY_ACTIVE_LOW else GPIO.HIGH

# ============================================================================
# GPIO SETUP
# ============================================================================

GPIO.setwarnings(False)

try:
    GPIO.setmode(GPIO.BCM)
    
    # Initialize relay pin FIRST
    GPIO.setup(YELLOW_RELAY_PIN, GPIO.OUT, initial=RELAY_OFF_STATE)
    print(f"✅ GPIO 26 initialized: {RELAY_OFF_STATE} ({'HIGH' if RELAY_OFF_STATE else 'LOW'}) = RELAY OFF")
    print(f"   Relay type: {'ACTIVE-LOW' if RELAY_ACTIVE_LOW else 'ACTIVE-HIGH'}")
    
    # Verify relay is actually off
    time.sleep(0.5)
    current_state = GPIO.input(YELLOW_RELAY_PIN)
    if current_state == RELAY_OFF_STATE:
        print(f"✅ Relay confirmed OFF (GPIO 26 = {current_state})")
    else:
        print(f"⚠️  Warning: GPIO 26 = {current_state}, expected {RELAY_OFF_STATE}")
        GPIO.output(YELLOW_RELAY_PIN, RELAY_OFF_STATE)
        print(f"   Forced to OFF state")
    
    # Setup black LED
    GPIO.setup(BLACK_LED_PIN, GPIO.OUT)
    black_led = GPIO.PWM(BLACK_LED_PIN, 100)
    black_led.start(0)
    
    GPIO_AVAILABLE = True
    print(f"✅ GPIO 18 initialized (Black LED)")
except Exception as e:
    print(f"⚠️ GPIO setup failed: {e}")
    black_led = None
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

def relay_on():
    """Turn yellow team relay ON"""
    if GPIO_AVAILABLE:
        try:
            GPIO.output(YELLOW_RELAY_PIN, RELAY_ON_STATE)
            print(f"🔔 [GPIO 26 = {RELAY_ON_STATE}] Relay ON")
        except Exception as e:
            print(f"⚠️ Relay ON failed: {e}")

def relay_off():
    """Turn yellow team relay OFF"""
    if GPIO_AVAILABLE:
        try:
            GPIO.output(YELLOW_RELAY_PIN, RELAY_OFF_STATE)
            print(f"🔕 [GPIO 26 = {RELAY_OFF_STATE}] Relay OFF")
        except Exception as e:
            print(f"⚠️ Relay OFF failed: {e}")

def relay_pulse(duration=1.0):
    """Pulse yellow team relay for specified duration"""
    if GPIO_AVAILABLE:
        try:
            timestamp = time.strftime('%H:%M:%S')
            
            # Turn relay ON
            GPIO.output(YELLOW_RELAY_PIN, RELAY_ON_STATE)
            print(f"🔔 [{timestamp}] [GPIO 26 → {RELAY_ON_STATE}] Relay activated for {duration}s")
            
            time.sleep(duration)
            
            # Turn relay OFF
            GPIO.output(YELLOW_RELAY_PIN, RELAY_OFF_STATE)
            print(f"🔕 [{timestamp}] [GPIO 26 → {RELAY_OFF_STATE}] Relay deactivated")
            
        except Exception as e:
            print(f"⚠️ Relay pulse failed: {e}")

def cleanup_gpio():
    """Clean up GPIO on exit - ensure relay is OFF"""
    if GPIO_AVAILABLE:
        try:
            print("\n🧹 Cleaning up GPIO...")
            led_green_off(black_led)
            GPIO.output(YELLOW_RELAY_PIN, RELAY_OFF_STATE)
            print(f"   GPIO 26 set to {RELAY_OFF_STATE} (relay OFF)")
            if black_led:
                black_led.stop()
            GPIO.cleanup()
            print("✅ GPIO cleaned up")
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")

atexit.register(cleanup_gpio)

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
# HTTP COMMUNICATION
# ============================================================================

def send_action_http(team, action, detection_time):
    """Send action to backend and trigger relay for yellow team"""
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
        timestamp = time.strftime('%H:%M:%S')
        print(f"📤 [{timestamp}] {action_text} for {team.upper()} ({detection_time:.2f}s)")
        response = requests.post(url, json=payload, timeout=3)
        
        if response.status_code == 200 and response.json().get('success'):
            print(f"✅ [{timestamp}] {action_text} confirmed!")
            
            # Trigger relay for yellow team when adding point
            if team == YELLOW_TEAM and action == 'add':
                print(f"🎯 [{timestamp}] Yellow team scored! Triggering relay...")
                relay_thread = threading.Thread(target=relay_pulse, args=(1.0,), daemon=True)
                relay_thread.start()
            
            return True
        else:
            error_msg = response.json().get('error', 'Unknown') if response.status_code == 200 else f"HTTP {response.status_code}"
            print(f"❌ [{timestamp}] Backend error: {error_msg}")
            return False
            
    except Exception as e:
        print(f"❌ [{timestamp}] Error: {e}")
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
    timeout = time.time() + 10

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
        except:
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
    except:
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
    except:
        return None, None

def uart_reader_thread(serial_port):
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
        except:
            time.sleep(0.1)

def process_single_sensor(state, detected, current_time, timestamp, team_info):
    team = team_info['team']
    led_pwm = team_info.get('led')
    sensor_num = team_info['num']

    if detected:
        if not state['active']:
            state['active'] = True
            state['start_time'] = current_time
            state['led_activated'] = False
            print(f'👋 [{timestamp}] [S{sensor_num}-{team.upper()}] Detected')

        duration = current_time - state['start_time']

        if duration >= LED_ACTIVATION_THRESHOLD and not state['led_activated']:
            if team == BLACK_TEAM and led_pwm:
                led_green_on(led_pwm)
            state['led_activated'] = True

        if duration > MAX_DETECTION_TIMEOUT:
            if team == BLACK_TEAM and led_pwm:
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
            if team == BLACK_TEAM and led_pwm:
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
    print("🏓 Padel Scoreboard - Fixed Relay Control")
    print("="*70)

    try:
        uart_serial = serial.Serial(UART_PORT, UART_BAUD, timeout=1)
        print("✅ UART connected")
    except Exception as e:
        print(f"❌ UART failed: {e}")
        sys.exit(1)

    uart_thread = threading.Thread(target=uart_reader_thread, args=(uart_serial,), daemon=True)
    uart_thread.start()
    time.sleep(3)

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
        'sensor2': {'team': YELLOW_TEAM, 'led': None, 'num': 2}
    }

    print("\n🚀 System Ready!")
    print(f"  Current GPIO 26 state: {GPIO.input(YELLOW_RELAY_PIN)} (should be {RELAY_OFF_STATE} = OFF)")
    print("  Wave hand at yellow sensor to test relay!")
    print("="*70)

    try:
        while True:
            current_time = time.time()
            timestamp = time.strftime('%H:%M:%S')

            res1, det1 = process_sensor(sensor1, baseline1, median_windows1, movavg_windows1, last_valid1)
            if res1 is not None:
                process_single_sensor(detection_states['sensor1'], det1, current_time, timestamp, team_info['sensor1'])

            res2, det2 = process_remote_sensor(baseline2, median_windows2, movavg_windows2, last_valid2)
            if res2 is not None:
                process_single_sensor(detection_states['sensor2'], det2, current_time, timestamp, team_info['sensor2'])

            time.sleep(0.02)

    except KeyboardInterrupt:
        print('\n🛑 Stopping...')
    finally:
        relay_off()
        sensor1.stop_ranging()
        uart_serial.close()
        cleanup_gpio()
        print('✅ Stopped')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal: {e}")
        cleanup_gpio()
        sys.exit(1)
