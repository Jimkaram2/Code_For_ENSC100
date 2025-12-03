#!/usr/bin/env python3
"""
Daily Dose - Combined pill dispenser logic for Raspberry Pi 4
- Terminal-based menu (no LCD hardware, just prints)
- 3 buttons (BCM: 5, 6, 13)
- Fingerprint sensor on /dev/ttyS0
- HX711 load cell on 23 (DT) and 24 (SCK)
- Two SG5010 servos driven by PCA9685 (channels 0 and 1)
- Pill inventory tracked in software (user input + load cell)
- State (schedules + pill counts) persisted in daily_dose_state.json
"""

import time
import datetime
import serial
import json
import os

import RPi.GPIO as GPIO
import board
import busio
from adafruit_pca9685 import PCA9685
import adafruit_fingerprint
from hx711 import HX711

# =========================
#  FILE PERSISTENCE
# =========================

STATE_FILE = "daily_dose_state.json"

# =========================
#  HARDWARE SETUP
# =========================

GPIO.setmode(GPIO.BCM)

# Buttons
BTN_SET  = 5   # Button 1: Set schedule / refill
BTN_FP   = 6   # Button 2: Fingerprint / confirm
BTN_TIME = 13  # Button 3: Time remaining / return to menu (double press)

for pin in (BTN_SET, BTN_FP, BTN_TIME):
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# ===== PCA9685 SERVO DRIVER =====
i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 50  # 50 Hz for standard servos

MIN_US = 500
MAX_US = 2500
PERIOD_US = 1000000 / 50.0  # 20000 µs period

# === PER-SERVO CENTERS (physical degrees) ===
PHYSICAL_CENTER_SERVO1 = 30
PHYSICAL_CENTER_SERVO2 = 10

# === PER-SERVO TARGET OFFSETS (relative to each center) ===
TARGET_OFFSET_SERVO1 = -30   # from 30° -> 0°
TARGET_OFFSET_SERVO2 = 31    # from 10° -> 41°

def angle_to_duty(angle_deg):
    """Convert angle in degrees to 16-bit duty cycle for PCA9685."""
    angle = max(0, min(180, angle_deg))  # clamp to servo range
    pulse_us = MIN_US + (MAX_US - MIN_US) * (angle / 180.0)
    duty = int((pulse_us / PERIOD_US) * 65535)
    return duty

def set_servo_physical(channel, physical_angle):
    """Set servo on PCA9685 channel to a physical angle."""
    pca.channels[channel].duty_cycle = angle_to_duty(physical_angle)

def set_servo1_logical(offset):
    """offset in degrees relative to servo 1's center."""
    physical = PHYSICAL_CENTER_SERVO1 + offset
    set_servo_physical(0, physical)

def set_servo2_logical(offset):
    """offset in degrees relative to servo 2's center."""
    physical = PHYSICAL_CENTER_SERVO2 + offset
    set_servo_physical(1, physical)

def dispense_servo1_once():
    """
    Move servo 1: center -> target offset -> back to center.
    Uses the same stepping logic as your test script.
    """
    set_servo1_logical(0)
    time.sleep(0.3)

    max_step   = abs(TARGET_OFFSET_SERVO1)
    STEP_SIZE  = max_step   # one big jump
    STEP_DELAY = 0.055

    # Center -> Target offset
    for step in range(0, max_step + STEP_SIZE, STEP_SIZE):
        if TARGET_OFFSET_SERVO1 >= 0:
            off1 = min(step, TARGET_OFFSET_SERVO1)
        else:
            off1 = max(-step, TARGET_OFFSET_SERVO1)
        set_servo1_logical(off1)
        time.sleep(STEP_DELAY)

    # Target -> Center
    for step in range(max_step, -STEP_SIZE, -STEP_SIZE):
        if TARGET_OFFSET_SERVO1 >= 0:
            off1 = max(step, 0)
        else:
            off1 = min(-step, 0)
        set_servo1_logical(off1)
        time.sleep(STEP_DELAY)

    set_servo1_logical(0)
    time.sleep(0.2)

def dispense_servo2_once():
    """
    Move servo 2: center -> target offset -> back to center.
    Uses the same stepping logic as your test script.
    """
    set_servo2_logical(0)
    time.sleep(0.3)

    max_step   = abs(TARGET_OFFSET_SERVO2)
    STEP_SIZE  = max_step   # one big jump
    STEP_DELAY = 0.055

    # Center -> Target offset
    for step in range(0, max_step + STEP_SIZE, STEP_SIZE):
        if TARGET_OFFSET_SERVO2 >= 0:
            off2 = min(step, TARGET_OFFSET_SERVO2)
        else:
            off2 = max(-step, TARGET_OFFSET_SERVO2)
        set_servo2_logical(off2)
        time.sleep(STEP_DELAY)

    # Target -> Center
    for step in range(max_step, -STEP_SIZE, -STEP_SIZE):
        if TARGET_OFFSET_SERVO2 >= 0:
            off2 = max(step, 0)
        else:
            off2 = min(-step, 0)
        set_servo2_logical(off2)
        time.sleep(STEP_DELAY)

    set_servo2_logical(0)
    time.sleep(0.2)

# ===== HX711 LOAD CELL =====
DT_PIN  = 23   # HX711 DT
SCK_PIN = 24   # HX711 SCK

# Use your calibrated factor
CALIBRATION_FACTOR = 45.06  # <-- adjust if needed

hx = HX711(DT_PIN, SCK_PIN)
hx.set_reference_unit(CALIBRATION_FACTOR)
hx.reset()
hx.tare()

# Fingerprint sensor
uart = serial.Serial("/dev/ttyS0", baudrate=57600, timeout=1)
finger = adafruit_fingerprint.Adafruit_Fingerprint(uart)

# =========================
#  PER-FUNNEL PILL WEIGHT SETTINGS
# =========================
# Tune these for your two pills (in grams).
# Example: F1 pill ~0.75g, F2 pill ~1.2g
PILL_THRESHOLD_F1   = 0.4   # minimum |weight| to call "one pill" in Funnel 1
PILL_THRESHOLD_F2   = 0.4   # minimum |weight| to call "one pill" in Funnel 2

OVERDOSE_FACTOR_F1  = 1.8   # ≥ threshold * factor => potential overdose (F1)
OVERDOSE_FACTOR_F2  = 1.8   # ≥ threshold * factor => potential overdose (F2)

MAX_ATTEMPTS_PER_DOSE = 10  # safety: how many retries per dose

# =========================
#  SCHEDULER STATE
# =========================

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Schedule for Funnel 1 and Funnel 2
schedule_funnel_1 = {"day": None, "hour": None, "minute": None}
schedule_funnel_2 = {"day": None, "hour": None, "minute": None}

# per-funnel tracking
last_target_minute_f1 = None
last_target_minute_f2 = None
dispense_done_for_target_f1 = False
dispense_done_for_target_f2 = False

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
#  PILL INVENTORY + STATE PERSISTENCE
# =========================

pills_funnel_1 = 0
pills_funnel_2 = 0

def save_state():
    """Save pill counts and schedules to JSON file."""
    state = {
        "pills_funnel_1": pills_funnel_1,
        "pills_funnel_2": pills_funnel_2,
        "schedule_funnel_1": schedule_funnel_1,
        "schedule_funnel_2": schedule_funnel_2,
    }
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Error saving state: {e}")

def load_state():
    """Load pill counts and schedules from JSON file, if present."""
    global pills_funnel_1, pills_funnel_2
    global schedule_funnel_1, schedule_funnel_2
    if not os.path.exists(STATE_FILE):
        return False
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        pills_funnel_1 = state.get("pills_funnel_1", 0)
        pills_funnel_2 = state.get("pills_funnel_2", 0)
        sf1 = state.get("schedule_funnel_1", {})
        sf2 = state.get("schedule_funnel_2", {})
        schedule_funnel_1["day"]    = sf1.get("day", None)
        schedule_funnel_1["hour"]   = sf1.get("hour", None)
        schedule_funnel_1["minute"] = sf1.get("minute", None)
        schedule_funnel_2["day"]    = sf2.get("day", None)
        schedule_funnel_2["hour"]   = sf2.get("hour", None)
        schedule_funnel_2["minute"] = sf2.get("minute", None)
        return True
    except Exception as e:
        print(f"Error loading state: {e}")
        return False

def count_with_buttons(prompt_funnel, initial_value=0, max_count=99):
    """
    Generic counter using:
    - Button 1 single press: increment count (wraps 0..max_count) by 5
    - Button 2 single press: confirm and return the value
    """
    count = max(0, min(initial_value, max_count))
    while True:
        lcd_print(
            f"{prompt_funnel}",
            f"Count: {count:02d}  (B1:+5  B2:OK)"
        )

        press_set = detect_press_type(BTN_SET)   # Button 1
        press_fp  = detect_press_type(BTN_FP)    # Button 2

        if press_set == 1:   # increment by 5
            count = (count + 5) % (max_count + 1)
        elif press_fp == 1:  # confirm
            return count

        time.sleep(0.05)

def init_pill_counts():
    """
    Ask user how many pills are in each funnel using buttons:
    - B1: increment by 5
    - B2: confirm
    """
    global pills_funnel_1, pills_funnel_2

    pills_funnel_1 = count_with_buttons("Init Funnel 1 Pills:", pills_funnel_1)
    pills_funnel_2 = count_with_buttons("Init Funnel 2 Pills:", pills_funnel_2)

    lcd_print("Initial inventory:",
              f"F1:{pills_funnel_1}  F2:{pills_funnel_2}")
    time.sleep(2)
    save_state()

def update_leds_with_inventory():
    """No-op now (LEDs removed)."""
    return

# =========================
#  REFILL MENU
# =========================

def refill_menu():
    """
    Refill procedure using buttons:
    - Button 1 single press: increment count (0–99 loop) by 5
    - Button 2 single press: confirm value and move on
    Adjusts Funnel 1 then Funnel 2.
    """
    global pills_funnel_1, pills_funnel_2

    pills_funnel_1 = count_with_buttons("Refill Funnel 1:", pills_funnel_1)
    pills_funnel_2 = count_with_buttons("Refill Funnel 2:", pills_funnel_2)

    save_state()

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
    global schedule_funnel_1, schedule_funnel_2
    global last_target_minute_f1, last_target_minute_f2
    global dispense_done_for_target_f1, dispense_done_for_target_f2

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

    schedule_funnel_1["day"] = day
    schedule_funnel_1["hour"] = hour
    schedule_funnel_1["minute"] = minute

    target_min_f1 = day * 24 * 60 + hour * 60 + minute
    last_target_minute_f1 = target_min_f1
    dispense_done_for_target_f1 = False

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

    target_min_f2 = day * 24 * 60 + hour * 60 + minute
    last_target_minute_f2 = target_min_f2
    dispense_done_for_target_f2 = False

    lcd_print("Funnel 2 Schedule Set!",
              f"{DAYS[day]} {hour:02d}:{minute:02d}")
    time.sleep(2)

    save_state()
    show_main_menu()

# =========================
#  TIME REMAINING HELPERS
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

    # Funnel 1 line
    if tr1 is None:
        line1 = "F1: -- (no sched)"
    else:
        d1, h1, m1, _ = tr1
        if d1 > 0:
            line1 = f"F1: {d1}d {h1}h {m1}m"
        else:
            line1 = f"F1: {h1:02d}h {m1:02d}m"

    # Funnel 2 line
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
#  FINGERPRINT + SCALE HELPERS
# =========================

def get_fingerprint():
    """Low-level fingerprint check (returns True if match)."""
    while finger.get_image() != adafruit_fingerprint.OK:
        time.sleep(0.1)

    if finger.image_2_tz(1) != adafruit_fingerprint.OK:
        return False

    if finger.finger_search() != adafruit_fingerprint.OK:
        return False

    return True

def verify_fingerprint_for_dose(timeout=20):
    """Ask user to scan fingerprint before dispensing."""
    lcd_print("Dose Ready!", "Scan finger")
    start = time.time()

    while time.time() - start < timeout:
        if finger.get_image() == adafruit_fingerprint.OK:
            if get_fingerprint():
                lcd_print("FP OK", "")
                time.sleep(1)
                return True
            else:
                lcd_print("FP FAIL", "Try again")
                time.sleep(2)
                lcd_print("Scan finger", "again")
        time.sleep(0.1)

    lcd_print("FP timeout", "No dispense")
    time.sleep(2)
    show_main_menu()
    return False

def fingerprint_setup_menu():
    """
    Simple fingerprint menu:
    - Single press (Button 2): Enroll fingerprint (slot 1)
    - Double press (Button 2): Exit back to main
    """
    while True:
        lcd_print("FP Menu:", "B2:Enroll  B2dbl:Exit")
        press = detect_press_type(BTN_FP)
        if press == 1:
            enroll_fingerprint(slot=1)
        elif press == 2:
            lcd_print("Leaving FP", "Menu...")
            time.sleep(1)
            show_main_menu()
            break
        time.sleep(0.05)

def enroll_fingerprint(slot=1):
    """Basic enroll routine."""
    lcd_print("Enroll FP", f"ID {slot}")
    time.sleep(1)

    lcd_print("Place finger", "on sensor")
    while finger.get_image() != adafruit_fingerprint.OK:
        time.sleep(0.1)
    if finger.image_2_tz(1) != adafruit_fingerprint.OK:
        lcd_print("FP Error", "Try again")
        time.sleep(2)
        return False

    lcd_print("Remove finger", "")
    time.sleep(2)
    while finger.get_image() != adafruit_fingerprint.NOFINGER:
        time.sleep(0.1)

    lcd_print("Place same", "finger again")
    while finger.get_image() != adafruit_fingerprint.OK:
        time.sleep(0.1)
    if finger.image_2_tz(2) != adafruit_fingerprint.OK:
        lcd_print("FP Error", "Try again")
        time.sleep(2)
        return False

    if finger.create_model() != adafruit_fingerprint.OK:
        lcd_print("Model fail", "")
        time.sleep(2)
        return False

    if finger.store_model(slot) != adafruit_fingerprint.OK:
        lcd_print("Store fail", "")
        time.sleep(2)
        return False

    lcd_print("Enroll OK", f"ID {slot}")
    time.sleep(2)
    show_main_menu()
    return True

def pill_detected_by_scale_raw(num_samples=5):
    """
    Helper to read the scale and return the raw weight in grams (could be negative).
    """
    try:
        weight = hx.get_weight(num_samples)
        hx.power_down()
        hx.power_up()
        return weight
    except Exception as e:
        print(f"Load cell error: {e}")
        return 0.0

# =========================
#  DISPENSE PER FUNNEL (WITH PER-FUNNEL THRESHOLDS)
# =========================

def run_dispense_for_funnel(funnel):
    """
    Dispense sequence for a single funnel (1 or 2) with retry + per-funnel
    pill thresholds + overdose detection:
    - Ask for fingerprint
    - Repeatedly run the servo for that funnel until:
        * load cell detects at least one pill, OR
        * max attempts reached
    - If load cell suggests >1 pill (big weight), show 'Potential overdose'
    """
    global pills_funnel_1, pills_funnel_2

    # --- fingerprint gate ---
    if not verify_fingerprint_for_dose():
        lcd_print("FP failed", "No dispense")
        time.sleep(2)
        show_main_menu()
        return

    # Pick thresholds for the correct funnel
    if funnel == 1:
        SINGLE_PILL_THRESHOLD = PILL_THRESHOLD_F1
        OVERDOSE_FACTOR       = OVERDOSE_FACTOR_F1
    else:
        SINGLE_PILL_THRESHOLD = PILL_THRESHOLD_F2
        OVERDOSE_FACTOR       = OVERDOSE_FACTOR_F2

    attempts      = 0
    pill_detected = False
    overdose      = False

    # Try to zero the scale at start of dispense
    try:
        hx.tare()
    except Exception as e:
        print(f"HX711 tare error: {e}")

    while attempts < MAX_ATTEMPTS_PER_DOSE and not pill_detected:
        attempts += 1

        # ---- spin the right motor once ----
        if funnel == 1:
            lcd_print("Motor 1 ON", f"Attempt {attempts}")
            dispense_servo1_once()
        else:
            lcd_print("Motor 2 ON", f"Attempt {attempts}")
            dispense_servo2_once()

        # small delay for pill to land
        time.sleep(0.5)

        # ---- read load cell ----
        weight = pill_detected_by_scale_raw(5)
        weight_abs = abs(weight)
        print(f"[Funnel {funnel}] Attempt {attempts}, weight = {weight:.2f} g (abs={weight_abs:.2f} g)")

        if weight_abs >= SINGLE_PILL_THRESHOLD:
            # at least one pill detected
            pill_detected = True
            if weight_abs >= SINGLE_PILL_THRESHOLD * OVERDOSE_FACTOR:
                overdose = True
        else:
            # no pill yet -> retry after a short pause
            lcd_print("No pill detected", "Retrying...")
            time.sleep(1.0)

    # ---- after loop: check result ----
    if not pill_detected:
        # all attempts failed
        lcd_print(f"F{funnel}: NO PILL", "Max retries reached")
        time.sleep(2)
        show_main_menu()
        return

    # at least one pill was detected -> decrement count for that funnel
    if funnel == 1:
        if pills_funnel_1 > 0:
            pills_funnel_1 -= 1
        left = pills_funnel_1
    else:
        if pills_funnel_2 > 0:
            pills_funnel_2 -= 1
        left = pills_funnel_2

    save_state()

    if overdose:
        lcd_print("Potential overdose", f"F{funnel}: >1 pill?")
    else:
        lcd_print(f"Pill OK (F{funnel})", f"Pills left: {left}")

    time.sleep(2)
    show_main_menu()

# =========================
#  MAIN LOOP / MENU
# =========================

def main():
    global last_target_minute_f1, last_target_minute_f2
    global dispense_done_for_target_f1, dispense_done_for_target_f2

    # Load previous state if exists; otherwise ask for pill counts
    if load_state():
        lcd_print("Loaded saved state",
                  f"F1:{pills_funnel_1}  F2:{pills_funnel_2}")
        time.sleep(2)
    else:
        init_pill_counts()

    lcd_splash()
    show_main_menu()

    try:
        while True:
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

            # Button 3: single press -> show time remaining (F1 + F2)
            if press_time == 1:
                show_time_remaining()

            # Button 3: double press -> go to main menu
            if press_time == 2:
                lcd_print("Returning to", "Main Menu")
                time.sleep(1)
                show_main_menu()

            # ===== Background scheduling logic for Funnel 1 =====
            tr1 = _get_time_remaining_for_schedule(schedule_funnel_1)
            if tr1 is not None:
                d1, h1, m1, t1 = tr1

                if last_target_minute_f1 != t1:
                    last_target_minute_f1 = t1
                    dispense_done_for_target_f1 = False

                # 1 minute before dose
                if d1 == 0 and h1 == 0 and m1 == 1 and not dispense_done_for_target_f1:
                    lcd_print("Arming scale F1", "Dose in 1 minute")
                    time.sleep(2)
                    show_main_menu()

                # At dose time
                if d1 == 0 and h1 == 0 and m1 == 0 and not dispense_done_for_target_f1:
                    run_dispense_for_funnel(1)
                    dispense_done_for_target_f1 = True

            # ===== Background scheduling logic for Funnel 2 =====
            tr2 = _get_time_remaining_for_schedule(schedule_funnel_2)
            if tr2 is not None:
                d2, h2, m2, t2 = tr2

                if last_target_minute_f2 != t2:
                    last_target_minute_f2 = t2
                    dispense_done_for_target_f2 = False

                # 1 minute before dose
                if d2 == 0 and h2 == 0 and m2 == 1 and not dispense_done_for_target_f2:
                    lcd_print("Arming scale F2", "Dose in 1 minute")
                    time.sleep(2)
                    show_main_menu()

                # At dose time
                if d2 == 0 and h2 == 0 and m2 == 0 and not dispense_done_for_target_f2:
                    run_dispense_for_funnel(2)
                    dispense_done_for_target_f2 = True

            time.sleep(0.05)  # Loop delay

    except KeyboardInterrupt:
        pass
    finally:
        # Release servos and cleanup
        pca.channels[0].duty_cycle = 0
        pca.channels[1].duty_cycle = 0
        pca.deinit()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
