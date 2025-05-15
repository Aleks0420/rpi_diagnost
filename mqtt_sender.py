# mqtt_sender.py
# -*- coding: utf-8 -*-

import json
import sys
import time
import threading
import argparse
import signal
import copy # For deepcopy if needed, though processing module handles its own copies

from mqtt_buffer_sqlite import init_db

# --- Configuration Management ---
try:
    from config_manager import load_config, run_config_menu, save_config, get_default_config
    print("Config manager module loaded.")
except ImportError:
    print("Error: config_manager.py not found. Cannot run application.")
    sys.exit(1)

# --- MQTT Utilities ---
try:
    from mqtt_utils import create_mqtt_client, connect_mqtt, is_mqtt_connected
    print("MQTT utilities module loaded.")
except ImportError:
    print("Error: mqtt_utils.py not found. Cannot run application.")
    sys.exit(1)

# --- Sensor Initialization ---
try:
    # These functions will use sensor modules (MPU6050, DS18B20, current_sensors) internally
    from sensor_initializer import (
        initialize_mpu_sensors,
        initialize_ds18b20_sensors,
        initialize_current_sensors,
        MPU6050, DS18B20, CURRENT_SENSORS_AVAILABLE # Import availability flags/modules
    )
    print("Sensor initializer module loaded.")
except ImportError:
    print("Error: sensor_initializer.py not found. Cannot run application.")
    sys.exit(1)

# --- Sensor Processing Threads ---
try:
    from processing.sensor_processing import (
        mpu_processing_and_publish_loop,
        temperature_thread_loop,
        current_thread_loop,
        mqtt_watchdog_loop
    )
    print("Sensor processing module loaded.")
except ImportError:
    print("Error: sensor_processing.py not found. Cannot run application.")
    sys.exit(1)

try:
    import RPi.GPIO as GPIO
    from led_indicator import LEDIndicator  # Import the LEDIndicator class
    LEDS_AVAILABLE = True
except ImportError:
    LEDS_AVAILABLE = False
    print("RPi.GPIO or led_indicator module not found. LED indication disabled.")


# --- Global Configuration Dictionary ---
config = {}

# --- Shared Data Storage ---
# These dictionaries hold the latest measured data or error states.
# They are updated by sensor initialization and reading threads.
latest_vibration_data = {}
latest_temperature_data = {}
latest_current_data = {}

# --- Control Event ---
# Flag to signal threads to stop gracefully
stop_event = threading.Event()


def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="MQTT Sensor Sender")
    parser.add_argument('--no-menu', action='store_true', help='Start without configuration menu')
    parser.add_argument('--calibrate', dest='calibrate', action='store_true', help='Force calibration for MPU and Current sensors')
    parser.add_argument('--no-calibrate', dest='calibrate', action='store_false', help='Skip calibration for MPU and Current sensors')
    parser.set_defaults(calibrate=None) # None means use config setting or default True
    parser.add_argument('--config', type=str, default='config.json', help='Path to configuration file')
    return parser.parse_args()


def signal_handler(signum, frame):
    """Handles signals (like Ctrl+C) to stop the application."""
    print(f"\nSignal {signum} received. Stopping threads...")
    stop_event.set()
    if LEDS_AVAILABLE:
       GPIO.cleanup() # To ensure all GPIOs are reset to default state before exiting.



def pre_populate_error_states(cfg, latest_vib_data, latest_temp_data, latest_curr_data):
    """
    Pre-populates the shared data dictionaries with initial error states
    based on module availability and sensor configuration.
    This ensures the JSON structure includes all configured sensor names
    even if their initialization or reading later fails.
    """
    latest_vib_data.clear()
    latest_temp_data.clear()
    latest_curr_data.clear()

    # MPU6050
    mpu_configs = cfg.get('sensors', {}).get('mpu6050', [])
    if not MPU6050: # Module itself not loaded
        latest_vib_data["general"] = {"error": "not_found_module", "module": "MPU6050"}
    elif not mpu_configs: # Module loaded, but no sensors configured
        latest_vib_data["general"] = {"error": "not_configured_type", "type": "MPU6050"}
    else: # Module loaded, sensors configured - set per-sensor initial state
        for mpu_cfg in mpu_configs:
            name = mpu_cfg.get('name')
            if name: latest_vib_data[name] = {"error": "not_initialized"}

    # DS18B20
    ds_configs = cfg.get('sensors', {}).get('ds18b20', [])
    if not DS18B20:
        latest_temp_data["general"] = {"error": "not_found_module", "module": "DS18B20"}
    elif not ds_configs:
        latest_temp_data["general"] = {"error": "not_configured_type", "type": "DS18B20"}
    else:
        for ds_cfg in ds_configs:
            name = ds_cfg.get('name')
            if name: latest_temp_data[name] = {"error": "not_initialized"}

    # Current Sensors
    current_cfg = cfg.get('sensors', {}).get('current', {})
    current_channels_configs = current_cfg.get('channels', [])
    if not CURRENT_SENSORS_AVAILABLE:
        latest_curr_data["general"] = {"error": "not_found_module", "module": "current_sensors"}
    elif not current_channels_configs:
        latest_curr_data["general"] = {"error": "not_configured_channels"}
    elif not current_cfg.get('adc'):
         # Channels might be configured, but ADC section is missing
         latest_curr_data["general"] = {"error": "not_configured_adc"}
    else:
        for channel_cfg in current_channels_configs:
            name = channel_cfg.get('name')
            if name: latest_curr_data[name] = {"error": "not_initialized"}

def main():
    """Main function to load config, run menu, initialize sensors, and start threads."""
    global config, latest_vibration_data, latest_temperature_data, latest_current_data

    args = parse_arguments()
    init_db()

    # --- 1. Load configuration ---
    config.update(load_config(args.config)) # Load into global config dict

    # --- 2. Run configuration menu (unless --no-menu is passed) ---
    if not args.no_menu:
        should_start = run_config_menu(config) # Pass global config to be modified by menu
        if not should_start:
            print("Exiting application via menu.")
            sys.exit(0)
    else:
        print("Skipping configuration menu (--no-menu). Starting automatically.")

    # --- Determine calibration flags ---
    # Priority: command-line > config file > default (which is True for calibrate)
    mpu_calibrate_flag = args.calibrate
    if mpu_calibrate_flag is None: # Not set by command line
        mpu_calibrate_flag = config.get('calibration', {}).get('mpu', True)

    current_calibrate_flag = args.calibrate
    if current_calibrate_flag is None: # Not set by command line
        current_calibrate_flag = config.get('calibration', {}).get('current', True)

    # --- 3. Create and Connect to MQTT broker ---
    device_id = config.get('device_id', 'unknown_device')
    mqtt_broker = config.get('mqtt', {}).get('broker', '127.0.0.1')
    mqtt_port = config.get('mqtt', {}).get('port', 1883)

    if LEDS_AVAILABLE:
        led_indicator = LEDIndicator(green_pin=17, blue_pin=18, yellow_pin=27, red_pin=22, white_pin=23)
    else:
        led_indicator = None

    mqtt_client = create_mqtt_client(client_id=device_id) # Create client instance
    connect_mqtt(mqtt_client, mqtt_broker, mqtt_port, device_id, stop_event, led_indicator)
    # connect_mqtt starts loop_start() and handles initial connection attempt.
    # Reconnection will be handled by paho-mqtt's loop.

    # --- 4. Pre-populate shared data with initial error states ---
    print("\nPre-populating sensor states...")
    pre_populate_error_states(config, latest_vibration_data, latest_temperature_data, latest_current_data)

    # --- 5. Initialize Sensors based on final configuration ---
    # These functions will update the latest_*_data dictionaries with more specific errors
    # or remove entries on success.
    print("\nInitializing sensors...")
    mpu_configs = config.get('sensors', {}).get('mpu6050', [])
    initialized_mpu_sensors = initialize_mpu_sensors(
        mpu_configs, latest_vibration_data, calibrate_flag=mpu_calibrate_flag
    )

    ds_configs = config.get('sensors', {}).get('ds18b20', [])
    initialized_ds18b20_sensors = initialize_ds18b20_sensors(
        ds_configs, latest_temperature_data
    )

    current_cfg = config.get('sensors', {}).get('current', {})
    initialized_current_data = initialize_current_sensors(
        current_cfg, latest_current_data, calibrate_flag=current_calibrate_flag
    ) # Returns a dict or None

    if led_indicator:
       led_indicator.set_white(args.calibrate is True) # True if forced, None defaults to config, but set_white only takes bool


    # --- 6. Start Sensor Reading and Processing Threads ---
    print("\nStarting sensor processing threads...")
    threads = []

    # MPU Processing and Publishing Thread
    # This thread now handles MPU reading, RMS calculation, data aggregation, and MQTT publishing.
    if initialized_mpu_sensors or \
       initialized_ds18b20_sensors or \
       (initialized_current_data and initialized_current_data.get('channel_analogin_map')):
        # Start this thread if any sensor type is available for publishing

        # For mpu_processing_and_publish_loop, we need to pass the actual initialized MPU sensors objects
        # It will directly compute RMS from them.
        # It will also read latest_temperature_data and latest_current_data.
        # And it will update latest_vibration_data with RMS values for consistency.

        mpu_thread = threading.Thread(
            target=mpu_processing_and_publish_loop,
            args=(
                initialized_mpu_sensors, # Dict of initialized MPU objects
                config,
                mqtt_client,
                stop_event,
                latest_vibration_data, # To store RMS values
                latest_temperature_data, # To read for publishing
                latest_current_data,     # To read for publishing
                is_mqtt_connected,        # Function to check MQTT status
                led_indicator
            ),
            daemon=True # Daemon threads exit when main program exits
        )
        threads.append(mpu_thread)
        mpu_thread.start()
        print("MPU processing and publishing thread started.")
    else:
        print("No sensors initialized successfully, MPU processing and publishing thread not started.")


    # Temperature Thread (only reads and updates latest_temperature_data)
    if initialized_ds18b20_sensors:
        temp_thread = threading.Thread(
            target=temperature_thread_loop,
            args=(initialized_ds18b20_sensors, config, stop_event, latest_temperature_data),
            daemon=True
        )
        threads.append(temp_thread)
        temp_thread.start()
    else:
        # Info already provided by pre_populate_error_states and initialize_ds18b20_sensors
        pass # print("No DS18B20 sensors initialized, temperature thread not started.")


    # Current Thread (only reads and updates latest_current_data)
    if initialized_current_data and initialized_current_data.get('channel_analogin_map'):
        current_thread = threading.Thread(
            target=current_thread_loop,
            args=(initialized_current_data, config, stop_event, latest_current_data),
            daemon=True
        )
        threads.append(current_thread)
        current_thread.start()
    else:
        # Info already provided by pre_populate_error_states and initialize_current_sensors
        pass # print("Current sensors not initialized/configured, current thread not started.")

    # --- 7. Set up signal handling for clean exit ---
    # --- MQTT Watchdog Thread ---
    watchdog_thread = threading.Thread(
        target=mqtt_watchdog_loop,
        args=(mqtt_client, config, stop_event, is_mqtt_connected),
        daemon=True
    )
    threads.append(watchdog_thread)
    watchdog_thread.start()
    print("MQTT Watchdog thread started.")
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # Handle kill signal

    print("\nApplication running. Press Ctrl+C to stop.")

    # --- 8. Keep the main thread alive until stop_event is set ---
    try:
        while not stop_event.is_set():
            # You can add a short sleep here if you want the main thread to do periodic checks
            # but stop_event.wait() is generally more efficient if it's just waiting.
            # For instance, to periodically check if any critical thread died unexpectedly:
            # stop_event.wait(timeout=5.0) # Check every 5 seconds
            # if not any(t.is_alive() for t in threads if t.daemon is False): # Example check for non-daemon threads
            #    print("A critical non-daemon thread seems to have exited. Stopping.")
            #    stop_event.set()
            # For daemon threads, this check is less critical as they won't keep python alive
            stop_event.wait() # Wait indefinitely until stop_event is set

    except KeyboardInterrupt: # Redundant if SIGINT is handled, but good fallback
        print("KeyboardInterrupt caught in main loop. Stopping...")
        stop_event.set()

    # --- 9. Wait for all threads to finish ---
    print("Stop event received by main thread. Waiting for threads to join...")
    # Make sure threads list only contains started threads
    active_threads = [t for t in threads if t.is_alive()]
    for i, thread in enumerate(active_threads):
        print(f"Waiting for thread {thread.name or i} to join...")
        thread.join(timeout=5) # Add a timeout for join
        if thread.is_alive():
            print(f"Warning: Thread {thread.name or i} did not join gracefully within timeout.")

    # --- 10. Stop MQTT network loop and disconnect ---
    if mqtt_client:
        print("Stopping MQTT client...")
        mqtt_client.loop_stop() # Stop the network loop
        mqtt_client.disconnect() # Disconnect
        print("MQTT client stopped.")

    if led_indicator:
       led_indicator.cleanup()

    print("Application finished.")


# --- Run the main function ---
if __name__ == "__main__":
    main()