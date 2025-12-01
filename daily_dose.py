#!/usr/bin/env python3
"""
Daily Dose - Combined pill dispenser logic for Raspberry Pi 4
- 16x2 I2C LCD
- 3 buttons (BCM: 5, 6, 13)
- Fingerprint sensor on /dev/ttyS0
- IR sensors on 17 (Funnel 1) and 21 (Funnel 2)
- LEDs on 27 (OK) and 22 (ERR)
- HX711 load cell on 23 (DT) and 24 (SCK)
- Two SG5010 servos on 18 and 19
"""

import time
import datetime
import serial
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD

import adafruit_fingerprint
from hx711 import HX711

# =========================
#  HARDWARE SETUP
# =========================

GPIO.setmode(GPIO.BCM)

# Buttons
BTN_SET  = 5   # Button 1: Set schedule
BTN_FP   = 6   # Button 2: Fingerprint
BTN_TIME = 13  # Button 3: Time remaining

for pin in (BTN_SET, BTN_FP, BTN_TIME):
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# IR sensors (for two funnels)
IR_PIN_F1 = 17  # Funnel 1 IR sensor (old)
IR_PIN_F2 = 21  # Funnel 2 IR sensor (new)
GPIO.setup(IR_PIN_F1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(IR_PIN_F2, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# LEDs
LED_OK  = 27
LED_ERR = 22
GPIO.setup(LED_OK, GPIO.OUT)
GPIO.setup(LED_ERR, GPIO.OUT)
GPIO.output(LED_OK, GPIO.LOW)
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

# LCD 16x2 over I2C (update address 0x27 if needed)
lcd = CharLCD('PCF8574', 0x27, cols=16, rows=2)

# Load cell / HX711
DT_PIN  = 23   # HX711 DT
SCK_PIN = 24   # HX711 SCK
CALIBRATION_FACTOR = -7050  # TODO: adjust this

hx = HX711(DT_PIN, SCK_PIN)   # positional args
hx.set_reference_unit(CALIBRATION_FACTOR)
hx.reset()
hx.tare()

# Fingerprint sensor
uart = serial.Serial("/dev/ttyS0", baudrate=57600, timeout=1)
finger = adafruit_fingerprint.Adafruit_Fingerprint(uart)

# =========================
#  LCD HELPERS
# =========================

def lcd_print(line1="", line2=""):
    """Clear LCD and print up to 16 chars per line."""
    lcd.clear()
    lcd.write_string(str(line1)[:16])
    lcd.cursor_pos = (1, 0)
    lcd.write_string(str(line2)[:16])

def lcd_splash():
    """Show 'Daily Dose' splash."""
    lcd_print("=== DAILY DOSE", " Pill System")
    time.sleep(2)
    lcd_print("Welcome!", "Daily Dose :)")
    time.sleep(2)

def show_main_menu():
    """Show the main menu screen."""
    lcd_print(">Daily Dose", "1:Set 2:FP 3:Tm")

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
        # first press
        time.sleep(0.15)  # debounce
        # Wait to see if there is a second press
        start = time.time()
        while time.time() - start < timeout:
            if GPIO.input(pin) == GPIO.LOW:
                # second press
                time.sleep(0.15)  # debounce
                return 2
            time.sleep(0.01)
        return 1
    return 0

# =========================
#  SCHEDULER LOGIC
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

def set_schedule_menu():
    """
    Simple schedule setting with Button 1 only:
    - Single press increments value
    - Double press confirms and moves to next field
    Fields: Day -> Hour -> Minute
    """
    # ---- Day ----
    day = 0
    while True:
        lcd_print("Set Day:", DAYS[day])
        press = detect_press_type(BTN_SET)
        if press == 1:
            day = (day + 1) % 7
        elif press == 2:
            break
        time.sleep(0.05)

    # ---- Hour ---- (start at 0)
    hour = 0
    while True:
        lcd_print("Set Hour:", f"{hour:02d}")
        press = detect_press_type(BTN_SET)
        if press == 1:
            hour = (hour + 1) % 24
        elif press == 2:
            break
        time.sleep(0.05)

    # ---- Minute ---- (start at 0)
    minute = 0
    while True:
        lcd_print("Set Minute:", f"{minute:02d}")
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

    lcd_print("Schedule Set!", f"{DAYS[day]} {hour:02d}:{minute:02d}")
    time.sleep(2)
    show_main_menu()

def show_schedule():
    """Show the current schedule for Funnel 1 and Funnel 2"""
    funnel_1_schedule = f"F1: {DAYS[schedule_funnel_1['day']]} {schedule_funnel_1['hour']:02d}:{schedule_funnel_1['minute']:02d}"
    funnel_2_schedule = f"F2: {DAYS[schedule_funnel_2['day']]} {schedule_funnel_2['hour']:02d}:{schedule_funnel_2['minute']:02d}"
    
    lcd_print(funnel_1_schedule, funnel_2_schedule)
    time.sleep(2)
    show_main_menu()

def get_time_remaining():
    """
    Return (days, hours, minutes, target_minute) until next scheduled dose.
    If no schedule set, return None.
    """
    if schedule_funnel_1["day"] is None:
        return None

    now = datetime.datetime.now()
    current_min = now.weekday() * 24 * 60 + now.hour * 60 + now.minute
    target_min = schedule_funnel_1["day"] * 24 * 60 + schedule_funnel_1["hour"] * 60 + schedule_funnel_1["minute"]

    # Only move to next week if strictly in the past
    if target_min < current_min:
        target_min += 7 * 24 * 60

    delta = target_min - current_min
    d = delta // (24 * 60)
    h = (delta % (24 * 60)) // 60
    m = delta % 60
    return d, h, m, target_min

def show_time_remaining():
    """Show time remaining on LCD (Button 3 single press)."""
    tr = get_time_remaining()
    if tr is None:
        lcd_print("No Schedule", "Set w/ Btn1")
        time.sleep(2)
        show_main_menu()
        return

    d, h, m, _ = tr
    if d > 0:
        lcd_print("Next:", f"{d}d {h}h {m}m")
    else:
        lcd_print("Next:", f"In {h:02d}h {m:02d}m")
    time.sleep(2)
    show_main_menu()

# =========================
#  FINGERPRINT HELPERS
# =========================

def get_fingerprint():
    """
    Basic fingerprint match routine.
    Returns True if a stored finger template is matched, False otherwise.
    """
    while finger.get_image() != adafruit_fingerprint.OK:
        time.sleep(0.1)

    if finger.image_2_tz(1) != adafruit_fingerprint.OK:
        return False

    if finger.finger_search() != adafruit_fingerprint.OK:
        return False

    return True

def enroll_fingerprint(slot=1):
    """
    Enroll routine using Adafruit library.
    """
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

def fingerprint_setup_menu():
    """
    Simple fingerprint menu:
    - Single press (Button 2): Enroll fingerprint (slot 1)
    - Double press (Button 2): Exit back to main
    """
    while True:
        lcd_print("FP Menu:", "1:Enroll  2:Exit")
        press = detect_press_type(BTN_FP)
        if press == 1:
            enroll_fingerprint(slot=1)
        elif press == 2:
            lcd_print("Leaving FP", "Menu...")
            time.sleep(1)
            show_main_menu()
            break
        time.sleep(0.05)

def verify_fingerprint_for_dose():
    """Ask user to scan finger before dispensing."""
    lcd_print("Dose Ready!", "Scan finger")
    start = time.time()
    timeout = 20  # seconds to wait

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

# =========================
#  IR + LOAD CELL HELPERS
# =========================

def update_leds_with_infrared():
    """
    Use the IR sensor to show pill presence in the funnel:
    - If beam broken (pill there), LEDs OFF
    - If clear (no pill), LEDs ON
    """
    val_f1 = GPIO.input(IR_PIN_F1)
    val_f2 = GPIO.input(IR_PIN_F2)

    # Assuming LOW = beam broken (pill present)
    pill_present_f1 = (val_f1 == GPIO.LOW)
    pill_present_f2 = (val_f2 == GPIO.LOW)

    # Funnel 1
    if pill_present_f1:
        GPIO.output(LED_OK, GPIO.LOW)  # LED OFF
    else:
        GPIO.output(LED_OK, GPIO.HIGH)  # LED ON

    # Funnel 2
    if pill_present_f2:
        GPIO.output(LED_ERR, GPIO.LOW)  # LED OFF
    else:
        GPIO.output(LED_ERR, GPIO.HIGH)  # LED ON

def pill_detected_by_scale(threshold_grams=1.0):
    """
    Uses HX711 to check if at least 'threshold_grams' of weight change.
    """
    try:
        weight = hx.get_weight(5)
        hx.power_down()
        hx.power_up()
        return weight >= threshold_grams
    except Exception as e:
        print(f"Load cell error: {e}")
        return False

# =========================
#  SERVO HELPERS
# =========================

def set_servo_angle(servo, angle):
    """
    Move a standard servo to 'angle' degrees (approx).
    """
    duty = 2 + (angle / 18.0)
    servo.ChangeDutyCycle(duty)
    time.sleep(0.4)
    servo.ChangeDutyCycle(0)

def dispense_pill_motor(servo):
    """
    Simple "open then close" motion to drop 1 pill.
    """
    set_servo_angle(servo, 90)
    time.sleep(0.5)
    set_servo_angle(servo, 0)
    time.sleep(0.5)

# =========================
#  MAIN DISPENSE SEQUENCE
# =========================

def run_dispense_sequence():
    """
    Full sequence:
    - Ask for fingerprint
    - Run Motor1, check load cell
    - Run Motor2, check load cell
    IR only controls LEDs now.
    """
    # Fingerprint gate (handles timeout + menu return on failure)
    if not verify_fingerprint_for_dose():
        GPIO.output(LED_ERR, GPIO.HIGH)
        time.sleep(2)
        GPIO.output(LED_ERR, GPIO.LOW)
        show_main_menu()  # Ensure we return to the main menu if FP fails
        return

    GPIO.output(LED_OK, GPIO.HIGH)

    # Motor 1
    lcd_print("Motor1 ON", "Pill 1 drop")
    dispense_pill_motor(servo1)
    lcd_print("Checking P1", "")
    if pill_detected_by_scale():
        lcd_print("Pill 1 OK", "")
        time.sleep(1)
    else:
        lcd_print("Pill1 FAIL", "Check funnel")
        time.sleep(2)

    # Motor 2
    lcd_print("Motor2 ON", "Pill 2 drop")
    dispense_pill_motor(servo2)
    lcd_print("Checking P2", "")
    if pill_detected_by_scale():
        lcd_print("Pill 2 OK", "")
        time.sleep(1)
    else:
        lcd_print("Pill2 FAIL", "Check funnel")
        time.sleep(2)

    GPIO.output(LED_OK, GPIO.LOW)
    lcd_print("Done!", "")
    time.sleep(2)
    show_main_menu()

# =========================
#  MAIN LOOP / MENU
# =========================

def main():
    global last_target_minute, dispense_done_for_target

    lcd_splash()
    show_main_menu()

    try:
        while True:
            # Update IR + LEDs status all the time
            update_leds_with_infrared()

            # Read button actions
            press_set  = detect_press_type(BTN_SET)
            press_fp   = detect_press_type(BTN_FP)
            press_time = detect_press_type(BTN_TIME)

            # Button 1: single press -> set schedule
            if press_set == 1:
                set_schedule_menu()

            # Button 2: single press -> fingerprint setup menu
            if press_fp == 1:
                fingerprint_setup_menu()

            # Button 3: single press -> show time remaining
            if press_time == 1:
                show_time_remaining()

            # Button 3: double press -> go to main menu
            if press_time == 2:
                show_main_menu()

            # Background scheduling logic
            tr = get_time_remaining()
            if tr is not None:
                d, h, m, target_minute = tr

                if last_target_minute != target_minute:
                    last_target_minute = target_minute
                    dispense_done_for_target = False

                # 1 minute before dose
                if d == 0 and h == 0 and m == 1 and not dispense_done_for_target:
                    lcd_print("Arming scale", "Dose soon...")
                    time.sleep(2)
                    show_main_menu()  # Return to menu after showing the arming message

                # At dose time
                if d == 0 and h == 0 and m == 0 and not dispense_done_for_target:
                    run_dispense_sequence()
                    dispense_done_for_target = True

            time.sleep(0.05)  # Delay to control loop timing

    except KeyboardInterrupt:
        pass
    finally:
        lcd.clear()
        servo1.stop()
        servo2.stop()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
