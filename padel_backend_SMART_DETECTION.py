#!/usr/bin/env python3
"""
Padel Scoreboard Backend - Software UART Configuration (GPIO 23 & 24)
Uses named pipes from pigpio_uart_bridge.py for dual Pico communication

Key behavior:
- All addpoint/subtractpoint are IGNORED for scoring until a game mode is chosen (gamemode is None).
- /setgamemode accepts "basic", "competition", "lock", or null (to clear).
- ✅ NO SIDE SWITCH NOTIFICATION when match is won (2-0, 2-1, etc.)
- ✅ Automatic ball detection via VL53L5CX sensors through Picos
- ✅ Reads from named pipes as files (not serial ports)
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime
import threading
import logging
import os
import time
import pygame

app = Flask(__name__)
CORS(app, cors_allowed_origins="*")

# Silence werkzeug logs
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25
)

# ✅ INITIALIZE PYGAME MIXER FOR AUDIO
pygame.mixer.init()
print("🔊 Audio system initialized")

# ===== PICO UART CONFIGURATION (Named Pipes from Bridge) =====
PICO_CONFIGS = {
    "PICO_1": {
        "port": "/tmp/pico1_serial",
        "baudrate": 57600,
        "timeout": 1,
        "team": "black",
        "name": "PICO 1 (Black Team)"
    },
    "PICO_2": {
        "port": "/tmp/pico2_serial",
        "baudrate": 57600,
        "timeout": 1,
        "team": "yellow",
        "name": "PICO 2 (Yellow Team)"
    }
}


# ===== SMART DETECTION THRESHOLDS =====
CALIBRATION_SAMPLES = 10              # Number of samples for baseline calibration
DISTANCE_DROP_THRESHOLD = 500         # mm - Significant drop from baseline indicates ball
VERY_CLOSE_THRESHOLD = 300            # mm - Ball hit this sensor's side (other team scored)
MIN_TIME_BETWEEN_HITS = 1.0           # seconds - Debounce time


# ===== SENSOR/PICO STATE =====
sensor_validation = {
    "validated": False,
    "pico1_connected": False,
    "pico2_connected": False,
    "pico1_port": PICO_CONFIGS["PICO_1"]["port"],
    "pico2_port": PICO_CONFIGS["PICO_2"]["port"],
    "status": "pending",
    "error_message": None,
    "timestamp": None
}

pico_data = {
    "PICO_1": {
        "connected": False,
        "last_frame": None,
        "frame_count": 0,
        "error_count": 0,
        "last_detection": 0,
        "pipe_fd": None,
        "thread": None,
        # Calibration data
        "baseline_distance": None,
        "calibrated": False,
        "calibration_samples": []
    },
    "PICO_2": {
        "connected": False,
        "last_frame": None,
        "frame_count": 0,
        "error_count": 0,
        "last_detection": 0,
        "pipe_fd": None,
        "thread": None,
        # Calibration data
        "baseline_distance": None,
        "calibrated": False,
        "calibration_samples": []
    }
}

data_lock = threading.Lock()
sensor_running = True

# ===== SENSOR MAPPING (for side switching) =====
sensor_mapping = {
    "pico_1_team": "black",
    "pico_2_team": "yellow",
    "last_swap": None
}

def get_team_from_pico(pico_name):
    """Returns the current team assignment for a given Pico."""
    if pico_name == "PICO_1":
        return sensor_mapping["pico_1_team"]
    elif pico_name == "PICO_2":
        return sensor_mapping["pico_2_team"]
    return None

# ===== PICO VALIDATION =====
def test_pico_connection(pico_name, config):
    """Test if Pico named pipe exists"""
    try:
        return os.path.exists(config["port"])
    except Exception as e:
        return False

def validate_picos():
    """Validate that both Pico named pipes are available."""
    global sensor_validation
    print("🔌 Validating Raspberry Pi Pico connections (via named pipes)...")

    try:
        pico1_ok = test_pico_connection("PICO_1", PICO_CONFIGS["PICO_1"])
        pico2_ok = test_pico_connection("PICO_2", PICO_CONFIGS["PICO_2"])

        sensor_validation["pico1_connected"] = pico1_ok
        sensor_validation["pico2_connected"] = pico2_ok
        sensor_validation["timestamp"] = datetime.now().isoformat()

        if pico1_ok:
            print(f"✓ PICO_1 pipe found at {PICO_CONFIGS['PICO_1']['port']}")
        else:
            print(f"✗ PICO_1 pipe NOT found at {PICO_CONFIGS['PICO_1']['port']}")

        if pico2_ok:
            print(f"✓ PICO_2 pipe found at {PICO_CONFIGS['PICO_2']['port']}")
        else:
            print(f"✗ PICO_2 pipe NOT found at {PICO_CONFIGS['PICO_2']['port']}")

        if pico1_ok and pico2_ok:
            sensor_validation["validated"] = True
            sensor_validation["status"] = "valid"
            sensor_validation["error_message"] = None
            print("✓ Pico validation PASSED - Both named pipes available")
            print("💡 Make sure pigpio_uart_bridge.py is running!")
            return True
        elif not pico1_ok and not pico2_ok:
            sensor_validation["validated"] = False
            sensor_validation["status"] = "error"
            sensor_validation["error_message"] = "ERROR #1: No named pipes detected - Start pigpio_uart_bridge.py first!"
            print("✗ Pico validation FAILED - No named pipes detected")
            print("💡 RUN: python3 pigpio_uart_bridge.py")
            return False
        else:
            sensor_validation["validated"] = False
            sensor_validation["status"] = "warning"
            missing = "PICO_1" if not pico1_ok else "PICO_2"
            sensor_validation["error_message"] = f"WARNING: {missing} pipe not found - Partial operation"
            print(f"⚠ Pico validation PARTIAL - {missing} missing")
            return True

    except Exception as e:
        sensor_validation["validated"] = False
        sensor_validation["status"] = "error"
        sensor_validation["error_message"] = f"ERROR #1: Pico check failed - {str(e)}"
        sensor_validation["timestamp"] = datetime.now().isoformat()
        print(f"✗ Pico validation ERROR: {e}")
        return False

def run_initial_sensor_validation():
    time.sleep(2)
    validate_picos()
    socketio.emit('sensor_validation_result', sensor_validation)
    print(f"→ Pico validation result broadcasted: {sensor_validation['status']}")

# ===== PICO DATA READING THREADS =====
def read_pico_data(pico_name, config):
    """Thread function to continuously read data from one Pico via named pipe AS A FILE"""
    global sensor_running, pico_data

    pipe_fd = None
    reconnect_attempts = 0
    max_reconnect = 5

    print(f"📡 Starting reader thread for {pico_name}")

    while sensor_running:
        try:
            if pipe_fd is None:
                if not os.path.exists(config["port"]):
                    if reconnect_attempts == 0:
                        print(f"[{pico_name}] ⏳ Waiting for named pipe: {config['port']}")
                        print(f"[{pico_name}] 💡 Make sure pigpio_uart_bridge.py is running!")
                    time.sleep(2)
                    reconnect_attempts += 1
                    if reconnect_attempts > max_reconnect:
                        print(f"[{pico_name}] ✗ Named pipe not available after {max_reconnect} attempts")
                        break
                    continue

                # ✅ Open named pipe as a regular file (blocking mode)
                pipe_fd = open(config["port"], 'rb', buffering=0)

                with data_lock:
                    pico_data[pico_name]["connected"] = True
                    pico_data[pico_name]["pipe_fd"] = pipe_fd

                print(f"[{pico_name}] ✓ Connected to {config['port']}")
                reconnect_attempts = 0

            # Read from pipe line by line
            try:
                # Read one line
                line_bytes = b''
                while True:
                    byte = pipe_fd.read(1)
                    if not byte:
                        raise IOError("Pipe closed")
                    if byte == b'\n':
                        break
                    line_bytes += byte

                    # Prevent infinite loop on malformed data
                    if len(line_bytes) > 1000:
                        line_bytes = b''
                        break

                line = line_bytes.decode('utf-8', errors='ignore').strip()

                if line == "DATA_START":
                    zones = []
                    for i in range(16):
                        data_line_bytes = b''
                        while True:
                            byte = pipe_fd.read(1)
                            if not byte:
                                raise IOError("Pipe closed")
                            if byte == b'\n':
                                break
                            data_line_bytes += byte
                            if len(data_line_bytes) > 100:
                                break

                        data_line = data_line_bytes.decode('utf-8', errors='ignore').strip()
                        try:
                            distance, status = data_line.split(',')
                            zones.append({
                                "zone": i,
                                "distance_mm": int(distance),
                                "status": int(status)
                            })
                        except:
                            with data_lock:
                                pico_data[pico_name]["error_count"] += 1
                            continue

                    # Read DATA_END marker
                    end_marker_bytes = b''
                    while True:
                        byte = pipe_fd.read(1)
                        if not byte:
                            raise IOError("Pipe closed")
                        if byte == b'\n':
                            break
                        end_marker_bytes += byte
                        if len(end_marker_bytes) > 100:
                            break

                    end_marker = end_marker_bytes.decode('utf-8', errors='ignore').strip()

                    if end_marker == "DATA_END" and len(zones) == 16:
                        with data_lock:
                            pico_data[pico_name]["last_frame"] = zones
                            pico_data[pico_name]["frame_count"] += 1
                            pico_data[pico_name]["connected"] = True

                        process_smart_ball_detection(pico_name, zones)

            except IOError:
                raise

        except (IOError, OSError) as e:
            with data_lock:
                pico_data[pico_name]["connected"] = False

            if pipe_fd:
                try:
                    pipe_fd.close()
                except:
                    pass
                pipe_fd = None

            reconnect_attempts += 1

            if reconnect_attempts <= max_reconnect:
                print(f"[{pico_name}] ⚠ Connection lost. Reconnecting... ({reconnect_attempts}/{max_reconnect})")
                time.sleep(2)
            else:
                print(f"[{pico_name}] ✗ Max reconnection attempts reached. Stopping thread.")
                break

        except Exception as e:
            with data_lock:
                pico_data[pico_name]["error_count"] += 1
            time.sleep(0.1)

    if pipe_fd:
        try:
            pipe_fd.close()
        except:
            pass

    print(f"[{pico_name}] Thread stopped")


# ===== CALIBRATION LOGIC =====
def calibrate_sensor(pico_name):
    """
    Calibrate sensor by measuring baseline distance (no ball present)
    Takes multiple samples and averages them
    """
    global pico_data

    print(f"🔧 [{pico_name}] Starting calibration...")
    print(f"    Please ensure NO BALL is in front of sensor!")

    samples = []
    with data_lock:
        pico_data[pico_name]["calibration_samples"] = []
        pico_data[pico_name]["calibrated"] = False

    # Collect baseline samples
    for i in range(CALIBRATION_SAMPLES):
        with data_lock:
            last_frame = pico_data[pico_name]["last_frame"]

        if last_frame and len(last_frame) == 16:
            # Get minimum distance from all zones
            min_distance = min(zone["distance_mm"] for zone in last_frame)
            samples.append(min_distance)
            print(f"    Sample {i+1}/{CALIBRATION_SAMPLES}: {min_distance}mm")

        time.sleep(0.2)  # 200ms between samples

    # Calculate baseline if we got enough samples
    if len(samples) >= CALIBRATION_SAMPLES // 2:  # At least half the samples
        baseline = sum(samples) / len(samples)

        with data_lock:
            pico_data[pico_name]["baseline_distance"] = baseline
            pico_data[pico_name]["calibrated"] = True
            pico_data[pico_name]["calibration_samples"] = samples

        team = get_team_from_pico(pico_name)
        print(f"✓ [{pico_name}] Calibration COMPLETE!")
        print(f"    Baseline: {baseline:.0f}mm | Team: {team.upper()}")
        print(f"    Detection threshold: {DISTANCE_DROP_THRESHOLD}mm drop from baseline")

        # Broadcast calibration complete event
        socketio.emit('calibration_complete', {
            "pico": pico_name,
            "baseline": baseline,
            "team": team,
            "samples": len(samples),
            "timestamp": datetime.now().isoformat()
        })

        return True
    else:
        print(f"✗ [{pico_name}] Calibration FAILED - Not enough valid samples")
        return False

def auto_calibrate_all_sensors():
    """Auto-calibrate both sensors when they're both connected"""
    print("\n" + "="*70)
    print("AUTO-CALIBRATION STARTING")
    print("="*70)

    # Wait for both sensors to have data
    max_wait = 10
    for i in range(max_wait):
        with data_lock:
            pico1_ready = pico_data["PICO_1"]["last_frame"] is not None
            pico2_ready = pico_data["PICO_2"]["last_frame"] is not None

        if pico1_ready and pico2_ready:
            break

        print(f"Waiting for sensor data... ({i+1}/{max_wait})")
        time.sleep(1)

    # Calibrate both
    pico1_ok = calibrate_sensor("PICO_1")
    time.sleep(0.5)
    pico2_ok = calibrate_sensor("PICO_2")

    if pico1_ok and pico2_ok:
        print("\n✓ AUTO-CALIBRATION COMPLETE - System ready for ball detection!")
        print("="*70 + "\n")
        return True
    else:
        print("\n⚠ AUTO-CALIBRATION INCOMPLETE - Some sensors failed")
        print("="*70 + "\n")
        return False

def process_smart_ball_detection(pico_name, zones):
    """
    SMART BALL DETECTION with calibration baseline
    - Checks if sensor is calibrated
    - Calculates distance drop from baseline
    - Determines add vs subtract based on proximity threshold
    """
    global pico_data, game_state

    with data_lock:
        if not pico_data[pico_name]["calibrated"]:
            return  # Not calibrated yet, skip detection

        baseline = pico_data[pico_name]["baseline_distance"]
        last_detection = pico_data[pico_name]["last_detection"]

    # Get minimum distance from all 16 zones
    min_distance = min(zone["distance_mm"] for zone in zones)

    # Calculate distance drop from baseline
    distance_drop = baseline - min_distance

    # Check if significant drop detected (ball passing through)
    if distance_drop > DISTANCE_DROP_THRESHOLD:
        current_time = time.time()

        # Debounce check
        if current_time - last_detection < MIN_TIME_BETWEEN_HITS:
            return

        with data_lock:
            pico_data[pico_name]["last_detection"] = current_time

        team = get_team_from_pico(pico_name)

        # ✅ SMART DECISION: ADD or SUBTRACT based on final distance
        if min_distance < VERY_CLOSE_THRESHOLD:
            # Ball hit VERY CLOSE to this sensor = Ball bounced on THIS side = OTHER team scored
            action = "subtract"
            target_team = get_opposite_team(team)
            print(f"🎾 Ball VERY CLOSE on {pico_name} ({min_distance}mm) → OTHER team scored → ADD to {target_team.upper()}")
        else:
            # Ball passed but didn't get very close = Ball went over net = THIS team scored
            action = "add"
            target_team = team
            print(f"🎾 Ball detected on {pico_name} (Distance: {min_distance}mm, Drop: {distance_drop:.0f}mm) → ADD to {team.upper()}")

        # Only process if game mode is selected
        if game_state["gamemode"] is not None:
            process_add_point(target_team)
        else:
            print(f"⚠ Ball detected but game mode not selected - ignoring")


def get_opposite_team(team):
    """Get the opposite team"""
    return "yellow" if team == "black" else "black"


def start_pico_readers():
    """Start reader threads for both Picos"""
    global pico_data

    for pico_name, config in PICO_CONFIGS.items():
        thread = threading.Thread(
            target=read_pico_data,
            args=(pico_name, config),
            daemon=True
        )
        thread.start()
        pico_data[pico_name]["thread"] = thread
        print(f"✓ Reader thread started for {pico_name}")

# ===== GAME STATE =====
game_state = {
    "game1": 0, "game2": 0,
    "set1": 0, "set2": 0,
    "point1": 0, "point2": 0,
    "score1": 0, "score2": 0,
    "matchwon": False,
    "winner": None,
    "sethistory": [],
    "matchhistory": [],
    "matchstarttime": datetime.now().isoformat(),
    "matchendtime": None,
    "lastupdated": datetime.now().isoformat(),
    "shouldswitchsides": False,
    "totalgamesinset": 0,
    "initial_switch_done": False,
    "mode": "normal",
    "gamemode": None
}

match_storage = {
    "matchcompleted": False,
    "matchdata": {
        "winnerteam": None,
        "winnername": None,
        "finalsetsscore": None,
        "detailedsets": [],
        "matchduration": None,
        "totalpointswon": {"black": 0, "yellow": 0},
        "totalgameswon": {"black": 0, "yellow": 0},
        "setsbreakdown": [],
        "matchsummary": None
    },
    "displayshown": False
}

# ===== AUDIO PLAYBACK =====
def play_change_audio():
    """Play change.mp3 when side switch is required"""
    try:
        if os.path.exists('change.mp3'):
            pygame.mixer.music.load('change.mp3')
            pygame.mixer.music.play()
            print("🔊 Playing change.mp3")
        else:
            print("⚠️ change.mp3 not found in directory")
    except Exception as e:
        print(f"❌ Error playing audio: {e}")

# ===== SIDE SWITCHING =====
def trigger_basic_mode_side_switch_if_needed():
    """BASIC MODE: Trigger side switch immediately when a new set starts."""
    global game_state

    if game_state["matchwon"]:
        print("⛔ BASIC MODE: Side switch skipped - match already won")
        return

    if game_state["gamemode"] != "basic":
        return

    total_games = game_state["game1"] + game_state["game2"]
    set1 = game_state["set1"]
    set2 = game_state["set2"]
    total_sets = set1 + set2

    if total_sets == 0 and total_games == 0:
        print(f"→ BASIC MODE: Skipping side switch at match start (0-0, 0-0)")
        return

    if (total_games == 0 and total_sets in [1, 2] and not game_state.get("initial_switch_done", False)):
        game_state["initial_switch_done"] = True
        game_state["shouldswitchsides"] = True
        game_state["totalgamesinset"] = 0
        broadcast_sideswitch()
        print(f"→ BASIC MODE: Side switch triggered at START of set (Sets {set1}-{set2}, Games 0-0)")

def check_side_switch():
    """Switch after odd games in competition/lock; basic only switches at start-of-set."""
    global game_state

    if game_state["matchwon"]:
        print("⛔ Side switch check skipped - match already won")
        return False

    total_games = game_state["game1"] + game_state["game2"]
    mode = game_state["gamemode"]

    if mode == "basic":
        return False

    if (total_games % 2) == 1:
        game_state["shouldswitchsides"] = True
        game_state["totalgamesinset"] = total_games
        return True

    game_state["shouldswitchsides"] = False
    return False

# ===== SOCKET.IO HANDLERS =====
@socketio.on('connect')
def handle_connect():
    print(f"✓ Client connected: {request.sid}")
    emit('gamestateupdate', game_state)
    emit('sensor_validation_result', sensor_validation)
    if game_state["gamemode"] == "basic":
        trigger_basic_mode_side_switch_if_needed()
    return True

@socketio.on('disconnect')
def handle_disconnect():
    print(f"✗ Client disconnected: {request.sid}")

@socketio.on('request_gamestate')
def handle_request_gamestate():
    emit('gamestateupdate', game_state)

@socketio.on('request_sensor_validation')
def handle_request_sensor_validation():
    emit('sensor_validation_result', sensor_validation)

# ===== BROADCAST HELPERS =====
def broadcast_gamestate():
    socketio.emit('gamestateupdate', game_state, namespace='/')

def broadcast_pointscored(team, actiontype):
    data = {
        "team": team,
        "action": actiontype,
        "gamestate": game_state,
        "timestamp": datetime.now().isoformat()
    }
    socketio.emit('pointscored', data, namespace='/')

def broadcast_sideswitch():
    """Only broadcast side switch if match is NOT won"""
    if game_state["matchwon"]:
        print("⛔ Side switch broadcast BLOCKED - match already won")
        return

    data = {
        "totalgames": game_state["totalgamesinset"],
        "gamescore": f"{game_state['game1']}-{game_state['game2']}",
        "setscore": f"{game_state['set1']}-{game_state['set2']}",
        "message": "CHANGE SIDES",
        "timestamp": datetime.now().isoformat()
    }
    socketio.emit('sideswitchrequired', data, namespace='/')
    play_change_audio()
    print(f"→ Side switch broadcasted | Total games: {data['totalgames']}, Score: {data['gamescore']}")

def broadcast_matchwon():
    data = {
        "winner": game_state["winner"],
        "matchdata": match_storage["matchdata"],
        "timestamp": datetime.now().isoformat()
    }
    socketio.emit('matchwon', data, namespace='/')
    print(f"🏆 Match won broadcast sent - winner: {game_state['winner']['team']}")

# ===== HISTORY =====
def add_to_history(action, team, scorebefore, scoreafter, gamebefore, gameafter, setbefore, setafter):
    global game_state
    history_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "team": team,
        "scores": {
            "before": {"score1": scorebefore[0], "score2": scorebefore[1]},
            "after": {"score1": scoreafter[0], "score2": scoreafter[1]}
        },
        "games": {
            "before": {"game1": gamebefore[0], "game2": gamebefore[1]},
            "after": {"game1": gameafter[0], "game2": gameafter[1]}
        },
        "sets": {
            "before": {"set1": setbefore[0], "set2": setbefore[1]},
            "after": {"set1": setafter[0], "set2": setafter[1]}
        }
    }
    game_state["matchhistory"].append(history_entry)

def calculate_match_statistics():
    global game_state
    black_points = len([h for h in game_state["matchhistory"] if h["action"] == "point" and h["team"] == "black"])
    yellow_points = len([h for h in game_state["matchhistory"] if h["action"] == "point" and h["team"] == "yellow"])
    black_games = len([h for h in game_state["matchhistory"] if h["action"] == "game" and h["team"] == "black"])
    yellow_games = len([h for h in game_state["matchhistory"] if h["action"] == "game" and h["team"] == "yellow"])

    sets_breakdown = []
    for i, set_score in enumerate(game_state["sethistory"], 1):
        if "-" in set_score:
            games = set_score.split("-")
            black_g = int(games[0].split("(")[0])
            yellow_g = int(games[1].split("(")[0])
            sets_breakdown.append({
                "setnumber": i,
                "blackgames": black_g,
                "yellowgames": yellow_g,
                "setwinner": "black" if black_g > yellow_g else "yellow"
            })

    return {
        "totalpoints": {"black": black_points, "yellow": yellow_points},
        "totalgames": {"black": black_games, "yellow": yellow_games},
        "setsbreakdown": sets_breakdown
    }

def store_match_data():
    global game_state, match_storage
    if not game_state["matchwon"] or not game_state["winner"]:
        return

    stats = calculate_match_statistics()
    start_time = datetime.fromisoformat(game_state["matchstarttime"])
    end_time = datetime.fromisoformat(game_state["matchendtime"])
    duration_seconds = int((end_time - start_time).total_seconds())
    duration_minutes = duration_seconds // 60
    duration_text = f"{duration_minutes}m {duration_seconds % 60}s" if duration_minutes > 0 else f"{duration_seconds}s"

    sets_display = []
    for breakdown in stats["setsbreakdown"]:
        sets_display.append(f"{breakdown['blackgames']}-{breakdown['yellowgames']}")

    match_storage["matchcompleted"] = True
    match_storage["matchdata"] = {
        "winnerteam": game_state["winner"]["team"],
        "winnername": game_state["winner"]["teamname"],
        "finalsetsscore": game_state["winner"]["finalsets"],
        "detailedsets": sets_display,
        "matchduration": duration_text,
        "totalpointswon": stats["totalpoints"],
        "totalgameswon": stats["totalgames"],
        "setsbreakdown": stats["setsbreakdown"],
        "matchsummary": create_match_summary(stats, sets_display),
        "timestamp": game_state["matchendtime"]
    }
    match_storage["displayshown"] = False
    print(f"✅ Match data stored: {match_storage['matchdata']['winnername']} wins {match_storage['matchdata']['finalsetsscore']}")

def create_match_summary(stats, sets_display):
    sets_text = ", ".join(sets_display)
    return f"Sets: {sets_text} | Points: {stats['totalpoints']['black']}-{stats['totalpoints']['yellow']} | Games: {stats['totalgames']['black']}-{stats['totalgames']['yellow']}"

def wipe_match_storage():
    global match_storage
    match_storage = {
        "matchcompleted": False,
        "matchdata": {
            "winnerteam": None,
            "winnername": None,
            "finalsetsscore": None,
            "detailedsets": [],
            "matchduration": None,
            "totalpointswon": {"black": 0, "yellow": 0},
            "totalgameswon": {"black": 0, "yellow": 0},
            "setsbreakdown": [],
            "matchsummary": None
        },
        "displayshown": False
    }

# ===== SET & MATCH LOGIC =====
def check_set_winner():
    global game_state
    g1 = game_state["game1"]
    g2 = game_state["game2"]
    s1 = game_state["set1"]
    s2 = game_state["set2"]

    if g1 >= 6 and g1 - g2 >= 2:
        set_before = (s1, s2)
        game_state["set1"] += 1
        game_state["sethistory"].append(f"{g1}-{g2}")
        add_to_history("set", "black",
                      (game_state["score1"], game_state["score2"]), (0, 0),
                      (g1, g2), (0, 0), set_before, (game_state["set1"], game_state["set2"]))
        game_state["game1"] = 0
        game_state["game2"] = 0
        game_state["totalgamesinset"] = 0
        game_state["shouldswitchsides"] = False
        game_state["initial_switch_done"] = False
        print(f"→ Set won by BLACK. Score: {game_state['set1']}-{game_state['set2']}. Flag reset for new set.")

        match_won = check_match_winner()

        if not match_won:
            trigger_basic_mode_side_switch_if_needed()

        return match_won

    if g2 >= 6 and g2 - g1 >= 2:
        set_before = (s1, s2)
        game_state["set2"] += 1
        game_state["sethistory"].append(f"{g1}-{g2}")
        add_to_history("set", "yellow",
                      (game_state["score1"], game_state["score2"]), (0, 0),
                      (g1, g2), (0, 0), set_before, (game_state["set1"], game_state["set2"]))
        game_state["game1"] = 0
        game_state["game2"] = 0
        game_state["totalgamesinset"] = 0
        game_state["shouldswitchsides"] = False
        game_state["initial_switch_done"] = False
        print(f"→ Set won by YELLOW. Score: {game_state['set1']}-{game_state['set2']}. Flag reset for new set.")

        match_won = check_match_winner()

        if not match_won:
            trigger_basic_mode_side_switch_if_needed()

        return match_won

    if g1 == 6 and g2 == 6 and game_state["mode"] == "normal":
        if (s1 == 0 and s2 == 0) or (s1 == 1 and s2 == 0) or (s1 == 0 and s2 == 1):
            print("→ Entering NORMAL TIE BREAK mode")
            game_state["mode"] = "tiebreak"
            game_state["point1"] = 0
            game_state["point2"] = 0
            game_state["score1"] = 0
            game_state["score2"] = 0
        elif s1 == 1 and s2 == 1:
            print("→ Entering SUPER TIE BREAK mode (decider)")
            game_state["mode"] = "supertiebreak"
            game_state["point1"] = 0
            game_state["point2"] = 0
            game_state["score1"] = 0
            game_state["score2"] = 0

    return False

def check_match_winner():
    global game_state

    if game_state["set1"] == 2:
        game_state["matchwon"] = True
        game_state["matchendtime"] = datetime.now().isoformat()

        total_black_games = 0
        total_yellow_games = 0
        for set_score in game_state["sethistory"]:
            if "-" in set_score:
                parts = set_score.split("-")
                total_black_games += int(parts[0].split("(")[0])
                total_yellow_games += int(parts[1].split("(")[0])

        total_black_games += game_state["game1"]
        total_yellow_games += game_state["game2"]

        game_state["winner"] = {
            "team": "black",
            "teamname": "BLACK TEAM",
            "finalsets": f"{game_state['set1']}-{game_state['set2']}",
            "matchsummary": ", ".join(game_state["sethistory"]),
            "totalgameswon": total_black_games,
            "matchduration": calculate_match_duration()
        }
        add_to_history("match", "black",
                      (game_state["score1"], game_state["score2"]),
                      (game_state["score1"], game_state["score2"]),
                      (game_state["game1"], game_state["game2"]),
                      (game_state["game1"], game_state["game2"]),
                      (game_state["set1"], game_state["set2"]),
                      (game_state["set1"], game_state["set2"]))
        store_match_data()
        print(f"🏆 MATCH WON by BLACK - Side switches now DISABLED")
        return True

    if game_state["set2"] == 2:
        game_state["matchwon"] = True
        game_state["matchendtime"] = datetime.now().isoformat()

        total_black_games = 0
        total_yellow_games = 0
        for set_score in game_state["sethistory"]:
            if "-" in set_score:
                parts = set_score.split("-")
                total_black_games += int(parts[0].split("(")[0])
                total_yellow_games += int(parts[1].split("(")[0])

        total_black_games += game_state["game1"]
        total_yellow_games += game_state["game2"]

        game_state["winner"] = {
            "team": "yellow",
            "teamname": "YELLOW TEAM",
            "finalsets": f"{game_state['set1']}-{game_state['set2']}",
            "matchsummary": ", ".join(game_state["sethistory"]),
            "totalgameswon": total_yellow_games,
            "matchduration": calculate_match_duration()
        }
        add_to_history("match", "yellow",
                      (game_state["score1"], game_state["score2"]),
                      (game_state["score1"], game_state["score2"]),
                      (game_state["game1"], game_state["game2"]),
                      (game_state["game1"], game_state["game2"]),
                      (game_state["set1"], game_state["set2"]),
                      (game_state["set1"], game_state["set2"]))
        store_match_data()
        print(f"🏆 MATCH WON by YELLOW - Side switches now DISABLED")
        return True

    return False

def calculate_match_duration():
    if game_state["matchendtime"]:
        start = datetime.fromisoformat(game_state["matchstarttime"])
        end = datetime.fromisoformat(game_state["matchendtime"])
        duration = end - start
        total_minutes = int(duration.total_seconds() // 60)
        return f"{total_minutes} minutes"
    return "In progress"

# ===== SCORING =====
def set_normal_score_from_points():
    p1 = game_state["point1"]
    p2 = game_state["point2"]
    def mappoint(p):
        if p == 0: return 0
        if p == 1: return 15
        if p == 2: return 30
        return 40
    game_state["score1"] = mappoint(p1)
    game_state["score2"] = mappoint(p2)

def reset_points():
    game_state["point1"] = 0
    game_state["point2"] = 0
    game_state["score1"] = 0
    game_state["score2"] = 0

def handle_normal_game_win(team):
    if team == "black":
        game_state["game1"] += 1
    else:
        game_state["game2"] += 1
    reset_points()
    check_set_winner()

def handle_tiebreak_win(team):
    g1 = game_state["game1"]
    g2 = game_state["game2"]
    tb_score = f"({game_state['point2']})" if team == "black" else f"({game_state['point1']})"
    set_before = (game_state["set1"], game_state["set2"])

    if team == "black":
        game_state["set1"] += 1
        game_state["sethistory"].append(f"7-6{tb_score}")
        add_to_history("set", "black",
                      (game_state["score1"], game_state["score2"]), (0, 0),
                      (g1, g2), (0, 0), set_before, (game_state["set1"], game_state["set2"]))
    else:
        game_state["set2"] += 1
        game_state["sethistory"].append(f"6-7{tb_score}")
        add_to_history("set", "yellow",
                      (game_state["score1"], game_state["score2"]), (0, 0),
                      (g1, g2), (0, 0), set_before, (game_state["set1"], game_state["set2"]))

    game_state["game1"] = 0
    game_state["game2"] = 0
    game_state["totalgamesinset"] = 0
    game_state["shouldswitchsides"] = False
    game_state["initial_switch_done"] = False
    reset_points()
    game_state["mode"] = "normal"
    print("→ Tie-break won. New set starting. Flag reset for new set.")

    match_won = check_match_winner()

    if not match_won:
        trigger_basic_mode_side_switch_if_needed()

def handle_supertiebreak_win(team):
    set_before = (game_state["set1"], game_state["set2"])

    if team == "black":
        game_state["set1"] += 1
        game_state["sethistory"].append(f"10-{game_state['point2']}(STB)")
        add_to_history("set", "black",
                      (game_state["score1"], game_state["score2"]), (0, 0),
                      (game_state["game1"], game_state["game2"]), (0, 0),
                      set_before, (game_state["set1"], game_state["set2"]))
    else:
        game_state["set2"] += 1
        game_state["sethistory"].append(f"{game_state['point1']}-10(STB)")
        add_to_history("set", "yellow",
                      (game_state["score1"], game_state["score2"]), (0, 0),
                      (game_state["game1"], game_state["game2"]), (0, 0),
                      set_before, (game_state["set1"], game_state["set2"]))

    game_state["initial_switch_done"] = False
    reset_points()
    game_state["mode"] = "normal"
    print("→ Super tie-break won. Match ending.")
    check_match_winner()

def scoring_gamemode_selected():
    """Returns True only if gamemode is one of the allowed modes."""
    return game_state["gamemode"] in ("basic", "competition", "lock")

def process_add_point(team):
    global game_state

    if not scoring_gamemode_selected():
        broadcast_pointscored(team, "addpoint")
        return {"success": True, "ignored": True, "message": "Point ignored until mode is selected", "gamestate": game_state}

    if game_state["matchwon"]:
        return {"success": False, "error": "Match is already completed",
                "winner": game_state["winner"], "matchwon": True}

    score_before = (game_state["score1"], game_state["score2"])
    game_before = (game_state["game1"], game_state["game2"])
    set_before = (game_state["set1"], game_state["set2"])
    action_type = "point"
    game_just_won = False
    phase_mode = game_state["mode"]

    if team == "black":
        game_state["point1"] += 1
    else:
        game_state["point2"] += 1

    p1 = game_state["point1"]
    p2 = game_state["point2"]

    if phase_mode == "normal":
        set_normal_score_from_points()
        if team == "black":
            if p1 >= 4 and p1 - p2 >= 2:
                handle_normal_game_win("black")
                action_type = "game"
                game_just_won = True
        else:
            if p2 >= 4 and p2 - p1 >= 2:
                handle_normal_game_win("yellow")
                action_type = "game"
                game_just_won = True

    elif phase_mode == "tiebreak":
        game_state["score1"] = game_state["point1"]
        game_state["score2"] = game_state["point2"]
        if team == "black":
            if p1 >= 7 and p1 - p2 >= 2:
                handle_tiebreak_win("black")
                action_type = "set"
        else:
            if p2 >= 7 and p2 - p1 >= 2:
                handle_tiebreak_win("yellow")
                action_type = "set"

    elif phase_mode == "supertiebreak":
        game_state["score1"] = game_state["point1"]
        game_state["score2"] = game_state["point2"]
        if team == "black":
            if p1 >= 10 and p1 - p2 >= 2:
                handle_supertiebreak_win("black")
                action_type = "set"
        else:
            if p2 >= 10 and p2 - p1 >= 2:
                handle_supertiebreak_win("yellow")
                action_type = "set"

    if not game_state["matchwon"]:
        add_to_history(action_type, team,
                      score_before, (game_state["score1"], game_state["score2"]),
                      game_before, (game_state["game1"], game_state["game2"]),
                      set_before, (game_state["set1"], game_state["set2"]))

    game_state["lastupdated"] = datetime.now().isoformat()

    sideswitchneeded = False
    if game_just_won and not game_state["matchwon"] and game_state["mode"] == "normal":
        sideswitchneeded = check_side_switch()
        if sideswitchneeded:
            broadcast_sideswitch()

    broadcast_gamestate()

    if game_state["matchwon"]:
        broadcast_matchwon()
    else:
        broadcast_pointscored(team, action_type)

    response = {
        "success": True,
        "message": f"Point added to team {team}",
        "gamestate": game_state,
        "matchwon": game_state["matchwon"],
        "winner": game_state["winner"] if game_state["matchwon"] else None
    }

    if game_state["shouldswitchsides"]:
        response["sideswitch"] = {
            "required": True,
            "totalgames": game_state["totalgamesinset"],
            "gamescore": f"{game_state['game1']}-{game_state['game2']}",
            "setscore": f"{game_state['set1']}-{game_state['set2']}",
        }
        game_state["shouldswitchsides"] = False
        print(f"✅ Side switch signal sent in HTTP response, flag cleared")

    return response

def process_subtract_point(team):
    """Simple subtraction of internal raw point; no undo of games/sets."""
    global game_state

    if not scoring_gamemode_selected():
        broadcast_pointscored(team, "subtractpoint")
        return {"success": True, "ignored": True, "message": "Subtraction ignored until mode is selected", "gamestate": game_state}

    if game_state["matchwon"]:
        return {"success": False, "error": "Cannot subtract points from completed match"}

    score_before = (game_state["score1"], game_state["score2"])
    game_before = (game_state["game1"], game_state["game2"])
    set_before = (game_state["set1"], game_state["set2"])

    if team == "black":
        game_state["point1"] = max(0, game_state["point1"] - 1)
    else:
        game_state["point2"] = max(0, game_state["point2"] - 1)

    if game_state["mode"] == "normal":
        set_normal_score_from_points()
    else:
        game_state["score1"] = game_state["point1"]
        game_state["score2"] = game_state["point2"]

    add_to_history("point_subtract", team,
                  score_before, (game_state["score1"], game_state["score2"]),
                  game_before, (game_state["game1"], game_state["game2"]),
                  set_before, (game_state["set1"], game_state["set2"]))

    game_state["lastupdated"] = datetime.now().isoformat()
    broadcast_gamestate()

    return {"success": True, "message": f"Point subtracted from team {team}", "gamestate": game_state}

# ===== FLASK ROUTES =====
@app.route("/")
def serve_scoreboard():
    return send_from_directory(".", "padel_scoreboard.html")

@app.route("/<path:filename>")
def serve_static_files(filename):
    if os.path.exists(filename):
        return send_from_directory(".", filename)
    return f"File {filename} not found", 404

@app.route("/addpoint", methods=["POST"])
def addpoint():
    try:
        data = request.get_json() or {}
        team = data.get("team", "black")
        result = process_add_point(team)
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/subtractpoint", methods=["POST"])
def subtractpoint():
    try:
        data = request.get_json() or {}
        team = data.get("team", "black")
        result = process_subtract_point(team)
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/gamestate", methods=["GET"])
def getgamestate():
    response_data = game_state.copy()
    response_data["matchstorageavailable"] = match_storage["matchcompleted"] and not match_storage["displayshown"]
    return jsonify(response_data)

@app.route("/sensorvalidation", methods=["GET"])
def getsensorvalidation():
    return jsonify(sensor_validation)

@app.route("/picodata", methods=["GET"])
def getpicodata():
    """Get current Pico connection status and last frame data"""
    with data_lock:
        data = {
            "PICO_1": {
                "connected": pico_data["PICO_1"]["connected"],
                "frame_count": pico_data["PICO_1"]["frame_count"],
                "error_count": pico_data["PICO_1"]["error_count"],
                "team": sensor_mapping["pico_1_team"],
                "last_frame": pico_data["PICO_1"]["last_frame"]
            },
            "PICO_2": {
                "connected": pico_data["PICO_2"]["connected"],
                "frame_count": pico_data["PICO_2"]["frame_count"],
                "error_count": pico_data["PICO_2"]["error_count"],
                "team": sensor_mapping["pico_2_team"],
                "last_frame": pico_data["PICO_2"]["last_frame"]
            }
        }
    return jsonify({"success": True, "pico_data": data})

@app.route("/getmatchdata", methods=["GET"])
def getmatchdata():
    global match_storage
    if not match_storage["matchcompleted"]:
        return jsonify({"success": False, "error": "No completed match data"}), 404
    return jsonify({"success": True, "matchdata": match_storage["matchdata"], "displayshown": match_storage["displayshown"]})

@app.route("/markmatchdisplayed", methods=["POST"])
def markmatchdisplayed():
    global match_storage
    if not match_storage["matchcompleted"]:
        return jsonify({"success": False, "error": "No match data"}), 400

    match_storage["displayshown"] = True
    wipe_immediately = request.get_json().get("wipeimmediately", True) if request.get_json() else True

    if wipe_immediately:
        wipe_match_storage()
        message = "Match data wiped"
    else:
        message = "Match data marked as displayed"

    return jsonify({"success": True, "message": message})

@app.route("/setgamemode", methods=["POST"])
def setgamemode():
    """Set game mode to 'basic' | 'competition' | 'lock' | null (to clear)."""
    global game_state
    try:
        data = request.get_json() or {}
        mode = data.get("mode", None)

        if mode is None:
            game_state["gamemode"] = None
            game_state["initial_switch_done"] = False
            print("Game mode cleared (None)")
            broadcast_gamestate()
            return jsonify({"success": True, "message": "Game mode cleared", "gamemode": None})

        if mode not in ("basic", "competition", "lock"):
            return jsonify({"success": False, "error": "Invalid mode. Must be basic, competition, lock, or null"}), 400

        game_state["gamemode"] = mode
        game_state["initial_switch_done"] = False
        print(f"Game mode set to {mode.upper()}")
        broadcast_gamestate()

        if mode == "basic":
            trigger_basic_mode_side_switch_if_needed()

        return jsonify({"success": True, "message": f"Game mode set to {mode}", "gamemode": mode})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/resetmatch", methods=["POST"])
def resetmatch():
    global game_state, match_storage

    wipe_match_storage()

    game_state.update({
        "game1": 0, "game2": 0,
        "set1": 0, "set2": 0,
        "point1": 0, "point2": 0,
        "score1": 0, "score2": 0,
        "matchwon": False,
        "winner": None,
        "sethistory": [],
        "matchhistory": [],
        "matchstarttime": datetime.now().isoformat(),
        "matchendtime": None,
        "lastupdated": datetime.now().isoformat(),
        "shouldswitchsides": False,
        "totalgamesinset": 0,
        "mode": "normal",
        "initial_switch_done": False
    })

    broadcast_gamestate()
    print("✅ Match reset - all scores cleared, side switches re-enabled")

    return jsonify({"success": True, "message": "Match reset successfully", "gamestate": game_state})

@app.route("/swappicos", methods=["POST"])
def swap_picos():
    """Swap Pico team assignments: PICO_1 ↔ PICO_2"""
    global sensor_mapping

    old_pico1 = sensor_mapping["pico_1_team"]
    old_pico2 = sensor_mapping["pico_2_team"]

    sensor_mapping["pico_1_team"] = old_pico2
    sensor_mapping["pico_2_team"] = old_pico1
    sensor_mapping["last_swap"] = datetime.now().isoformat()

    print(f"🔄 Picos swapped: PICO_1={sensor_mapping['pico_1_team']}, PICO_2={sensor_mapping['pico_2_team']}")

    socketio.emit('sensor_mapping_updated', sensor_mapping, namespace='/')

    return jsonify({
        "success": True,
        "message": "Picos swapped successfully",
        "mapping": {
            "pico_1_team": sensor_mapping["pico_1_team"],
            "pico_2_team": sensor_mapping["pico_2_team"]
        },
        "timestamp": sensor_mapping["last_swap"]
    })

@app.route("/getsensormapping", methods=["GET"])
def get_sensor_mapping():
    """Get current Pico to team mapping"""
    return jsonify({"success": True, "mapping": sensor_mapping})


@app.route("/calibrate", methods=["POST"])
def manual_calibrate():
    """Manually trigger calibration for one or both sensors"""
    try:
        data = request.get_json() or {}
        pico = data.get("pico", "all")  # "PICO_1", "PICO_2", or "all"

        results = {}

        if pico == "all" or pico == "PICO_1":
            results["PICO_1"] = calibrate_sensor("PICO_1")

        if pico == "all" or pico == "PICO_2":
            results["PICO_2"] = calibrate_sensor("PICO_2")

        return jsonify({
            "success": all(results.values()),
            "results": results,
            "message": "Calibration complete" if all(results.values()) else "Some calibrations failed"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/calibration_status", methods=["GET"])
def get_calibration_status():
    """Get current calibration status for both sensors"""
    with data_lock:
        status = {
            "PICO_1": {
                "calibrated": pico_data["PICO_1"]["calibrated"],
                "baseline": pico_data["PICO_1"]["baseline_distance"],
                "team": sensor_mapping["pico_1_team"]
            },
            "PICO_2": {
                "calibrated": pico_data["PICO_2"]["calibrated"],
                "baseline": pico_data["PICO_2"]["baseline_distance"],
                "team": sensor_mapping["pico_2_team"]
            }
        }

    return jsonify({"success": True, "calibration": status})

@app.route("/health", methods=["GET"])
def healthcheck():
    logoexists = os.path.exists("logo.png")
    backexists = os.path.exists("back.png")
    changeaudioexists = os.path.exists("change.mp3")

    with data_lock:
        pico_status = {
            "PICO_1": {
                "connected": pico_data["PICO_1"]["connected"],
                "frames": pico_data["PICO_1"]["frame_count"],
                "errors": pico_data["PICO_1"]["error_count"]
            },
            "PICO_2": {
                "connected": pico_data["PICO_2"]["connected"],
                "frames": pico_data["PICO_2"]["frame_count"],
                "errors": pico_data["PICO_2"]["error_count"]
            }
        }

    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "socketio": "enabled",
        "gamestate": game_state,
        "matchstatus": "completed" if game_state["matchwon"] else "in-progress",
        "historyentries": len(game_state["matchhistory"]),
        "matchstorage": {"completed": match_storage["matchcompleted"], "displayed": match_storage["displayshown"]},
        "sensorvalidation": sensor_validation,
        "pico_status": pico_status,
        "files": {
            "logo.png": "found" if logoexists else "missing",
            "back.png": "found" if backexists else "missing",
            "change.mp3": "found" if changeaudioexists else "missing"
        }
    })

if __name__ == "__main__":
    print("=" * 70)
    print("Padel Scoreboard Backend - SOFTWARE UART CONFIGURATION 🎾")
    print("=" * 70)
    print("HARDWARE SETUP (GPIO 23 & 24 via pigpio bridge)")
    print("  PICO_1: {} → Team {}".format(PICO_CONFIGS["PICO_1"]["port"], sensor_mapping["pico_1_team"].upper()))
    print("  PICO_2: {} → Team {}".format(PICO_CONFIGS["PICO_2"]["port"], sensor_mapping["pico_2_team"].upper()))
    print("=" * 70)
    print("⚠️  IMPORTANT: Start pigpio_uart_bridge.py FIRST!")
    print("   Run in another terminal: python3 pigpio_uart_bridge.py")
    print("=" * 70)
    print("GAME MODES")
    print("  BASIC: Side switch at start of each set (0-0 states).")
    print("         ❌ NO switch at match start (0-0, 0-0)")
    print("         ❌ NO switch after match won (2-0, 2-1, etc.)")
    print("  COMPETITION/LOCK: Switch after odd games (1,3,5,7...).")
    print("                     ❌ NO switch after match won")
    print("=" * 70)
    print("DETECTION SETTINGS:")
    print(f"  Distance drop threshold: {DISTANCE_DROP_THRESHOLD}mm")
    print(f"  Very close threshold: {VERY_CLOSE_THRESHOLD}mm")
    print(f"  Debounce time: {MIN_TIME_BETWEEN_HITS}s")
    print("="*70)    print("✅ Smart ball detection active")
    print("✅ Detection threshold: {}mm".format(DETECTION_THRESHOLD))
    print("=" * 70)
    print("Socket.IO enabled for real-time updates")
    print("Access at http://127.0.0.1:5000")
    print("=" * 70)

    validation_thread = threading.Thread(target=run_initial_sensor_validation, daemon=True)
    validation_thread.start()


    # Start Pico reader threads
    time.sleep(3)
    if sensor_validation["validated"] or sensor_validation["status"] == "warning":
        start_pico_readers()

        # Auto-calibrate sensors after 5 seconds
        def delayed_calibration():
            time.sleep(5)
            auto_calibrate_all_sensors()

        calibration_thread = threading.Thread(target=delayed_calibration, daemon=True)
        calibration_thread.start()


    try:
        socketio.run(app, debug=False, host="127.0.0.1", port=5000, allow_unsafe_werkzeug=True)
    finally:
        sensor_running = False
        print("\n🛑 Shutting down sensor threads...")
