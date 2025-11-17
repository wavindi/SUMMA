#!/usr/bin/env python3

"""
VL53L5CX Dual Sensors Detection - FIXED Duration-Based Action System
- Sensor 1 = black team (LED: GPIO 18)
- Sensor 2 = yellow team (LED: GPIO 23)
- Waits for complete detection duration, then sends appropriate action to backend:
  * 0.2-3.0s: Send add_point with detection_time
  * 3.5-10.0s: Send subtract_point with detection_time  
  * 10.5-15.0s: Send reset_match with detection_time
- LED turns green after 0.2s and stays on until detection ends
- FIXED: Proper state management, no more detection spam
"""

import time
import collections
import statistics
import requests
import RPi.GPIO as GPIO
import sys
import atexit
from vl53l5cx_ctypes import VL53L5CX

# Server configuration - Enhanced for duration-based actions
SERVER_URL = 'http://localhost:5000'
ADD_POINT_URL = f'{SERVER_URL}/add_point'
SUBTRACT_POINT_URL = f'{SERVER_URL}/subtract_point'
RESET_MATCH_URL = f'{SERVER_URL}/reset_match'

# GPIO setup (with error handling)
try:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(18, GPIO.OUT)  # Black LED
    GPIO.setup(23, GPIO.OUT)  # Yellow LED
    black_led = GPIO.PWM(18, 100)
    yellow_led = GPIO.PWM(23, 100)
    black_led.start(0)
    yellow_led.start(0)
    GPIO_AVAILABLE = True
except Exception as e:
    print(f"⚠️ GPIO setup failed: {e} - Running without LEDs")
    black_led = yellow_led = None
    GPIO_AVAILABLE = False

def led_green_on(led_pwm, brightness=80):
    """Turn LED green at specified brightness (0-100)"""
    if GPIO_AVAILABLE and led_pwm:
        try:
            led_pwm.ChangeDutyCycle(brightness)
        except:
            pass

def led_green_off(led_pwm):
    """Turn LED off"""
    if GPIO_AVAILABLE and led_pwm:
        try:
            led_pwm.ChangeDutyCycle(0)
        except:
            pass

def cleanup_leds():
    """Clean up GPIO on exit"""
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

# Calibration settings
CALIBRATION_SAMPLES = 60
MEDIAN_WINDOW = 3
MOVING_AVG_WINDOW = 1
OUTLIER_THRESHOLD = 100
MAX_VALID_CALIBRATION = 50
MIN_VALID_CALIBRATION = 3

# Detection settings
DETECTION_THRESHOLD = 8
MIN_ZONES_FOR_DETECTION = 3
GOOD_ZONES = [0, 5, 6, 9, 10, 11, 12, 13]

# Auto-reset settings
AUTO_RESET_THRESHOLD = 80
AUTO_RESET_RAW_LIMIT = 20

# Time-based action windows (in seconds)
ADD_POINT_WINDOW = (0.2, 3.0)      # Add point after detection in this range
SUBTRACT_POINT_WINDOW = (3.5, 10.0) # Subtract point after detection in this range
RESET_MATCH_WINDOW = (10.5, 15.0)   # Reset match after detection in this range
LED_ACTIVATION_THRESHOLD = 0.2      # LED on after this duration
MAX_DETECTION_TIMEOUT = 15.5        # Timeout if detection > 15.5s

# Team names
BLACK_TEAM = 'black'
YELLOW_TEAM = 'yellow'

# Sensor I2C addresses
SENSOR1_ADDR = 0x29
SENSOR2_ADDR = 0x39

def send_action_http(team, action, detection_time):
    """Send action to backend with detection duration information"""
    
    if action == 'add':
        url = ADD_POINT_URL
        payload = {
            'team': team,
            'action_type': 'add_point',
            'detection_time': detection_time,
            'duration_seconds': round(detection_time, 2)
        }
        action_text = "Add point"
    elif action == 'subtract':
        url = SUBTRACT_POINT_URL
        payload = {
            'team': team,
            'action_type': 'subtract_point', 
            'detection_time': detection_time,
            'duration_seconds': round(detection_time, 2)
        }
        action_text = "Subtract point"
    elif action == 'reset':
        url = RESET_MATCH_URL
        payload = {
            'action': 'reset_match',
            'triggered_by': team if team else 'sensor',
            'detection_time': detection_time,
            'duration_seconds': round(detection_time, 2)
        }
        action_text = "Reset match"
    else:
        print(f"❌ Unknown action: {action}")
        return False
    
    try:
        print(f"📤 [{time.strftime('%H:%M:%S')}] Sending to backend: {action_text} for {team.upper() if team else 'MATCH'} (duration: {detection_time:.2f}s)")
        response = requests.post(url, json=payload, timeout=3)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ [{time.strftime('%H:%M:%S')}] {action_text} confirmed by backend - Duration: {detection_time:.2f}s")
                return True
            else:
                print(f"❌ [{time.strftime('%H:%M:%S')}] Backend rejected {action_text}: {data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ [{time.strftime('%H:%M:%S')}] HTTP error {response.status_code} for {action_text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ [{time.strftime('%H:%M:%S')}] Network error sending {action_text}: {e}")
        return False
    except Exception as e:
        print(f"❌ [{time.strftime('%H:%M:%S')}] Error sending {action_text}: {e}")
        return False

def determine_action(detection_duration):
    """Determine action based on total detection duration"""
    if ADD_POINT_WINDOW[0] <= detection_duration <= ADD_POINT_WINDOW[1]:
        return 'add'
    elif SUBTRACT_POINT_WINDOW[0] <= detection_duration <= SUBTRACT_POINT_WINDOW[1]:
        return 'subtract'
    elif RESET_MATCH_WINDOW[0] <= detection_duration <= RESET_MATCH_WINDOW[1]:
        return 'reset'
    else:
        return None  # No valid action

def median_filter(window, value):
    """Apply median filter to reduce noise"""
    window.append(value)
    if len(window) < 2:
        return value
    return statistics.median(window)

def moving_average(window, value):
    """Apply moving average for smoothing"""
    window.append(value)
    return sum(window) / len(window)

def calibrate_baseline(sensor, name):
    """Calibrate baseline with spike filtering"""
    print(f"📊 Calibrating {name} (target: {CALIBRATION_SAMPLES} valid samples)...")
    samples = {i: [] for i in range(16)}
    collected = 0
    rejected = 0
    total_attempts = 0
    
    while collected < CALIBRATION_SAMPLES:
        total_attempts += 1
        if sensor.data_ready():
            data = sensor.get_data()
            valid_sample = True
            zone_readings = []
            
            for i in range(16):
                try:
                    val = int(data.distance_mm[0][i])
                except:
                    val = 0
                
                if MIN_VALID_CALIBRATION < val < MAX_VALID_CALIBRATION:
                    zone_readings.append((i, val))
                elif val >= MAX_VALID_CALIBRATION:
                    valid_sample = False
                    break
            
            if valid_sample and len(zone_readings) > 12:
                for zone_idx, val in zone_readings:
                    samples[zone_idx].append(val)
                collected += 1
                
                if collected % 10 == 0:
                    print(f"  {name}: {collected}/{CALIBRATION_SAMPLES} samples collected")
            else:
                rejected += 1
        time.sleep(0.02)
    
    baseline = {}
    for i in range(16):
        if samples[i]:
            baseline[i] = statistics.median(samples[i])
        else:
            baseline[i] = 0
            print(f"  ⚠️ {name} zone {i}: No valid samples, defaulting to 0")
    
    print(f"✅ {name} calibration complete!")
    print(f"  Valid: {collected} | Rejected: {rejected} | Total: {total_attempts}")
    return baseline

def process_sensor(sensor, baseline, median_windows, movavg_windows, last_valid):
    """Process sensor data with filtering and outlier rejection"""
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
    """Main detection loop - FIXED state management"""
    print("🏓 Padel Scoreboard FIXED Duration-Based Sensor System Starting...")
    print("=" * 70)
    
    # Initialize sensors
    print("🔧 Initializing sensors...")
    try:
        sensor1 = VL53L5CX(i2c_addr=SENSOR1_ADDR)
        sensor2 = VL53L5CX(i2c_addr=SENSOR2_ADDR)
        
        sensor1.set_resolution(4*4)
        sensor2.set_resolution(4*4)
        sensor1.set_ranging_frequency_hz(15)
        sensor2.set_ranging_frequency_hz(15)
        
        sensor1.start_ranging()
        sensor2.start_ranging()
        time.sleep(2)
        print("✅ Sensors initialized")
    except Exception as e:
        print(f"❌ Sensor initialization failed: {e}")
        sys.exit(1)
    
    print("=" * 70)
    
    # Calibrate baselines
    print("🎯 Calibrating sensors...")
    baseline1 = calibrate_baseline(sensor1, 'Sensor 1 (Black Team)')
    baseline2 = calibrate_baseline(sensor2, 'Sensor 2 (Yellow Team)')
    print("=" * 70)
    
    # Initialize filtering windows
    median_windows1 = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
    movavg_windows1 = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
    last_valid1 = {i: None for i in range(16)}
    
    median_windows2 = {i: collections.deque(maxlen=MEDIAN_WINDOW) for i in range(16)}
    movavg_windows2 = {i: collections.deque(maxlen=MOVING_AVG_WINDOW) for i in range(16)}
    last_valid2 = {i: None for i in range(16)}
    
    # FIXED: Proper state management - global detection tracking
    detection_states = {
        'sensor1': {'active': False, 'start_time': None, 'led_activated': False},
        'sensor2': {'active': False, 'start_time': None, 'led_activated': False}
    }
    
    team_info = {
        'sensor1': {'team': BLACK_TEAM, 'led': black_led, 'num': 1},
        'sensor2': {'team': YELLOW_TEAM, 'led': yellow_led, 'num': 2}
    }
    
    print("🎯 Starting duration-based detection...")
    print(f" Detection threshold: {DETECTION_THRESHOLD}mm")
    print(f" Min zones required: {MIN_ZONES_FOR_DETECTION}")
    print(f" Action windows:")
    print(f"   ➕ Add point: {ADD_POINT_WINDOW[0]:.1f}s - {ADD_POINT_WINDOW[1]:.1f}s")
    print(f"   ➖ Subtract: {SUBTRACT_POINT_WINDOW[0]:.1f}s - {SUBTRACT_POINT_WINDOW[1]:.1f}s")
    print(f"   🔄 Reset: {RESET_MATCH_WINDOW[0]:.1f}s - {RESET_MATCH_WINDOW[1]:.1f}s")
    print(f"   🟢 LED activation: > {LED_ACTIVATION_THRESHOLD}s")
    print(f"   ⏰ Timeout: > {MAX_DETECTION_TIMEOUT}s")
    print("=" * 70)
    
    print("🚀 System ready! Object detection will measure full duration before action.")
    print("   Hold object longer for different actions:")
    print("   • 0.2-3.0s = Add point")
    print("   • 3.5-10.0s = Subtract point") 
    print("   • 10.5-15.0s = Reset match")
    print("=" * 70)
    
    try:
        consecutive_no_detection = 0
        detection_threshold_counter = 0
        
        while True:
            # Process both sensors
            res1, det1 = process_sensor(sensor1, baseline1, median_windows1, movavg_windows1, last_valid1)
            res2, det2 = process_sensor(sensor2, baseline2, median_windows2, movavg_windows2, last_valid2)
            
            if res1 is None or res2 is None:
                time.sleep(0.01)
                continue
            
            current_time = time.time()
            timestamp = time.strftime('%H:%M:%S')
            
            # Process Sensor 1 (BLACK)
            process_single_sensor(detection_states['sensor1'], det1, current_time, timestamp, 
                                team_info['sensor1'], baseline1, median_windows1, 
                                movavg_windows1, last_valid1, sensor1)
            
            # Process Sensor 2 (YELLOW) 
            process_single_sensor(detection_states['sensor2'], det2, current_time, timestamp,
                                team_info['sensor2'], baseline2, median_windows2, 
                                movavg_windows2, last_valid2, sensor2)
            
            time.sleep(0.05)  # 20Hz loop rate
    
    except KeyboardInterrupt:
        print('\n' + '=' * 70)
        print('🛑 Shutting down gracefully...')
    
    finally:
        led_green_off(black_led)
        led_green_off(yellow_led)
        sensor1.stop_ranging()
        sensor2.stop_ranging()
        cleanup_leds()
        print('✅ Sensors and LEDs stopped.')
        print('=' * 70)

def process_single_sensor(state, detected, current_time, timestamp, team_info, baseline, 
                         median_windows, movavg_windows, last_valid, sensor):
    """Process single sensor with proper state management"""
    team = team_info['team']
    led_pwm = team_info['led']
    sensor_num = team_info['num']
    
    if detected:
        # Object is detected
        if not state['active']:
            # NEW detection - start timing
            state['active'] = True
            state['start_time'] = current_time
            state['led_activated'] = False
            print(f'👋 [{timestamp}] [Sensor {sensor_num} - {team.upper()}] Object detected - measuring duration...')
        
        # Calculate duration
        duration = current_time - state['start_time']
        
        # Activate LED after threshold
        if duration >= LED_ACTIVATION_THRESHOLD and not state['led_activated']:
            led_green_on(led_pwm)
            state['led_activated'] = True
            print(f"🟢 [{timestamp}] [{team.upper()}] LED ON - Duration: {duration:.2f}s")
        
        # Log progress every 2 seconds during long detection
        if duration >= 2.0 and int(duration) % 2 == 0:
            print(f"⏳ [{timestamp}] [Sensor {sensor_num} - {team.upper()}] Measuring... {duration:.1f}s")
        
        # Timeout handling
        if duration > MAX_DETECTION_TIMEOUT:
            total_duration = duration
            print(f'⏰ [{timestamp}] [Sensor {sensor_num} - {team.upper()}] TIMEOUT - Total: {total_duration:.2f}s')
            led_green_off(led_pwm)
            action = determine_action(total_duration)
            if action:
                send_action_http(team, action, total_duration)
            state['active'] = False
            state['start_time'] = None
            state['led_activated'] = False
            return
    
    else:
        # No detection - check if we were previously detecting
        if state['active']:
            # Detection ENDED - process total duration
            total_duration = current_time - state['start_time']
            led_green_off(led_pwm)
            print(f'✋ [{timestamp}] [Sensor {sensor_num} - {team.upper()}] Detection ended - Total: {total_duration:.2f}s')
            
            # Determine and send appropriate action
            action = determine_action(total_duration)
            if action:
                success = send_action_http(team, action, total_duration)
                if success:
                    print(f"🎯 [{timestamp}] [{team.upper()}] Action completed: {action.upper()}")
                else:
                    print(f"❌ [{timestamp}] [{team.upper()}] Action failed: {action.upper()}")
            else:
                print(f"ℹ️  [{timestamp}] [{team.upper()}] Duration {total_duration:.2f}s - No action (outside valid windows)")
            
            # Reset state
            state['active'] = False
            state['start_time'] = None
            state['led_activated'] = False

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        cleanup_leds()
        sys.exit(1)
