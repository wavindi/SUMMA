#!/usr/bin/env python3

"""
Padel Scoreboard Backend - OPTIMIZED FOR ULTRA-LOW LATENCY
Real-time scoring with minimal delay
WITH SIDE SWITCHING and GAME MODES (BASIC, COMPETITION, LOCK)

BASIC MODE: Side switch IMMEDIATELY when new set starts (0-0, 1-0, 0-1, 1-1)
COMPETITION/LOCK: Side switch AFTER odd games (1, 3, 5, 7...)

Rules:
- Normal games: first to 4 points (internal 0,1,2,3,...) with 2-point lead, displayed as 0, 15, 30, 40 (tennis style).
- Normal tie break: to 7 with 2-point lead (at 6-6 in games, sets 0-0 or 0-1).
- Super tie break: to 10 with 2-point lead (decider when sets are 1-1).
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

app = Flask(__name__)
CORS(app, cors_allowed_origins="*")

# Logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Socket.IO
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25
)

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
    # Scores
    "game1": 0, "game2": 0,  # Games in current set
    "set1": 0, "set2": 0,    # Sets in match
    "point1": 0, "point2": 0,  # Internal points for current game/TB (0,1,2,...)
    "score1": 0, "score2": 0,  # Display score - In tie-break modes: same as internal points (0,1,2,...)
    
    # Match status
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
    "initial_switch_done": False,  # Track if start-of-set switch done in BASIC mode
    
    # Mode: "normal", "tiebreak", "supertiebreak"
    "mode": "normal",
    
    # Game mode: "basic", "competition", "lock"
    "gamemode": None,  # ✅ No default - must be selected first
    
    # ✅ NEW: Track if we're still in initial state (splash/mode selection)
    "scoreboard_active": False  # True when scoreboard is visible and accepting points
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

def trigger_basic_mode_side_switch_if_needed():
    """
    BASIC MODE: Trigger side switch immediately when a new set starts.
    Called after set ends and games reset to 0-0.
    Checks if sets are 0-0, 1-0, 0-1, or 1-1.
    """
    global game_state
    if game_state["gamemode"] != "basic":
        return
    
    total_games = game_state["game1"] + game_state["game2"]
    set1 = game_state["set1"]
    set2 = game_state["set2"]
    total_sets = set1 + set2
    
    # Check if we're at start of a set that needs switching
    if (total_games == 0 and 
        total_sets in [0, 1, 2] and 
        not game_state.get("initial_switch_done", False)):
        game_state["initial_switch_done"] = True
        game_state["shouldswitchsides"] = True
        game_state["totalgamesinset"] = 0
        # Broadcast side switch immediately
        broadcast_sideswitch()
        print(f"→ BASIC MODE: Side switch triggered at START of set (Sets {set1}-{set2}, Games 0-0)")

def check_side_switch():
    """Check if side switch is needed based on game mode."""
    global game_state
    total_games = game_state["game1"] + game_state["game2"]
    game_mode = game_state["gamemode"]
    
    if game_mode == "basic":
        # BASIC: No switching after games (switch happens at start of each set)
        return False
    else:
        # COMPETITION and LOCK: Switch after every odd game (1, 3, 5, 7...)
        if (total_games % 2) == 1:
            game_state["shouldswitchsides"] = True
            game_state["totalgamesinset"] = total_games
            return True
        else:
            game_state["shouldswitchsides"] = False
            return False

def acknowledge_side_switch():
    global game_state
    game_state["shouldswitchsides"] = False

# ===== SOCKET.IO HANDLERS =====
@socketio.on('connect')
def handle_connect():
    print(f"✓ Client connected: {request.sid}")
    emit('gamestateupdate', game_state)
    emit('sensor_validation_result', sensor_validation)
    
    # BASIC MODE: Trigger initial side switch if match just started
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

@socketio.on('acknowledge_side_switch')
def handle_acknowledge_side_switch():
    acknowledge_side_switch()
    print("✓ Side switch acknowledged by client")
    emit('side_switch_acknowledged', {"success": True})

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
    data = {
        "totalgames": game_state["totalgamesinset"],
        "gamescore": f"{game_state['game1']}-{game_state['game2']}",
        "setscore": f"{game_state['set1']}-{game_state['set2']}",
        "message": "CHANGE SIDES",
        "timestamp": datetime.now().isoformat()
    }
    socketio.emit('sideswitchrequired', data, namespace='/')
    print(f"→ Side switch broadcasted | Total games: {data['totalgames']}, Score: {data['gamescore']}")

def broadcast_matchwon():
    data = {
        "winner": game_state["winner"],
        "matchdata": match_storage["matchdata"],
        "timestamp": datetime.now().isoformat()
    }
    socketio.emit('matchwon', data, namespace='/')

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

# ===== MATCH STATISTICS =====
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
            # Extract just numbers (handle "7-6(5)" → "7" and "6")
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
    
    # Normal set win: 6 games with 2-game lead
    if g1 >= 6 and g1 - g2 >= 2:
        set_before = (s1, s2)
        game_state["set1"] += 1
        game_state["sethistory"].append(f"{g1}-{g2}")
        add_to_history("set", "black", (game_state["score1"], game_state["score2"]),
                      (0, 0), (g1, g2), (0, 0), set_before, (game_state["set1"], game_state["set2"]))
        game_state["game1"] = 0
        game_state["game2"] = 0
        game_state["totalgamesinset"] = 0
        game_state["shouldswitchsides"] = False
        game_state["initial_switch_done"] = False  # Reset for new set
        print(f"→ Set won by BLACK. Score: {game_state['set1']}-{game_state['set2']}. Flag reset for new set.")
        
        # BASIC MODE: Trigger side switch immediately for new set
        trigger_basic_mode_side_switch_if_needed()
        return check_match_winner()
    
    if g2 >= 6 and g2 - g1 >= 2:
        set_before = (s1, s2)
        game_state["set2"] += 1
        game_state["sethistory"].append(f"{g1}-{g2}")
        add_to_history("set", "yellow", (game_state["score1"], game_state["score2"]),
                      (0, 0), (g1, g2), (0, 0), set_before, (game_state["set1"], game_state["set2"]))
        game_state["game1"] = 0
        game_state["game2"] = 0
        game_state["totalgamesinset"] = 0
        game_state["shouldswitchsides"] = False
        game_state["initial_switch_done"] = False  # Reset for new set
        print(f"→ Set won by YELLOW. Score: {game_state['set1']}-{game_state['set2']}. Flag reset for new set.")
        
        # BASIC MODE: Trigger side switch immediately for new set
        trigger_basic_mode_side_switch_if_needed()
        return check_match_winner()
    
    # Tie-break decision at 6-6 in games
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
        
        # Calculate total games won across all sets
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
        add_to_history("match", "black", (game_state["score1"], game_state["score2"]),
                      (game_state["score1"], game_state["score2"]),
                      (game_state["game1"], game_state["game2"]),
                      (game_state["game1"], game_state["game2"]),
                      (game_state["set1"], game_state["set2"]),
                      (game_state["set1"], game_state["set2"]))
        store_match_data()
        return True
    
    if game_state["set2"] == 2:
        game_state["matchwon"] = True
        game_state["matchendtime"] = datetime.now().isoformat()
        
        # Calculate total games won across all sets
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
        add_to_history("match", "yellow", (game_state["score1"], game_state["score2"]),
                      (game_state["score1"], game_state["score2"]),
                      (game_state["game1"], game_state["game2"]),
                      (game_state["game1"], game_state["game2"]),
                      (game_state["set1"], game_state["set2"]),
                      (game_state["set1"], game_state["set2"]))
        store_match_data()
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

# ===== SCORING LOGIC =====
def set_normal_score_from_points():
    """
    Map internal raw points (0,1,2,3,...) to tennis-style display (0,15,30,40).
    Anything >= 3 is displayed as 40 (we use win-by-2 rule on raw points).
    """
    p1 = game_state["point1"]
    p2 = game_state["point2"]
    
    def map_point(p):
        if p == 0:
            return 0
        elif p == 1:
            return 15
        elif p == 2:
            return 30
        else:
            return 40
    
    game_state["score1"] = map_point(p1)
    game_state["score2"] = map_point(p2)

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
    """Normal tie break win - record set with TB notation"""
    g1 = game_state["game1"]
    g2 = game_state["game2"]
    tb_score = f"({game_state['point2']})" if team == "black" else f"({game_state['point1']})"
    
    set_before = (game_state["set1"], game_state["set2"])
    
    if team == "black":
        game_state["set1"] += 1
        # Winner gets 7, loser stays at 6, show TB score in parens
        game_state["sethistory"].append(f"7-6{tb_score}")
        add_to_history("set", "black", (game_state["score1"], game_state["score2"]),
                      (0, 0), (g1, g2), (0, 0), set_before, (game_state["set1"], game_state["set2"]))
    else:
        game_state["set2"] += 1
        game_state["sethistory"].append(f"6-7{tb_score}")
        add_to_history("set", "yellow", (game_state["score1"], game_state["score2"]),
                      (0, 0), (g1, g2), (0, 0), set_before, (game_state["set1"], game_state["set2"]))
    
    game_state["game1"] = 0
    game_state["game2"] = 0
    game_state["totalgamesinset"] = 0
    game_state["shouldswitchsides"] = False
    game_state["initial_switch_done"] = False  # Reset for new set
    reset_points()
    game_state["mode"] = "normal"
    print(f"→ Tie-break won. New set starting. Flag reset for new set.")
    
    # BASIC MODE: Trigger side switch immediately for new set
    trigger_basic_mode_side_switch_if_needed()
    check_match_winner()

def handle_supertiebreak_win(team):
    """Super tie break win - store as special set and end match"""
    stb_score = f"(STB:{game_state['point1']}-{game_state['point2']})"
    
    set_before = (game_state["set1"], game_state["set2"])
    
    if team == "black":
        game_state["set1"] += 1
        game_state["sethistory"].append(f"10-{game_state['point2']}(STB)")
        add_to_history("set", "black", (game_state["score1"], game_state["score2"]),
                      (0, 0), (game_state["game1"], game_state["game2"]), (0, 0),
                      set_before, (game_state["set1"], game_state["set2"]))
    else:
        game_state["set2"] += 1
        game_state["sethistory"].append(f"{game_state['point1']}-10(STB)")
        add_to_history("set", "yellow", (game_state["score1"], game_state["score2"]),
                      (0, 0), (game_state["game1"], game_state["game2"]), (0, 0),
                      set_before, (game_state["set1"], game_state["set2"]))
    
    game_state["initial_switch_done"] = False  # Reset (match ends but good practice)
    reset_points()
    game_state["mode"] = "normal"
    print(f"→ Super tie-break won. Match ending.")
    check_match_winner()

def process_add_point(team):
    global game_state
    
    if game_state["matchwon"]:
        return {"success": False, "error": "Match is already completed",
                "winner": game_state["winner"], "matchwon": True}
    
    # ✅ CRITICAL: Block points if scoreboard is not active
    if not game_state["scoreboard_active"]:
        print(f"⚠️ Point from {team} BLOCKED - Scoreboard not active yet (splash/mode selection)")
        return {
            "success": False,
            "error": "Scoreboard not active yet",
            "blocked": True,
            "trigger_transition": True  # Signal frontend to transition
        }
    
    score_before = (game_state["score1"], game_state["score2"])
    game_before = (game_state["game1"], game_state["game2"])
    set_before = (game_state["set1"], game_state["set2"])
    action_type = "point"
    game_just_won = False
    
    mode = game_state["mode"]
    
    # Increment internal point counter
    if team == "black":
        game_state["point1"] += 1
    else:
        game_state["point2"] += 1
    
    p1 = game_state["point1"]
    p2 = game_state["point2"]
    
    if mode == "normal":
        set_normal_score_from_points()
        
        # NORMAL GAMES: win when raw >= 4 and lead >= 2 (display 0/15/30/40)
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
    
    elif mode == "tiebreak":
        # NORMAL TIE BREAK: internal points display directly (0,1,2,...)
        game_state["score1"] = game_state["point1"]
        game_state["score2"] = game_state["point2"]
        
        if team == "black":
            if p1 >= 7 and p1 - p2 >= 2:
                handle_tiebreak_win("black")
                action_type = "set"  # Mark as set win for proper toast
        else:
            if p2 >= 7 and p2 - p1 >= 2:
                handle_tiebreak_win("yellow")
                action_type = "set"
    
    elif mode == "supertiebreak":
        # SUPER TIE BREAK
        game_state["score1"] = game_state["point1"]
        game_state["score2"] = game_state["point2"]
        
        if team == "black":
            if p1 >= 10 and p1 - p2 >= 2:
                handle_supertiebreak_win("black")
                action_type = "set"  # Mark as set win for proper toast
        else:
            if p2 >= 10 and p2 - p1 >= 2:
                handle_supertiebreak_win("yellow")
                action_type = "set"
    
    # History
    if not game_state["matchwon"]:
        add_to_history(action_type, team, score_before,
                      (game_state["score1"], game_state["score2"]),
                      game_before, (game_state["game1"], game_state["game2"]),
                      set_before, (game_state["set1"], game_state["set2"]))
    
    game_state["lastupdated"] = datetime.now().isoformat()
    
    # Side switch only for normal game wins (COMPETITION/LOCK modes only)
    side_switch_needed = False
    if game_just_won and not game_state["matchwon"] and game_state["mode"] == "normal":
        side_switch_needed = check_side_switch()
        if side_switch_needed:
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
        "winner": game_state["winner"] if game_state["matchwon"] else None,
        "matchstored": match_storage["matchcompleted"] and not match_storage["displayshown"]
    }
    
    if side_switch_needed:
        response["sideswitch"] = {
            "required": True,
            "totalgames": game_state["totalgamesinset"],
            "gamescore": f"{game_state['game1']}-{game_state['game2']}",
            "setscore": f"{game_state['set1']}-{game_state['set2']}"
        }
    
    return response

def process_subtract_point(team):
    """
    Simple subtraction:
    - Decrement raw internal point & update displayed score accordingly.
    - Does not undo games/sets.
    """
    global game_state
    
    if game_state["matchwon"]:
        return {"success": False, "error": "Cannot subtract points from completed match"}
    
    # ✅ CRITICAL: Block subtract points if scoreboard is not active
    if not game_state["scoreboard_active"]:
        print(f"⚠️ Subtract point from {team} BLOCKED - Scoreboard not active yet (splash/mode selection)")
        return {
            "success": False,
            "error": "Scoreboard not active yet",
            "blocked": True,
            "trigger_transition": True  # Signal frontend to transition
        }
    
    score_before = (game_state["score1"], game_state["score2"])
    game_before = (game_state["game1"], game_state["game2"])
    set_before = (game_state["set1"], game_state["set2"])
    
    if team == "black":
        game_state["point1"] = max(0, game_state["point1"] - 1)
    else:
        game_state["point2"] = max(0, game_state["point2"] - 1)
    
    # Update display scores depending on mode
    if game_state["mode"] == "normal":
        set_normal_score_from_points()
    else:
        game_state["score1"] = game_state["point1"]
        game_state["score2"] = game_state["point2"]
    
    add_to_history("point_subtract", team, score_before,
                  (game_state["score1"], game_state["score2"]),
                  game_before, (game_state["game1"], game_state["game2"]),
                  set_before, (game_state["set1"], game_state["set2"]))
    
    game_state["lastupdated"] = datetime.now().isoformat()
    broadcast_gamestate()
    
    return {"success": True, "message": f"Point subtracted from team {team}", "gamestate": game_state}

# ===== FLASK ROUTES =====
@app.route('/')
def serve_scoreboard():
    return send_from_directory('.', 'padel_scoreboard.html')

@app.route('/<path:filename>')
def serve_static_files(filename):
    if os.path.exists(filename):
        return send_from_directory('.', filename)
    return f"File {filename} not found", 404

@app.route('/addpoint', methods=['POST'])
def add_point():
    try:
        data = request.get_json()
        team = data.get("team", "black")
        
        result = process_add_point(team)
        
        # If blocked, return specific response
        if not result.get("success", False) and result.get("blocked", False):
            return jsonify(result), 200  # Return 200 but with blocked flag
        
        return jsonify(result), 200 if result["success"] else 400
    except Exception as e:
        print(f"✗ Error in add_point: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/subtractpoint', methods=['POST'])
def subtract_point():
    try:
        data = request.get_json()
        team = data.get("team", "black")
        
        result = process_subtract_point(team)
        
        # If blocked, return specific response
        if not result.get("success", False) and result.get("blocked", False):
            return jsonify(result), 200  # Return 200 but with blocked flag
        
        return jsonify(result), 200 if result["success"] else 400
    except Exception as e:
        print(f"✗ Error in subtract_point: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/setgamemode', methods=['POST'])
def set_game_mode():
    try:
        data = request.get_json()
        mode = data.get("mode")
        
        if mode not in ["basic", "competition", "lock"]:
            return jsonify({"success": False, "error": "Invalid mode"}), 400
        
        game_state["gamemode"] = mode
        # ✅ Activate scoreboard when mode is set
        game_state["scoreboard_active"] = True
        game_state["lastupdated"] = datetime.now().isoformat()
        
        print(f"✓ Game mode set to: {mode.upper()} | Scoreboard ACTIVE")
        
        # BASIC MODE: Trigger initial side switch
        if mode == "basic":
            trigger_basic_mode_side_switch_if_needed()
        
        broadcast_gamestate()
        
        return jsonify({
            "success": True,
            "mode": mode,
            "gamestate": game_state
        }), 200
    except Exception as e:
        print(f"✗ Error setting game mode: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/resetmatch', methods=['POST'])
def reset_match():
    global game_state
    
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
        "gamemode": None,  # ✅ Reset to None - must select again
        "scoreboard_active": False  # ✅ Reset to inactive
    }
    
    wipe_match_storage()
    broadcast_gamestate()
    
    print("✓ Match reset successfully | Scoreboard INACTIVE")
    return jsonify({"success": True, "message": "Match reset", "gamestate": game_state}), 200

@app.route('/gamestatus', methods=['GET'])
def game_status():
    return jsonify({
        "gamestate": game_state,
        "sensorvalidation": sensor_validation,
        "matchstorage": match_storage
    }), 200

@app.route('/matchdata', methods=['GET'])
def get_match_data():
    if match_storage["matchcompleted"]:
        match_storage["displayshown"] = True
        return jsonify(match_storage["matchdata"]), 200
    else:
        return jsonify({"error": "No completed match data available"}), 404

if __name__ == '__main__':
    print("=" * 50)
    print("🎾 PADEL SCOREBOARD BACKEND STARTING 🎾")
    print("=" * 50)
    
    # Start sensor validation in background
    validation_thread = threading.Thread(target=run_initial_sensor_validation, daemon=True)
    validation_thread.start()
    
    # Run Flask-SocketIO app
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
