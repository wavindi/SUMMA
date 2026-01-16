#!/usr/bin/env python3
"""Test 4 relays on GPIO 12, 16, 20, 21"""

import RPi.GPIO as GPIO
import time

# Pins
BLACK_ADD = 12
BLACK_SUB = 16
YELLOW_ADD = 20
YELLOW_SUB = 21

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

RELAY_OFF = GPIO.HIGH  # Active-low relays
RELAY_ON = GPIO.LOW

GPIO.setup(BLACK_ADD, GPIO.OUT, initial=RELAY_OFF)
GPIO.setup(BLACK_SUB, GPIO.OUT, initial=RELAY_OFF)
GPIO.setup(YELLOW_ADD, GPIO.OUT, initial=RELAY_OFF)
GPIO.setup(YELLOW_SUB, GPIO.OUT, initial=RELAY_OFF)

print("Testing 4 relays (listen for clicks)...\n")

try:
    relays = [
        (BLACK_ADD, "Black Add (GPIO 12)"),
        (BLACK_SUB, "Black Subtract (GPIO 16)"),
        (YELLOW_ADD, "Yellow Add (GPIO 20)"),
        (YELLOW_SUB, "Yellow Subtract (GPIO 21)")
    ]
    
    for pin, name in relays:
        print(f"Testing {name}...")
        GPIO.output(pin, RELAY_ON)
        time.sleep(1)
        GPIO.output(pin, RELAY_OFF)
        time.sleep(0.5)
    
    print("\n✅ All relays tested successfully!")
    
except KeyboardInterrupt:
    print("\nStopped")
finally:
    GPIO.output(BLACK_ADD, RELAY_OFF)
    GPIO.output(BLACK_SUB, RELAY_OFF)
    GPIO.output(YELLOW_ADD, RELAY_OFF)
    GPIO.output(YELLOW_SUB, RELAY_OFF)
    GPIO.cleanup()
    print("Cleanup done")
