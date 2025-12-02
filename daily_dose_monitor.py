#!/usr/bin/env python3
"""
Daily Dose - Combined pill dispenser logic for Raspberry Pi 4
- Terminal-based menu (no LCD)
- 3 buttons (BCM: 5, 6, 13)
- Fingerprint sensor on /dev/ttyS0
- LEDs on 27 (Funnel 1 empty) and 22 (Funnel 2 empty)
- HX711 load cell on 23 (DT) and 24 (SCK)
- Two SG5010 servos on 18 and 19
- Pill inventory tracked in software (user input + load cell)
"""

import time
import datetime
import serial
import RPi.GPIO as GPIO

import adafruit_fingerprint
from hx711 import HX711

# =========================
#  HARDWARE SETUP
# =========================

GPIO.setmode(GPIO.BCM)

# Buttons
BTN_SET  = 5   # Button 1: Set schedule / refill (double press)
BTN_FP   = 6   # Button 2: Fingerprint menu
BTN_TIME = 13  # Button 3: Time remaining / return to menu (double press)

for pin in (BTN_SET, BTN_FP, BTN_TIME):
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# LEDs (used as "empty" indicators)
LED_OK  = 27   # Funnel 1 empty indicator
LED_ERR = 22   # Funnel 2 empty indicator
GPIO.setup(LED_OK, GPIO.OUT)
GPIO.setup(LED_ERR, GPIO.OUT)
GPIO.output(LED_OK, GPIO.LOW)   # LOW = not empty
GPIO.output(LED_ERR, GPIO.LOW)

# Servos
SERVO1_PIN = 18   # Funnel 1
SERVO2_PIN = 19   # Funnel 2
GPIO.setup(SERVO1_PIN, GPIO.OUT)
GPIO.setup(SERVO2_PIN, GPIO.OUT)

servo1 = GPIO.PWM(SERVO1_PIN, 50)  # 50 Hz PWM
servo2 = GPIO.PWM(SERVO2_PIN, 50)
servo1.start(0)
servo2.start(0)

# Load cell / HX711
DT_PIN  = 23   # HX711 DT
SCK_PIN = 24   # HX711 SCK
CALIBRATION_FACTOR = -7050  # TODO: adjust this

hx = HX711(DT_PIN, SCK_PIN)
hx.set_reference_unit(CALIBRATION_FACTOR)
hx.reset()
hx.tare()

# Fingerprint sensor
uart = serial.Serial("/dev/ttyS0", baudrate=57600, timeout=1)
finger = adafruit_fingerprint.Adafruit_Fingerprint(uart)

# =========================
#  SCHEDULER STATE  <<< NEW >>>
# =========================

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Schedule for Funnel 1 and Funnel 2
schedule_funnel_1 = {
    "day": None,     # 0-6
    "hour": None,    # 0-23
    "minute": None   # 0-59
}

schedule_funnel_2 = {
    "day": None,     # 0-6
    "hour": None,    # 0-23
    "minute": None   # 0-59
}

last_target_minute = None
dispense_done_for_target = False

# =========================
#  "LCD" HELPERS -> TERMINAL
# =========================

def lcd_print(line1="", line2=""):
    """Simulated LCD print to terminal."""
    print("\n" + "=" * 40)
    if line1 is not None:
        print(str(line1))
    if line2:
        print(str(line2))
    print("=" * 40)

def lcd_splash():
    """Show 'Daily Dose' splash in terminal."""
    lcd_print("=== DAILY DOSE ===", "   Pill System")
    time.sleep(2)
    lcd_print("Welcome!", "Daily Dose :)")
    time.sleep(2)

def show_main_menu():
    """Show the main menu screen in terminal."""
    lcd_print(
        "> Daily Dose Menu",
        "1:Set Sched  (dbl:Refill)\n2:FP Menu     3:Time (dbl:Menu)"
    )

# =========================
#  BUTTON HELPERS
# =========================

def detect_press_type(pin, timeout=0.4):
    """
    Distinguish between single and double press on a button.
    Returns:
        0 = no press
        1 = single press
        2 = double press
    """
    if GPIO.input(pin) == GPIO.LOW:
        time.sleep(0.15)  # debounce
        start = time.time()
        while time.time() - start < timeout:
            if GPIO.input(pin) == GPIO.LOW:
                time.sleep(0.15)  # debounce
                return 2
            time.sleep(0.01)
        return 1
    return 0

# =========================
#  PILL INVENTORY
# =========================

pills_funnel_1 = 0
pills_funnel_2 = 0

def init_pill_counts():
    """Ask user how many pills are in each funnel initially (via keyboard)."""
    global pills_funnel_1, pills_funnel_2

    while True:
        try:
            val = int(input("Enter initial pill count for Funnel 1: "))
            if val < 0:
                print("Please enter a non-negative number.")
                continue
            pills_funnel_1 = val
            break
        except ValueError:
            print("Invalid input. Please enter an integer.")

    while True:
        try:
            val = int(input("Enter initial pill count for Funnel 2: "))
            if val < 0:
                print("Please enter a non-negative number.")
                continue
            pills_funnel_2 = val
            break
        except ValueError:
            print("Invalid input. Please enter an integer.")

    update_leds_with_inventory()
    print(f"Initial inventory -> Funnel 1: {pills_funnel_1}, Funnel 2: {pills_funnel_2}")

def update_leds_with_inventory():
    """
    LEDs indicate empty funnels now:
    - If pill count <= 0 -> LED ON (HIGH) = empty
    - If pill count > 0  -> LED OFF (LOW)
    """
    if pills_funnel_1 <= 0:
        GPIO.output(LED_OK, GPIO.HIGH)
    else:
        GPIO.output(LED_OK, GPIO.LOW)

    if pills_funnel_2 <= 0:
        GPIO.output(LED_ERR, GPIO.HIGH)
    else:
        GPIO.output(LED_ERR, GPIO.LOW)

# =========================
#  REFILL MENU
# =========================

def refill_menu():
    """
    Refill procedure using Button 1:
    - Single press: increment count (0–99 loop)
    - Double press: confirm value and move on
    Adjusts Funnel 1 then Funnel 2.
    """
    global pills_funnel_1, pills_funnel_2
    max_count = 99

    # ---- Refill Funnel 1 ----
    count = max(0, min(pills_funnel_1, max_count))
    while True:
        lcd_print(
            f"Refill Funnel 1:",
            f"Count: {count:02d}  (B1:+  B1 dbl:OK)"
        )
        press = detect_press_type(BTN_SET)
        if press == 1:
            count = (count + 1) % (max_count + 1)
        elif press == 2:
            pills_funnel_1 = count
            break
        time.sleep(0.05)

    # ---- Refill Funnel 2 ----
    count = max(0, min(pills_funnel_2, max_count))
    while True:
        lcd_print(
            f"Refill Funnel 2:",
            f"Count: {count:02d}  (B1:+  B1 dbl:OK)"
        )
        press = detect_press_type(BTN_SET)
        if press == 1:
            count = (count + 1) % (max_count + 1)
        elif press == 2:
            pills_funnel_2 = count
            break
        time.sleep(0.05)

    update_leds_with_inventory()
    lcd_print("Refill Complete",
              f"F1:{pills_funnel_1}  F2:{pills_funnel_2}")
    time.sleep(2)
    show_main_menu()

# =========================
#  SCHEDULER SETUP
# =========================

def set_schedule_menu():
    """
    Simple schedule setting with Button 1 only:
    - Single press increments value
    - Double press confirms and moves to next field
    Fields: Funnel1 Day -> Hour -> Minute, then Funnel2 Day -> Hour -> Minute
    """
    # ---- Funnel 1 Day ----
    day = 0
    while True:
        lcd_print("Set Funnel 1 Day:", DAYS[day])
        press = detect_press_type(BTN_SET)
        if press == 1:
            day = (day + 1) % 7
        elif press == 2:
            break
        time.sleep(0.05)

    # ---- Funnel 1 Hour ----
    hour = 0
    while True:
        lcd_print("Set Funnel 1 Hour:", f"{hour:02d}")
        press = detect_press_type(BTN_SET)
        if press == 1:
            hour = (hour + 1) % 24
        elif press == 2:
            break
        time.sleep(0.05)

    # ---- Funnel 1 Minute ----
    minute = 0
    while True:
        lcd_print("Set Funnel 1 Minute:", f"{minute:02d}")
        press = detect_press_type(BTN_SET)
        if press == 1:
            minute = (minute + 1) % 60
        elif press == 2:
            break
        time.sleep(0.05)

    global schedule_funnel_1, schedule_funnel_2, last_target_minute, dispense_done_for_target
    schedule_funnel_1["day"] = day
    schedule_funnel_1["hour"] = hour
    schedule_funnel_1["minute"] = minute

    target_min = day * 24 * 60 + hour * 60 + minute
    last_target_minute = target_min
    dispense_done_for_target = False

    lcd_print("Funnel 1 Schedule Set!",
              f"{DAYS[day]} {hour:02d}:{minute:02d}")
    time.sleep(2)

    # ---- Funnel 2 Day ----
    day = 0
    while True:
        lcd_print("Set Funnel 2 Day:", DAYS[day])
        press = detect_press_type(BTN_SET)
        if press == 1:
            day = (day + 1) % 7
        elif press == 2:
            break
        time.sleep(0.05)

    # ---- Funnel 2 Hour ----
    hour = 0
    while True:
        lcd_print("Set Funnel 2 Hour:", f"{hour:02d}")
        press = detect_press_type(BTN_SET)
        if press == 1:
            hour = (hour + 1) % 24
        elif press == 2:
            break
        time.sleep(0.05)

    # ---- Funnel 2 Minute ----
    minute = 0
    while True:
        lcd_print("Set Funnel 2 Minute:", f"{minute:02d}")
        press = detect_press_type(BTN_SET)
        if press == 1:
            minute = (minute + 1) % 60
        elif press == 2:
            break
        time.sleep(0.05)

    schedule_funnel_2["day"] = day
    schedule_funnel_2["hour"] = hour
    schedule_funnel_2["minute"] = minute

    lcd_print("Funnel 2 Schedule Set!",
              f"{DAYS[day]} {hour:02d}:{minute:02d}")
    time.sleep(2)
    show_main_menu()

# =========================
#  TIME REMAINING HELPERS  <<< NEW >>>
# =========================

def _get_time_remaining_for_schedule(schedule):
    """
    Compute time remaining for a given schedule dict.
    Returns (days, hours, minutes, target_minute) or None if not set.
    """
    if schedule["day"] is None:
        return None

    now = datetime.datetime.now()
    current_min = now.weekday() * 24 * 60 + now.hour * 60 + now.minute
    target_min = (schedule["day"] * 24 * 60 +
                  schedule["hour"] * 60 +
                  schedule["minute"])

    # Move to next week if already passed
    if target_min < current_min:
        target_min += 7 * 24 * 60

    delta = target_min - current_min
    d = delta // (24 * 60)
    h = (delta % (24 * 60)) // 60
    m = delta % 60
    return d, h, m, target_min


def get_time_remaining():
    """
    Kept for background scheduling logic (Funnel 1 only).
    Returns time remaining for Funnel 1 schedule.
    """
    return _get_time_remaining_for_schedule(schedule_funnel_1)


def show_time_remaining():
    """
    Show time remaining for BOTH Funnel 1 and Funnel 2 on the terminal.
    Triggered by Button 3 single press.
    """
    tr1 = _get_time_remaining_for_schedule(schedule_funnel_1)
    tr2 = _get_time_remaining_for_schedule(schedule_funnel_2)

    if tr1 is None and tr2 is None:
        lcd_print("No schedules set", "Use Btn1 to set")
        time.sleep(2)
        show_main_menu()
        return

    # Build line for Funnel 1
    if tr1 is None:
        line1 = "F1: -- (no sched)"
    else:
        d1, h1, m1, _ = tr1
        if d1 > 0:
            line1 = f"F1: {d1}d {h1}h {m1}m"
        else:
            line1 = f"F1: {h1:02d}h {m1:02d}m"

    # Build line for Funnel 2
    if tr2 is None:
        line2 = "F2: -- (no sched)"
    else:
        d2, h2, m2, _ = tr2
        if d2 > 0:
            line2 = f"F2: {d2}d {h2}h {m2}m"
        else:
            line2 = f"F2: {h2:02d}h {m2:02d}m"

    lcd_print(line1, line2)
    time.sleep(2)
    show_main_menu()

# =========================
#  MAIN DISPENSE SEQUENCE
# =========================
# Assumes:
#   - verify_fingerprint_for_dose()
#   - pill_detected_by_scale()
#   - dispense_pill_motor(servo)
#   - fingerprint_setup_menu()
# are defined elsewhere.

def run_dispense_sequence():
    """
    Full sequence:
    - Ask for fingerprint
    - Run Motor1, check load cell -> decrement Funnel 1 count
    - Run Motor2, check load cell -> decrement Funnel 2 count
    LEDs indicate empty funnels based on inventory.
    """
    global pills_funnel_1, pills_funnel_2

    if not verify_fingerprint_for_dose():
        GPIO.output(LED_ERR, GPIO.HIGH)
        time.sleep(2)
        GPIO.output(LED_ERR, GPIO.LOW)
        show_main_menu()
        return

    # Motor 1 -> Funnel 1
    lcd_print("Motor 1 ON", "Dropping Pill 1...")
    dispense_pill_motor(servo1)
    lcd_print("Checking Pill 1", "")
    if pill_detected_by_scale():
        if pills_funnel_1 > 0:
            pills_funnel_1 -= 1
        lcd_print("Pill 1 OK",
                  f"Funnel 1 left: {pills_funnel_1}")
        time.sleep(1)
    else:
        lcd_print("Pill 1 FAIL", "Check Funnel 1")
        time.sleep(2)

    update_leds_with_inventory()

    # Motor 2 -> Funnel 2
    lcd_print("Motor 2 ON", "Dropping Pill 2...")
    dispense_pill_motor(servo2)
    lcd_print("Checking Pill 2", "")
    if pill_detected_by_scale():
        if pills_funnel_2 > 0:
            pills_funnel_2 -= 1
        lcd_print("Pill 2 OK",
                  f"Funnel 2 left: {pills_funnel_2}")
        time.sleep(1)
    else:
        lcd_print("Pill 2 FAIL", "Check Funnel 2")
        time.sleep(2)

    update_leds_with_inventory()

    lcd_print("Dispense Done!", "")
    time.sleep(2)
    show_main_menu()

# =========================
#  MAIN LOOP / MENU
# =========================

def main():
    global last_target_minute, dispense_done_for_target

    init_pill_counts()
    lcd_splash()
    show_main_menu()

    try:
        while True:
            # LEDs reflect inventory state
            update_leds_with_inventory()

            # Read button actions
            press_set  = detect_press_type(BTN_SET)
            press_fp   = detect_press_type(BTN_FP)
            press_time = detect_press_type(BTN_TIME)

            # Button 1: single press -> set schedules
            if press_set == 1:
                set_schedule_menu()

            # Button 1: double press -> refill menu
            if press_set == 2:
                refill_menu()

            # Button 2: single press -> fingerprint setup menu
            if press_fp == 1:
                fingerprint_setup_menu()

            # Button 3: single press -> show time remaining (now shows F1 + F2)
            if press_time == 1:
                show_time_remaining()

            # Button 3: double press -> go to main menu
            if press_time == 2:
                lcd_print("Returning to", "Main Menu")
                time.sleep(1)
                show_main_menu()

            # Background scheduling logic (for Funnel 1 schedule)
            tr = get_time_remaining()
            if tr is not None:
                d, h, m, target_minute = tr

                if last_target_minute != target_minute:
                    last_target_minute = target_minute
                    dispense_done_for_target = False

                # 1 minute before dose
                if d == 0 and h == 0 and m == 1 and not dispense_done_for_target:
                    lcd_print("Arming scale...", "Dose in 1 minute")
                    time.sleep(2)
                    show_main_menu()

                # At dose time
                if d == 0 and h == 0 and m == 0 and not dispense_done_for_target:
                    run_dispense_sequence()
                    dispense_done_for_target = True

            time.sleep(0.05)  # Loop delay

    except KeyboardInterrupt:
        pass
    finally:
        servo1.stop()
        servo2.stop()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
