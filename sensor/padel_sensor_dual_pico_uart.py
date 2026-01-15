#!/usr/bin/env python3

"""
VL53L5CX Dual Sensors via DUAL PICO UART - OPTIMIZED VERSION

Hardware setup:
- Pico 1 (40m away): VL53L5CX sensor → UART TX → Pi GPIO 23 (Black team)
- Pico 2 (40m away): VL53L5CX sensor → UART TX → Pi GPIO 24 (Yellow team)
- Relay 1 (GPIO 21): Black team audio feedback
- Relay 2 (GPIO 22): Yellow team audio feedback

Features:
- Ultra-low latency with pigpio software UART
- Dual relay support (triggers after backend confirms)
- HTTP keep-alive for fast communication
- Automatic sensor-to-team swap on side switch
- Enhanced debugging and error handling
"""

import time
import collections
import statistics
import requests
import RPi.GPIO as GPIO
import sys
import atexit
import threading
import subprocess
import pigpio

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

# Relay GPIO Pins
BLACK_RELAY_PIN = 21
YELLOW_RELAY_PIN = 22

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

# ============================================================================
# OPTIMIZATION SETTINGS
# ============================================================================

LOOP_SLEEP_TIME = 0.005  # 5ms polling = 200Hz
HTTP_TIMEOUT = 0.8       # 800ms timeout
HTTP_CONNECTION_TIMEOUT = 0.3  # 300ms connection
USE_SESSION = True       # Keep-alive HTTP

# ============================================================================
# DEBUGGING SETTINGS
# ============================================================================

DEBUG_UART_DATA = False  # Set True to see UART frames
DEBUG_HTTP = True        # Print HTTP details
DEBUG_DETECTION = True   # Print detection events

# ============================================================================
# RELAY CONFIGURATION
# ============================================================================

RELAY_ACTIVE_LOW = True
RELAY_OFF_STATE = GPIO.HIGH if RELAY_ACTIVE_LOW else GPIO.LOW
RELAY_ON_STATE = GPIO.LOW if RELAY_ACTIVE_LOW else GPIO.HIGH

# ============================================================================
# GPIO SETUP (RELAYS ONLY - NOT UART PINS)
# ============================================================================

GPIO.setwarnings(False)
try:
    GPIO.setmode(GPIO.BCM)

    # Initialize BLACK relay (GPIO 21)
    GPIO.setup(BLACK_RELAY_PIN, GPIO.OUT, initial=RELAY_OFF_STATE)
    print(f"✅ GPIO {BLACK_RELAY_PIN} initialized (BLACK RELAY OFF)")

    # Initialize YELLOW relay (GPIO 22)
    GPIO.setup(YELLOW_RELAY_PIN, GPIO.OUT, initial=RELAY_OFF_STATE)
    print(f"✅ GPIO {YELLOW_RELAY_PIN} initialized (YELLOW RELAY OFF)")

    print(f"   Relay type: {'ACTIVE-LOW' if RELAY_ACTIVE_LOW else 'ACTIVE-HIGH'}")

    # Verify both relays are off
    time.sleep(0.5)
    black_state = GPIO.input(BLACK_RELAY_PIN)
    yellow_state = GPIO.input(YELLOW_RELAY_PIN)

    if black_state == RELAY_OFF_STATE and yellow_state == RELAY_OFF_STATE:
        print(f"✅ Both relays confirmed OFF")
    else:
        print(f"⚠️ Warning: Black={black_state}, Yellow={yellow_state}")
        GPIO.output(BLACK_RELAY_PIN, RELAY_OFF_STATE)
        GPIO.output(YELLOW_RELAY_PIN, RELAY_OFF_STATE)
        print(f"   Forced both to OFF state")

    GPIO_AVAILABLE = True
except Exception as e:
    print(f"⚠️ GPIO setup failed: {e}")
    GPIO_AVAILABLE = False

# ============================================================================
# HTTP SESSION - OPTIMIZATION: Keep-alive connection
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

def check_pigpiod_running():
    """Check if pigpiod daemon is running"""
    try:
        result = subprocess.run(['pgrep', '-x', 'pigpiod'], 
                              capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            print("✅ pigpiod daemon is running")
            return True
        else:
            print("❌ pigpiod daemon is NOT running")
            print("   Start it with: sudo pigpiod")
            return False
    except Exception as e:
        print(f"⚠️ Could not check pigpiod status: {e}")
        return False

def init_pigpio():
    """Initialize pigpio connection"""
    global pi

    if not check_pigpiod_running():
        print("\n💡 TIP: Start pigpiod before running this script:")
        print("   sudo pigpiod")
        sys.exit(1)

    try:
        pi = pigpio.pi()
        if not pi.connected:
            print("❌ Failed to connect to pigpiod")
            sys.exit(1)
        print("✅ pigpiod connected")
        return True
    except Exception as e:
        print(f"❌ Error connecting to pigpiod: {e}")
        sys.exit(1)

# ============================================================================
# SENSOR DATA - TWO UART SENSORS
# ============================================================================

sensor_lock_1 = threading.Lock()
sensor_data_1 = {
    'distances': [0] * 16,
    'last_update': 0,
    'frame_count': 0,
    'data_ready': False,
    'total_frames_received': 0
}

sensor_lock_2 = threading.Lock()
sensor_data_2 = {
    'distances': [0] * 16,
    'last_update': 0,
    'frame_count': 0,
    'data_ready': False,
    'total_frames_received': 0
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
            print("\n🧹 Cleaning up GPIO...")
            GPIO.output(BLACK_RELAY_PIN, RELAY_OFF_STATE)
            GPIO.output(YELLOW_RELAY_PIN, RELAY_OFF_STATE)
            print(f"   GPIO {BLACK_RELAY_PIN} set to OFF (BLACK relay)")
            print(f"   GPIO {YELLOW_RELAY_PIN} set to OFF (YELLOW relay)")
            GPIO.cleanup()
            print("✅ GPIO cleaned up")
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")

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
# HTTP COMMUNICATION - OPTIMIZED FOR SPEED
# ============================================================================

def send_action_http(team, action, detection_time):
    """
    Ultra-fast HTTP with backend confirmation:
    - Persistent HTTP session (keep-alive)
    - Low timeout values
    - Relay triggers ONLY after backend confirms
    - Handles side switch notification + automatic sensor swap
    """
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

            if DEBUG_HTTP:
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

                # TRIGGER RELAY ONLY AFTER BACKEND CONFIRMS
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
                error_msg = (response.json().get('error', 'Unknown')
                           if response.status_code == 200
                           else f"HTTP {response.status_code}")
                print(f"❌ [{timestamp}] Backend error: {error_msg}")
                return False

        except requests.exceptions.Timeout:
            print(f"⚠️ Backend timeout (>{HTTP_TIMEOUT*1000:.0f}ms)")
            return False
        except requests.exceptions.ConnectionError:
            print(f"❌ Connection error - Is backend running at {SERVER_URL}?")
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
                print(f"   Progress: {collected}/{CALIBRATION_SAMPLES}")

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

    last_frame_print = 0

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
                                sensor_data['total_frames_received'] += 1
                                sensor_data['data_ready'] = True

                            # Print frame info periodically for debugging
                            if DEBUG_UART_DATA and (time.time() - last_frame_print > 2.0):
                                print(f"📡 [{sensor_name}] Frame #{sensor_data['total_frames_received']}: {distances[:8]}...")
                                last_frame_print = time.time()

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
    """
    Instant detection of hand removal:
    - Detects hand removal in ~5ms
    - Sends HTTP immediately (non-blocking)
    - Relay triggers only after backend confirms
    """
    team = team_info_local['team']
    sensor_num = team_info_local['num']

    if detected:
        if not state['active']:
            state['active'] = True
            state['start_time'] = current_time
            if DEBUG_DETECTION:
                print(f'👋 [{timestamp}] [S{sensor_num}-{team.upper()}] Detection started')

        duration = current_time - state['start_time']
        if duration > MAX_DETECTION_TIMEOUT:
            if DEBUG_DETECTION:
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
    print("🏓 Padel Scoreboard - DUAL PICO UART OPTIMIZED")
    print("="*70)
    print("⚡ HARDWARE:")
    print(f"   • Pico 1 (Black): VL53L5CX → GPIO {PICO_1_GPIO} @ {BAUD_RATE} baud")
    print(f"   • Pico 2 (Yellow): VL53L5CX → GPIO {PICO_2_GPIO} @ {BAUD_RATE} baud")
    print(f"   • Black Relay: GPIO {BLACK_RELAY_PIN}")
    print(f"   • Yellow Relay: GPIO {YELLOW_RELAY_PIN}")
    print("\n⚡ OPTIMIZATIONS:")
    print(f"   • Sensor polling: {LOOP_SLEEP_TIME*1000:.1f}ms (200 Hz)")
    print(f"   • HTTP timeout: {HTTP_TIMEOUT*1000:.0f}ms")
    print(f"   • Keep-alive: {'ENABLED' if USE_SESSION else 'DISABLED'}")
    print(f"   • Relay trigger: After backend confirms")
    print(f"   • Side switch: Auto sensor swap on odd games")
    print("="*70)

    # Initialize pigpio
    init_pigpio()

    # Test backend connectivity
    print("\n🔗 Testing backend connectivity...")
    try:
        response = requests.get(f"{SERVER_URL}/health", timeout=2)
        if response.status_code == 200:
            print(f"✅ Backend is running at {SERVER_URL}")
        else:
            print(f"⚠️ Backend responded with status {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot connect to backend: {e}")
        print(f"   Make sure padel_backend.py is running")
        print("   Continue anyway? (Ctrl+C to quit)")
        time.sleep(3)

    # Start UART reader threads
    print("\n📡 Starting UART readers...")
    uart_thread1 = threading.Thread(
        target=uart_reader_thread,
        args=(PICO_1_GPIO, sensor_data_1, sensor_lock_1, "PICO_1_BLACK"),
        daemon=True
    )
    uart_thread1.start()

    uart_thread2 = threading.Thread(
        target=uart_reader_thread,
        args=(PICO_2_GPIO, sensor_data_2, sensor_lock_2, "PICO_2_YELLOW"),
        daemon=True
    )
    uart_thread2.start()

    # Wait and verify data reception
    print("\n⏳ Waiting for UART data from both Picos...")
    for i in range(10):
        time.sleep(1)
        frames1 = sensor_data_1['total_frames_received']
        frames2 = sensor_data_2['total_frames_received']
        print(f"   [{i+1}s] PICO_1: {frames1} frames, PICO_2: {frames2} frames")

        if frames1 > 0 and frames2 > 0:
            print("\n✅ Both sensors receiving data!")
            break
    else:
        print("\n⚠️ WARNING: Not all sensors are receiving data!")
        print(f"   PICO_1 frames: {sensor_data_1['total_frames_received']}")
        print(f"   PICO_2 frames: {sensor_data_2['total_frames_received']}")
        print("\n💡 Check:")
        print("   1. Pico connections (GPIO 23, 24, GND)")
        print("   2. Pico firmware is running")
        print("   3. Baud rate = 57600")
        print("   4. Long cables (40m) - signal integrity")
        print("\n   Continue anyway? (Ctrl+C to quit)")
        time.sleep(5)

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

    # Team mapping (will swap on side switch)
    team_info = {
        'sensor1': {'team': BLACK_TEAM, 'num': 1},
        'sensor2': {'team': YELLOW_TEAM, 'num': 2}
    }

    print("\n🚀 System Ready - Ultra-Low Latency Mode!")
    print(f"   Black relay (GPIO {BLACK_RELAY_PIN}): {GPIO.input(BLACK_RELAY_PIN)} = OFF")
    print(f"   Yellow relay (GPIO {YELLOW_RELAY_PIN}): {GPIO.input(YELLOW_RELAY_PIN)} = OFF")
    print("   Wave hand at sensors to score!")
    print("="*70)

    try:
        while True:
            current_time = time.time()
            timestamp = time.strftime('%H:%M:%S')

            # Process Sensor 1 (initially Black)
            res1, det1 = process_sensor(
                baseline1, median_windows1, movavg_windows1, last_valid1,
                sensor_data_1, sensor_lock_1
            )
            if res1 is not None:
                process_single_sensor(detection_states['sensor1'], det1,
                                    current_time, timestamp, team_info['sensor1'])

            # Process Sensor 2 (initially Yellow)
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
