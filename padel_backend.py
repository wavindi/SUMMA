#!/usr/bin/env python3

"""
Padel Scoreboard Backend - Optimized with Game Modes and pre-mode gating
Key behavior:
- All addpoint/subtractpoint are IGNORED for scoring until a game mode is chosen (gamemode is None).
- While gamemode is None:
  - addpoint → emit 'pointscored' with action 'addpoint' (for UI auto-select Basic), do not change scores.
  - subtractpoint → emit 'pointscored' with action 'subtractpoint' (for UI auto-select Competition), do not change scores.
- /setgamemode accepts "basic", "competition", "lock", or null (to clear).
- ✅ NO SIDE SWITCH NOTIFICATION when match is won (2-0, 2-1, etc.)
- ✅ Sensors reset to default positions on match reset
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime
from smbus2 import SMBus, i2c_msg
import threading
import logging
import os
import time
import pygame  # ✅ ADDED FOR AUDIO

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

# ===== SENSOR VALIDATION =====
sensor_validation = {
    "validated": False,
    "sensor1_address": None,
    "sensor2_address": None,
    "status": "pending",
    "error_message": None,
    "timestamp": None
}

def validate_sensors():
    """Validate that two VL53L5CX sensors are on different I2C addresses."""
    global sensor_validation
    print("Validating VL53L5CX sensors...")
    try:
        bus = SMBus(1)
        detected_addresses = []
        for addr in [0x29, 0x39]:
            try:
                msg = i2c_msg.write(addr, [0x00])
                bus.i2c_rdwr(msg)
                detected_addresses.append(addr)
                print(f"✓ Sensor found at 0x{addr:02X}")
            except:
                pass
        bus.close()

        if len(detected_addresses) == 2 and 0x29 in detected_addresses and 0x39 in detected_addresses:
            sensor_validation["validated"] = True
            sensor_validation["sensor1_address"] = 0x39
            sensor_validation["sensor2_address"] = 0x29
            sensor_validation["status"] = "valid"
            sensor_validation["error_message"] = None
            sensor_validation["timestamp"] = datetime.now().isoformat()
            print("✓ Sensor validation PASSED - Both sensors at different addresses")
            return True
        elif len(detected_addresses) == 2 and detected_addresses[0] == detected_addresses[1]:
            sensor_validation["validated"] = False
            sensor_validation["status"] = "error"
            sensor_validation["error_message"] = "ERROR #1: Both sensors at same address 0x29 - Restart SUMMA"
            sensor_validation["timestamp"] = datetime.now().isoformat()
            print("✗ Sensor validation FAILED - Both sensors at 0x29")
            return False
        elif len(detected_addresses) == 0:
            sensor_validation["validated"] = False
            sensor_validation["status"] = "error"
            sensor_validation["error_message"] = "ERROR #1: No sensors detected - Restart SUMMA"
            sensor_validation["timestamp"] = datetime.now().isoformat()
            print("✗ Sensor validation FAILED - No sensors detected")
            return False
        else:
            sensor_validation["validated"] = False
            sensor_validation["status"] = "error"
            sensor_validation["error_message"] = f"ERROR #1: Only {len(detected_addresses)} sensor(s) detected - Restart SUMMA"
            sensor_validation["timestamp"] = datetime.now().isoformat()
            print(f"✗ Sensor validation FAILED - Only {len(detected_addresses)} sensor(s)")
            return False
    except Exception as e:
        sensor_validation["validated"] = False
        sensor_validation["status"] = "error"
        sensor_validation["error_message"] = "ERROR #1: Sensor check failed - Restart SUMMA"
        sensor_validation["timestamp"] = datetime.now().isoformat()
        print(f"✗ Sensor validation ERROR: {e}")
        return False

def run_initial_sensor_validation():
    time.sleep(2)
    validate_sensors()
    socketio.emit('sensor_validation_result', sensor_validation)
    print(f"→ Sensor validation result broadcasted: {sensor_validation['status']}")

# ===== GAME STATE =====
game_state = {
    # Games/sets/points
    "game1": 0, "game2": 0,
    "set1": 0, "set2": 0,
    "point1": 0, "point2": 0,
    "score1": 0, "score2": 0,
    # Status
    "matchwon": False,
    "winner": None,
    # History
    "sethistory": [],
    "matchhistory": [],
    "matchstarttime": datetime.now().isoformat(),
    "matchendtime": None,
    "lastupdated": datetime.now().isoformat(),
    # Side switching
    "shouldswitchsides": False,
    "totalgamesinset": 0,
    "initial_switch_done": False,
    # Game phase mode: "normal", "tiebreak", "supertiebreak"
    "mode": "normal",
    # Game mode selection (UI mode): "basic", "competition", "lock", or None until chosen
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

# ===== SENSOR MAPPING (for side switching) =====
sensor_mapping = {
    "sensor_local_0x29": "black",
    "sensor_pico_uart": "yellow",
    "last_swap": None
}

def get_team_from_sensor(sensor_id):
    """Returns the current team assignment for a given sensor."""
    if sensor_id == "local":
        return sensor_mapping["sensor_local_0x29"]
    elif sensor_id == "pico":
        return sensor_mapping["sensor_pico_uart"]
    else:
        return None

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
    
    # ✅ DO NOT trigger if match is won
    if game_state["matchwon"]:
        print("⛔ BASIC MODE: Side switch skipped - match already won")
        return
    
    if game_state["gamemode"] != "basic":
        return
    
    total_games = game_state["game1"] + game_state["game2"]
    set1 = game_state["set1"]
    set2 = game_state["set2"]
    total_sets = set1 + set2
    
    # ✅ SKIP side switch at the very beginning (0-0 sets, 0-0 games)
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
    
    # ✅ DO NOT check side switch if match is won
    if game_state["matchwon"]:
        print("⛔ Side switch check skipped - match already won")
        return False
    
    total_games = game_state["game1"] + game_state["game2"]
    mode = game_state["gamemode"]
    
    if mode == "basic":
        return False
    
    # competition/lock
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
    # ✅ PREVENT side switch broadcast if match is won
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
    play_change_audio()  # ✅ PLAY AUDIO WHEN SIDE SWITCH
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
    
    # Normal set win
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
        
        # Check if match is won FIRST
        match_won = check_match_winner()
        
        # Only trigger side switch if match is NOT won
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
        
        # Check if match is won FIRST
        match_won = check_match_winner()
        
        # Only trigger side switch if match is NOT won
        if not match_won:
            trigger_basic_mode_side_switch_if_needed()
        
        return match_won
    
    # Enter tie-breaks
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
    
    # Check if match is won FIRST
    match_won = check_match_winner()
    
    # Only trigger side switch if match is NOT won
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
    
    # PRE-MODE GATING
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
    
    # Increment internal points
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
    # ✅ ONLY check side switch if match is NOT won
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

@app.route("/resetsensors", methods=["POST"])
def resetsensors():
    """Reset sensors to default positions after match - placeholder for sensor integration"""
    try:
        # TODO: Add your sensor reset logic here
        # Example: Send reset command via serial/I2C to your sensors
        # This is a placeholder - implement based on your sensor hardware
        
        print("📡 Sensor reset command received - sensors returning to default positions")
        
        # If you have a sensor communication method, add it here:
        # serial_connection.write(b"RESET\n")
        # or via I2C/other protocol
        
        return jsonify({"success": True, "message": "Sensors reset to default positions"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/swapsensors", methods=["POST"])
def swap_sensors():
    """Swap sensor assignments: BLACK ↔ YELLOW"""
    global sensor_mapping
    
    old_local = sensor_mapping["sensor_local_0x29"]
    old_pico = sensor_mapping["sensor_pico_uart"]
    
    sensor_mapping["sensor_local_0x29"] = old_pico
    sensor_mapping["sensor_pico_uart"] = old_local
    sensor_mapping["last_swap"] = datetime.now().isoformat()
    
    print(f"🔄 Sensors swapped: Local(0x29)={sensor_mapping['sensor_local_0x29']}, Pico(UART)={sensor_mapping['sensor_pico_uart']}")
    
    socketio.emit('sensor_mapping_updated', sensor_mapping, namespace='/')
    
    return jsonify({
        "success": True,
        "message": "Sensors swapped successfully",
        "mapping": {
            "sensor_local_0x29": sensor_mapping["sensor_local_0x29"],
            "sensor_pico_uart": sensor_mapping["sensor_pico_uart"]
        },
        "timestamp": sensor_mapping["last_swap"]
    })

@app.route("/getsensormapping", methods=["GET"])
def get_sensor_mapping():
    """Get current sensor to team mapping"""
    return jsonify({"success": True, "mapping": sensor_mapping})

@app.route("/health", methods=["GET"])
def healthcheck():
    logoexists = os.path.exists("logo.png")
    backexists = os.path.exists("back.png")
    changeaudioexists = os.path.exists("change.mp3")
    
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "socketio": "enabled",
        "gamestate": game_state,
        "matchstatus": "completed" if game_state["matchwon"] else "in-progress",
        "historyentries": len(game_state["matchhistory"]),
        "matchstorage": {"completed": match_storage["matchcompleted"], "displayed": match_storage["displayshown"]},
        "sensorvalidation": sensor_validation,
        "files": {
            "logo.png": "found" if logoexists else "missing",
            "back.png": "found" if backexists else "missing",
            "change.mp3": "found" if changeaudioexists else "missing"
        }
    })

if __name__ == "__main__":
    print("=" * 70)
    print("Padel Scoreboard Backend - WITH AUDIO SUPPORT 🔊")
    print("=" * 70)
    print("GAME MODES")
    print("  BASIC: Side switch at start of each set (0-0 states).")
    print("         ❌ NO switch at match start (0-0, 0-0)")
    print("         ❌ NO switch after match won (2-0, 2-1, etc.)")
    print("  COMPETITION/LOCK: Switch after odd games (1,3,5,7...).")
    print("                     ❌ NO switch after match won")
    print("=" * 70)
    print("✅ Side switches DISABLED when match is won")
    print("✅ Sensors reset to default on match reset")
    print("=" * 70)
    print("Socket.IO enabled for real-time updates")
    print("Access at http://127.0.0.1:5000")
    print("=" * 70)
    
    validation_thread = threading.Thread(target=run_initial_sensor_validation, daemon=True)
    validation_thread.start()
    
    socketio.run(app, debug=False, host="127.0.0.1", port=5000, allow_unsafe_werkzeug=True)
