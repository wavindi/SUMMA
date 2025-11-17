🏓 ALMUS Padel Scoring System
<div align="center">
Version
Python
Flask
License
Platform

Professional automated padel scoring system with real-time VL53L0X sensor integration and web-based display

Features • Hardware • Installation • Usage • Troubleshooting

</div>
📋 Table of Contents
Overview

Features

System Architecture

Hardware Requirements

Software Requirements

Installation

Configuration

Usage

API Documentation

Troubleshooting

Contributing

License

🎯 Overview
The ALMUS Padel Scoring System is a professional-grade, automated scoring solution for padel courts. It uses VL53L0X Time-of-Flight sensors to automatically detect scored points and displays real-time match statistics on a web-based scoreboard.

Key Highlights
✅ Automated Point Detection - VL53L0X sensors detect ball placement

✅ Real-time Updates - Socket.IO for instant score synchronization

✅ Professional Tennis Scoring - Implements 0-15-30-40-Game-Set-Match logic

✅ Multi-Sensor Support - Deploy sensors on both team sides

✅ Web-Based Display - Responsive HTML/CSS/JavaScript interface

✅ Match Statistics - Detailed history, sets breakdown, and duration tracking

✅ LED Visual Feedback - RGB LEDs indicate sensor status

✅ Winner Display - Animated overlay with comprehensive match data

✨ Features
Scoring System
Professional tennis scoring (0, 15, 30, 40, Game)

Set tracking (first to 6 games with 2-game lead)

Match tracking (first to 2 sets wins)

Point-by-point history

Detailed match statistics

Sensor Integration
Duration-based triggering:

1-3 seconds hold = ADD POINT (green LED blinks)

3.2-6 seconds hold = SUBTRACT POINT (red LED solid)

Automatic calibration on startup

Median filtering for noise reduction

Configurable detection thresholds

Web Interface
Real-time score updates via Socket.IO

Professional athletic design with skewed elements

Responsive layout for TV displays

Winner overlay with match summary

Manual control panel (hidden by default)

Match history and statistics viewer

Hardware Feedback
Green LED: Blinking = Add point zone active

Red LED: Solid = Subtract point zone active

Visual confirmation of sensor actions

🏗️ System Architecture
text
┌─────────────────┐
│  VL53L0X Sensor │ (GPIO Pins)
│   + RGB LEDs    │
└────────┬────────┘
         │ I2C + GPIO
         ▼
┌─────────────────┐
│   sensor.py     │ (Python)
│ Socket.IO Client│
└────────┬────────┘
         │ Socket.IO
         ▼
┌─────────────────┐
│ padel_backend.py│ (Flask + Socket.IO)
│   Port 5000     │
└────────┬────────┘
         │ HTTP + WebSocket
         ▼
┌─────────────────┐
│  Web Browser    │ (HTML/CSS/JS)
│  Scoreboard UI  │
└─────────────────┘
Communication Flow
Sensor Detection → VL53L0X detects object for 1-3 seconds

Event Processing → sensor.py calculates duration and determines action

Socket.IO Emission → Event sent to Flask backend

Score Calculation → Backend updates game state with tennis scoring logic

Broadcast → All connected clients receive updated state

UI Update → Browser displays new scores instantly

🔧 Hardware Requirements
Required Components
Component	Specification	Quantity	Notes
Raspberry Pi	Pi Zero W/2W, Pi 3, Pi 4, Pi 5	1	Any model with GPIO
VL53L0X Sensor	Time-of-Flight Distance Sensor	1-2	One per team side
RGB LEDs	5mm Common Cathode	2 per sensor	Green + Red per sensor
Resistors	220Ω	2 per LED	Current limiting
Jumper Wires	Female-to-Female	8+	For connections
Power Supply	5V 2.5A+	1	For Raspberry Pi
MicroSD Card	16GB+ Class 10	1	For OS
Wiring Diagram
VL53L0X Sensor (I2C)
text
VL53L0X    →  Raspberry Pi
────────────────────────────
VCC        →  Pin 1 (3.3V)
GND        →  Pin 6 (GND)
SDA        →  Pin 3 (GPIO 2)
SCL        →  Pin 5 (GPIO 3)
RGB LEDs (GPIO)
text
LED        →  Raspberry Pi
────────────────────────────
Green LED  →  Pin 37 (GPIO 26) + 220Ω resistor
Red LED    →  Pin 36 (GPIO 16) + 220Ω resistor
GND        →  Pin 39 (GND)
Optional Components
HDMI display for dedicated scoreboard

USB keyboard/mouse for configuration

Case/enclosure for Raspberry Pi

Mounting hardware for sensors

💻 Software Requirements
Operating System
Raspberry Pi OS (Bookworm or later recommended)

Python 3.11+ (pre-installed)

Python Packages
See requirements.txt for complete list. Key dependencies:

Flask 2.3.3 (Web framework)

Flask-SocketIO 5.3.4 (Real-time communication)

python-socketio 5.9.0 (Socket.IO client)

adafruit-blinka (Hardware abstraction)

adafruit-circuitpython-vl53l0x (Sensor driver)

📦 Installation
Step 1: Prepare Raspberry Pi
bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y python3-pip python3-dev i2c-tools git

# Enable I2C interface
sudo raspi-config nonint do_i2c 0

# Reboot
sudo reboot
Step 2: Clone Repository
bash
cd /home/pi/Desktop
git clone https://github.com/yourusername/padel-scoring-system.git
cd padel-scoring-system
Or download directly:

bash
mkdir -p /home/pi/Desktop/PadelScore-ALMUS
cd /home/pi/Desktop/PadelScore-ALMUS
# Upload all project files here
Step 3: Install Python Dependencies
bash
cd /home/pi/Desktop/PadelScore-ALMUS

# For Raspberry Pi OS Bookworm+
sudo pip3 install --break-system-packages -r requirements.txt

# For older OS versions
pip3 install -r requirements.txt
Step 4: Verify Hardware
bash
# Check I2C devices (VL53L0X should appear at 0x29)
i2cdetect -y 1

# Expected output:
#      0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
# ...
# 20: -- -- -- -- -- -- -- -- -- 29 -- -- -- -- -- --
# ...

# Test imports
python3 -c "import flask; import socketio; import adafruit_vl53l0x; print('✅ Installation successful!')"
Step 5: File Structure
Ensure your directory contains:

text
PadelScore-ALMUS/
├── padel_backend.py          # Flask + Socket.IO backend
├── sensor.py                 # VL53L0X sensor controller
├── padel_scoreboard.html     # Frontend HTML
├── padel_js.js              # JavaScript with Socket.IO
├── padel_css.css            # Styling
├── requirements.txt          # Python dependencies
├── logo.png                 # Logo image (optional)
├── back.png                 # Background image (optional)
└── README.md                # This file
⚙️ Configuration
Backend Configuration (padel_backend.py)
python
# Port configuration (default: 5000)
PORT = 5000

# Host configuration (0.0.0.0 = all interfaces)
HOST = '0.0.0.0'
Sensor Configuration (sensor.py)
python
# Detection thresholds (in millimeters)
THRESHOLD_MIN = 3   # Minimum distance change to detect
THRESHOLD_MAX = 20  # Maximum distance change to consider valid

# Duration-based actions (in seconds)
PLUS_MIN_S = 1.0    # Minimum hold time for ADD POINT
PLUS_MAX_S = 3.0    # Maximum hold time for ADD POINT
MINUS_MIN_S = 3.2   # Minimum hold time for SUBTRACT POINT
MINUS_MAX_S = 6.0   # Maximum hold time for SUBTRACT POINT

# Team assignment
TEAM_SIDE = 'black'  # Change to 'yellow' for other sensor

# Flask server URL
FLASK_SERVER_URL = 'http://localhost:5000'  # Update for remote Pi
JavaScript Configuration (padel_js.js)
javascript
// Update with your Raspberry Pi's IP address
const socket = io('http://192.168.1.16:5000', {
    transports: ['polling', 'websocket']
});

const API_BASE = "http://192.168.1.16:5000";
🚀 Usage
Starting the System
Terminal 1: Start Backend Server
bash
cd /home/pi/Desktop/PadelScore-ALMUS
python3 padel_backend.py
Expected output:

text
🏓 Starting Padel Scoreboard Server with Socket.IO...
======================================================================
🔌 Socket.IO enabled for real-time updates
🌐 Access at: http://localhost:5000
======================================================================
 * Running on http://0.0.0.0:5000
Terminal 2: Start Sensor
bash
cd /home/pi/Desktop/PadelScore-ALMUS
sudo python3 sensor.py
Expected output:

text
🔧 Initializing VL53L0X sensor...
🔌 Connecting to Flask server at http://localhost:5000...
✅ Socket.IO connection established!

📏 CALIBRATION_START...
✅ CALIBRATION_END: Baseline at 150 mm
🎯 Monitoring for BLACK team
   • 1-3s hold   = ADD POINT
   • 3.2-6s hold = SUBTRACT POINT
   • Socket.IO = ✅ CONNECTED

============================================================
Browser: Access Scoreboard
text
Open browser to: http://RASPBERRY_PI_IP:5000
Example: http://192.168.1.16:5000
Using Manual Controls
Click the logo in the top-right corner to show/hide control panel

Use buttons: BLACK +1, YELLOW +1, RESET

Keyboard shortcuts (when controls visible):

1 - Add point to BLACK

2 - Add point to YELLOW

Q - Subtract point from BLACK

W - Subtract point from YELLOW

Ctrl+R - Reset match

Ctrl+H - Toggle history

ESC - Close modals

Sensor Operation
Adding a Point:

Place ball/object in front of sensor

Hold for 1-3 seconds (green LED blinks)

Remove object

Score updates automatically

Subtracting a Point (correction):

Place ball/object in front of sensor

Hold for 3.2-6 seconds (red LED solid)

Remove object

Score decreases by one point

📡 API Documentation
HTTP Endpoints
GET /
Serves the main scoreboard HTML page.

GET /game_state
Returns current game state.

Response:

json
{
  "score_1": 15,
  "score_2": 0,
  "game_1": 0,
  "game_2": 0,
  "set_1": 0,
  "set_2": 0,
  "match_won": false,
  "winner": null,
  "set_history": [],
  "match_history": [...]
}
POST /add_point
Manually add a point to a team.

Request:

json
{
  "team": "black"  // or "yellow"
}
POST /subtract_point
Manually subtract a point from a team.

POST /reset_match
Reset all scores and start a new match.

GET /match_history
Get detailed match statistics and history.

GET /health
Health check endpoint with system status.

Socket.IO Events
Client → Server
Event	Data	Description
connect	-	Client connection established
disconnect	-	Client disconnected
request_game_state	-	Request current game state
sensor_point_scored	{team, action, timestamp}	Sensor detected point
Server → Client
Event	Data	Description
game_state_update	{score_1, score_2, ...}	Full game state update
point_scored	{team, action, game_state}	Point scored notification
match_won	{winner, match_data}	Match completion notification
🐛 Troubleshooting
Sensor Issues
Problem: OSError: [Errno 121] Remote I/O error

Solution:

bash
# Check sensor is detected
i2cdetect -y 1

# Should show 29 at address 0x29
# If not detected:
# 1. Check wiring (VCC → 3.3V, not 5V!)
# 2. Reseat connections
# 3. Try different jumper wires
Problem: Sensor readings unstable

Solution:

python
# In sensor.py, adjust thresholds:
THRESHOLD_MIN = 5   # Increase for less sensitivity
THRESHOLD_MAX = 15  # Decrease for tighter detection
Connection Issues
Problem: Browser shows "Not Connected"

Solution:

bash
# 1. Check backend is running
ps aux | grep padel_backend

# 2. Check Socket.IO port is open
sudo netstat -tlnp | grep 5000

# 3. Test connection
curl http://localhost:5000/health

# 4. Check firewall
sudo ufw status
sudo ufw allow 5000/tcp
Problem: Sensor can't connect to backend

Solution:

python
# In sensor.py, verify URL matches Pi's IP:
FLASK_SERVER_URL = 'http://192.168.1.16:5000'  # Update this
Display Issues
Problem: Scores not visible (text color issues)

Solution:

bash
# Hard refresh browser
Press: Ctrl+Shift+R

# Clear browser cache
Press: Ctrl+Shift+Delete
Problem: UI not updating in real-time

Solution:

bash
# Check browser console (F12)
# Should see: "✅ Connected to server via Socket.IO"

# If not connected:
# 1. Verify padel_js.js has correct IP
# 2. Check Socket.IO script loaded
# 3. Test with: socket.connected (in browser console)
Performance Issues
Problem: Slow response on Pi Zero

Solution:

bash
# Use production server instead of development Flask
gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:5000 padel_backend:app
Common Error Messages
Error	Cause	Solution
ModuleNotFoundError: No module named 'socketio'	Missing python-socketio	sudo pip3 install --break-system-packages python-socketio
/ is not a connected namespace	Sensor can't connect to backend	Verify backend is running, check URL
Permission denied: '/dev/i2c-1'	Need sudo for I2C	Run sensor with sudo python3 sensor.py
Address 0x29 not found	Sensor not connected	Check wiring, run i2cdetect -y 1
🔄 Autostart on Boot (Optional)
Using systemd Services
Backend Service
bash
sudo nano /etc/systemd/system/padel-backend.service
text
[Unit]
Description=Padel Scoreboard Backend
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Desktop/PadelScore-ALMUS
ExecStart=/usr/bin/python3 /home/pi/Desktop/PadelScore-ALMUS/padel_backend.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
Sensor Service
bash
sudo nano /etc/systemd/system/padel-sensor.service
text
[Unit]
Description=Padel Sensor Controller
After=network.target padel-backend.service

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi/Desktop/PadelScore-ALMUS
ExecStart=/usr/bin/python3 /home/pi/Desktop/PadelScore-ALMUS/sensor.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
Enable Services
bash
# Enable services
sudo systemctl enable padel-backend.service
sudo systemctl enable padel-sensor.service

# Start services
sudo systemctl start padel-backend.service
sudo systemctl start padel-sensor.service

# Check status
sudo systemctl status padel-backend.service
sudo systemctl status padel-sensor.service
📊 Match Scoring Logic
Tennis Scoring System
text
Point Progression:
0 → 15 → 30 → 40 → Game

Game Rules:
- Win 4 points to win a game
- Must win by 2 points (deuce not implemented)

Set Rules:
- First to 6 games wins set
- Must win by 2 games minimum
- Example: 6-4 ✓ | 6-5 ✗ (continue) | 7-5 ✓

Match Rules:
- First to 2 sets wins match
- Best of 3 sets format
- Example: 2-0 or 2-1
Example Match Flow
text
Start: 0-0 | Games: 0-0 | Sets: 0-0

Point 1 (Black): 15-0 | Games: 0-0 | Sets: 0-0
Point 2 (Black): 30-0 | Games: 0-0 | Sets: 0-0
Point 3 (Black): 40-0 | Games: 0-0 | Sets: 0-0
Point 4 (Black): 0-0 | Games: 1-0 | Sets: 0-0  ← Game won!

... (continue until 6 games won)

Games: 6-4 | Sets: 1-0  ← Set won!

... (continue second set)

Sets: 2-0 or 2-1  ← Match won! 🏆
🤝 Contributing
Contributions are welcome! Please follow these guidelines:

Fork the repository

Create a feature branch (git checkout -b feature/amazing-feature)

Commit your changes (git commit -m 'Add amazing feature')

Push to the branch (git push origin feature/amazing-feature)

Open a Pull Request

Development Setup
bash
# Install development dependencies
pip3 install pytest pytest-cov black flake8

# Run tests
pytest tests/

# Format code
black *.py

# Lint code
flake8 *.py
📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

👨‍💻 Author
ALMUS Team

GitHub: @yourusername

Email: your.email@example.com

🙏 Acknowledgments
Adafruit Industries - VL53L0X driver and hardware support

Flask - Web framework

Socket.IO - Real-time communication

Raspberry Pi Foundation - Hardware platform

📸 Screenshots
Scoreboard Main View
Main scoreboard display with real-time scores

Winner Display
Winner overlay with match statistics

Control Panel
Manual control panel (accessible via logo click)

🔗 Related Resources
VL53L0X Datasheet

Raspberry Pi GPIO Pinout

Flask-SocketIO Documentation

Adafruit CircuitPython VL53L0X Guide

<div align="center">
Made with ❤️ for the padel community

⭐ Star this repo if you found it helpful!

</div>
