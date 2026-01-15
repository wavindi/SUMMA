#!/usr/bin/env python3
"""
VL53L5CX Dual Sensors - DUAL SOFTWARE UART MODE (GPIO 23 & 24)
Ultra-low latency with side switching and auto sensor swap
"""

import time
import collections
import statistics
import requests
import RPi.GPIO as GPIO
import sys
import atexit
import threading
import pigpio

# ============================================================================
# CONFIGURATION - DUAL SOFTWARE UART
# ============================================================================
SERVER_URL = 'http://localhost:5000'
ADD_POINT_URL = f'{SERVER_URL}/addpoint'
SUBTRACT_POINT_URL = f'{SERVER_URL}/subtractpoint'
RESET_MATCH_URL = f'{SERVER_URL}/resetmatch'

# Software UART pins (RX only - we only receive from Picos)
PICO1_RX_PIN = 23  # Connects to Pico 1 TX
PICO2_RX_PIN = 24  # Connects to Pico 2 TX
UART_BAUD = 57600

# Relay pins (MOVED from 23/24 to avoid conflict)
BLACK_RELAY_PIN = 17
YELLOW_RELAY_PIN = 27

# Calibration & Filtering
CALIBRATION_SAMPLES = 60
MEDIAN_WINDOW = 3
MOVING_AVG_WINDOW = 1
OUTLIER_THRESHOLD = 100
MAX_VALID_CALIBRATION = 150
MIN_VALID_CALIBRATION = 0

# Detection
DETECTION_THRESHOLD = 8
MIN_ZONES_FOR_DETECTION = 3
GOOD_ZONES = [0, 5, 6, 9, 10, 11, 12, 13]
AUTO_RESET_THRESHOLD = 80
AUTO_RESET_RAW_LIMIT = 20

# Timing windows for actions
ADD_POINT_WINDOW = (0.15, 3.0)
SUBTRACT_POINT_WINDOW = (3.0, 7.0)
RESET_MATCH_WINDOW = (7.5, 15.0)
MAX_DETECTION_TIMEOUT = 15.5

# Teams
BLACK_TEAM = 'black'
YELLOW_TEAM = 'yellow'

# ============================================================================
# OPTIMIZATION SETTINGS
# ============================================================================
LOOP_SLEEP_TIME = 0.005  # 5ms polling
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
# GPIO SETUP
# ============================================================================
GPIO.setwarnings(False)
try:
    GPIO.setmode(GPIO.BCM)
    # Initialize BLACK relay (GPIO 17)
    GPIO.setup(BLACK_RELAY_PIN, GPIO.OUT, initial=RELAY_OFF_STATE)
    print(f"✅ GPIO {BLACK_RELAY_PIN} initialized: BLACK RELAY OFF")
    
    # Initialize YELLOW relay (GPIO 27)
    GPIO.setup(YELLOW_RELAY_PIN, GPIO.OUT, initial=RELAY_OFF_STATE)
    print(f"✅ GPIO {YELLOW_RELAY_PIN} initialized: YELLOW RELAY OFF")
    
    print(f"   Relay type: {'ACTIVE-LOW' if RELAY_ACTIVE_LOW else 'ACTIVE-HIGH'}")
    
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
# HTTP SESSION
# ============================================================================
if USE_SESSION:
    http_session = requests.Session()
    http_session.headers.update({'Connection': 'keep-alive'})
    print("✅ HTTP session created (keep-alive enabled)")
else:
    http_session = requests

# ============================================================================
# DUAL UART DATA STORAGE
# ============================================================================
pico1_sensor_lock = threading.Lock()
pico1_sensor_data = {
    'distances': [0] * 16,
    'last_update': 0,
    'frame_count': 0,
    'data_ready': False
}

pico2_sensor_lock = threading.Lock()
pico2_sensor_data = {
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

def cleanup_gpio():
    """Clean up GPIO on exit - ensure both relays are OFF."""
    if GPIO_AVAILABLE:
        try:
            print("\n🧹 Cleaning up GPIO...")
            GPIO.output(BLACK_RELAY_PIN, RELAY_OFF_STATE)
            GPIO.output(YELLOW_RELAY_PIN, RELAY_OFF_STATE)
            print(f"   GPIO {BLACK_RELAY_PIN} set to {RELAY_OFF_STATE} (BLACK relay OFF)")
            print(f"   GPIO {YELLOW_RELAY_PIN} set to {RELAY_OFF_STATE} (YELLOW relay OFF)")
            GPIO.cleanup()
            print("✅ GPIO cleaned up")
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")

atexit.register(cleanup_gpio)

# ============================================================================
# TEAM ASSIGNMENT SWAP
# ============================================================================
def swap_team_assignments():
    """Swap which sensor controls which team."""
    global teams_swapped, team_info
    
    if team_info is None:
        print("⚠️ team_info not initialized, cannot swap assignments")
        return
    
    teams_swapped = not teams_swapped
    
    if teams_swapped:
        team_info['sensor1']['team'] = YELLOW_TEAM
        team_info['sensor2']['team'] = BLACK_TEAM
        print("🔄 Teams swapped: Pico1→YELLOW, Pico2→BLACK")
    else:
        team_info['sensor1']['team'] = BLACK_TEAM
        team_info['sensor2']['team'] = YELLOW_TEAM
        print("🔄 Teams restored: Pico1→BLACK, Pico2→YELLOW")

# ============================================================================
# HTTP COMMUNICATION
# ============================================================================
def send_action_http(team, action, detection_time):
    """Ultra-fast HTTP with backend confirmation and relay trigger."""
    
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
                
                # Side switch handling
                side_switch = response_data.get('sideswitch')
                if side_switch:
                    print(f"🔄 [{timestamp_confirm}] SIDE SWITCH REQUIRED!")
                    print(f"   Total games played: {side_switch.get('totalgames')}")
                    print(f"   Current score: {side_switch.get('gamescore')}")
                    print(f"   Set score: {side_switch.get('setscore')}")
                    print("   🏃 Players should change court sides now!")
                    swap_team_assignments()
                
                # Trigger relay only after backend confirms
                if action == 'add':
                    if team == BLACK_TEAM:
                        relay_thread = threading.Thread(
                            target=relay_pulse,
                            args=(BLACK_RELAY_PIN, BLACK_TEAM, 1.0),
                            daemon=True
                        )
                        relay_thread.start()
                    elif team == YELLOW_TEAM:
                        relay_thread = threading.Thread(
                            target=relay_pulse,
                            args=(YELLOW_RELAY_PIN, YELLOW_TEAM, 1.0),
                            daemon=True
                        )
                        relay_thread.start()
                
                return True
            else:
                error_msg = (response.json().get('error', 'Unknown')
                            if response.status_code == 200
                            else f"HTTP {response.status_code}")
                print(f"❌ [{timestamp}] Backend error ({response_time:.1f}ms): {error_msg}")
                return False
        
        except requests.exceptions.Timeout:
            print(f"⚠️ Backend timeout (>{HTTP_TIMEOUT*1000:.0f}ms)")
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
# SOFTWARE UART READER THREADS
# ============================================================================
def software_uart_reader_thread(pi_gpio, rx_pin, sensor_data, sensor_lock, sensor_name):
    """Background thread to read software UART data from Pico."""
    
    try:
        pi_gpio.set_mode(rx_pin, pigpio.INPUT)
        pi_gpio.bb_serial_read_open(rx_pin, UART_BAUD)
        print(f"✅ {sensor_name} Software UART opened on GPIO {rx_pin}")
    except Exception as e:
        print(f"❌ {sensor_name} UART setup failed: {e}")
        return
    
    reading_data = False
    data_buffer = []
    incomplete_line = ""
    
    while True:
        try:
            (count, data) = pi_gpio.bb_serial_read(rx_pin)
            
            if count > 0:
                text = incomplete_line + data.decode('utf-8', errors='ignore')
                lines = text.split('\n')
                
                # Last item might be incomplete
                incomplete_line = lines[-1]
                lines = lines[:-1]
                
                for line in lines:
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
                    
                    elif line and (line.startswith("PICO") or 
                                  line.startswith("CONFIG") or 
                                  line.startswith("READY") or
                                  line.startswith("ERROR")):
                        print(f"  [{sensor_name}] {line}")
            else:
                time.sleep(0.001)
        
        except Exception as e:
            print(f"⚠️ {sensor_name} read error: {e}")
            time.sleep(0.1)

# ============================================================================
# CALIBRATION
# ============================================================================
def calibrate_pico_baseline(sensor_data, sensor_lock, name):
    """Calibrate sensor baseline via Software UART."""
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
    
    baseline = {i: (statistics.median(samples[i]) if samples[i] else 20) 
                for i in range(16)}
    print(f"✅ {name} calibrated ({collected} samples)")
    return baseline

# ============================================================================
# SENSOR PROCESSING
# ============================================================================
def process_remote_sensor_generic(sensor_data, sensor_lock, baseline, 
                                   median_windows, movavg_windows, last_valid):
    """Process remote sensor data from any UART source."""
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
# DETECTION STATE MACHINE
# ============================================================================
def process_single_sensor(state, detected, current_time, timestamp, team_info_local):
    """Instant detection of hand removal with HTTP confirmation before relay."""
    
    team = team_info_local['team']
    sensor_num = team_info_local['num']
    
    if detected:
        if not state['active']:
            state['active'] = True
            state['start_time'] = current_time
            print(f'👋 [{timestamp}] [Pico{sensor_num}-{team.upper()}] Detection started')
        
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
    print("🏓 Padel Scoreboard - DUAL SOFTWARE UART MODE")
    print("="*70)
    print("⚡ CONFIGURATION:")
    print(f"   • Pico 1 (Black): GPIO {PICO1_RX_PIN} (Software UART RX)")
    print(f"   • Pico 2 (Yellow): GPIO {PICO2_RX_PIN} (Software UART RX)")
    print(f"   • Black Relay: GPIO {BLACK_RELAY_PIN}")
    print(f"   • Yellow Relay: GPIO {YELLOW_RELAY_PIN}")
    print(f"   • Baud Rate: {UART_BAUD}")
    print(f"   • Polling Rate: {1000*LOOP_SLEEP_TIME:.1f}ms ({1/LOOP_SLEEP_TIME:.0f} Hz)")
    print(f"   • HTTP Timeout: {HTTP_TIMEOUT*1000:.0f}ms")
    print(f"   • Side Switch: Auto sensor swap enabled")
    print("="*70)
    
    # Initialize pigpio
    pi = pigpio.pi()
    if not pi.connected:
        print("❌ pigpio daemon not running!")
        print("   Run: sudo systemctl start pigpiod")
        sys.exit(1)
    print("✅ pigpio connected")
    
    # Start UART reader threads
    pico1_thread = threading.Thread(
        target=software_uart_reader_thread,
        args=(pi, PICO1_RX_PIN, pico1_sensor_data, pico1_sensor_lock, "PICO1-BLACK"),
        daemon=True
    )
    pico1_thread.start()
    
    pico2_thread = threading.Thread(
        target=software_uart_reader_thread,
        args=(pi, PICO2_RX_PIN, pico2_sensor_data, pico2_sensor_lock, "PICO2-YELLOW"),
        daemon=True
    )
    pico2_thread.start()
    
    print("⏳ Waiting for Picos to boot (3s)...")
    time.sleep(3)
    
    # Check if data is coming from both Picos
    with pico1_sensor_lock:
        pico1_ready = pico1_sensor_data['data_ready']
    with pico2_sensor_lock:
        pico2_ready = pico2_sensor_data['data_ready']
    
    if not pico1_ready:
        print("⚠️ Warning: No data from Pico 1 yet")
    if not pico2_ready:
        print("⚠️ Warning: No data from Pico 2 yet")
    
    # Calibration
    print("\n" + "="*70)
    print("🎯 Calibrating sensors (keep hands away)...")
    print("="*70)
    baseline1 = calibrate_pico_baseline(pico1_sensor_data, pico1_sensor_lock, 'PICO1 (Black)')
    baseline2 = calibrate_pico_baseline(pico2_sensor_data, pico2_sensor_lock, 'PICO2 (Yellow)')
    
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
    
    print("\n🚀 System Ready - Dual Software UART Mode!")
    print(f"   Black relay (GPIO {BLACK_RELAY_PIN}): {GPIO.input(BLACK_RELAY_PIN)} = OFF")
    print(f"   Yellow relay (GPIO {YELLOW_RELAY_PIN}): {GPIO.input(YELLOW_RELAY_PIN)} = OFF")
    print("   Wave hand at sensors to score!")
    print("="*70)
    
    try:
        while True:
            current_time = time.time()
            timestamp = time.strftime('%H:%M:%S')
            
            # Process Pico 1 (initially Black team sensor)
            res1, det1 = process_remote_sensor_generic(
                pico1_sensor_data, pico1_sensor_lock,
                baseline1, median_windows1, movavg_windows1, last_valid1
            )
            if res1 is not None:
                process_single_sensor(
                    detection_states['sensor1'], det1, 
                    current_time, timestamp, team_info['sensor1']
                )
            
            # Process Pico 2 (initially Yellow team sensor)
            res2, det2 = process_remote_sensor_generic(
                pico2_sensor_data, pico2_sensor_lock,
                baseline2, median_windows2, movavg_windows2, last_valid2
            )
            if res2 is not None:
                process_single_sensor(
                    detection_states['sensor2'], det2,
                    current_time, timestamp, team_info['sensor2']
                )
            
            time.sleep(LOOP_SLEEP_TIME)
    
    except KeyboardInterrupt:
        print('\n🛑 Stopping...')
    finally:
        pi.bb_serial_read_close(PICO1_RX_PIN)
        pi.bb_serial_read_close(PICO2_RX_PIN)
        pi.stop()
        cleanup_gpio()
        if USE_SESSION:
            http_session.close()
        print('✅ Stopped cleanly')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        cleanup_gpio()
        sys.exit(1)
