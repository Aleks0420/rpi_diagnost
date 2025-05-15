# -*- coding: utf-8 -*-
import time
import math
import traceback # Import traceback for detailed error printing
import sys # Import sys to print sys.path for debugging if needed

print("Attempting to import current sensor dependencies...") # Debug print

# --- Import necessary libraries ---
try:
    import board
    import busio

    # Import specific classes from the library
    from adafruit_ads1x15.ads1115 import ADS1115
    from adafruit_ads1x15.analog_in import AnalogIn

    # Import the internal dictionary that holds gain configuration values
    # Based on the ads1x15.py content, GAIN constants are values in this dictionary
    from adafruit_ads1x15.ads1x15 import _ADS1X15_CONFIG_GAIN

    # Note: We don't import ADS class directly as it's not needed for initialization
    # We don't import GAIN_... constants directly as they are not defined on module level

    print("Imported ADS1115 and related components.")

# --- Handle ImportError if library or components are not found ---
except ImportError as e:
    print(f"Error importing current sensor dependencies: {e}")
    # Set imported names to None so the rest of the script can check availability
    ADS1115 = None
    AnalogIn = None
    _ADS1X15_CONFIG_GAIN = None # Also set this to None on import error
    busio = None
    board = None # Setting board to None might affect other sensors if they use it globally, consider carefully or adjust logic in mqtt_sender

    print("Adafruit ADS1x15 library not found. Current sensing disabled.")

# === Calibration and parameters ===
# These parameters define how raw voltage readings are converted to current
# Adjust these based on your specific current sensor (e.g., SCT-013 30A/1V)
# For SCT-013 30A/1V, 1V RMS output corresponds to 30A RMS current.
BASE_VOLTAGE_TO_CURRENT = 30.0 / 1.0 # A/V, based on sensor's nominal ratio (30A per 1V)
CALIBRATION_FACTOR = 1.0 # Start with 1.0, adjust if needed based on actual measurements
VOLTAGE_TO_CURRENT = BASE_VOLTAGE_TO_CURRENT * CALIBRATION_FACTOR # Final conversion factor

# Thresholds to filter noise when current is near zero
# Adjust these based on your sensor's noise floor
CURRENT_THRESHOLD_AMPS = 0.5 # Minimum current (RMS) to report (below this is considered zero)

# Optional: Define plausible raw voltage range for filtering (depends on sensor and ADC connection)
# SENSOR_MIN_RAW_VOLTAGE = 0.1
# SENSOR_MAX_RAW_VOLTAGE = 4.9 # Example for 5V powered sensor measured by ADC

# --- init_adc function ---
def init_adc(adc_config):
    """Initializes the ADS1115 ADC using config and returns the instance."""
    # Check if necessary components were successfully imported at the module level
    # Include _ADS1X15_CONFIG_GAIN in the check
    if ADS1115 is None or AnalogIn is None or busio is None or board is None or _ADS1X15_CONFIG_GAIN is None:
        print("ADS1x15 library components or gain configuration not available, cannot initialize ADC.")
        return None

    try:
        print("Initializing ADS1115 ADC...")
        # Get parameters from config, with defaults
        bus = adc_config.get('bus', 1)  # Default I2C bus 1
        address_str = adc_config.get('address')
        gain_value = float(adc_config.get('gain', 1.0)) # Get gain as float, default 1.0

        if address_str is None:
            print("ADC address not provided in configuration.")
            return None
        address = int(address_str, 0)  # Handle hex or decimal string

        # Get the correct hexadecimal gain value from the imported dictionary
        ads_gain = _ADS1X15_CONFIG_GAIN.get(gain_value)


        # Initialize the I2C interface using the configured bus
        try:
            # Use getattr to dynamically get the correct SCL/SDA pin based on bus number
            i2c = busio.I2C(getattr(board, f'SCL_{bus}', board.SCL), getattr(board, f'SDA_{bus}', board.SDA))
        except AttributeError:
            # Fallback for systems where pins are not named SCL_1, SDA_1 etc.
            print(f"Warning: board definition does not have SCL_{bus}/SDA_{bus}. Falling back to default pins.")
            try:
                i2c = busio.I2C(board.SCL, board.SDA)  # Fallback to default pins
            except Exception as e:
                print(f"Failed to initialize I2C bus {bus}: {e}")
                traceback.print_exc() # Print detailed error
                return None
        except Exception as e:
             print(f"Failed to initialize I2C bus {bus}: {e}")
             traceback.print_exc() # Print detailed error
             return None


        # Create an ADS1115 object
        adc_instance = ADS1115(i2c, address=address)
        adc_instance.data_rate = 860
        # Set the gain using the hexadecimal value obtained from the dictionary
        #adc_instance.gain = ads_gain
        try:
            adc_instance.gain = gain_value
        except ValueError as e:
            print(f"Error setting gain {gain_value}: {e}")
            return None

        except Exception as e:
            print(f"Unexpected error setting gain {gain_value}: {e}")
            traceback.print_exc()
            return None


        print(f"ADS1115 ADC initialized at bus {bus}, address 0x{address:02x}, gain {gain_value}.")
        return adc_instance

    except Exception as e:
        # Catch any other exceptions during the initialization process
        print("ADS1115 init error:", e)
        traceback.print_exc() # Print detailed error
        return None # Return None on failure


# --- read_rms function (keep as is) ---
def read_rms(chan, offset_voltage, samples=100, scale=1.0):
    """Reads RMS voltage for a single AnalogIn channel and converts it to current, using per-channel scale."""
    if AnalogIn is None:
        return {"error": "analogin_not_available"}
    squared_sum = 0.0
    read_count = 0
    try:
        for _ in range(samples):
            if not isinstance(chan, AnalogIn):
                return {"error": "invalid_channel_object"}
            voltage = chan.voltage
            centered_voltage = voltage - offset_voltage
            squared_sum += centered_voltage ** 2
            read_count += 1
            time.sleep(0.0001)
    except Exception as e:
        print(f"Error reading current sample on channel {str(chan)}: {e}")
        traceback.print_exc()
        return {"error": "read_exception"}
    if read_count == 0:
        return {"error": "no_valid_samples"}
    vrms = math.sqrt(squared_sum / read_count)
    irms = vrms * VOLTAGE_TO_CURRENT * scale
    final_irms = 0.0 if irms < CURRENT_THRESHOLD_AMPS else irms
    return round(final_irms, 3)

# --- calibrate_current_sensors function (keep as is, but adjust check) ---
def calibrate_current_sensors(analogin_list, samples=500):
    """Calibrates current sensors by reading offset voltage with no load.
       Requires a list of initialized AnalogIn channel objects.
       Returns a list of offset_voltages corresponding to the input list order,
       or None on failure."""
    # Check if AnalogIn class is available (should be available if init_adc passed)
    if AnalogIn is None:
        print("AnalogIn class not available for calibration.")
        return None

    if not analogin_list:
        print("No AnalogIn channels provided for calibration. Skipping calibration.")
        return [] # Return empty list if no channels configured/provided

    print(f"Calibrating {len(analogin_list)} current sensor channels (assuming no load)...")
    offset_voltages = []
    try:
        # Use enumerate to get both the index (0, 1, 2...) and the AnalogIn object
        for index, chan in enumerate(analogin_list): # Iterate through the provided list of AnalogIn objects
            # Check if the object is actually an AnalogIn instance
            if not isinstance(chan, AnalogIn):
                 print(f"Error: Invalid object found in analogin_list during calibration at index {index}: {type(chan)}. Expected AnalogIn.")
                 return None # Return None if list contains invalid objects

            sum_voltage = 0.0
            # Use the index from enumerate for printing the channel number
            print(f"Calibrating ADC channel index {index}...")
            for _ in range(samples):
                sum_voltage += chan.voltage # This is correct, read the voltage from the AnalogIn object
                time.sleep(0.0001) # Small delay between samples

            if samples > 0:
                 offset = sum_voltage / samples
            else:
                 offset = 0.0 # Avoid division by zero if samples is 0
                 print("Warning: Calibration samples set to 0, offset will be 0.")

            offset_voltages.append(offset)
            # Use the index from enumerate for printing the channel number
            print(f"Sensor on ADC channel index {index} offset: {offset:.4f} V")

        print(f"Calibration complete for {len(offset_voltages)} channels.")
        print(f"Voltage-to-current factor: {VOLTAGE_TO_CURRENT:.2f} A/V, Current threshold: {CURRENT_THRESHOLD_AMPS:.2f} A")
        return offset_voltages # Return the list of offsets

    except Exception as e:
        print("Current sensor calibration error:", e)
        traceback.print_exc() # Print detailed error
        return None # Return None on failure
    
    

# --- measure_all_currents function (keep as is, but handle read_rms error dict) ---
def measure_all_currents(channel_analogin_map, channel_offset_map, channel_scale_map=None):
    """
    Measures current for all calibrated channels using name maps.
    Accepts dicts: channel_analogin_map (name->AnalogIn), channel_offset_map (name->offset), channel_scale_map (name->scale).
    """
    if AnalogIn is None or not channel_analogin_map or not channel_offset_map or set(channel_analogin_map.keys()) != set(channel_offset_map.keys()):
        return {"general": {"error": "calibration_maps_invalid"}}

    currents = {}
    for name, chan in channel_analogin_map.items():
        offset_voltage = channel_offset_map.get(name)
        scale = 1.0
        if channel_scale_map and name in channel_scale_map:
            scale = channel_scale_map[name]
        current_reading = read_rms(chan, offset_voltage, samples=500, scale=scale)
        if isinstance(current_reading, dict) and "error" in current_reading:
            currents[name] = current_reading
        elif isinstance(current_reading, (int, float)):
            currents[name] = current_reading
        else:
            print(f"Warning: Unexpected return type from read_rms for channel '{name}': {type(current_reading)}")
            currents[name] = {"error": "unexpected_read_rms_output"}
    return currents
