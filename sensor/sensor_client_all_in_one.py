#!/usr/bin/env python3
"""
Padel Sensor Client - ALL-IN-ONE VERSION
Combines pigpio UART reading + sensor processing + HTTP backend communication

This single script:
  1. Reads from GPIO 23 & 24 using pigpio (software UART)
  2. Calibrates sensors
  3. Detects hand movements (time-based)
  4. Sends HTTP to backend (/addpoint, /subtractpoint, /resetmatch)

Run ONLY this file + padel_backend.py (or padel_backend_SMART_DETECTION.py)
"""

import pigpio
import time
import collections
import statistics
import requests
import RPi.GPIO as GPIO
import sys
import atexit
import threading

# ============================================================================
# CONFIGURATION
# ============================================================================

SERVER_URL = 'http://localhost:5000'
ADD_POINT_URL = f'{SERVER_URL}/addpoint'
SUBTRACT_POINT_URL = f'{SERVER_URL}/subtractpoint'
RESET_MATCH_URL = f'{SERVER_URL}/resetmatch'

# GPIO Configuration (Software UART via pigpio)
PICO_1_GPIO = 23  # Black team (Pico 1 TX → Pi GPIO 23 RX)
PICO_2_GPIO = 24  # Yellow team (Pico 2 TX → Pi GPIO 24 RX)
BAUD_RATE = 57600

# Calibration & Detection
CALIBRATION_SAMPLES = 60
MEDIAN_WINDOW = 3
MOVING_AVG_WINDOW = 1
OUTLIER_THRESHOLD = 100
MAX_VALID_CALIBRATION = 150
MIN_VALID_CALIBRATION = 0
DETECTION_THRESHOLD = 8
MIN_ZONES_FOR_DETECTION = 3
GOOD_ZONES = [0, 5, 6, 9, 10, 11, 12, 13]
AUTO_RESET_THRESHOLD = 80
AUTO_RESET_RAW_LIMIT = 20

# Timing windows for actions (TIME-BASED DETECTION)
ADD_POINT_WINDOW = (0.15, 3.0)
SUBTRACT_POINT_WINDOW = (3.0, 7.0)
RESET_MATCH_WINDOW = (7.5, 15.0)
MAX_DETECTION_TIMEOUT = 15.5

BLACK_TEAM = 'black'
YELLOW_TEAM = 'yellow'

# Relay GPIO Pins (NOT using 23/24 as those are UART)
BLACK_RELAY_PIN = 21
YELLOW_RELAY_PIN = 22

# ============================================================================
# OPTIMIZATION SETTINGS
# ============================================================================

LOOP_SLEEP_TIME = 0.005
HTTP_TIMEOUT = 0.8
HTTP_CONNECTION_TIMEOUT = 0.3
USE_SESSION = True

# ============================================================================
# RELAY CONFIGURATION
# ============================================================================

RELAY_ACTIVE_LOW = True
RELAY_OFF_STATE = GPIO.HIGH if RELAY_ACTIVE_LOW else GPIO.LOW
RELAY_ON_STATE = GPIO.LOW if RELAY_ACTIVE_LOW else GPIO.HIGH

# ============================================================================
# GPIO SETUP (RELAYS ONLY)
# ============================================================================

GPIO.setwarnings(False)
try:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BLACK_RELAY_PIN, GPIO.OUT, initial=RELAY_OFF_STATE)
    print(f"✅ GPIO {BLACK_RELAY_PIN} initialized (BLACK RELAY OFF)")
    GPIO.setup(YELLOW_RELAY_PIN, GPIO.OUT, initial=RELAY_OFF_STATE)
    print(f"✅ GPIO {YELLOW_RELAY_PIN} initialized (YELLOW RELAY OFF)")
    print(f"   Relay type: {'ACTIVE-LOW' if RELAY_ACTIVE_LOW else 'ACTIVE-HIGH'}")
    GPIO_AVAILABLE = True
except Exception as e:
    print(f"⚠️ GPIO setup failed: {e}")
    GPIO_AVAILABLE = False

# ============================================================================
# HTTP SESSION
# ============================================================================

if USE_SESSION:
    http_session = requests.Session()
    http_session.headers.update({'Connection': 'keep-alive'})
    print("✅ HTTP session created (keep-alive enabled)")
else:
    http_session = requests

# ============================================================================
# PIGPIO SETUP
# ============================================================================

pi = None

def init_pigpio():
    """Initialize pigpio connection"""
    global pi
    try:
        pi = pigpio.pi()
        if not pi.connected:
            print("❌ Failed to connect to pigpiod")
            print("   Start pigpiod with: sudo pigpiod")
            sys.exit(1)
        print("✅ pigpiod connected")
        return True
    except Exception as e:
        print(f"❌ Error connecting to pigpiod: {e}")
        sys.exit(1)

# ============================================================================
# SENSOR DATA - TWO SENSORS
# ============================================================================

sensor_lock_1 = threading.Lock()
sensor_data_1 = {
    'distances': [0] * 16,
    'last_update': 0,
    'frame_count': 0,
    'data_ready': False
}

sensor_lock_2 = threading.Lock()
sensor_data_2 = {
    'distances': [0] * 16,
    'last_update': 0,
    'frame_count': 0,
    'data_ready': False
}

# ============================================================================
# GLOBAL TEAM MAPPING / SIDE SWITCH STATE
# ============================================================================

team_info = None
teams_swapped = False

# ============================================================================
# RELAY CONTROL FUNCTIONS
# ============================================================================

def relay_pulse(pin, team_name, duration=1.0):
    """Pulse relay for specified duration."""
    if GPIO_AVAILABLE:
        try:
            timestamp = time.strftime('%H:%M:%S.%f')[:-3]
            GPIO.output(pin, RELAY_ON_STATE)
            print(f"🔔 [{timestamp}] {team_name.upper()} relay ON ({duration}s)")
            time.sleep(duration)
            GPIO.output(pin, RELAY_OFF_STATE)
            print(f"🔕 [{timestamp}] {team_name.upper()} relay OFF")
        except Exception as e:
            print(f"⚠️ {team_name} relay pulse failed: {e}")

def cleanup():
    """Clean up on exit"""
    global pi
    if GPIO_AVAILABLE:
        try:
            print("\n🧹 Cleaning up...")
            GPIO.output(BLACK_RELAY_PIN, RELAY_OFF_STATE)
            GPIO.output(YELLOW_RELAY_PIN, RELAY_OFF_STATE)
            GPIO.cleanup()
        except:
            pass

    if pi and pi.connected:
        try:
            pi.bb_serial_read_close(PICO_1_GPIO)
            pi.bb_serial_read_close(PICO_2_GPIO)
            pi.stop()
            print("✅ pigpio closed")
        except:
            pass

    if USE_SESSION:
        try:
            http_session.close()
        except:
            pass

atexit.register(cleanup)

# ============================================================================
# TEAM ASSIGNMENT SWAP
# ============================================================================

def swap_team_assignments():
    """Swap which sensor controls which team."""
    global teams_swapped, team_info

    if team_info is None:
        return

    teams_swapped = not teams_swapped

    if teams_swapped:
        team_info['sensor1']['team'] = YELLOW_TEAM
        team_info['sensor2']['team'] = BLACK_TEAM
        print("🔄 Teams swapped: Sensor1→YELLOW, Sensor2→BLACK")
    else:
        team_info['sensor1']['team'] = BLACK_TEAM
        team_info['sensor2']['team'] = YELLOW_TEAM
        print("🔄 Teams restored: Sensor1→BLACK, Sensor2→YELLOW")

# ============================================================================
# HTTP COMMUNICATION
# ============================================================================

def send_action_http(team, action, detection_time):
    """Send action to backend via HTTP."""
    if action == 'add':
        url = ADD_POINT_URL
        payload = {'team': team}
        action_text = "Add point"
    elif action == 'subtract':
        url = SUBTRACT_POINT_URL
        payload = {'team': team}
        action_text = "Subtract point"
    elif action == 'reset':
        url = RESET_MATCH_URL
        payload = {}
        action_text = "Reset match"
    else:
        return False

    def _send_and_trigger():
        try:
            start_time = time.time()
            timestamp = time.strftime('%H:%M:%S.%f')[:-3]
            print(f"📤 [{timestamp}] Sending: {action_text} for {team.upper()} ({detection_time:.2f}s)")

            response = http_session.post(
                url,
                json=payload,
                timeout=(HTTP_CONNECTION_TIMEOUT, HTTP_TIMEOUT)
            )

            response_time = (time.time() - start_time) * 1000

            if response.status_code == 200 and response.json().get('success'):
                timestamp_confirm = time.strftime('%H:%M:%S.%f')[:-3]
                print(f"✅ [{timestamp_confirm}] Backend confirmed in {response_time:.1f}ms!")

                response_data = response.json()

                # Check for side switch (works with both backend versions)
                side_switch = response_data.get('sideswitch') or response_data.get('side_switch')

                if side_switch:
                    print(f"🔄 [{timestamp_confirm}] SIDE SWITCH REQUIRED!")
                    total_games = side_switch.get('totalgames') or side_switch.get('total_games')
                    game_score = side_switch.get('gamescore') or side_switch.get('game_score')
                    set_score = side_switch.get('setscore') or side_switch.get('set_score')
                    print(f"   Total games: {total_games}")
                    print(f"   Game score: {game_score}")
                    print(f"   Set score: {set_score}")
                    print("   🏃 Players should change sides!")
                    swap_team_assignments()

                # Trigger relay for add point
                if action == 'add':
                    relay_pin = BLACK_RELAY_PIN if team == BLACK_TEAM else YELLOW_RELAY_PIN
                    relay_thread = threading.Thread(
                        target=relay_pulse,
                        args=(relay_pin, team, 1.0),
                        daemon=True
                    )
                    relay_thread.start()

                return True
            else:
                error_msg = response.json().get('error', 'Unknown') if response.status_code == 200 else f"HTTP {response.status_code}"
                print(f"❌ [{timestamp}] Backend error: {error_msg}")
                return False

        except requests.exceptions.Timeout:
            print(f"⚠️ Backend timeout")
            return False
        except Exception as e:
            print(f"❌ HTTP Error: {e}")
            return False

    http_thread = threading.Thread(target=_send_and_trigger, daemon=True)
    http_thread.start()
    return True

def determine_action(detection_duration):
    """Determine action based on detection duration."""
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

def calibrate_sensor(name, sensor_data, sensor_lock):
    """Calibrate sensor baseline."""
    print(f"📊 Calibrating {name}...")
    samples = {i: [] for i in range(16)}
    collected = 0
    timeout = time.time() + 10

    while collected < CALIBRATION_SAMPLES and time.time() < timeout:
        with sensor_lock:
            if sensor_data['data_ready']:
                distances = sensor_data['distances'].copy()
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

def process_sensor(baseline, median_windows, movavg_windows, last_valid, sensor_data, sensor_lock):
    """Process sensor data."""
    with sensor_lock:
        if not sensor_data['data_ready']:
            return None, None
        distances = sensor_data['distances'].copy()

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

# ============================================================================
# PIGPIO UART READER THREAD
# ============================================================================

def uart_reader_thread(gpio_pin, sensor_data, sensor_lock, sensor_name):
    """Read UART data from Pico via pigpio."""
    global pi

    reading_data = False
    data_buffer = []
    line_buffer = ""

    # Open software serial
    pi.set_mode(gpio_pin, pigpio.INPUT)
    pi.bb_serial_read_open(gpio_pin, BAUD_RATE, 8)
    print(f"✅ {sensor_name} - GPIO{gpio_pin} opened for UART reading")

    while True:
        try:
            (count, data) = pi.bb_serial_read(gpio_pin)

            if count > 0:
                text = data.decode('utf-8', errors='ignore')
                line_buffer += text

                while '\n' in line_buffer:
                    line, line_buffer = line_buffer.split('\n', 1)
                    line = line.strip()

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
                            with sensor_lock:
                                sensor_data['distances'] = distances
                                sensor_data['last_update'] = time.time()
                                sensor_data['frame_count'] += 1
                                sensor_data['data_ready'] = True

                    elif reading_data:
                        data_buffer.append(line)

            time.sleep(0.001)

        except Exception as e:
            print(f"⚠️ [{sensor_name}] UART error: {e}")
            time.sleep(0.1)

# ============================================================================
# DETECTION STATE MACHINE
# ============================================================================

def process_single_sensor(state, detected, current_time, timestamp, team_info_local):
    """Process detection state for one sensor."""
    team = team_info_local['team']
    sensor_num = team_info_local['num']

    if detected:
        if not state['active']:
            state['active'] = True
            state['start_time'] = current_time
            print(f'👋 [{timestamp}] [S{sensor_num}-{team.upper()}] Detection started')

        duration = current_time - state['start_time']
        if duration > MAX_DETECTION_TIMEOUT:
            print(f'⏱️ [{timestamp}] [{team.upper()}] Timeout ({duration:.2f}s) - resetting')
            state['active'] = False
            state['start_time'] = None

    else:
        if state['active']:
            total_duration = current_time - state['start_time']
            timestamp_ms = time.strftime('%H:%M:%S.%f')[:-3]
            print(f'✋ [{timestamp_ms}] [{team.upper()}] Hand removed after {total_duration:.2f}s')

            action = determine_action(total_duration)
            if action:
                send_action_http(team, action, total_duration)
                print(f'⚡ [{timestamp_ms}] Action "{action}" sent to backend')

            state['active'] = False
            state['start_time'] = None

# ============================================================================
# MAIN
# ============================================================================

def main():
    global team_info

    print("="*70)
    print("🏓 Padel Sensor Client - ALL-IN-ONE VERSION")
    print("="*70)
    print("⚡ CONFIGURATION:")
    print(f"   • PICO 1 (Black): GPIO {PICO_1_GPIO} @ {BAUD_RATE} baud")
    print(f"   • PICO 2 (Yellow): GPIO {PICO_2_GPIO} @ {BAUD_RATE} baud")
    print(f"   • Backend: {SERVER_URL}")
    print(f"   • Relays: GPIO {BLACK_RELAY_PIN} (Black), GPIO {YELLOW_RELAY_PIN} (Yellow)")
    print("="*70)

    # Initialize pigpio
    init_pigpio()

    # Start UART reader threads
    print("\n📡 Starting UART readers...")

    uart_thread1 = threading.Thread(
        target=uart_reader_thread,
        args=(PICO_1_GPIO, sensor_data_1, sensor_lock_1, "PICO_1"),
        daemon=True
    )
    uart_thread1.start()

    uart_thread2 = threading.Thread(
        target=uart_reader_thread,
        args=(PICO_2_GPIO, sensor_data_2, sensor_lock_2, "PICO_2"),
        daemon=True
    )
    uart_thread2.start()

    print("⏳ Waiting for sensor data...")
    time.sleep(3)

    # Calibration
    print("\n" + "="*70)
    print("🎯 Calibrating sensors...")
    print("="*70)

    baseline1 = calibrate_sensor('PICO_1 (Black)', sensor_data_1, sensor_lock_1)
    baseline2 = calibrate_sensor('PICO_2 (Yellow)', sensor_data_2, sensor_lock_2)

    # Initialize filtering windows
    median_windows1 = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
    movavg_windows1 = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
    last_valid1 = {i: None for i in range(16)}

    median_windows2 = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
    movavg_windows2 = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
    last_valid2 = {i: None for i in range(16)}

    # Detection states
    detection_states = {
        'sensor1': {'active': False, 'start_time': None},
        'sensor2': {'active': False, 'start_time': None}
    }

    # Team mapping
    team_info = {
        'sensor1': {'team': BLACK_TEAM, 'num': 1},
        'sensor2': {'team': YELLOW_TEAM, 'num': 2}
    }

    print("\n🚀 System Ready!")
    print("   Wave hand at sensors to score!")
    print("="*70)

    try:
        while True:
            current_time = time.time()
            timestamp = time.strftime('%H:%M:%S')

            # Process Sensor 1
            res1, det1 = process_sensor(
                baseline1, median_windows1, movavg_windows1, last_valid1,
                sensor_data_1, sensor_lock_1
            )

            if res1 is not None:
                process_single_sensor(detection_states['sensor1'], det1,
                                    current_time, timestamp, team_info['sensor1'])

            # Process Sensor 2
            res2, det2 = process_sensor(
                baseline2, median_windows2, movavg_windows2, last_valid2,
                sensor_data_2, sensor_lock_2
            )

            if res2 is not None:
                process_single_sensor(detection_states['sensor2'], det2,
                                    current_time, timestamp, team_info['sensor2'])

            time.sleep(LOOP_SLEEP_TIME)

    except KeyboardInterrupt:
        print('\n🛑 Stopping...')
    finally:
        cleanup()
        print('✅ Stopped cleanly')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        cleanup()
        sys.exit(1)
