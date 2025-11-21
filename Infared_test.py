#!/usr/bin/env python3
# Test-only menu for pill dispenser (no sensor, no GPIO)
# Simulates empty LED blinking in terminal.

import time

def blink_led_sim(blinks=6, on_time=0.5, off_time=0.5):
    """Terminal blink simulation."""
    for _ in range(blinks):
        print("EMPTY LED: ON ")
        time.sleep(on_time)
        print("EMPTY LED: OFF")
        time.sleep(off_time)

def main():
    print("=== Pill Dispenser Test Menu (Simulation) ===")

    # ask for initial pills
    while True:
        try:
            capacity = int(input("Enter dispenser capacity (max pills): "))
            if capacity <= 0:
                print("Capacity must be > 0.")
                continue
            break
        except ValueError:
            print("Enter a whole number.")

    while True:
        try:
            pills_inside = int(input("Enter current pills inside: "))
            if pills_inside < 0 or pills_inside > capacity:
                print(f"Enter a number from 0 to {capacity}.")
                continue
            break
        except ValueError:
            print("Enter a whole number.")

    print("\n--- Status ---")
    print(f"Capacity: {capacity}")
    print(f"Pills inside: {pills_inside}")

    if pills_inside == 0:
        print("Status: EMPTY → blinking LED simulation")
        blink_led_sim()
    else:
        print("Status: NOT EMPTY → LED stays OFF")

    # simple loop so you can test your “menu” repeatedly
    while True:
        print("\n--- Menu ---")
        print("1) Dispense a pill (simulate)")
        print("2) Refill pills")
        print("3) Show status")
        print("4) Exit")

        choice = input("Select option: ").strip()

        if choice == "1":
            if pills_inside > 0:
                pills_inside -= 1
                print("Dispensed 1 pill.")
                if pills_inside == 0:
                    print("Now EMPTY → blinking LED simulation")
                    blink_led_sim()
            else:
                print("Already empty → blinking LED simulation")
                blink_led_sim()

        elif choice == "2":
            while True:
                try:
                    add = int(input("How many pills to add? "))
                    if add < 0:
                        print("Enter 0 or more.")
                        continue
                    pills_inside = min(capacity, pills_inside + add)
                    print(f"Refilled. Pills inside now: {pills_inside}")
                    break
                except ValueError:
                    print("Enter a whole number.")

        elif choice == "3":
            print("\n--- Status ---")
            print(f"Pills inside: {pills_inside}/{capacity}")
            if pills_inside == 0:
                print("Status: EMPTY → blinking LED simulation")
                blink_led_sim()
            else:
                print("Status: NOT EMPTY → LED OFF")

        elif choice == "4":
            print("Exiting test.")
            break

        else:
            print("Invalid option. Pick 1–4.")

if __name__ == "__main__":
    main()
