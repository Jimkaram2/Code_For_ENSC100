DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

schedule = {
    "day_index": None,
    "hour": None,
    "minute": None
}

def lcd_clear():
    # Simulate clearing a 16x2 LCD
    print("\n" * 3)

def lcd_print(line1, line2=""):
    # Simulate printing to LCD
    lcd_clear()
    print("LCD:", line1)
    if line2:
        print("LCD:", line2)

def get_button(prompt="Press [s]=Schedule/Increment, [e]=Enter: "):
    """
    Simulate button presses using keyboard:
    - s = SCHEDULE (increment)
    - e = ENTER (confirm)
    """
    while True:
        choice = input(prompt).strip().lower()
        if choice in ("s", "e"):
            return choice
        print("Invalid input, try again (s/e).")

def get_value(label, min_val, max_val, initial=0, formatter=str):
    """
    Same logic as on the Pi:
    - Show current value on 'LCD'
    - s increments (wraps around)
    - e confirms
    """
    value = initial
    while True:
        lcd_print(f"Set {label}:", formatter(value))
        btn = get_button()
        if btn == "s":
            value += 1
            if value > max_val:
                value = min_val
        elif btn == "e":
            return value

def set_schedule():
    """
    Full scheduling flow using only s (increment) and e (enter),
    just like it will be on the real device.
    """
    lcd_print("Scheduling mode", "Use s=+1, e=OK")
    input("Press Enter to start scheduling...")

    # --- Select DAY ---
    day_index = get_value(
        label="Day",
        min_val=0,
        max_val=6,
        initial=0,
        formatter=lambda d: DAYS[d]
    )

    # --- Select HOUR (24h) ---
    hour = get_value(
        label="Hour",
        min_val=0,
        max_val=23,
        initial=1,
        formatter=lambda h: f"{h:02d}:--"
    )

    # --- Select MINUTE ---
    minute = get_value(
        label="Minute",
        min_val=0,
        max_val=59,
        initial=0,
        formatter=lambda m: f"--:{m:02d}"
    )

    schedule["day_index"] = day_index
    schedule["hour"] = hour
    schedule["minute"] = minute

    lcd_print("Schedule Saved", f"{DAYS[day_index]} {hour:02d}:{minute:02d}")

def check_time_against_schedule():
    """
    Lets you input a 'fake' current time and checks whether the
    dispenser would activate at that moment.
    """
    if schedule["day_index"] is None:
        print("No schedule set yet.")
        return

    print("\nCurrent saved schedule:")
    print(f"  Day:  {DAYS[schedule['day_index']]}")
    print(f"  Time: {schedule['hour']:02d}:{schedule['minute']:02d}")
    print("\nNow enter a 'simulated' current time to test matching.")

    day_input = input("Day (Mon/Tue/...): ").strip().title()
    if day_input not in DAYS:
        print("Invalid day.")
        return
    day_index = DAYS.index(day_input)

    try:
        hour = int(input("Hour (0-23): "))
        minute = int(input("Minute (0-59): "))
    except ValueError:
        print("Invalid hour/minute.")
        return

    if (day_index == schedule["day_index"] and
        hour == schedule["hour"] and
        minute == schedule["minute"]):
        print("\n>>> MATCH! Dispenser would activate now.")
    else:
        print("\nNo match. Dispenser would NOT activate now.")

def main():
    while True:
        print("\n=== Daily Dose Simulator ===")
        if schedule["day_index"] is None:
            print("Current schedule: [none]")
        else:
            print("Current schedule:",
                  f"{DAYS[schedule['day_index']]} {schedule['hour']:02d}:{schedule['minute']:02d}")

        print("Options:")
        print("  1) Set / change schedule (simulate buttons)")
        print("  2) Test a simulated current time")
        print("  3) Quit")

        choice = input("Select option (1-3): ").strip()
        if choice == "1":
            set_schedule()
        elif choice == "2":
            check_time_against_schedule()
        elif choice == "3":
            print("Goodbye.")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
