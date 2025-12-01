import time
from hx711 import HX711

# Define the pins for the HX711 load cell
DT_PIN  = 23   # HX711 Data pin
SCK_PIN = 24   # HX711 Clock pin

# Create an HX711 object
hx = HX711(DT_PIN, SCK_PIN)

# Tare the load cell (this sets the zero reference)
hx.reset()
hx.tare()
time.sleep(1)

# Now, ask the user to place a known weight on the scale
known_weight = float(input("Enter the known weight of the object (in grams): "))

# Take a few readings to get an average
raw_value = hx.get_weight(5)
print(f"Raw value with the known weight: {raw_value}")

# Calculate the calibration factor
calibration_factor = known_weight / raw_value
print(f"Calculated Calibration Factor: {calibration_factor}")

# Set the new calibration factor in the HX711 object
hx.set_reference_unit(calibration_factor)

# Perform a test reading with the new calibration factor
hx.reset()
hx.tare()
time.sleep(1)

# Test the calibration by reading the weight again
raw_value = hx.get_weight(5)
print(f"Test reading with the known weight: {raw_value} grams")

# You can now use the `calibration_factor` for further accurate readings
