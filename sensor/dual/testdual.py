#!/usr/bin/env python3
"""
Dual VL53L5CX Sensor Reader - Live Mode
Starts reading immediately without waiting for startup
"""

import pigpio
import time
import sys
import threading

SENSOR1_PIN = 23
SENSOR2_PIN = 24
BAUD_RATE = 57600

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    END = '\033[0m'
    BOLD = '\033[1m'

class SensorReader:
    def __init__(self, pi, gpio, sensor_id, color):
        self.pi = pi
        self.gpio = gpio
        self.sensor_id = sensor_id
        self.color = color
        self.line_buffer = ""
        self.reading_data = False
        self.data_buffer = []
        self.frame_count = 0
        self.running = True
        self.last_frame_time = time.time()
        
    def parse_frame(self):
        distances = []
        for line in self.data_buffer:
            line = line.strip()
            if ',' in line:
                try:
                    parts = line.split(',')
                    if len(parts) == 2:
                        dist = int(parts[0])
                        distances.append(dist)
                except ValueError:
                    pass
        return distances
    
    def print_grid(self, distances):
        if len(distances) != 16:
            return
        
        current_time = time.time()
        fps = 1.0 / (current_time - self.last_frame_time) if self.last_frame_time else 0
        self.last_frame_time = current_time
            
        print(f"\n{self.color}{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{self.color}{Colors.BOLD}Sensor #{self.sensor_id} - Frame {self.frame_count} ({fps:.1f} Hz) - {time.strftime('%H:%M:%S')}{Colors.END}")
        print(f"{self.color}{Colors.BOLD}{'='*60}{Colors.END}")
        
        for row in range(4):
            print(f"{self.color}Row {row}: {Colors.END}", end="")
            for col in range(4):
                idx = row * 4 + col
                dist = distances[idx]
                
                if dist < 200:
                    c = Colors.RED
                elif dist < 500:
                    c = Colors.YELLOW
                elif dist < 1000:
                    c = Colors.GREEN
                else:
                    c = Colors.CYAN
                
                print(f"{c}{dist:5d}mm{Colors.END} ", end="")
            print()
        
        valid = [d for d in distances if 0 < d < 4000]
        if valid:
            print(f"{self.color}Min: {min(valid)}mm | Max: {max(valid)}mm | Avg: {sum(valid)//len(valid)}mm{Colors.END}")
    
    def process_line(self, line):
        line = line.strip()
        if not line:
            return
        
        # Look for any PICO1 or PICO2 prefix, or just DATA_START/DATA_END
        if "DATA_START" in line:
            self.reading_data = True
            self.data_buffer = []
        
        elif "DATA_END" in line:
            self.reading_data = False
            distances = self.parse_frame()
            if len(distances) == 16:
                self.frame_count += 1
                self.print_grid(distances)
        
        elif self.reading_data:
            self.data_buffer.append(line)
        
        # Status messages
        elif "START" in line or "READY" in line or "OK" in line:
            print(f"{self.color}✓ Sensor #{self.sensor_id}: {line}{Colors.END}")
        
        elif "ERROR" in line:
            print(f"{Colors.RED}✗ Sensor #{self.sensor_id}: {line}{Colors.END}")
    
    def read_loop(self):
        while self.running:
            (count, data) = self.pi.bb_serial_read(self.gpio)
            
            if count > 0:
                try:
                    text = data.decode('utf-8', errors='ignore')
                    self.line_buffer += text
                    
                    while '\n' in self.line_buffer:
                        line, self.line_buffer = self.line_buffer.split('\n', 1)
                        self.process_line(line)
                
                except Exception:
                    pass
            
            time.sleep(0.001)

def main():
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}Dual VL53L5CX Sensor Reader - Live Mode{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")
    
    # Initialize pigpio
    try:
        pi = pigpio.pi()
        if not pi.connected:
            print(f"{Colors.RED}✗ Failed to connect to pigpiod{Colors.END}")
            print("\nRun: sudo killall pigpiod && sudo pigpiod")
            sys.exit(1)
        
        print(f"{Colors.GREEN}✓ pigpiod connected{Colors.END}")
        
        # Open serial for both sensors
        pi.set_mode(SENSOR1_PIN, pigpio.INPUT)
        pi.bb_serial_read_open(SENSOR1_PIN, BAUD_RATE, 8)
        print(f"{Colors.CYAN}✓ Sensor #1 on GPIO{SENSOR1_PIN} @ {BAUD_RATE} baud{Colors.END}")
        
        pi.set_mode(SENSOR2_PIN, pigpio.INPUT)
        pi.bb_serial_read_open(SENSOR2_PIN, BAUD_RATE, 8)
        print(f"{Colors.MAGENTA}✓ Sensor #2 on GPIO{SENSOR2_PIN} @ {BAUD_RATE} baud{Colors.END}")
        
    except Exception as e:
        print(f"{Colors.RED}✗ Error: {e}{Colors.END}")
        sys.exit(1)
    
    print(f"\n{Colors.GREEN}Reading data from both sensors...{Colors.END}\n")
    
    # Create sensor readers
    reader1 = SensorReader(pi, SENSOR1_PIN, 1, Colors.CYAN)
    reader2 = SensorReader(pi, SENSOR2_PIN, 2, Colors.MAGENTA)
    
    # Start threads
    thread1 = threading.Thread(target=reader1.read_loop)
    thread2 = threading.Thread(target=reader2.read_loop)
    
    thread1.daemon = True
    thread2.daemon = True
    
    thread1.start()
    thread2.start()
    
    try:
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print(f"\n\n{Colors.BOLD}{'='*70}{Colors.END}")
        print(f"{Colors.BOLD}Summary{Colors.END}")
        print(f"{Colors.BOLD}{'='*70}{Colors.END}")
        print(f"{Colors.CYAN}Sensor #1 frames: {reader1.frame_count}{Colors.END}")
        print(f"{Colors.MAGENTA}Sensor #2 frames: {reader2.frame_count}{Colors.END}")
    
    finally:
        reader1.running = False
        reader2.running = False
        pi.bb_serial_read_close(SENSOR1_PIN)
        pi.bb_serial_read_close(SENSOR2_PIN)
        pi.stop()
        print(f"\n{Colors.GREEN}Closed{Colors.END}")

if __name__ == "__main__":
    main()
