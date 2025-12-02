#!/usr/bin/env python3
"""
Simulated Daily Dose - Combined pill dispenser logic for Python (no hardware)
- 3 Menus: Set Schedule, Refill, Time Remaining
- Simple terminal input for menu selection
- Simulates pill dispensing with decrementing pill count
- Schedule and pill count data persist across program runs
"""

import time
import datetime
import os

# Simulated components and variables
pills_funnel_1 = 0
pills_funnel_2 = 0

LED_OK = "Funnel 1 LED (empty)"
LED_ERR = "Funnel 2 LED (empty)"

# Days of the week (0=Mon, 1=Tue, ..., 6=Sun)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Schedule for Funnel 1 and Funnel 2 (loaded from file)
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

# File to save schedule data
schedule_file = "schedule_data.txt"

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
        "1:Set Sched  2:Refill\n3:Time Remaining  4:Exit"
    )

# =========================
#  BUTTON SIMULATION
# =========================

def simulate_menu_selection():
    """Simulate menu selections with numeric input."""
    print("\nSelect an option:")
    print("1: Set Schedule")
    print("2: Refill Pills")
    print("3: Show Time Remaining")
    print("4: Exit")
    return input("Enter your choice (1, 2, 3, 4): ")

# =========================
#  PILL INVENTORY
# =========================

def init_pill_counts():
    """Ask user how many pills are in each funnel initially (via keyboard)."""
    global pills_funnel_1, pills_funnel_2

    # Prompt user to input pill counts for Funnel 1 and Funnel 2
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
    - If pill count <= 0 -> LED ON (empty)
    - If pill count > 0  -> LED OFF
    """
    if pills_funnel_1 <= 0:
        print(f"{LED_OK} is ON (empty)")
    else:
        print(f"{LED_OK} is OFF (not empty)")

    if pills_funnel_2 <= 0:
        print(f"{LED_ERR} is ON (empty)")
    else:
        print(f"{LED_ERR} is OFF (not empty)")

# =========================
#  REFILL MENU
# =========================

def refill_menu():
    """
    Refill procedure using keyboard input:
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
            f"Count: {count:02d}  (Press 1: +  Press 2: Confirm)"
        )
        choice = input("Enter your choice (1 to increment, 2 to confirm): ")
        if choice == "1":
            count = (count + 1) % (max_count + 1)
        elif choice == "2":
            pills_funnel_1 = count
            break
        time.sleep(0.05)

    # ---- Refill Funnel 2 ----
    count = max(0, min(pills_funnel_2, max_count))
    while True:
        lcd_print(
            f"Refill Funnel 2:",
            f"Count: {count:02d}  (Press 1: +  Press 2: Confirm)"
        )
        choice = input("Enter your choice (1 to increment, 2 to confirm): ")
        if choice == "1":
            count = (count + 1) % (max_count + 1)
        elif choice == "2":
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
    Simple schedule setting with numeric input:
    Fields: Funnel1 Day -> Hour -> Minute, then Funnel2 Day -> Hour -> Minute
    Press 'q' to exit and return to the main menu
    """
    global schedule_funnel_1, schedule_funnel_2, last_target_minute, dispense_done_for_target

    # ---- Funnel 1 Day ----
    day = 0
    while True:
        lcd_print(f"Set Funnel 1 Day:", f"{DAYS[day]}")
        press = input("Press '1' to increment day, '2' to confirm, 'q' to quit: ")
        if press == "1":
            day = (day + 1) % 7
        elif press == "2":
            break
        elif press == "q":
            show_main_menu()
            return
        time.sleep(0.05)

    # ---- Funnel 1 Hour ----
    hour = 0
    while True:
        lcd_print("Set Funnel 1 Hour:", f"{hour:02d}")
        press = input("Press '1' to increment hour, '2' to confirm, 'q' to quit: ")
        if press == "1":
            hour = (hour + 1) % 24
        elif press == "2":
            break
        elif press == "q":
            show_main_menu()
            return
        time.sleep(0.05)

    # ---- Funnel 1 Minute ----
    minute = 0
    while True:
        lcd_print("Set Funnel 1 Minute:", f"{minute:02d}")
        press = input("Press '1' to increment minute, '2' to confirm, 'q' to quit: ")
        if press == "1":
            minute = (minute + 1) % 60
        elif press == "2":
            break
        elif press == "q":
            show_main_menu()
            return
        time.sleep(0.05)

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
        lcd_print(f"Set Funnel 2 Day:", f"{DAYS[day]}")
        press = input("Press '1' to increment day, '2' to confirm, 'q' to quit: ")
        if press == "1":
            day = (day + 1) % 7
        elif press == "2":
            break
        elif press == "q":
            show_main_menu()
            return
        time.sleep(0.05)

    # ---- Funnel 2 Hour ----
    hour = 0
    while True:
        lcd_print(f"Set Funnel 2 Hour:", f"{hour:02d}")
        press = input("Press '1' to increment hour, '2' to confirm, 'q' to quit: ")
        if press == "1":
            hour = (hour + 1) % 24
        elif press == "2":
            break
        elif press == "q":
            show_main_menu()
            return
        time.sleep(0.05)

    # ---- Funnel 2 Minute ----
    minute = 0
    while True:
        lcd_print("Set Funnel 2 Minute:", f"{minute:02d}")
        press = input("Press '1' to increment minute, '2' to confirm, 'q' to quit: ")
        if press == "1":
            minute = (minute + 1) % 60
        elif press == "2":
            break
        elif press == "q":
            show_main_menu()
            return
        time.sleep(0.05)

    schedule_funnel_2["day"] = day
    schedule_funnel_2["hour"] = hour
    schedule_funnel_2["minute"] = minute

    lcd_print("Funnel 2 Schedule Set!",
              f"{DAYS[day]} {hour:02d}:{minute:02d}")
    time.sleep(2)

    save_schedule()  # Save the schedule and pill count data to the file
    show_main_menu()

# =========================
#  TIME REMAINING SIMULATION
# =========================

def get_time_remaining():
    """
    Simulate the time remaining until the next scheduled dose
    for Funnel 1 (currently used as main schedule).
    If no schedule set, return None.
    """
    if schedule_funnel_1["day"] is None:
        return None

    now = datetime.datetime.now()
    current_min = now.weekday() * 24 * 60 + now.hour * 60 + now.minute
    target_min = (schedule_funnel_1["day"] * 24 * 60 +
                  schedule_funnel_1["hour"] * 60 +
                  schedule_funnel_1["minute"])

    # Only move to next week if strictly in the past
    if target_min < current_min:
        target_min += 7 * 24 * 60

    delta = target_min - current_min
    d = delta // (24 * 60)
    h = (delta % (24 * 60)) // 60
    m = delta % 60
    return d, h, m, target_min

def show_time_remaining():
    """Show time remaining on terminal (Button 3 single press)."""
    tr = get_time_remaining()
    if tr is None:
        lcd_print("No Schedule", "Set w/ Button 1")
        time.sleep(2)
        show_main_menu()
        return

    d, h, m, _ = tr
    if d > 0:
        lcd_print("Next dose in:", f"{d}d {h}h {m}m")
    else:
        lcd_print("Next dose in:", f"{h:02d}h {m:02d}m")
    time.sleep(2)
    show_main_menu()

# =========================
#  FINGERPRINT SIMULATION
# =========================

def fingerprint_simulation():
    """Simulate fingerprint verification."""
    print("Simulating Fingerprint Verification... (Always success)")
    time.sleep(1)
    return True

# =========================
#  SCHEDULE SAVE / LOAD
# =========================

def save_schedule():
    """Save schedule and pill count data to a file."""
    with open(schedule_file, "w") as f:
        # Save Funnel 1 Schedule and pill count
        f.write(f"{schedule_funnel_1['day']} {schedule_funnel_1['hour']} {schedule_funnel_1['minute']} {pills_funnel_1}\n")
        # Save Funnel 2 Schedule and pill count
        f.write(f"{schedule_funnel_2['day']} {schedule_funnel_2['hour']} {schedule_funnel_2['minute']} {pills_funnel_2}\n")

def load_schedule():
    """Load schedule and pill count data from a file."""
    global schedule_funnel_1, schedule_funnel_2, pills_funnel_1, pills_funnel_2

    if os.path.exists(schedule_file):
        with open(schedule_file, "r") as f:
            # Load Funnel 1 Schedule and pill count
            schedule_funnel_1['day'], schedule_funnel_1['hour'], schedule_funnel_1['minute'], pills_funnel_1 = map(int, f.readline().split())
            # Load Funnel 2 Schedule and pill count
            schedule_funnel_2['day'], schedule_funnel_2['hour'], schedule_funnel_2['minute'], pills_funnel_2 = map(int, f.readline().split())

# =========================
#  MAIN DISPENSE SEQUENCE
# =========================

def run_dispense_sequence():
    """
    Full sequence:
    - Simulate Fingerprint
    - Run Motor1, check load cell -> decrement Funnel 1 count
    - Run Motor2, check load cell -> decrement Funnel 2 count
    LEDs indicate empty funnels based on inventory.
    """
    global pills_funnel_1, pills_funnel_2

    if not fingerprint_simulation():
        print("Fingerprint verification failed!")
        return

    # Simulate "arming" and "dispensing soon"
    lcd_print("Arming scale...", "Dose soon...")
    time.sleep(2)

    # Motor 1 -> Funnel 1
    lcd_print("Motor 1 ON", "Dropping Pill 1...")
    time.sleep(1)  # Simulating dispensing
    if pills_funnel_1 > 0:
        pills_funnel_1 -= 1
        lcd_print("Pill 1 Dispensed",
                  f"Funnel 1 left: {pills_funnel_1}")
    else:
        lcd_print("Pill 1 FAIL", "Check Funnel 1")
        time.sleep(2)

    update_leds_with_inventory()

    # Motor 2 -> Funnel 2
    lcd_print("Motor 2 ON", "Dropping Pill 2...")
    time.sleep(1)  # Simulating dispensing
    if pills_funnel_2 > 0:
        pills_funnel_2 -= 1
        lcd_print("Pill 2 Dispensed",
                  f"Funnel 2 left: {pills_funnel_2}")
        time.sleep(1)
    else:
        lcd_print("Pill 2 FAIL", "Check Funnel 2")
        time.sleep(2)

    update_leds_with_inventory()

    lcd_print("Dispense Complete!", "")
    time.sleep(2)
    show_main_menu()

# =========================
#  MAIN LOOP / MENU
# =========================

def main():
    # Load saved data
    load_schedule()

    # Ask user for initial pill counts if not loaded
    if pills_funnel_1 == 0 and pills_funnel_2 == 0:
        init_pill_counts()

    lcd_splash()
    show_main_menu()

    try:
        while True:
            # Simulate menu selection
            user_input = simulate_menu_selection()

            # Button 1: single press -> set schedules
            if user_input == "1":
                set_schedule_menu()

            # Button 2: single press -> refill menu
            elif user_input == "2":
                refill_menu()

            # Button 3: single press -> show time remaining
            elif user_input == "3":
                show_time_remaining()

            # Exit the program
            elif user_input == "4":
                print("Exiting program...")
                break

            time.sleep(0.05)  # Loop delay

    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
