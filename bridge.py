#!/usr/bin/env python3
"""
Pigpio Software UART Bridge for Dual Picos
This script reads from GPIO 23 and GPIO 24 using pigpio
and makes the data available to the backend via named pipes (FIFOs)
"""

import pigpio
import time
import sys
import os
import threading

# ============================================================================
# CONFIGURATION - Match your Pico connections
# ============================================================================
PICO_1_GPIO = 23        # GPIO pin where Pico 1 TX is connected
PICO_2_GPIO = 24        # GPIO pin where Pico 2 TX is connected
BAUD_RATE = 57600

# Virtual serial port paths (named pipes)
PICO_1_PIPE = "/tmp/pico1_serial"
PICO_2_PIPE = "/tmp/pico2_serial"

# ============================================================================
# COLORS FOR OUTPUT
# ============================================================================
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

# ============================================================================
# PICO READER CLASS
# ============================================================================
class PicoReader:
    def __init__(self, name, gpio_pin, pipe_path, pi):
        self.name = name
        self.gpio_pin = gpio_pin
        self.pipe_path = pipe_path
        self.pi = pi
        self.running = True
        self.frame_count = 0
        self.error_count = 0

    def start(self):
        """Start reading from Pico via pigpio"""
        # Open software serial
        self.pi.set_mode(self.gpio_pin, pigpio.INPUT)
        self.pi.bb_serial_read_open(self.gpio_pin, BAUD_RATE, 8)
        print(f"{Colors.GREEN}✓ {self.name} - GPIO{self.gpio_pin} opened{Colors.END}")

        # Create named pipe (FIFO) if it doesn't exist
        if os.path.exists(self.pipe_path):
            os.remove(self.pipe_path)
        os.mkfifo(self.pipe_path)
        print(f"{Colors.GREEN}✓ {self.name} - Created pipe: {self.pipe_path}{Colors.END}")

        # Start reader thread
        thread = threading.Thread(target=self._read_loop, daemon=True)
        thread.start()

    def _read_loop(self):
        """Continuously read from pigpio and write to pipe"""
        line_buffer = ""

        # Open pipe for writing (this will block until backend opens for reading)
        print(f"{Colors.CYAN}⏳ {self.name} - Waiting for backend to connect...{Colors.END}")

        while self.running:
            try:
                # Open pipe in non-blocking mode initially
                pipe_fd = os.open(self.pipe_path, os.O_WRONLY | os.O_NONBLOCK)

                # Switch to blocking mode after opening
                import fcntl
                flags = fcntl.fcntl(pipe_fd, fcntl.F_GETFL)
                fcntl.fcntl(pipe_fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)

                print(f"{Colors.GREEN}✓ {self.name} - Backend connected!{Colors.END}")

                # Read and forward data
                while self.running:
                    (count, data) = self.pi.bb_serial_read(self.gpio_pin)

                    if count > 0:
                        try:
                            # Write raw data to pipe
                            os.write(pipe_fd, data)

                            # Parse for status (optional)
                            text = data.decode('utf-8', errors='ignore')
                            line_buffer += text

                            while '\n' in line_buffer:
                                line, line_buffer = line_buffer.split('\n', 1)

                                if "DATA_START" in line:
                                    self.frame_count += 1
                                    if self.frame_count % 100 == 0:
                                        print(f"{Colors.CYAN}📊 {self.name} - {self.frame_count} frames forwarded{Colors.END}")

                        except Exception as e:
                            self.error_count += 1

                    time.sleep(0.001)  # 1ms delay

                os.close(pipe_fd)

            except OSError as e:
                if e.errno == 6:  # ENXIO - no reader
                    time.sleep(1)
                    continue
                else:
                    print(f"{Colors.RED}✗ {self.name} - Pipe error: {e}{Colors.END}")
                    time.sleep(1)

            except Exception as e:
                print(f"{Colors.RED}✗ {self.name} - Error: {e}{Colors.END}")
                time.sleep(1)

    def stop(self):
        """Stop reading"""
        self.running = False
        self.pi.bb_serial_read_close(self.gpio_pin)
        if os.path.exists(self.pipe_path):
            os.remove(self.pipe_path)

# ============================================================================
# MAIN
# ============================================================================
def main():
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}Pigpio Software UART Bridge - Dual Pico Configuration{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")

    print(f"Configuration:")
    print(f"  PICO_1: GPIO{PICO_1_GPIO} → {PICO_1_PIPE}")
    print(f"  PICO_2: GPIO{PICO_2_GPIO} → {PICO_2_PIPE}")
    print(f"  Baud Rate: {BAUD_RATE}\n")

    # Initialize pigpio
    try:
        pi = pigpio.pi()
        if not pi.connected:
            print(f"{Colors.RED}✗ Failed to connect to pigpiod{Colors.END}")
            print("\nStart pigpiod with: sudo pigpiod")
            sys.exit(1)

        print(f"{Colors.GREEN}✓ pigpiod connected{Colors.END}\n")

    except Exception as e:
        print(f"{Colors.RED}✗ Error connecting to pigpiod: {e}{Colors.END}")
        sys.exit(1)

    # Create readers for both Picos
    pico1_reader = PicoReader("PICO_1", PICO_1_GPIO, PICO_1_PIPE, pi)
    pico2_reader = PicoReader("PICO_2", PICO_2_GPIO, PICO_2_PIPE, pi)

    # Start both readers
    print(f"{Colors.BOLD}Starting readers...{Colors.END}\n")
    pico1_reader.start()
    time.sleep(0.5)
    pico2_reader.start()

    print(f"\n{Colors.GREEN}✓ Bridge is running!{Colors.END}")
    print(f"\n{Colors.BOLD}Update your backend configuration to:{Colors.END}")
    print(f"{Colors.CYAN}  PICO_1 port: {PICO_1_PIPE}{Colors.END}")
    print(f"{Colors.CYAN}  PICO_2 port: {PICO_2_PIPE}{Colors.END}")
    print(f"\nPress Ctrl+C to stop\n")

    # Keep running
    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Stopping...{Colors.END}")
        pico1_reader.stop()
        pico2_reader.stop()
        pi.stop()

        print(f"\n{Colors.BOLD}Statistics:{Colors.END}")
        print(f"  PICO_1: {pico1_reader.frame_count} frames, {pico1_reader.error_count} errors")
        print(f"  PICO_2: {pico2_reader.frame_count} frames, {pico2_reader.error_count} errors")
        print(f"\n{Colors.GREEN}Bridge stopped{Colors.END}")

if __name__ == "__main__":
    main()
