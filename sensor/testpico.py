#!/usr/bin/env python3
"""
Simple UART Test Reader
Receives messages from Pico on GPIO24
"""

import pigpio
import time
import sys

# Configuration
RX_PIN = 23       # GPIO24
BAUD_RATE = 57600

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

def main():
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}UART Test Reader - GPIO{RX_PIN} @ {BAUD_RATE} baud{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")
    
    # Initialize pigpio
    try:
        pi = pigpio.pi()
        if not pi.connected:
            print(f"{Colors.RED}✗ Failed to connect to pigpiod{Colors.END}")
            print("\nRun: sudo killall pigpiod && sudo pigpiod")
            sys.exit(1)
        
        print(f"{Colors.GREEN}✓ pigpiod connected{Colors.END}")
        
        # Open software serial
        pi.set_mode(RX_PIN, pigpio.INPUT)
        pi.bb_serial_read_open(RX_PIN, BAUD_RATE, 8)
        print(f"{Colors.GREEN}✓ Serial opened on GPIO{RX_PIN}{Colors.END}")
        
    except Exception as e:
        print(f"{Colors.RED}✗ Error: {e}{Colors.END}")
        sys.exit(1)
    
    print(f"\n{Colors.YELLOW}Waiting for Pico...{Colors.END}\n")
    
    line_buffer = ""
    message_count = 0
    corrupted_count = 0
    start_time = time.time()
    
    try:
        while True:
            (count, data) = pi.bb_serial_read(RX_PIN)
            
            if count > 0:
                try:
                    text = data.decode('utf-8', errors='ignore')
                    line_buffer += text
                    
                    while '\n' in line_buffer:
                        line, line_buffer = line_buffer.split('\n', 1)
                        line = line.strip()
                        
                        if not line:
                            continue
                        
                        # Check if clean message
                        if "Hello Pi" in line:
                            message_count += 1
                            elapsed = int(time.time() - start_time)
                            
                            # Check if corrupted
                            printable_ratio = sum(c.isprintable() or c in '\n\r\t' for c in line) / len(line) if len(line) > 0 else 0
                            
                            if printable_ratio > 0.9:
                                print(f"{Colors.GREEN}✓ [{elapsed:3d}s] {line}{Colors.END}")
                            else:
                                corrupted_count += 1
                                print(f"{Colors.YELLOW}⚠ [{elapsed:3d}s] {line} (corrupted){Colors.END}")
                        
                        elif line.startswith("==="):
                            print(f"{Colors.CYAN}{line}{Colors.END}")
                        
                        elif line.startswith("TX:"):
                            print(f"{Colors.CYAN}✓ {line}{Colors.END}")
                        
                        else:
                            # Unknown message
                            if len(line) > 2:
                                print(f"[DEBUG] {line}")
                
                except Exception as e:
                    pass
            
            time.sleep(0.001)
    
    except KeyboardInterrupt:
        total = message_count + corrupted_count
        success_rate = (message_count / total * 100) if total > 0 else 0
        
        print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
        print(f"{Colors.BOLD}Test Summary{Colors.END}")
        print(f"{Colors.BOLD}{'='*70}{Colors.END}")
        print(f"Clean messages:   {Colors.GREEN}{message_count}{Colors.END}")
        print(f"Corrupted:        {Colors.YELLOW}{corrupted_count}{Colors.END}")
        print(f"Success rate:     {Colors.GREEN if success_rate > 95 else Colors.YELLOW}{success_rate:.1f}%{Colors.END}")
        print(f"Duration:         {int(time.time() - start_time)} seconds")
    
    except Exception as e:
        print(f"\n{Colors.RED}✗ Error: {e}{Colors.END}")
    
    finally:
        pi.bb_serial_read_close(RX_PIN)
        pi.stop()
        print(f"\n{Colors.CYAN}Serial closed{Colors.END}")

if __name__ == "__main__":
    main()
