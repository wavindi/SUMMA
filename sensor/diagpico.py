#!/usr/bin/env python3
"""
VL53L5CX via Raspberry Pi Pico UART Bridge - Enhanced Diagnostics
- Verifies Pi ↔ Pico communication
- Monitors data frequency and rate
- Tracks communication health
- Real-time statistics
- Auto-retry connection with periodic status updates
"""

import serial
import time
import sys
from collections import deque

# Configuration
SERIAL_PORT = '/dev/serial0'
BAUD_RATE = 57600
TIMEOUT = 2
CONNECTION_CHECK_INTERVAL = 5  # Seconds between status messages

# Colors
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    END = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

def print_color(text, color):
    print(f"{color}{text}{Colors.END}")

def print_header():
    """Print program header"""
    print_color("\n" + "="*80, Colors.BOLD)
    print_color("  VL53L5CX via Raspberry Pi Pico UART Bridge - Enhanced Diagnostics", Colors.BOLD)
    print_color("="*80, Colors.BOLD)
    print(f"  Serial Port: {SERIAL_PORT}")
    print(f"  Baud Rate: {BAUD_RATE}")
    print_color("="*80 + "\n", Colors.BOLD)

class CommunicationStats:
    """Track communication statistics"""
    def __init__(self):
        self.frame_count = 0
        self.bytes_received = 0
        self.last_frame_time = None
        self.fps_history = deque(maxlen=10)
        self.start_time = time.time()
        self.pico_ready = False
        self.sensor_initialized = False
        self.errors = 0
        self.last_error = None
        self.connection_established = False
        self.waiting_start_time = time.time()
        
    def record_frame(self, frame_size):
        """Record a received frame"""
        current_time = time.time()
        self.frame_count += 1
        self.bytes_received += frame_size
        
        if self.last_frame_time:
            time_diff = current_time - self.last_frame_time
            if time_diff > 0:
                fps = 1.0 / time_diff
                self.fps_history.append(fps)
        
        self.last_frame_time = current_time
    
    def get_avg_fps(self):
        """Calculate average FPS"""
        if not self.fps_history:
            return 0.0
        return sum(self.fps_history) / len(self.fps_history)
    
    def get_current_fps(self):
        """Get current FPS"""
        if not self.fps_history:
            return 0.0
        return self.fps_history[-1]
    
    def get_data_rate(self):
        """Calculate data rate in bytes/sec"""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return self.bytes_received / elapsed
        return 0
    
    def get_uptime(self):
        """Get uptime in seconds"""
        return time.time() - self.start_time
    
    def get_waiting_time(self):
        """Get time spent waiting for connection"""
        return time.time() - self.waiting_start_time
    
    def record_error(self, error_msg):
        """Record error"""
        self.errors += 1
        self.last_error = error_msg

def print_waiting_message(stats, attempt_num):
    """Print periodic waiting message"""
    waiting_time = stats.get_waiting_time()
    
    # Animated spinner
    spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    spin_char = spinner[attempt_num % len(spinner)]
    
    print(f"\r{Colors.YELLOW}{spin_char} Waiting for Pico response... "
          f"[{int(waiting_time)}s elapsed]{Colors.END}", end='', flush=True)

def print_connection_status(stats, check_count):
    """Print detailed connection status every 5 seconds"""
    waiting_time = stats.get_waiting_time()
    
    print(f"\n\n{Colors.YELLOW}{'─'*80}{Colors.END}")
    print(f"{Colors.YELLOW}⏳ CONNECTION STATUS CHECK #{check_count}{Colors.END}")
    print(f"{Colors.YELLOW}{'─'*80}{Colors.END}")
    print(f"  Status: {Colors.RED}No communication from Pico{Colors.END}")
    print(f"  Waiting time: {Colors.CYAN}{int(waiting_time)} seconds{Colors.END}")
    print(f"  Serial port: {Colors.CYAN}{SERIAL_PORT}{Colors.END}")
    print(f"  Baud rate: {Colors.CYAN}{BAUD_RATE}{Colors.END}")
    
    print(f"\n  {Colors.DIM}Possible issues:{Colors.END}")
    print(f"    • Pico not powered or not running code")
    print(f"    • Incorrect wiring (check TX/RX connections)")
    print(f"    • Pico code not started or crashed")
    print(f"    • Wrong serial port or baud rate")
    
    print(f"\n  {Colors.GREEN}Still listening... Press Ctrl+C to abort{Colors.END}")
    print(f"{Colors.YELLOW}{'─'*80}{Colors.END}\n")

def print_status_bar(stats):
    """Print real-time status bar"""
    uptime = stats.get_uptime()
    avg_fps = stats.get_avg_fps()
    current_fps = stats.get_current_fps()
    data_rate = stats.get_data_rate()
    
    # Status indicator
    if stats.pico_ready and stats.sensor_initialized:
        status_color = Colors.GREEN
        status_text = "● OPERATIONAL"
    elif stats.connection_established:
        status_color = Colors.YELLOW
        status_text = "● INITIALIZING"
    else:
        status_color = Colors.RED
        status_text = "● WAITING"
    
    # Connection health
    if avg_fps > 8:
        health = f"{Colors.GREEN}EXCELLENT{Colors.END}"
    elif avg_fps > 5:
        health = f"{Colors.YELLOW}GOOD{Colors.END}"
    elif avg_fps > 0:
        health = f"{Colors.RED}POOR{Colors.END}"
    else:
        health = f"{Colors.DIM}NO DATA{Colors.END}"
    
    print(f"\r{Colors.BOLD}[{status_color}{status_text}{Colors.END}{Colors.BOLD}]{Colors.END} "
          f"Frames: {stats.frame_count:4d} | "
          f"FPS: {current_fps:4.1f} (avg: {avg_fps:4.1f}) | "
          f"Rate: {data_rate/1024:5.1f} KB/s | "
          f"Health: {health} | "
          f"Uptime: {uptime:5.0f}s | "
          f"Errors: {stats.errors:2d}", 
          end='', flush=True)

def print_detailed_stats(stats):
    """Print detailed statistics"""
    print("\n\n" + "="*80)
    print_color("📊 DETAILED STATISTICS", Colors.BOLD)
    print("="*80)
    
    # Communication Status
    print(f"\n{Colors.BOLD}Communication Status:{Colors.END}")
    print(f"  Connection Established: {Colors.GREEN if stats.connection_established else Colors.RED}{'✓' if stats.connection_established else '✗'}{Colors.END}")
    print(f"  Pico Ready: {Colors.GREEN if stats.pico_ready else Colors.RED}{'✓' if stats.pico_ready else '✗'}{Colors.END}")
    print(f"  Sensor Initialized: {Colors.GREEN if stats.sensor_initialized else Colors.RED}{'✓' if stats.sensor_initialized else '✗'}{Colors.END}")
    
    # Frequency Statistics
    print(f"\n{Colors.BOLD}Frequency Statistics:{Colors.END}")
    print(f"  Current FPS: {Colors.CYAN}{stats.get_current_fps():.2f} Hz{Colors.END}")
    print(f"  Average FPS: {Colors.CYAN}{stats.get_avg_fps():.2f} Hz{Colors.END}")
    if stats.fps_history:
        print(f"  Min FPS: {Colors.YELLOW}{min(stats.fps_history):.2f} Hz{Colors.END}")
        print(f"  Max FPS: {Colors.YELLOW}{max(stats.fps_history):.2f} Hz{Colors.END}")
    
    # Data Transfer
    print(f"\n{Colors.BOLD}Data Transfer:{Colors.END}")
    print(f"  Total Frames: {Colors.GREEN}{stats.frame_count}{Colors.END}")
    print(f"  Bytes Received: {Colors.GREEN}{stats.bytes_received:,} bytes ({stats.bytes_received/1024:.2f} KB){Colors.END}")
    print(f"  Data Rate: {Colors.GREEN}{stats.get_data_rate():.2f} bytes/sec ({stats.get_data_rate()/1024:.2f} KB/s){Colors.END}")
    print(f"  Average Frame Size: {Colors.CYAN}{stats.bytes_received / stats.frame_count if stats.frame_count > 0 else 0:.0f} bytes{Colors.END}")
    
    # System Health
    print(f"\n{Colors.BOLD}System Health:{Colors.END}")
    print(f"  Uptime: {Colors.CYAN}{stats.get_uptime():.1f} seconds{Colors.END}")
    print(f"  Errors: {Colors.RED if stats.errors > 0 else Colors.GREEN}{stats.errors}{Colors.END}")
    if stats.last_error:
        print(f"  Last Error: {Colors.RED}{stats.last_error}{Colors.END}")
    
    print("\n" + "="*80)

def print_grid_8x8(distances, frame_num, fps):
    """Print 8x8 grid with enhanced display"""
    print("\n\n" + "="*80)
    print(f"{Colors.BOLD}{Colors.CYAN}Frame #{frame_num} - 8x8 Distance Map (mm) - {time.strftime('%H:%M:%S')} - {fps:.1f} Hz{Colors.END}")
    print("="*80)
    
    print("\n     ", end="")
    for col in range(8):
        print(f" Col{col} ", end="")
    print("\n     " + "-"*60)
    
    for row in range(8):
        print(f" R{row} |", end="")
        row_start = row * 8
        row_end = row_start + 8
        row_data = distances[row_start:row_end]
        
        for dist in row_data:
            if dist < 200:
                color = Colors.RED
                symbol = "█"
            elif dist < 500:
                color = Colors.YELLOW
                symbol = "▓"
            elif dist < 1000:
                color = Colors.GREEN
                symbol = "▒"
            else:
                color = Colors.CYAN
                symbol = "░"
            
            print(f" {color}{dist:4d}{symbol}{Colors.END}", end="")
        print(" |")
    
    print("     " + "-"*60)
    
    # Statistics
    valid_distances = [d for d in distances if 0 < d < 4000]
    if valid_distances:
        min_dist = min(valid_distances)
        max_dist = max(valid_distances)
        avg_dist = sum(valid_distances) // len(valid_distances)
        
        print(f"\n {Colors.BOLD}Zone Stats:{Colors.END}")
        print(f"  Min: {Colors.RED}{min_dist:4d}mm{Colors.END} | "
              f"Max: {Colors.CYAN}{max_dist:4d}mm{Colors.END} | "
              f"Avg: {Colors.GREEN}{avg_dist:4d}mm{Colors.END} | "
              f"Valid: {Colors.YELLOW}{len(valid_distances)}/64{Colors.END}")
        
        # Detection zones
        close_zones = len([d for d in valid_distances if d < 500])
        if close_zones > 3:
            print(f"\n {Colors.RED}⚠ DETECTION: {close_zones} zones < 500mm{Colors.END}")

def parse_frame(data_buffer):
    """Parse sensor data"""
    distances = []
    statuses = []
    
    for line in data_buffer:
        line = line.strip()
        if ',' in line:
            try:
                parts = line.split(',')
                if len(parts) == 2:
                    dist = int(parts[0])
                    status = int(parts[1])
                    distances.append(dist)
                    statuses.append(status)
            except ValueError:
                pass
    
    return distances, statuses

def main():
    print_header()
    
    print_color("📡 Opening serial port...", Colors.YELLOW)
    
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            timeout=TIMEOUT,
            write_timeout=TIMEOUT
        )
        print_color("✓ Serial port opened successfully", Colors.GREEN)
        print_color("✓ Waiting for Pico communication...\n", Colors.YELLOW)
    except serial.SerialException as e:
        print_color(f"✗ Serial connection failed: {e}", Colors.RED)
        print("\n" + "="*80)
        print_color("TROUBLESHOOTING GUIDE:", Colors.BOLD)
        print("="*80)
        print("  1. Enable UART:")
        print("     sudo raspi-config → Interface Options → Serial Port")
        print("     - Login shell: NO")
        print("     - Serial port hardware: YES")
        print("\n  2. Check /boot/config.txt:")
        print("     enable_uart=1")
        print("     dtoverlay=disable-bt")
        print("\n  3. Verify wiring:")
        print("     Pico GP0 (TX) → Pi Pin 10 (RX)")
        print("     Pico GP1 (RX) → Pi Pin 8 (TX)")
        print("     Pico GND → Pi Pin 14 (GND)")
        print("\n  4. Check Pico:")
        print("     - USB power connected")
        print("     - Code uploaded and running")
        print("     - LED blinking (if coded)")
        print("\n  5. Test port:")
        print("     ls -l /dev/serial0")
        print("="*80)
        sys.exit(1)
    
    stats = CommunicationStats()
    reading_data = False
    data_buffer = []
    last_status_check = time.time()
    last_spinner_update = time.time()
    status_check_count = 0
    spinner_count = 0
    show_full_frames = True  # Toggle to show/hide full grid
    
    try:
        while True:
            current_time = time.time()
            
            # Check if we're still waiting for connection
            if not stats.connection_established:
                # Update spinner animation more frequently
                if current_time - last_spinner_update > 0.1:
                    print_waiting_message(stats, spinner_count)
                    spinner_count += 1
                    last_spinner_update = current_time
                
                # Print detailed status every 5 seconds
                if current_time - last_status_check > CONNECTION_CHECK_INTERVAL:
                    status_check_count += 1
                    print_connection_status(stats, status_check_count)
                    last_status_check = current_time
            
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    stats.bytes_received += len(line) + 1  # +1 for newline
                except Exception as e:
                    stats.record_error(f"Decode error: {e}")
                    continue
                
                if not line:
                    continue
                
                # Mark connection as established on first message
                if not stats.connection_established:
                    stats.connection_established = True
                    waiting_time = stats.get_waiting_time()
                    print(f"\r{' '*80}\r", end='')  # Clear waiting message
                    print_color(f"✓ Communication established with Pico! (after {int(waiting_time)}s)", Colors.GREEN)
                
                # Status messages
                if line == "PICO_BRIDGE_START":
                    print_color("✓ Pico bridge started", Colors.GREEN)
                
                elif line == "INIT_SENSOR":
                    print_color("⏳ Initializing VL53L5CX sensor...", Colors.YELLOW)
                
                elif line == "SENSOR_FOUND":
                    stats.sensor_initialized = True
                    print_color("✓ VL53L5CX sensor detected and initialized", Colors.GREEN)
                
                elif line.startswith("CONFIG:"):
                    print_color(f"⚙  {line}", Colors.CYAN)
                
                elif line == "READY":
                    stats.pico_ready = True
                    print_color("✓ System ready - streaming data...\n", Colors.GREEN)
                    print_color("Press Ctrl+C for detailed statistics\n", Colors.DIM)
                
                elif line.startswith("ERROR:"):
                    stats.record_error(line)
                    print_color(f"\n✗ {line}", Colors.RED)
                
                # Data frames
                elif line == "DATA_START":
                    reading_data = True
                    data_buffer = []
                
                elif line == "DATA_END":
                    reading_data = False
                    distances, statuses = parse_frame(data_buffer)
                    
                    if distances:
                        frame_size = sum(len(l) for l in data_buffer)
                        stats.record_frame(frame_size)
                        
                        if show_full_frames and len(distances) == 64:
                            print_grid_8x8(distances, stats.frame_count, stats.get_current_fps())
                        
                        # Print status bar every frame
                        print_status_bar(stats)
                
                elif reading_data:
                    data_buffer.append(line)
                
                # Debug messages
                else:
                    if line and not line.startswith("Frame"):
                        print(f"\n{Colors.DIM}[Pico] {line}{Colors.END}")
            
            else:
                # Print status bar for connected state even without new data
                if stats.connection_established and current_time - last_status_check > 1.0:
                    print_status_bar(stats)
                    last_status_check = current_time
                
                time.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\n\n")
        print_color("="*80, Colors.BOLD)
        print_color("  Program interrupted (Ctrl+C)", Colors.YELLOW)
        print_color("="*80, Colors.BOLD)
        
        # Print final detailed statistics
        if stats.connection_established:
            print_detailed_stats(stats)
        else:
            print_color("\nNo communication was established with Pico.", Colors.RED)
            print_color(f"Waited for {int(stats.get_waiting_time())} seconds.", Colors.YELLOW)
    
    except Exception as e:
        print_color(f"\n\n✗ Unexpected error: {e}", Colors.RED)
        import traceback
        traceback.print_exc()
    
    finally:
        if ser and ser.is_open:
            ser.close()
            print_color("\n✓ Serial port closed cleanly", Colors.CYAN)
            print()

if __name__ == "__main__":
    main()
