#!/usr/bin/env python3

"""
Padel Scoreboard Backend - OPTIMIZED FOR ULTRA-LOW LATENCY
Real-time scoring with minimal delay
WITH SIDE SWITCHING after odd-numbered games

Rules:
- Normal games: first to 4 points (internal 0,1,2,3,...) with 2-point lead,
  displayed as 0, 15, 30, 40 (tennis style).
- Normal tie break: to 7 with 2-point lead (at 6–6 in games, sets 0–0 or 0–1).
- Super tie break: to 10 with 2-point lead (decider when sets are 1–1).
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

# ============================================================================
# LOGGING / SOCKET.IO
# ============================================================================

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

# ============================================================================
# SENSOR VALIDATION
# ============================================================================

sensor_validation = {
    'validated': False,
    'sensor_1_address': None,
    'sensor_2_address': None,
    'status': 'pending',
    'error_message': None,
    'timestamp': None
}

def validate_sensors():
    """Validate that two VL53L5CX sensors are on different I2C addresses."""
    global sensor_validation
    print("\n🔍 Validating VL53L5CX sensors...")
    try:
        bus = SMBus(1)
        detected_addresses = []

        for addr in [0x29, 0x39]:
            try:
                msg = i2c_msg.write(addr, [0x00])
                bus.i2c_rdwr(msg)
                detected_addresses.append(addr)
                print(f" ✓ Sensor found at 0x{addr:02X}")
            except:
                pass

        bus.close()

        if len(detected_addresses) == 2 and 0x29 in detected_addresses and 0x39 in detected_addresses:
            sensor_validation['validated'] = True
            sensor_validation['sensor_1_address'] = 0x39
            sensor_validation['sensor_2_address'] = 0x29
            sensor_validation['status'] = 'valid'
            sensor_validation['error_message'] = None
            sensor_validation['timestamp'] = datetime.now().isoformat()
            print("✅ Sensor validation PASSED - Both sensors at different addresses")
            return True
        elif len(detected_addresses) == 2 and detected_addresses[0] == detected_addresses[1]:
            sensor_validation['validated'] = False
            sensor_validation['status'] = 'error'
            sensor_validation['error_message'] = 'ERROR 1: Both sensors at same address 0x29 - Restart SUMMA'
            sensor_validation['timestamp'] = datetime.now().isoformat()
            print("❌ Sensor validation FAILED - Both sensors at 0x29")
            return False
        elif len(detected_addresses) == 0:
            sensor_validation['validated'] = False
            sensor_validation['status'] = 'error'
            sensor_validation['error_message'] = 'ERROR 1: No sensors detected - Restart SUMMA'
            sensor_validation['timestamp'] = datetime.now().isoformat()
            print("❌ Sensor validation FAILED - No sensors detected")
            return False
        else:
            sensor_validation['validated'] = False
            sensor_validation['status'] = 'error'
            sensor_validation['error_message'] = f'ERROR 1: Only {len(detected_addresses)} sensor(s) detected - Restart SUMMA'
            sensor_validation['timestamp'] = datetime.now().isoformat()
            print(f"❌ Sensor validation FAILED - Only {len(detected_addresses)} sensor(s)")
            return False

    except Exception as e:
        sensor_validation['validated'] = False
        sensor_validation['status'] = 'error'
        sensor_validation['error_message'] = 'ERROR 1: Sensor check failed - Restart SUMMA'
        sensor_validation['timestamp'] = datetime.now().isoformat()
        print(f"❌ Sensor validation ERROR: {e}")
        return False

def run_initial_sensor_validation():
    time.sleep(2)
    validate_sensors()
    socketio.emit('sensor_validation_result', sensor_validation)
    print(f"📡 Sensor validation result broadcasted: {sensor_validation['status']}")

# ============================================================================
# GAME STATE
# ============================================================================

game_state = {
    # Games in current set
    'game_1': 0,
    'game_2': 0,

    # Sets in match
    'set_1': 0,
    'set_2': 0,

    # Internal points for current game / TB (0,1,2,...)
    'point_1': 0,
    'point_2': 0,

    # Display scores for current game:
    # - In normal mode: 0,15,30,40
    # - In tie-break modes: same as internal points (0,1,2,...)
    'score_1': 0,
    'score_2': 0,

    # Match status
    'match_won': False,
    'winner': None,

    # History
    'set_history': [],
    'match_history': [],

    'match_start_time': datetime.now().isoformat(),
    'match_end_time': None,
    'last_updated': datetime.now().isoformat(),

    # Side switching
    'should_switch_sides': False,
    'total_games_in_set': 0,

    # Mode: 'normal', 'tiebreak', 'supertiebreak'
    'mode': 'normal'
}

match_storage = {
    'match_completed': False,
    'match_data': {
        'winner_team': None,
        'winner_name': None,
        'final_sets_score': None,
        'detailed_sets': [],
        'match_duration': None,
        'total_points_won': {'black': 0, 'yellow': 0},
        'total_games_won': {'black': 0, 'yellow': 0},
        'sets_breakdown': [],
        'match_summary': None
    },
    'display_shown': False
}

# ============================================================================
# SIDE SWITCH LOGIC
# ============================================================================

def check_side_switch():
    global game_state
    total_games = game_state['game_1'] + game_state['game_2']
    if total_games % 2 == 1:
        game_state['should_switch_sides'] = True
        game_state['total_games_in_set'] = total_games
        return True
    else:
        game_state['should_switch_sides'] = False
        return False

def acknowledge_side_switch():
    global game_state
    game_state['should_switch_sides'] = False

# ============================================================================
# SOCKET.IO
# ============================================================================

@socketio.on('connect')
def handle_connect():
    print(f'🔌 Client connected: {request.sid}')
    emit('game_state_update', game_state)
    emit('sensor_validation_result', sensor_validation)
    return True

@socketio.on('disconnect')
def handle_disconnect():
    print(f'🔌 Client disconnected: {request.sid}')

@socketio.on('request_game_state')
def handle_request_game_state():
    emit('game_state_update', game_state)

@socketio.on('request_sensor_validation')
def handle_request_sensor_validation():
    emit('sensor_validation_result', sensor_validation)

@socketio.on('acknowledge_side_switch')
def handle_acknowledge_side_switch():
    acknowledge_side_switch()
    print("✅ Side switch acknowledged by client")
    emit('side_switch_acknowledged', {'success': True})

def broadcast_game_state():
    socketio.emit('game_state_update', game_state, namespace='/')

def broadcast_point_scored(team, action_type):
    data = {
        'team': team,
        'action': action_type,
        'game_state': game_state,
        'timestamp': datetime.now().isoformat()
    }
    socketio.emit('point_scored', data, namespace='/')

def broadcast_side_switch():
    data = {
        'total_games': game_state['total_games_in_set'],
        'game_score': f"{game_state['game_1']}-{game_state['game_2']}",
        'set_score': f"{game_state['set_1']}-{game_state['set_2']}",
        'message': 'CHANGE SIDES',
        'timestamp': datetime.now().isoformat()
    }
    socketio.emit('side_switch_required', data, namespace='/')
    print(f"🔄 Side switch broadcasted: Total games = {data['total_games']}, Score = {data['game_score']}")

def broadcast_match_won():
    data = {
        'winner': game_state['winner'],
        'match_data': match_storage['match_data'],
        'timestamp': datetime.now().isoformat()
    }
    socketio.emit('match_won', data, namespace='/')

# ============================================================================
# HISTORY / STATS
# ============================================================================

def add_to_history(action, team, score_before, score_after, game_before, game_after, set_before, set_after):
    global game_state
    history_entry = {
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'team': team,
        'scores': {
            'before': {'score_1': score_before[0], 'score_2': score_before[1]},
            'after': {'score_1': score_after[0], 'score_2': score_after[1]}
        },
        'games': {
            'before': {'game_1': game_before[0], 'game_2': game_before[1]},
            'after': {'game_1': game_after[0], 'game_2': game_after[1]}
        },
        'sets': {
            'before': {'set_1': set_before[0], 'set_2': set_before[1]},
            'after': {'set_1': set_after[0], 'set_2': set_after[1]}
        }
    }
    game_state['match_history'].append(history_entry)

def calculate_match_statistics():
    global game_state
    black_points = len([h for h in game_state['match_history'] if h['action'] == 'point' and h['team'] == 'black'])
    yellow_points = len([h for h in game_state['match_history'] if h['action'] == 'point' and h['team'] == 'yellow'])
    black_games = len([h for h in game_state['match_history'] if h['action'] == 'game' and h['team'] == 'black'])
    yellow_games = len([h for h in game_state['match_history'] if h['action'] == 'game' and h['team'] == 'yellow'])

    sets_breakdown = []
    for i, set_score in enumerate(game_state['set_history'], 1):
        # Handle both normal "6-4" and tie break "7-6(5)" formats
        if '-' in set_score:
            games = set_score.split('-')
            # Extract just numbers (handle "7-6(5)" → "7" and "6")
            black_g = int(games[0].split('(')[0])
            yellow_g = int(games[1].split('(')[0])
            sets_breakdown.append({
                'set_number': i,
                'black_games': black_g,
                'yellow_games': yellow_g,
                'set_winner': 'black' if black_g > yellow_g else 'yellow'
            })

    return {
        'total_points': {'black': black_points, 'yellow': yellow_points},
        'total_games': {'black': black_games, 'yellow': yellow_games},
        'sets_breakdown': sets_breakdown
    }

def store_match_data():
    global game_state, match_storage
    if not game_state['match_won'] or not game_state['winner']:
        return

    stats = calculate_match_statistics()
    start_time = datetime.fromisoformat(game_state['match_start_time'])
    end_time = datetime.fromisoformat(game_state['match_end_time'])
    duration_seconds = int((end_time - start_time).total_seconds())
    duration_minutes = duration_seconds // 60
    duration_text = f"{duration_minutes}m {duration_seconds % 60}s" if duration_minutes > 0 else f"{duration_seconds}s"

    sets_display = []
    for breakdown in stats['sets_breakdown']:
        sets_display.append(f"{breakdown['black_games']}-{breakdown['yellow_games']}")

    match_storage['match_completed'] = True
    match_storage['match_data'] = {
        'winner_team': game_state['winner']['team'],
        'winner_name': game_state['winner']['team_name'],
        'final_sets_score': game_state['winner']['final_sets'],
        'detailed_sets': sets_display,
        'match_duration': duration_text,
        'total_points_won': stats['total_points'],
        'total_games_won': stats['total_games'],
        'sets_breakdown': stats['sets_breakdown'],
        'match_summary': create_match_summary(stats, sets_display),
        'timestamp': game_state['match_end_time']
    }
    match_storage['display_shown'] = False

def create_match_summary(stats, sets_display):
    sets_text = ", ".join(sets_display)
    return f"Sets: {sets_text} | Points: {stats['total_points']['black']}-{stats['total_points']['yellow']} | Games: {stats['total_games']['black']}-{stats['total_games']['yellow']}"

def wipe_match_storage():
    global match_storage
    match_storage = {
        'match_completed': False,
        'match_data': {
            'winner_team': None,
            'winner_name': None,
            'final_sets_score': None,
            'detailed_sets': [],
            'match_duration': None,
            'total_points_won': {'black': 0, 'yellow': 0},
            'total_games_won': {'black': 0, 'yellow': 0},
            'sets_breakdown': [],
            'match_summary': None
        },
        'display_shown': False
    }

# ============================================================================
# SET / MATCH WIN LOGIC
# ============================================================================

def check_set_winner():
    global game_state

    g1 = game_state['game_1']
    g2 = game_state['game_2']
    s1 = game_state['set_1']
    s2 = game_state['set_2']

    # Normal set win: 6+ games with 2-game lead
    if g1 >= 6 and (g1 - g2) >= 2:
        set_before = (s1, s2)
        game_state['set_1'] += 1
        game_state['set_history'].append(f"{g1}-{g2}")
        add_to_history('set', 'black',
                       (game_state['score_1'], game_state['score_2']),
                       (0, 0),
                       (g1, g2),
                       (0, 0),
                       set_before,
                       (game_state['set_1'], game_state['set_2']))
        game_state['game_1'] = 0
        game_state['game_2'] = 0
        game_state['total_games_in_set'] = 0
        game_state['should_switch_sides'] = False
        return check_match_winner()

    if g2 >= 6 and (g2 - g1) >= 2:
        set_before = (s1, s2)
        game_state['set_2'] += 1
        game_state['set_history'].append(f"{g1}-{g2}")
        add_to_history('set', 'yellow',
                       (game_state['score_1'], game_state['score_2']),
                       (0, 0),
                       (g1, g2),
                       (0, 0),
                       set_before,
                       (game_state['set_1'], game_state['set_2']))
        game_state['game_1'] = 0
        game_state['game_2'] = 0
        game_state['total_games_in_set'] = 0
        game_state['should_switch_sides'] = False
        return check_match_winner()

    # Tie-break decision at 6–6 in games
    if g1 == 6 and g2 == 6 and game_state['mode'] == 'normal':
        if (s1 == 0 and s2 == 0) or (s1 + s2 == 1):
            print("🎯 Entering NORMAL TIE BREAK mode")
            game_state['mode'] = 'tiebreak'
            game_state['point_1'] = 0
            game_state['point_2'] = 0
            game_state['score_1'] = 0
            game_state['score_2'] = 0
        elif s1 == 1 and s2 == 1:
            print("🎯 Entering SUPER TIE BREAK mode (decider)")
            game_state['mode'] = 'supertiebreak'
            game_state['point_1'] = 0
            game_state['point_2'] = 0
            game_state['score_1'] = 0
            game_state['score_2'] = 0

    return False

def check_match_winner():
    global game_state
    if game_state['set_1'] >= 2:
        game_state['match_won'] = True
        game_state['match_end_time'] = datetime.now().isoformat()
        
        # Calculate total games won across all sets
        total_black_games = 0
        total_yellow_games = 0
        for set_score in game_state['set_history']:
            if '-' in set_score:
                parts = set_score.split('-')
                total_black_games += int(parts[0].split('(')[0])
                total_yellow_games += int(parts[1].split('(')[0])
        total_black_games += game_state['game_1']
        total_yellow_games += game_state['game_2']
        
        game_state['winner'] = {
            'team': 'black',
            'team_name': 'BLACK TEAM',
            'final_sets': f"{game_state['set_1']}-{game_state['set_2']}",
            'match_summary': ', '.join(game_state['set_history']),
            'total_games_won': total_black_games,
            'match_duration': calculate_match_duration()
        }
        add_to_history('match', 'black',
                       (game_state['score_1'], game_state['score_2']),
                       (game_state['score_1'], game_state['score_2']),
                       (game_state['game_1'], game_state['game_2']),
                       (game_state['game_1'], game_state['game_2']),
                       (game_state['set_1'], game_state['set_2']),
                       (game_state['set_1'], game_state['set_2']))
        store_match_data()
        return True

    if game_state['set_2'] >= 2:
        game_state['match_won'] = True
        game_state['match_end_time'] = datetime.now().isoformat()
        
        # Calculate total games won across all sets
        total_black_games = 0
        total_yellow_games = 0
        for set_score in game_state['set_history']:
            if '-' in set_score:
                parts = set_score.split('-')
                total_black_games += int(parts[0].split('(')[0])
                total_yellow_games += int(parts[1].split('(')[0])
        total_black_games += game_state['game_1']
        total_yellow_games += game_state['game_2']
        
        game_state['winner'] = {
            'team': 'yellow',
            'team_name': 'YELLOW TEAM',
            'final_sets': f"{game_state['set_1']}-{game_state['set_2']}",
            'match_summary': ', '.join(game_state['set_history']),
            'total_games_won': total_yellow_games,
            'match_duration': calculate_match_duration()
        }
        add_to_history('match', 'yellow',
                       (game_state['score_1'], game_state['score_2']),
                       (game_state['score_1'], game_state['score_2']),
                       (game_state['game_1'], game_state['game_2']),
                       (game_state['game_1'], game_state['game_2']),
                       (game_state['set_1'], game_state['set_2']),
                       (game_state['set_1'], game_state['set_2']))
        store_match_data()
        return True

    return False

def calculate_match_duration():
    if game_state['match_end_time']:
        start = datetime.fromisoformat(game_state['match_start_time'])
        end = datetime.fromisoformat(game_state['match_end_time'])
        duration = end - start
        total_minutes = int(duration.total_seconds() / 60)
        return f"{total_minutes} minutes"
    return "In progress"

# ============================================================================
# POINT LOGIC (NORMAL / TIE BREAK / SUPER TB)
# ============================================================================

def _set_normal_score_from_points():
    """
    Map internal raw points (0,1,2,3,...) to tennis-style display 0,15,30,40.
    Anything >=3 is displayed as 40 (we use win-by-2 rule on raw points).
    """
    p1 = game_state['point_1']
    p2 = game_state['point_2']

    def map_point(p):
        if p <= 0:
            return 0
        elif p == 1:
            return 15
        elif p == 2:
            return 30
        else:
            return 40

    game_state['score_1'] = map_point(p1)
    game_state['score_2'] = map_point(p2)

def _reset_points():
    game_state['point_1'] = 0
    game_state['point_2'] = 0
    game_state['score_1'] = 0
    game_state['score_2'] = 0

def _handle_normal_game_win(team):
    if team == 'black':
        game_state['game_1'] += 1
    else:
        game_state['game_2'] += 1
    _reset_points()
    check_set_winner()

def _handle_tiebreak_win(team):
    """Normal tie break win - record set with TB notation"""
    g1 = game_state['game_1']
    g2 = game_state['game_2']
    tb_score = f"({game_state['point_2'] if team == 'black' else game_state['point_1']})"
    
    set_before = (game_state['set_1'], game_state['set_2'])

    if team == 'black':
        game_state['set_1'] += 1
        # Winner gets 7, loser stays at 6, show TB score in parens
        game_state['set_history'].append(f"7-6{tb_score}")
        add_to_history('set', 'black',
                       (game_state['score_1'], game_state['score_2']),
                       (0, 0),
                       (g1, g2),
                       (0, 0),
                       set_before,
                       (game_state['set_1'], game_state['set_2']))
    else:
        game_state['set_2'] += 1
        game_state['set_history'].append(f"6-7{tb_score}")
        add_to_history('set', 'yellow',
                       (game_state['score_1'], game_state['score_2']),
                       (0, 0),
                       (g1, g2),
                       (0, 0),
                       set_before,
                       (game_state['set_1'], game_state['set_2']))

    game_state['game_1'] = 0
    game_state['game_2'] = 0
    game_state['total_games_in_set'] = 0
    game_state['should_switch_sides'] = False
    _reset_points()
    game_state['mode'] = 'normal'
    check_match_winner()

def _handle_supertiebreak_win(team):
    """Super tie break win - store as special set and end match"""
    stb_score = f"STB({game_state['point_1']}-{game_state['point_2']})"
    set_before = (game_state['set_1'], game_state['set_2'])
    
    if team == 'black':
        game_state['set_1'] += 1
        game_state['set_history'].append(f"10-{game_state['point_2']}(STB)")
        add_to_history('set', 'black',
                       (game_state['score_1'], game_state['score_2']),
                       (0, 0),
                       (game_state['game_1'], game_state['game_2']),
                       (0, 0),
                       set_before,
                       (game_state['set_1'], game_state['set_2']))
    else:
        game_state['set_2'] += 1
        game_state['set_history'].append(f"{game_state['point_1']}-10(STB)")
        add_to_history('set', 'yellow',
                       (game_state['score_1'], game_state['score_2']),
                       (0, 0),
                       (game_state['game_1'], game_state['game_2']),
                       (0, 0),
                       set_before,
                       (game_state['set_1'], game_state['set_2']))

    _reset_points()
    game_state['mode'] = 'normal'
    check_match_winner()

def process_add_point(team):
    global game_state

    if game_state['match_won']:
        return {
            'success': False,
            'error': 'Match is already completed',
            'winner': game_state['winner'],
            'match_won': True
        }

    score_before = (game_state['score_1'], game_state['score_2'])
    game_before = (game_state['game_1'], game_state['game_2'])
    set_before = (game_state['set_1'], game_state['set_2'])
    action_type = 'point'
    game_just_won = False
    mode = game_state['mode']

    # Increment internal point counter
    if team == 'black':
        game_state['point_1'] += 1
    else:
        game_state['point_2'] += 1

    p1 = game_state['point_1']
    p2 = game_state['point_2']

    # NORMAL GAMES: win when raw >=4 and lead >=2; display 0/15/30/40
    if mode == 'normal':
        _set_normal_score_from_points()

        if team == 'black':
            if p1 >= 4 and (p1 - p2) >= 2:
                _handle_normal_game_win('black')
                action_type = 'game'
                game_just_won = True
        else:
            if p2 >= 4 and (p2 - p1) >= 2:
                _handle_normal_game_win('yellow')
                action_type = 'game'
                game_just_won = True

    # NORMAL TIE BREAK: internal points display directly (0,1,2,..)
    elif mode == 'tiebreak':
        game_state['score_1'] = game_state['point_1']
        game_state['score_2'] = game_state['point_2']

        if team == 'black':
            if p1 >= 7 and (p1 - p2) >= 2:
                _handle_tiebreak_win('black')
                action_type = 'set'  # Mark as set win for proper toast
        else:
            if p2 >= 7 and (p2 - p1) >= 2:
                _handle_tiebreak_win('yellow')
                action_type = 'set'

    # SUPER TIE BREAK
    elif mode == 'supertiebreak':
        game_state['score_1'] = game_state['point_1']
        game_state['score_2'] = game_state['point_2']

        if team == 'black':
            if p1 >= 10 and (p1 - p2) >= 2:
                _handle_supertiebreak_win('black')
                action_type = 'set'  # Mark as set win for proper toast
        else:
            if p2 >= 10 and (p2 - p1) >= 2:
                _handle_supertiebreak_win('yellow')
                action_type = 'set'

    # History
    if not game_state['match_won']:
        add_to_history(action_type, team,
                       score_before,
                       (game_state['score_1'], game_state['score_2']),
                       game_before,
                       (game_state['game_1'], game_state['game_2']),
                       set_before,
                       (game_state['set_1'], game_state['set_2']))
        game_state['last_updated'] = datetime.now().isoformat()

    # Side switch only for normal game wins
    side_switch_needed = False
    if game_just_won and not game_state['match_won'] and game_state['mode'] == 'normal':
        side_switch_needed = check_side_switch()
        if side_switch_needed:
            broadcast_side_switch()

    broadcast_game_state()
    if game_state['match_won']:
        broadcast_match_won()
    else:
        broadcast_point_scored(team, action_type)

    response = {
        'success': True,
        'message': f'Point added to {team} team',
        'game_state': game_state,
        'match_won': game_state['match_won'],
        'winner': game_state['winner'] if game_state['match_won'] else None,
        'match_stored': match_storage['match_completed'] and not match_storage['display_shown']
    }

    if side_switch_needed:
        response['side_switch'] = {
            'required': True,
            'total_games': game_state['total_games_in_set'],
            'game_score': f"{game_state['game_1']}-{game_state['game_2']}",
            'set_score': f"{game_state['set_1']}-{game_state['set_2']}"
        }

    return response

def process_subtract_point(team):
    """
    Simple subtraction:
    - Decrement raw internal point; update displayed score accordingly.
    - Does not undo games/sets.
    """
    global game_state

    if game_state['match_won']:
        return {
            'success': False,
            'error': 'Cannot subtract points from completed match'
        }

    score_before = (game_state['score_1'], game_state['score_2'])
    game_before = (game_state['game_1'], game_state['game_2'])
    set_before = (game_state['set_1'], game_state['set_2'])

    if team == 'black':
        game_state['point_1'] = max(0, game_state['point_1'] - 1)
    else:
        game_state['point_2'] = max(0, game_state['point_2'] - 1)

    # Update display scores depending on mode
    if game_state['mode'] == 'normal':
        _set_normal_score_from_points()
    else:
        game_state['score_1'] = game_state['point_1']
        game_state['score_2'] = game_state['point_2']

    add_to_history('point_subtract', team,
                   score_before,
                   (game_state['score_1'], game_state['score_2']),
                   game_before,
                   (game_state['game_1'], game_state['game_2']),
                   set_before,
                   (game_state['set_1'], game_state['set_2']))

    game_state['last_updated'] = datetime.now().isoformat()
    broadcast_game_state()

    return {
        'success': True,
        'message': f'Point subtracted from {team} team',
        'game_state': game_state
    }

# ============================================================================
# HTTP API
# ============================================================================

@app.route('/')
def serve_scoreboard():
    return send_from_directory('.', 'padel_scoreboard.html')

@app.route('/<path:filename>')
def serve_static_files(filename):
    if os.path.exists(filename):
        return send_from_directory('.', filename)
    return f"File {filename} not found", 404

@app.route('/add_point', methods=['POST'])
def add_point():
    try:
        data = request.get_json()
        team = data.get('team', 'black')
        result = process_add_point(team)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/subtract_point', methods=['POST'])
def subtract_point():
    try:
        data = request.get_json()
        team = data.get('team', 'black')
        result = process_subtract_point(team)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/game_state', methods=['GET'])
def get_game_state():
    response_data = game_state.copy()
    response_data['match_storage_available'] = match_storage['match_completed'] and not match_storage['display_shown']
    return jsonify(response_data)

@app.route('/sensor_validation', methods=['GET'])
def get_sensor_validation():
    return jsonify(sensor_validation)

@app.route('/get_match_data', methods=['GET'])
def get_match_data():
    global match_storage
    if not match_storage['match_completed']:
        return jsonify({'success': False, 'error': 'No completed match data'}), 404
    return jsonify({
        'success': True,
        'match_data': match_storage['match_data'],
        'display_shown': match_storage['display_shown']
    })

@app.route('/mark_match_displayed', methods=['POST'])
def mark_match_displayed():
    global match_storage
    if not match_storage['match_completed']:
        return jsonify({'success': False, 'error': 'No match data'}), 400
    match_storage['display_shown'] = True
    wipe_immediately = request.get_json().get('wipe_immediately', True) if request.get_json() else True
    if wipe_immediately:
        wipe_match_storage()
        message = 'Match data wiped'
    else:
        message = 'Match data marked as displayed'
    return jsonify({'success': True, 'message': message})

@app.route('/match_history', methods=['GET'])
def get_match_history():
    global game_state
    black_points = len([h for h in game_state['match_history'] if h['action'] == 'point' and h['team'] == 'black'])
    yellow_points = len([h for h in game_state['match_history'] if h['action'] == 'point' and h['team'] == 'yellow'])
    black_games = len([h for h in game_state['match_history'] if h['action'] == 'game' and h['team'] == 'black'])
    yellow_games = len([h for h in game_state['match_history'] if h['action'] == 'game' and h['team'] == 'yellow'])
    black_sets = len([h for h in game_state['match_history'] if h['action'] == 'set' and h['team'] == 'black'])
    yellow_sets = len([h for h in game_state['match_history'] if h['action'] == 'set' and h['team'] == 'yellow'])

    match_info = {
        'start_time': game_state['match_start_time'],
        'end_time': game_state['match_end_time'],
        'duration': calculate_match_duration(),
        'winner': game_state['winner'] if game_state['match_won'] else None,
        'match_completed': game_state['match_won'],
        'total_actions': len(game_state['match_history'])
    }

    statistics = {
        'black_team_stats': {
            'points_won': black_points,
            'games_won': black_games,
            'sets_won': black_sets,
            'current_score': game_state['score_1'],
            'current_games': game_state['game_1'],
            'current_sets': game_state['set_1']
        },
        'yellow_team_stats': {
            'points_won': yellow_points,
            'games_won': yellow_games,
            'sets_won': yellow_sets,
            'current_score': game_state['score_2'],
            'current_games': game_state['game_2'],
            'current_sets': game_state['set_2']
        }
    }

    return jsonify({
        'success': True,
        'match_info': match_info,
        'statistics': statistics,
        'detailed_history': game_state['match_history'],
        'set_history': game_state['set_history'],
        'current_state': {
            'score_1': game_state['score_1'],
            'score_2': game_state['score_2'],
            'game_1': game_state['game_1'],
            'game_2': game_state['game_2'],
            'set_1': game_state['set_1'],
            'set_2': game_state['set_2'],
            'match_won': game_state['match_won']
        }
    })

@app.route('/reset_match', methods=['POST'])
def reset_match():
    global game_state, match_storage
    wipe_match_storage()
    game_state.update({
        'game_1': 0,
        'game_2': 0,
        'set_1': 0,
        'set_2': 0,
        'point_1': 0,
        'point_2': 0,
        'score_1': 0,
        'score_2': 0,
        'match_won': False,
        'winner': None,
        'set_history': [],
        'match_history': [],
        'match_start_time': datetime.now().isoformat(),
        'match_end_time': None,
        'last_updated': datetime.now().isoformat(),
        'should_switch_sides': False,
        'total_games_in_set': 0,
        'mode': 'normal'
    })
    broadcast_game_state()
    return jsonify({
        'success': True,
        'message': 'Match reset successfully',
        'game_state': game_state
    })

@app.route('/health', methods=['GET'])
def health_check():
    logo_exists = os.path.exists('logo.png')
    back_exists = os.path.exists('back.png')
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'socketio': 'enabled',
        'game_state': game_state,
        'match_status': 'completed' if game_state['match_won'] else 'in_progress',
        'history_entries': len(game_state['match_history']),
        'match_storage': {
            'completed': match_storage['match_completed'],
            'displayed': match_storage['display_shown']
        },
        'sensor_validation': sensor_validation,
        'files': {
            'logo_png': 'found' if logo_exists else 'missing',
            'back_png': 'found' if back_exists else 'missing'
        }
    })

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("="*70)
    print("🏓 Padel Scoreboard Backend - OPTIMIZED with Side Switching & Padel Rules")
    print("="*70)
    print("⚡ OPTIMIZATIONS:")
    print(" • Logging: MINIMAL (errors only)")
    print(" • SocketIO: Immediate broadcast")
    print(" • HTTP: Fast JSON processing")
    print(" • Expected response: <50ms")
    print(" • Side switch: After odd games (1, 3, 5, 7...)")
    print("="*70)
    print("🔌 Socket.IO enabled for real-time updates")
    print("🌐 Access at: http://127.0.0.1:5000")
    print("="*70)

    validation_thread = threading.Thread(target=run_initial_sensor_validation, daemon=True)
    validation_thread.start()

    socketio.run(app, debug=False, host='127.0.0.1', port=5000, allow_unsafe_werkzeug=True)
