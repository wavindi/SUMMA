#!/usr/bin/env python3
"""
Dual Pico VL53L5CX Monitor for SUMMA Padel Scoring
Raspberry Pi 3B - Receives data from 2 Picos over UART
"""

import serial
import time
import threading
from collections import deque

# ============================================================================
# CONFIGURATION
# ============================================================================
# Serial port configuration for two Picos
PICO_CONFIGS = {
    "PICO_1": {
        "port": "/dev/ttyAMA0",  # GPIO 14/15 (primary UART)
        "baudrate": 57600,
        "timeout": 1
    },
    "PICO_2": {
        "port": "/dev/ttyAMA1",  # Secondary UART (or /dev/ttyUSB0 if using USB adapter)
        "baudrate": 57600,
        "timeout": 1
    }
}

# Data storage
pico_data = {
    "PICO_1": {"connected": False, "last_frame": None, "frame_count": 0, "error_count": 0},
    "PICO_2": {"connected": False, "last_frame": None, "frame_count": 0, "error_count": 0}
}

# Thread locks
data_lock = threading.Lock()
running = True

# ============================================================================
# CONNECTION CHECK
# ============================================================================
def test_connection(pico_name, config):
    """Test if Pico is connected and responding"""
    try:
        ser = serial.Serial(
            port=config["port"],
            baudrate=config["baudrate"],
            timeout=config["timeout"]
        )

        # Clear any stale data
        ser.reset_input_buffer()

        # Wait briefly for data
        time.sleep(0.5)

        # Check if there's any data available
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            ser.close()
            return True

        ser.close()
        return False

    except serial.SerialException as e:
        return False
    except Exception as e:
        return False

def initial_connection_test():
    """Test both Picos and report status"""
    print("\n╔════════════════════════════════════════════╗")
    print("║  SUMMA Dual Pico Connection Test          ║")
    print("╚════════════════════════════════════════════╝\n")

    connected_picos = []

    for pico_name, config in PICO_CONFIGS.items():
        print(f"Testing {pico_name} on {config['port']}...", end=" ")

        if test_connection(pico_name, config):
            print("✓ CONNECTED")
            connected_picos.append(pico_name)
            pico_data[pico_name]["connected"] = True
        else:
            print("✗ NOT CONNECTED")
            pico_data[pico_name]["connected"] = False

    print()

    # Report summary
    if len(connected_picos) == 2:
        print("✓ Both Picos connected successfully!")
        return True
    elif len(connected_picos) == 1:
        print(f"⚠ Only {connected_picos[0]} is connected")
        print("  Continuing with partial data...")
        return True
    else:
        print("✗ No Picos connected. Exiting...")
        return False

# ============================================================================
# DATA READING THREAD
# ============================================================================
def read_pico_data(pico_name, config):
    """Thread function to continuously read data from one Pico"""
    global running

    ser = None
    reconnect_attempts = 0
    max_reconnect = 5

    while running:
        try:
            # Open serial connection
            if ser is None:
                ser = serial.Serial(
                    port=config["port"],
                    baudrate=config["baudrate"],
                    timeout=config["timeout"]
                )
                ser.reset_input_buffer()

                with data_lock:
                    pico_data[pico_name]["connected"] = True

                print(f"[{pico_name}] Connected to {config['port']}")
                reconnect_attempts = 0

            # Read line from serial
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()

                # Check for protocol markers
                if line == "DATA_START":
                    # Read 16 zones of data
                    zones = []
                    for i in range(16):
                        data_line = ser.readline().decode('utf-8', errors='ignore').strip()
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

                    # Wait for DATA_END
                    end_marker = ser.readline().decode('utf-8', errors='ignore').strip()

                    if end_marker == "DATA_END" and len(zones) == 16:
                        # Store data
                        with data_lock:
                            pico_data[pico_name]["last_frame"] = zones
                            pico_data[pico_name]["frame_count"] += 1
                            pico_data[pico_name]["connected"] = True

            time.sleep(0.005)  # 5ms polling

        except serial.SerialException as e:
            # Connection lost
            with data_lock:
                pico_data[pico_name]["connected"] = False

            if ser:
                ser.close()
                ser = None

            reconnect_attempts += 1

            if reconnect_attempts <= max_reconnect:
                print(f"[{pico_name}] Connection lost. Reconnecting... ({reconnect_attempts}/{max_reconnect})")
                time.sleep(2)
            else:
                print(f"[{pico_name}] Max reconnection attempts reached. Stopping thread.")
                break

        except Exception as e:
            with data_lock:
                pico_data[pico_name]["error_count"] += 1
            time.sleep(0.1)

    # Clean up
    if ser:
        ser.close()

    print(f"[{pico_name}] Thread stopped")

# ============================================================================
# DISPLAY THREAD
# ============================================================================
def display_data():
    """Display live data from both Picos"""
    global running

    while running:
        time.sleep(1)  # Update display every second

        # Clear screen (works on Linux terminal)
        print("\033[2J\033[H", end="")

        print("╔════════════════════════════════════════════════════════════╗")
        print("║       SUMMA Dual Pico VL53L5CX Live Monitor               ║")
        print("╚════════════════════════════════════════════════════════════╝\n")

        with data_lock:
            both_disconnected = True

            for pico_name in ["PICO_1", "PICO_2"]:
                status = "🟢 CONNECTED" if pico_data[pico_name]["connected"] else "🔴 DISCONNECTED"
                print(f"{pico_name}: {status}")
                print(f"  Port: {PICO_CONFIGS[pico_name]['port']}")
                print(f"  Frames: {pico_data[pico_name]['frame_count']} | Errors: {pico_data[pico_name]['error_count']}")

                if pico_data[pico_name]["connected"]:
                    both_disconnected = False

                    if pico_data[pico_name]["last_frame"]:
                        # Display 4x4 grid (simplified view - zone 0 to 3 only)
                        print(f"  Latest distances (first 4 zones):")
                        for i in range(min(4, len(pico_data[pico_name]["last_frame"]))):
                            zone = pico_data[pico_name]["last_frame"][i]
                            print(f"    Zone {zone['zone']}: {zone['distance_mm']} mm (status: {zone['status']})")
                    else:
                        print("  Waiting for data...")

                print()

            # Check if both disconnected
            if both_disconnected:
                print("⚠️  BOTH PICOS DISCONNECTED - STOPPING MONITOR")
                running = False

# ============================================================================
# MAIN
# ============================================================================
def main():
    global running

    # Initial connection test
    if not initial_connection_test():
        return

    print("\nStarting continuous monitoring...")
    print("Press Ctrl+C to stop\n")

    # Start reader threads
    threads = []

    for pico_name, config in PICO_CONFIGS.items():
        if pico_data[pico_name]["connected"]:
            thread = threading.Thread(
                target=read_pico_data,
                args=(pico_name, config),
                daemon=True
            )
            thread.start()
            threads.append(thread)

    # Start display thread
    display_thread = threading.Thread(target=display_data, daemon=True)
    display_thread.start()

    try:
        # Keep main thread alive
        while running:
            time.sleep(0.5)

            # Check if both disconnected
            with data_lock:
                both_disconnected = not pico_data["PICO_1"]["connected"] and not pico_data["PICO_2"]["connected"]

            if both_disconnected:
                print("\n⚠️  Both Picos disconnected. Exiting...")
                running = False
                break

    except KeyboardInterrupt:
        print("\n\nStopping monitor...")
        running = False

    # Wait for threads to finish
    time.sleep(1)

    print("\nFinal Statistics:")
    for pico_name in ["PICO_1", "PICO_2"]:
        print(f"{pico_name}: {pico_data[pico_name]['frame_count']} frames received, {pico_data[pico_name]['error_count']} errors")

if __name__ == "__main__":
    main()
