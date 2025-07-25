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
# import gui_config_menu  # import our graphical configuration module

# --- Configuration Management ---
try:
    from config_manager import load_config, run_config_menu, save_config, get_default_config
    print("Config manager module loaded.")
except ImportError:
    print("Error: config_manager.py not found. Cannot run application.")
    sys.exit(1)

# --- MQTT Utilities ---
try:
    from mqtt_utils import create_mqtt_client, connect_mqtt, is_mqtt_connected, monitor_mqtt_connection
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

# --- Global variables for sensor and thread management
initialized_mpu_sensors = {}
initialized_ds18b20_sensors = {}
initialized_current_data = {}
threads = []
mqtt_client = None
led_indicator = None

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
    global led_indicator, stop_event, threads, mqtt_client
    if led_indicator:
        led_indicator.cleanup()
    stop_event.set()
    if LEDS_AVAILABLE:
       GPIO.cleanup() # To ensure all GPIOs are reset to default state before exiting.
    # Wait for threads to join
    for thread in threads:
        thread.join()
    # Stop MQTT client
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    print("Application finished.")
    sys.exit(0)

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


def button_monitor(config, stop_event):
    """
    Monitors the button input on GPIO17 (physical pin 11) continuously.
    When the button is pressed (input goes LOW), it launches the Tkinter-based configuration menu.
    """
    import time
    BUTTON_PIN = 17  # GPIO17 corresponds to physical pin 11

    # Ensure GPIO is set up
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    while not stop_event.is_set():
        if GPIO.input(BUTTON_PIN) == GPIO.LOW:
            print("Button pressed! Launching configuration menu...")
            time.sleep(0.3)  # debounce delay
            # Wait for release of the button
            while GPIO.input(BUTTON_PIN) == GPIO.LOW and not stop_event.is_set():
                time.sleep(0.1)
            # Run configuration menu in a separate thread
            config_thread = threading.Thread(target=run_config_menu_thread, args=(config, stop_event))
            config_thread.daemon = True  # Allow the main thread to exit even if this thread is running
            config_thread.start()
            print("Configuration menu thread started.  Data collection continues in the background.")
        time.sleep(0.2)

def run_config_menu_thread(current_config, stop_event):
    """Runs the configuration menu and handles updating the main configuration."""
    global config, initialized_mpu_sensors, initialized_ds18b20_sensors, initialized_current_data, threads
    # Create a deep copy of the current configuration
    temp_config = copy.deepcopy(current_config)
    # Run the configuration menu
    should_start = run_config_menu(temp_config) # Модифицируем временную копию
    if should_start:
        print("Configuration finalized. Applying new configuration...")
        # Stop existing threads
        stop_threads()
        # Update the main configuration with the changes
        config.clear()
        config.update(temp_config)
        # Не сохраняем еще раз, т.к. уже сохранили в run_config_menu
        # Reinitialize sensors and threads
        initialize_sensors_and_threads()
    else:
        print("Configuration menu exited without saving.")


def initialize_sensors_and_threads():
    """Initializes sensors and starts sensor processing threads based on current config."""
    global config, latest_vibration_data, latest_temperature_data, latest_current_data
    global initialized_mpu_sensors, initialized_ds18b20_sensors, initialized_current_data, threads
    global mqtt_client, led_indicator

    # --- 4. Pre-populate shared data with initial error states ---
    print("\n--- Pre-populating sensor states... ---\n")
    pre_populate_error_states(config, latest_vibration_data, latest_temperature_data, latest_current_data)

    # --- 5. Initialize Sensors based on final configuration ---
    print("\n--- Initializing sensors... ---\n")
    mpu_configs = config.get('sensors', {}).get('mpu6050', [])
    initialized_mpu_sensors = initialize_mpu_sensors(
        mpu_configs, latest_vibration_data, calibrate_flag=config.get('calibration', {}).get('mpu', True)
    )

    ds_configs = config.get('sensors', {}).get('ds18b20', [])
    initialized_ds18b20_sensors = initialize_ds18b20_sensors(
        ds_configs, latest_temperature_data
    )

    current_cfg = config.get('sensors', {}).get('current', {})
    initialized_current_data = initialize_current_sensors(
        current_cfg, latest_current_data, calibrate_flag=config.get('calibration', {}).get('current', True)
    )  # Returns a dict or None

    # --- Reconnect MQTT client if needed ---
    if mqtt_client:
        # Если клиент был отключен, переподключаем его
        if not is_mqtt_connected():
            device_id = config.get('device_id', 'unknown_device')
            mqtt_broker = config.get('mqtt', {}).get('broker', '127.0.0.1')
            mqtt_port = config.get('mqtt', {}).get('port', 1883)
            connect_mqtt(mqtt_client, mqtt_broker, mqtt_port, device_id, stop_event, led_indicator)
            print("MQTT client reconnected.")

    # --- 6. Start Sensor Reading and Processing Threads ---
    print("\n--- Starting sensor processing threads... ---\n")
    threads.clear()

    # MPU Processing and Publishing Thread
    # This thread now handles MPU reading, RMS calculation, data aggregation, and MQTT publishing.
    if initialized_mpu_sensors or \
            initialized_ds18b20_sensors or \
            (initialized_current_data and initialized_current_data.get('channel_analogin_map')):
        # Start this thread if any sensor type is available for publishing
        mpu_thread = threading.Thread(
            target=mpu_processing_and_publish_loop,
            args=(
                initialized_mpu_sensors,  # Dict of initialized MPU objects
                config,
                mqtt_client,
                stop_event,
                latest_vibration_data,  # To store RMS values
                latest_temperature_data,  # To read for publishing
                latest_current_data,  # To read for publishing
                is_mqtt_connected,  # Function to check MQTT status
                led_indicator
            ),
            daemon=True  # Daemon threads exit when main program exits
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
        pass  # print("No DS18B20 sensors initialized, temperature thread not started.")

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
        pass  # print("Current sensors not initialized/configured, current thread not started.")

    # MQTT Watchdog Thread
    watchdog_thread = threading.Thread(
        target=mqtt_watchdog_loop,
        args=(mqtt_client, config, stop_event, is_mqtt_connected),
        daemon=True
    )
    threads.append(watchdog_thread)
    watchdog_thread.start()
    print("MQTT Watchdog thread started.")

    print("\n>>> Configuration applied successfully. Data collection is running... <<<\n")


def stop_threads():
    """Stops all sensor processing threads."""
    global stop_event, threads
    print("Stopping sensor processing threads...")
    stop_event.set()
    for thread in threads:
        thread.join()
    threads.clear()
    stop_event.clear()
    print("All sensor processing threads stopped.")


def main():
    """Main function to load config, run menu, initialize sensors, and start threads."""
    global config, latest_vibration_data, latest_temperature_data, latest_current_data
    global initialized_mpu_sensors, initialized_ds18b20_sensors, initialized_current_data, threads
    global mqtt_client, led_indicator

    args = parse_arguments()
    init_db()

    # --- 1. Load configuration ---
    config.update(load_config(args.config)) # Load into global config dict

    # --- Determine calibration flags ---
    mpu_calibrate_flag = args.calibrate
    if mpu_calibrate_flag is None:  # Not set by command line
        mpu_calibrate_flag = config.get('calibration', {}).get('mpu', True)

    current_calibrate_flag = args.calibrate
    if current_calibrate_flag is None:  # Not set by command line
        current_calibrate_flag = config.get('calibration', {}).get('current', True)

    # --- 2. Create and Connect to MQTT broker ---
    device_id = config.get('device_id', 'unknown_device')
    mqtt_broker = config.get('mqtt', {}).get('broker', '127.0.0.1')
    mqtt_port = config.get('mqtt', {}).get('port', 1883)

    if LEDS_AVAILABLE:
        led_indicator = LEDIndicator(green_pin=5, blue_pin=6, yellow_pin=13, red_pin=19, white_pin=26)
    else:
        led_indicator = None

    mqtt_client = create_mqtt_client(client_id=device_id)
    connect_mqtt(mqtt_client, mqtt_broker, mqtt_port, device_id, stop_event, led_indicator)

    monitor_thread = threading.Thread(target=monitor_mqtt_connection, args=(mqtt_client, stop_event, led_indicator))
    monitor_thread.daemon = True
    monitor_thread.start()

    # --- 3. Set up signal handling for clean exit ---
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Handle kill signal

    # --- Start Button Monitor Thread ---
    button_thread = threading.Thread(target=button_monitor, args=(config, stop_event), daemon=True)
    button_thread.start()
    print("Button monitor thread started.")

    # --- Initial Sensor and Thread Setup ---
    initialize_sensors_and_threads()

    # --- MQTT Watchdog Thread ---
    watchdog_thread = threading.Thread(
        target=mqtt_watchdog_loop,
        args=(mqtt_client, config, stop_event, is_mqtt_connected),
        daemon=True
    )
    threads.append(watchdog_thread)
    watchdog_thread.start()
    print("MQTT Watchdog thread started.")

    print("\nApplication running. Press Ctrl+C to stop.")

    # --- 8. Keep the main thread alive until stop_event is set ---
    try:
        while not stop_event.is_set():
            stop_event.wait(1) # Wait indefinitely until stop_event is set

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
