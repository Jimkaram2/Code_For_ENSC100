import time
import board
import busio
from digitalio import DigitalInOut, Direction, Pull
import adafruit_fingerprint

# ------------------------------------
# Hardware Setup
# ------------------------------------
uart = serial.Serial("/dev/ttyUSB0", baudrate=57600, timeout=1)
finger = adafruit_fingerprint.Adafruit_Fingerprint(uart)

menu_button = DigitalInOut(board.D5)
menu_button.direction = Direction.INPUT
menu_button.pull = Pull.UP

btn_enroll = DigitalInOut(board.D6)
btn_enroll.direction = Direction.INPUT
btn_enroll.pull = Pull.UP

btn_delete = DigitalInOut(board.D7)
btn_delete.direction = Direction.INPUT
btn_delete.pull = Pull.UP

btn_quit = DigitalInOut(board.D8)
btn_quit.direction = Direction.INPUT
btn_quit.pull = Pull.UP


# ------------------------------------
# Helper Functions
# ------------------------------------

def wait_button_press(button):
    """Blocks until button is pressed."""
    while button.value:  # waiting for LOW
        time.sleep(0.05)
    time.sleep(0.2)  # debounce
    return True


def wait_for_finger():
    if finger.get_image() != adafruit_fingerprint.OK:
        return False

    if finger.image_2_tz(1) != adafruit_fingerprint.OK:
        return False

    if finger.finger_search() != adafruit_fingerprint.OK:
        return False

    return True


def enroll_finger(location):
    for fingerimg in range(1, 3):
        print("\nPlace finger on sensor...")

        while True:
            i = finger.get_image()
            if i == adafruit_fingerprint.OK:
                print("Image taken")
                break
            if i == adafruit_fingerprint.NOFINGER:
                print(".", end="")
            else:
                print("Imaging error")
                return False

        print("Templating...")
        if finger.image_2_tz(fingerimg) != adafruit_fingerprint.OK:
            print("Template error")
            return False

        if fingerimg == 1:
            print("Remove finger")
            time.sleep(1)
            while finger.get_image() != adafruit_fingerprint.NOFINGER:
                pass

    print("Creating model...")
    if finger.create_model() != adafruit_fingerprint.OK:
        print("Model creation failed.")
        return False

    print("Storing fingerprint...")
    if finger.store_model(location) != adafruit_fingerprint.OK:
        print("Store failed")
        return False

    print("Fingerprint stored!")
    return True


def delete_finger(location):
    if finger.delete_model(location) == adafruit_fingerprint.OK:
        print("Fingerprint deleted.")
    else:
        print("Delete failed.")


def do_action(fp_id):
    print("\n========== ACTION ==========")
    print("Valid fingerprint detected! ID =", fp_id)
    print("================================\n")


# ------------------------------------
# ID Selection via Button
# ------------------------------------

def choose_id():
    """
    User scrolls through ID numbers using Enroll/Delete buttons.
    Press Quit to confirm.
    """
    current_id = 1
    print("\nSelect ID using buttons:")
    print("Enroll = +1   Delete = -1   Quit = Confirm")

    while True:
        print("ID:", current_id)

        if not btn_enroll.value:
            current_id += 1
            if current_id > 127:
                current_id = 1
            time.sleep(0.25)

        if not btn_delete.value:
            current_id -= 1
            if current_id < 1:
                current_id = 127
            time.sleep(0.25)

        if not btn_quit.value:
            print("Selected ID:", current_id)
            time.sleep(0.3)
            return current_id


# ------------------------------------
# Button-Based Menu
# ------------------------------------

def run_menu():
    print("\n===== FINGERPRINT MENU =====")
    print("Press Button 1 = Enroll new fingerprint")
    print("Press Button 2 = Delete fingerprint")
    print("Press Button 3 = Quit menu\n")
    print("============================\n")

    while True:
        # Enroll
        if not btn_enroll.value:
            print("\nEnroll selected.")
            fp_id = choose_id()
            enroll_finger(fp_id)

        # Delete
        if not btn_delete.value:
            print("\nDelete selected.")
            fp_id = choose_id()
            delete_finger(fp_id)

        # Quit
        if not btn_quit.value:
            print("Exiting menu...")
            time.sleep(0.3)
            return

        time.sleep(0.05)


# ------------------------------------
# Main Loop
# ------------------------------------

print("System ready.")
print("Press menu button to open menu.\n")

while True:

    # Open menu
    if not menu_button.value:
        print("\nMenu button pressed → Opening menu...")
        time.sleep(0.3)
        run_menu()

    # Normal mode: wait for fingerprint
    if finger.get_image() == adafruit_fingerprint.OK:
        print("Fingerprint detected → Processing...")
        if wait_for_finger():
            do_action(finger.finger_id)
        else:
            print("Fingerprint not recognized.")

    time.sleep(0.1)
