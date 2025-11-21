#!/usr/bin/env python3
"""
Read weight from YZC-131 load cell via HX711 on Raspberry Pi.
Requires: pip install hx711
"""

import time
import sys
from hx711 import HX711  # HX711 Python library

# GPIO pins (BCM numbering)
DT_PIN = 5   # Data pin from HX711
SCK_PIN = 6  # Clock pin from HX711

# Calibration factor (to be determined experimentally)
CALIBRATION_FACTOR = -7050  # Example value; adjust after calibration

def clean_and_exit():
    """Gracefully exit the program."""
    print("Cleaning up GPIO and exiting...")
    try:
        hx.power_down()
        hx.cleanup()
    except Exception:
        pass
    sys.exit()

try:
    # Initialize HX711
    hx = HX711(dout_pin=DT_PIN, pd_sck_pin=SCK_PIN)
    hx.set_reading_format("MSB", "MSB")  # Byte order
    hx.set_reference_unit(CALIBRATION_FACTOR)  # Calibration factor
    hx.reset()
    hx.tare()  # Reset the scale to zero

    print("Tare done. Place weight on the scale.")

    while True:
        try:
            # Read average of 5 samples
            weight = hx.get_weight(5)
            print(f"Weight: {weight:.2f} g")
            hx.power_down()
            hx.power_up()
            time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit):
            clean_and_exit()
        except Exception as e:
            print(f"Error reading weight: {e}")
            time.sleep(1)

except RuntimeError as e:
    print(f"Runtime error: {e}")
    clean_and_exit()
except KeyboardInterrupt:
    clean_and_exit()
