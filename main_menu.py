#!/usr/bin/env python3

import os
import sys
import time
import subprocess

# Directory where this script lives
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Menu entries: (menu text, filename)
MENU_ITEMS = {
    "1": ("Fingerprint System", "Fingerprintcode.py"),
    "2": ("Load Cell",          "Load_Cell.py"),
    "3": ("System Scheduler",   "System_Scheduler.py"),
}


def clear_screen():
    """
    Clear the terminal screen (works on most systems).
    """
    os.system("clear" if os.name != "nt" else "cls")


def run_script(filename):
    """
    Run another Python script using the same interpreter.
    When the script finishes, return to the menu.
    """
    script_path = os.path.join(SCRIPT_DIR, filename)

    if not os.path.exists(script_path):
        print(f"\n[ERROR] File not found: {script_path}")
        input("Press Enter to return to the menu...")
        return

    print(f"\n[INFO] Running: {filename}")
    print("[INFO] Press Ctrl+C to stop and return to menu (if supported by that script).")
    print("")

    try:
        # Use the same Python interpreter that is running this menu
        subprocess.run([sys.executable, script_path])
    except KeyboardInterrupt:
        print("\n[INFO] Script interrupted by user. Returning to menu...")
        time.sleep(1)
    except Exception as e:
        print(f"\n[ERROR] Problem running {filename}: {e}")
        input("Press Enter to return to the menu...")


def main_menu():
    """
    Main menu loop in the terminal.
    """
    while True:
        clear_screen()
        print("===================================")
        print("         MAIN SYSTEM MENU          ")
        print("===================================\n")
        for key, (label, _) in MENU_ITEMS.items():
            print(f"  {key}. {label}")
        print("  q. Quit\n")

        choice = input("Select an option: ").strip().lower()

        if choice == "q":
            print("\nExiting menu. Goodbye!")
            time.sleep(1)
            break

        if choice in MENU_ITEMS:
            label, filename = MENU_ITEMS[choice]
            clear_screen()
            print(f"--- {label} ---")
            run_script(filename)
        else:
            print("\n[ERROR] Invalid choice. Please try again.")
            time.sleep(1)


if __name__ == "__main__":
    main_menu()
