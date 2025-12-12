#!/usr/bin/env python3
"""
VL53L5CX Sensor Reader via Raspberry Pi Pico UART Bridge
"""

import serial
import time
import sys

# Configuration
SERIAL_PORT = '/dev/serial0'
BAUD_RATE = 57600
TIMEOUT = 2

# Colors
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_color(text, color):
    print(f"{color}{text}{Colors.END}")

def print_grid_8x8(distances):
    """Print 8x8 grid"""
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.CYAN}8x8 Distance Map (mm) - {time.strftime('%H:%M:%S')}{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    
    print("    ", end="")
    for col in range(8):
        print(f"Col{col:1d} ", end="")
    print()
    
    for row in range(8):
        print(f"R{row}: ", end="")
        row_start = row * 8
        row_end = row_start + 8
        row_data = distances[row_start:row_end]
        
        for dist in row_data:
            if dist < 200:
                color = Colors.RED
            elif dist < 500:
                color = Colors.YELLOW
            elif dist < 1000:
                color = Colors.GREEN
            else:
                color = Colors.CYAN
            
            print(f"{color}{dist:4d}{Colors.END} ", end="")
        print()
    
    valid_distances = [d for d in distances if 0 < d < 4000]
    if valid_distances:
        print(f"\n{Colors.BOLD}Stats:{Colors.END}")
        print(f"  Min: {min(valid_distances)}mm | Max: {max(valid_distances)}mm | Avg: {sum(valid_distances)//len(valid_distances)}mm")
        print(f"  Valid zones: {len(valid_distances)}/64")

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
    print_color("="*70, Colors.BOLD)
    print_color("VL53L5CX via Raspberry Pi Pico Bridge", Colors.BOLD)
    print_color("="*70, Colors.BOLD)
    
    print(f"\nConnecting to {SERIAL_PORT} at {BAUD_RATE} baud...")
    
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            timeout=TIMEOUT
        )
        print_color("✓ Serial port opened", Colors.GREEN)
    except serial.SerialException as e:
        print_color(f"✗ Error: {e}", Colors.RED)
        print("\nTroubleshooting:")
        print("  1. Check UART enabled: sudo raspi-config")
        print("  2. Check wiring: GP0→Pin10, GP1→Pin8, GND→Pin14")
        print("  3. Check Pico has power")
        sys.exit(1)
    
    print_color("Waiting for Pico...\n", Colors.YELLOW)
    
    reading_data = False
    data_buffer = []
    frame_count = 0
    last_frame_time = time.time()
    
    try:
        while True:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                except:
                    continue
                
                if not line:
                    continue
                
                # Status messages
                if line == "PICO_BRIDGE_START":
                    print_color("✓ Pico bridge started", Colors.GREEN)
                
                elif line == "INIT_SENSOR":
                    print_color("⏳ Initializing sensor...", Colors.YELLOW)
                
                elif line == "SENSOR_FOUND":
                    print_color("✓ VL53L5CX detected", Colors.GREEN)
                
                elif line.startswith("CONFIG:"):
                    print_color(f"✓ {line}", Colors.GREEN)
                
                elif line == "READY":
                    print_color("✓ System ready - receiving data...\n", Colors.GREEN)
                
                elif line.startswith("ERROR:"):
                    print_color(f"✗ {line}", Colors.RED)
                
                # Data frames
                elif line == "DATA_START":
                    reading_data = True
                    data_buffer = []
                
                elif line == "DATA_END":
                    reading_data = False
                    distances, statuses = parse_frame(data_buffer)
                    
                    if distances:
                        frame_count += 1
                        current_time = time.time()
                        fps = 1.0 / (current_time - last_frame_time) if last_frame_time else 0
                        last_frame_time = current_time
                        
                        print(f"\n{Colors.BOLD}--- Frame #{frame_count} ({fps:.1f} Hz) ---{Colors.END}")
                        
                        if len(distances) == 64:
                            print_grid_8x8(distances)
                        else:
                            print_color(f"⚠ Unexpected size: {len(distances)} zones", Colors.YELLOW)
                
                elif reading_data:
                    data_buffer.append(line)
                
                else:
                    # Debug unknown messages
                    if line and not line.startswith("Frame sent"):
                        print(f"[DEBUG] {line}")
            
            else:
                time.sleep(0.001)
    
    except KeyboardInterrupt:
        print_color("\n\n✓ Stopped (Ctrl+C)", Colors.GREEN)
    
    except Exception as e:
        print_color(f"\n✗ Error: {e}", Colors.RED)
        import traceback
        traceback.print_exc()
    
    finally:
        if ser and ser.is_open:
            ser.close()
            print_color("Serial port closed", Colors.CYAN)

if __name__ == "__main__":
    main()
