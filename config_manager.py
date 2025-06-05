# -*- coding: utf-8 -*-
import json
import os
import copy
import traceback

# --- Configuration File Path ---
CONFIG_FILE = "config.json"

# --- Default Configuration ---
def get_default_config():
    """Returns a dictionary with default configuration values."""
    return {
        "device_id": "station_1",
        "mqtt": {
            "broker": "192.168.0.93",
            "port": 1883,
            "topic": "sensors/data",
            "qos": 1
        },
        "intervals": {
            "temperature_sec": 5.0,
            "fast_sensors_sec": 0.333 # Used by MPU processing/publish loop & current sensor loop
        },
        "sensors": {
            "mpu6050": [
                # Example:
                # {"name": "engine", "address": "0x68", "bus": 1, "sample_rate_hz": 200, "buffer_size": 200},
            ],
            "mpu6050_fft": { # New section for FFT parameters
                "n_peaks": 5
            },
            "ds18b20": [
                # Example:
                # {"name": "engine_temp", "id": "28-000001111111"},
            ],
             "current": {
                "adc": {
                   "bus": 1,
                   "address": "0x48",
                   "gain": 1.0
                },
                "channels": [
                   # {"name": "phase_a", "adc_channel": 0},
                ]
             }
        },
        "calibration": {
             "mpu": True,
             "current": True
        }
    }

# --- Configuration File Handling ---
# load_config and save_config остаются без изменений, они достаточно гибки.
# merge_dicts также можно оставить без изменений, полагаясь на .get() в коде потребителя.

def load_config(filepath=CONFIG_FILE):
    """Loads configuration from a JSON file and merges with defaults."""
    default_config = get_default_config()
    config = copy.deepcopy(default_config) # Use deepcopy to avoid modifying default_config structure

    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                loaded_config = json.load(f)

            def merge_dicts(base, head):
                 for k, v in head.items():
                     if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                          merge_dicts(base[k], v)
                     # elif isinstance(v, list) and k in base and isinstance(base[k], list):
                          # Basic list merge: replace. More complex merging (element-wise) is not done here.
                          # base[k] = v
                     else:
                          base[k] = v

            merge_dicts(config, loaded_config)
            print(f"Configuration loaded from {filepath} and merged with defaults.")
            return config
        except Exception as e:
            print(f"Error loading configuration from {filepath}: {e}")
            # traceback.print_exc() # Uncomment for debugging
            print("Using default configuration due to load error.")
            return default_config
    else:
        print(f"Configuration file '{filepath}' not found. Using default configuration.")
        return default_config

def save_config(config_data, filepath=CONFIG_FILE):
    """Saves configuration to a JSON file."""
    try:
        with open(filepath, 'w') as f:
            json.dump(config_data, f, indent=4)
        print(f"Configuration saved to {filepath}")
        return True
    except Exception as e:
        print(f"Error saving configuration to {filepath}: {e}")
        # traceback.print_exc()
        return False

# --- Menu Functions ---
def display_config(config_data):
    """Prints the current configuration."""
    print("\n--- Current Configuration ---")
    print(json.dumps(config_data, indent=4)) # No need for deepcopy here if just printing
    print("-----------------------------\n")

def run_config_menu(config_data):
    """Runs the interactive configuration menu. Modifies config_data in place.
       Returns True if user chooses START, False if user chooses Exit."""
    print("\n--- Configuration Menu ---")

    while True:
        display_config(config_data)
        print("Options:")
        print("1. Set Device ID")
        # ... (options 2-6 for MQTT and Intervals remain the same) ...
        print("2. Set MQTT Broker Address")
        print("3. Set MQTT Port")
        print("4. Set MQTT Topic")
        print("5. Set Temperature Read Interval (sec)")
        print("6. Set Fast Sensors Read Interval (sec)")
        print("7. Configure MPU6050 Sensors (General)")
        print("8. Configure MPU6050 FFT Settings") # NEW
        print("9. Configure DS18B20 Sensors")
        print("10. Configure Current Sensors (ADC & Channels)")
        print("11. Configure Calibration Settings") # NEW for mpu/current calibration flags

        print("\nS. Save Configuration")
        print("L. Load Configuration (from file)")
        print("R. Restore Default Configuration")
        print("X. Exit without Saving")
        print("START. Start Data Collection")

        choice = input("Enter choice: ").strip().upper()

        # ... (Handling for choices 1-6 remains the same) ...
        if choice == '1':
            # ... (Device ID)
            new_id = input(f"Enter new Device ID (current: {config_data.get('device_id')}): ").strip()
            if new_id: config_data['device_id'] = new_id
        elif choice == '2':
            # ... (MQTT Broker)
            new_broker = input(f"Enter new MQTT Broker (current: {config_data.get('mqtt', {}).get('broker')}): ").strip()
            if new_broker: config_data.setdefault('mqtt', {})['broker'] = new_broker
        elif choice == '3':
            # ... (MQTT Port)
            try:
                new_port = int(input(f"Enter new MQTT Port (current: {config_data.get('mqtt', {}).get('port')}): ").strip())
                if 1 <= new_port <= 65535: config_data.setdefault('mqtt', {})['port'] = new_port
                else: print("Invalid port.")
            except ValueError: print("Invalid input.")
        elif choice == '4':
            # ... (MQTT Topic)
            new_topic = input(f"Enter new MQTT Topic (current: {config_data.get('mqtt', {}).get('topic')}): ").strip()
            if new_topic: config_data.setdefault('mqtt', {})['topic'] = new_topic
        elif choice == '5':
            # ... (Temp Interval)
            try:
                new_interval = float(input(f"Enter Temperature Interval (s) (current: {config_data.get('intervals', {}).get('temperature_sec')}): ").strip())
                if new_interval > 0: config_data.setdefault('intervals', {})['temperature_sec'] = new_interval
                else: print("Interval must be positive.")
            except ValueError: print("Invalid input.")
        elif choice == '6':
            # ... (Fast Interval)
            try:
                new_interval = float(input(f"Enter Fast Sensors Interval (s) (current: {config_data.get('intervals', {}).get('fast_sensors_sec')}): ").strip())
                if new_interval > 0: config_data.setdefault('intervals', {})['fast_sensors_sec'] = new_interval
                else: print("Interval must be positive.")
            except ValueError: print("Invalid input.")

        elif choice == '7': # Was MPU, now generic sensor setup
            config_data.setdefault('sensors', {}).setdefault('mpu6050', [])
            configure_mpu_sensors(config_data['sensors']['mpu6050'])

        elif choice == '8': # NEW: MPU FFT Settings
            config_data.setdefault('sensors', {}).setdefault('mpu6050_fft', get_default_config()['sensors']['mpu6050_fft'])
            configure_mpu_fft_settings(config_data['sensors']['mpu6050_fft'])

        elif choice == '9': # Was DS18B20
            config_data.setdefault('sensors', {}).setdefault('ds18b20', [])
            configure_ds18b20_sensors(config_data['sensors']['ds18b20'])

        elif choice == '10': # Was Current
            config_data.setdefault('sensors', {}).setdefault('current', get_default_config()['sensors']['current'])
            configure_current_sensors_menu(config_data['sensors']['current'])

        elif choice == '11': # NEW: Calibration Settings
            config_data.setdefault('calibration', get_default_config()['calibration'])
            configure_calibration_settings(config_data['calibration'])

        # ... (Handling for S, L, R, X, START remains the same) ...
        elif choice == 'S': save_config(config_data)
        elif choice == 'L':
            loaded = load_config(CONFIG_FILE)
            config_data.clear()
            config_data.update(loaded)
        elif choice == 'R':
            default = get_default_config()
            config_data.clear()
            config_data.update(default)
        elif choice == 'X': return False
        elif choice == 'START': return True
        else: print("Invalid choice.")


def configure_mpu_sensors(mpu_list):
    """Menu to configure MPU6050 sensors. Modifies mpu_list in place."""
    default_sr = 200.0
    default_bs = 200

    print("\n--- Configure MPU6050 Sensors ---")
    while True:
        print("\nCurrent MPU6050 Sensors:")
        if not mpu_list:
            print("  No MPU6050 sensors configured.")
        for i, sensor in enumerate(mpu_list):
            print(f"  {i+1}. Name: {sensor.get('name', 'N/A')}, "
                  f"Addr: {sensor.get('address', 'N/A')}, "
                  f"Bus: {sensor.get('bus', 'N/A')}, "
                  f"SR: {sensor.get('sample_rate_hz', 'N/A')}Hz, " # Display SR
                  f"Buffer: {sensor.get('buffer_size', 'N/A')}")   # Display Buffer Size

        print("\nOptions:")
        print("1. Add New MPU6050")
        if mpu_list:
            print("2. Edit MPU6050")
            print("3. Remove MPU6050")
        print("B. Back to main menu")

        choice = input("Enter choice: ").strip().upper()

        if choice == '1':
            name = input("Enter sensor name (e.g., engine): ").strip()
            address_str = input("Enter I2C address (e.g., 0x68): ").strip()
            bus_str = input(f"Enter I2C bus (default 1): ").strip() or "1"
            sr_str = input(f"Enter Sample Rate (Hz, default {default_sr}): ").strip() or str(default_sr)
            bs_str = input(f"Enter Buffer Size (default {default_bs}): ").strip() or str(default_bs)

            if name and address_str:
                try:
                    address = hex(int(address_str, 0))
                    bus = int(bus_str)
                    sr = float(sr_str)
                    bs = int(bs_str)
                    if sr <= 0 or bs <= 0:
                        print("Sample rate and buffer size must be positive.")
                        continue
                    mpu_list.append({"name": name, "address": address, "bus": bus,
                                     "sample_rate_hz": sr, "buffer_size": bs})
                    print("MPU6050 added.")
                except ValueError:
                    print("Invalid address, bus, sample rate, or buffer size format.")
            else:
                print("Name and address cannot be empty.")

        elif choice == '2' and mpu_list:
            try:
                idx = int(input("Enter the number of the sensor to edit: ")) - 1
                if 0 <= idx < len(mpu_list):
                    sensor = mpu_list[idx]
                    print(f"Editing sensor: {json.dumps(sensor)}")
                    new_name = input(f"New name (current: {sensor.get('name')}): ").strip()
                    new_address_str = input(f"New I2C address (current: {sensor.get('address')}): ").strip()
                    new_bus_str = input(f"New I2C bus (current: {sensor.get('bus')}): ").strip()
                    new_sr_str = input(f"New Sample Rate (Hz) (current: {sensor.get('sample_rate_hz', default_sr)}): ").strip()
                    new_bs_str = input(f"New Buffer Size (current: {sensor.get('buffer_size', default_bs)}): ").strip()

                    if new_name: sensor['name'] = new_name
                    if new_address_str:
                         try: sensor['address'] = hex(int(new_address_str, 0))
                         except ValueError: print("Invalid address format. Not updated.")
                    if new_bus_str:
                         try: sensor['bus'] = int(new_bus_str)
                         except ValueError: print("Invalid bus format. Not updated.")
                    if new_sr_str:
                         try:
                             sr = float(new_sr_str)
                             if sr > 0: sensor['sample_rate_hz'] = sr
                             else: print("Sample rate must be positive. Not updated.")
                         except ValueError: print("Invalid sample rate format. Not updated.")
                    if new_bs_str:
                         try:
                             bs = int(new_bs_str)
                             if bs > 0: sensor['buffer_size'] = bs
                             else: print("Buffer size must be positive. Not updated.")
                         except ValueError: print("Invalid buffer size format. Not updated.")
                    print("MPU6050 updated.")
                else: print("Invalid sensor number.")
            except ValueError: print("Invalid input.")

        # ... (Remove MPU and Back options remain the same) ...
        elif choice == '3' and mpu_list:
            # ... (logic to remove sensor) ...
            try:
                idx = int(input("Enter sensor number to remove: ")) - 1
                if 0 <= idx < len(mpu_list): mpu_list.pop(idx); print("Sensor removed.")
                else: print("Invalid number.")
            except ValueError: print("Invalid input.")
        elif choice == 'B': break
        else: print("Invalid choice.")

# NEW Sub-menu for MPU FFT settings
def configure_mpu_fft_settings(fft_config_data):
    """Menu to configure MPU6050 FFT settings. Modifies fft_config_data in place."""
    print("\n--- Configure MPU6050 FFT Settings ---")
    default_n_peaks = 5 # Fallback default

    while True:
        current_n_peaks = fft_config_data.get('n_peaks', default_n_peaks)
        print(f"\nCurrent FFT Settings:")
        print(f"  Number of FFT peaks to report: {current_n_peaks}")

        print("\nOptions:")
        print("1. Set Number of FFT Peaks")
        print("B. Back to main menu")

        choice = input("Enter choice: ").strip().upper()

        if choice == '1':
            try:
                new_n_peaks_str = input(f"Enter number of FFT peaks (current: {current_n_peaks}, e.g., 3, 5, 10): ").strip()
                if new_n_peaks_str: # Only update if user provided input
                    new_n_peaks = int(new_n_peaks_str)
                    if new_n_peaks >= 0: # 0 might mean disable FFT peaks reporting, or handle as error
                        fft_config_data['n_peaks'] = new_n_peaks
                        print(f"Number of FFT peaks updated to {new_n_peaks}.")
                    else:
                        print("Number of peaks must be non-negative.")
                else:
                    print("No change made to number of FFT peaks.")
            except ValueError:
                print("Invalid input. Please enter a number.")
        elif choice == 'B':
            break
        else:
            print("Invalid choice.")

# NEW Sub-menu for Calibration settings
def configure_calibration_settings(calib_config_data):
    """Menu to configure calibration settings. Modifies calib_config_data in place."""
    print("\n--- Configure Calibration Settings ---")
    default_calib_mpu = True
    default_calib_current = True

    while True:
        calib_mpu = calib_config_data.get('mpu', default_calib_mpu)
        calib_current = calib_config_data.get('current', default_calib_current)

        print(f"\nCurrent Calibration Settings:")
        print(f"  Calibrate MPU6050 on start: {'Yes' if calib_mpu else 'No'}")
        print(f"  Calibrate Current Sensors on start: {'Yes' if calib_current else 'No'}")

        print("\nOptions:")
        print("1. Toggle MPU6050 Calibration (on/off)")
        print("2. Toggle Current Sensor Calibration (on/off)")
        print("B. Back to main menu")

        choice = input("Enter choice: ").strip().upper()

        if choice == '1':
            calib_config_data['mpu'] = not calib_mpu # Toggle
            print(f"MPU6050 calibration on start set to: {'Yes' if calib_config_data['mpu'] else 'No'}")
        elif choice == '2':
            calib_config_data['current'] = not calib_current # Toggle
            print(f"Current sensor calibration on start set to: {'Yes' if calib_config_data['current'] else 'No'}")
        elif choice == 'B':
            break
        else:
            print("Invalid choice.")

# --- configure_ds18b20_sensors and configure_current_sensors_menu ---
# Эти функции остаются без изменений, так как параметры DS18B20 и Current не менялись
# ... (вставьте сюда ваши существующие configure_ds18b20_sensors и configure_current_sensors_menu) ...
def configure_ds18b20_sensors(ds_list):
    """Menu to configure DS18B20 sensors. Modifies ds_list in place."""
    print("\n--- Configure DS18B20 Sensors ---")
    while True:
        print("\nCurrent DS18B20 Sensors:")
        if not ds_list: print("  No DS18B20 sensors configured.")
        for i, sensor in enumerate(ds_list): print(f"  {i+1}. Name: {sensor.get('name', 'N/A')}, ID: {sensor.get('id', 'N/A')}")
        print("\nOptions:\n1. Add New DS18B20")
        if ds_list: print("2. Edit DS18B20\n3. Remove DS18B20")
        print("B. Back to main menu")
        choice = input("Enter choice: ").strip().upper()
        if choice == '1':
            name = input("Sensor name: ").strip()
            sensor_id = input("Sensor ID (e.g., 28-xxxxxxxxxxxx): ").strip()
            if name and sensor_id: ds_list.append({"name": name, "id": sensor_id}); print("DS18B20 added.")
            else: print("Name and ID required.")
        elif choice == '2' and ds_list:
             try:
                idx = int(input("Sensor number to edit: ")) - 1
                if 0 <= idx < len(ds_list):
                    sensor = ds_list[idx]
                    new_name = input(f"New name (current: {sensor.get('name')}): ").strip() or sensor.get('name')
                    new_id = input(f"New ID (current: {sensor.get('id')}): ").strip() or sensor.get('id')
                    sensor['name'], sensor['id'] = new_name, new_id
                    print("DS18B20 updated.")
                else: print("Invalid sensor number.")
             except ValueError: print("Invalid input.")
        elif choice == '3' and ds_list:
            try:
                idx = int(input("Sensor number to remove: ")) - 1
                if 0 <= idx < len(ds_list): ds_list.pop(idx); print("Sensor removed.")
                else: print("Invalid number.")
            except ValueError: print("Invalid input.")
        elif choice == 'B': break
        else: print("Invalid choice.")


def configure_current_channel_offsets(current_config_data):
    """
    Menu to view/edit offsets and scales for each current channel.
    """
    channels = current_config_data.get('channels', [])
    while True:
        print("\nCurrent channel offsets and scales:")
        for idx, ch in enumerate(channels):
            print(f"{idx+1}. {ch.get('name')}: offset={ch.get('offset', 0.0):.4f}, scale={ch.get('scale', 1.0):.3f}")
        print("\nOptions:")
        print("1. Edit offset/scale for a channel")
        print("2. Set all offsets to zero")
        print("3. Run auto-calibration (no load, updates all offsets)")
        print("4. Manual calibration - adjust scale using real current measurement")  # NEW option
        print("B. Back to previous menu")
        choice = input("Enter choice: ").strip().upper()
        if choice == '1':
            # (Existing code for editing individual channel offset/scale)
            try:
                idx = int(input("Channel number: ")) - 1
                if 0 <= idx < len(channels):
                    ch = channels[idx]
                    new_offset = input(f"New offset for {ch['name']} (current {ch.get('offset', 0.0)}): ").strip()
                    new_scale = input(f"New scale for {ch['name']} (current {ch.get('scale', 1.0)}): ").strip()
                    if new_offset:
                        try:
                            ch['offset'] = float(new_offset)
                        except ValueError:
                            print("Invalid offset")
                    if new_scale:
                        try:
                            ch['scale'] = float(new_scale)
                        except ValueError:
                            print("Invalid scale")
                else:
                    print("Invalid channel number.")
            except Exception:
                print("Invalid channel number.")
        elif choice == '2':
            for ch in channels:
                ch['offset'] = 0.0
            print("All offsets set to zero.")
        elif choice == '3':
            print("Starting auto-calibration (make sure all sensors are at zero current)...")
            try:
                from sensor_initializer import initialize_current_sensors
                from current_sensors import calibrate_current_sensors, AnalogIn, init_adc
                fake_data_ref = {}
                result = initialize_current_sensors(current_config_data, fake_data_ref, calibrate_flag=True)
                if result:
                    offset_map = result['channel_offset_map']
                    for ch in channels:
                        if ch['name'] in offset_map:
                            ch['offset'] = offset_map[ch['name']]
                    print("Auto-calibration complete. Offsets updated.")
                else:
                    print("Calibration failed! Offsets not changed.")
            except Exception as e:
                print(f"Calibration error: {e}")
        elif choice == '4':
            # NEW: Manual calibration for scale adjustment
            manual_calibrate_current_channels(current_config_data)
        elif choice == 'B':
            break
        else:
            print("Invalid choice.")



def manual_calibrate_current_channels(current_config_data):
    """
    Manual calibration for current sensors.
    For each channel, prompts the user to input the sensor reading (current reported by the system)
    and the actual measured current (from a multimeter). Then, calculates and updates the scale factor.
    """
    channels = current_config_data.get('channels', [])
    if not channels:
        print("No current sensor channels configured.")
        return

    print("\n--- Manual Calibration for Current Sensors ---")
    print("For each channel, please input the sensor reading and the actual measured current in Amps.")
    print("The new scale will be computed as: new_scale = (measured_actual_current / sensor_reading) * old_scale")
    for idx, ch in enumerate(channels):
        name = ch.get('name', f"Channel_{idx+1}")
        old_scale = ch.get('scale', 1.0)
        try:
            sensor_reading_str = input(f"\nEnter the sensor reading for '{name}' (value reported by system): ").strip()
            sensor_reading = float(sensor_reading_str)
        except ValueError:
            print("Invalid sensor reading. Skipping this channel.")
            continue

        try:
            measured_str = input(f"Enter the actual measured current for '{name}' (in Amps, measured by multimeter): ").strip()
            measured_current = float(measured_str)
        except ValueError:
            print("Invalid measured current value. Skipping this channel.")
            continue

        if sensor_reading == 0:
            print("Sensor reading is zero, cannot compute scale factor. Skipping this channel.")
            continue

        # Calculate new scale factor. The idea is to adjust the scale so that:
        #    sensor_reading * new_scale = measured_current
        # Hence, new_scale = (measured_current / sensor_reading) * old_scale
        new_scale = (measured_current / sensor_reading) * old_scale
        print(f"Channel '{name}': old scale = {old_scale:.3f}, new scale = {new_scale:.3f}")
        ch['scale'] = new_scale

    print("Manual calibration complete. New scale factors have been updated in configuration.")


def configure_current_sensors_menu(current_config_data):
    """Menu to configure Current sensors (ADC and Channels). Modifies current_config_data in place."""
    print("\n--- Configure Current Sensors ---")
    default_adc = get_default_config()['sensors']['current']['adc']
    default_channels = [] # No default channels, user must add

    while True:
        adc_cfg = current_config_data.get('adc', default_adc)
        channels_list = current_config_data.get('channels', default_channels)
        print(f"\n  ADC: Bus={adc_cfg.get('bus')}, Address={adc_cfg.get('address')}, Gain={adc_cfg.get('gain')}")
        print("  Channels:")
        if not channels_list: print("    No channels configured.")
        for i, ch in enumerate(channels_list): print(f"    {i+1}. Name: {ch.get('name')}, ADC Idx: {ch.get('adc_channel')}")
        print("\nOptions:\n1. Set ADC\n2. Add/Edit Channel")
        if channels_list: print("3. Remove Channel")
        print("4. Channel Offsets/Scales Advanced")
        print("B. Back to main menu")
        choice = input("Enter choice: ").strip().upper()

        if choice == '1':
            if 'adc' not in current_config_data: current_config_data['adc'] = copy.deepcopy(default_adc)
            try:
                bus = input(f"I2C Bus (current {adc_cfg.get('bus')}): ").strip()
                addr = input(f"I2C Address (current {adc_cfg.get('address')}): ").strip()
                gain = input(f"Gain (current {adc_cfg.get('gain')}): ").strip()
                if bus: current_config_data['adc']['bus'] = int(bus)
                if addr: current_config_data['adc']['address'] = hex(int(addr, 0))
                if gain: current_config_data['adc']['gain'] = float(gain)
                print("ADC config updated.")
            except ValueError: print("Invalid input for ADC config.")
        elif choice == '2':
            if 'channels' not in current_config_data: current_config_data['channels'] = []
            name = input("Channel name (e.g., phase_a): ").strip()
            adc_idx_str = input("ADC channel index (0-3): ").strip()
            if name and adc_idx_str:
                try:
                    adc_idx = int(adc_idx_str)
                    if not (0 <= adc_idx <= 3) : print("ADC index out of range."); continue
                    found_channel = next((ch for ch in current_config_data['channels'] if ch.get('name') == name), None)
                    if found_channel: found_channel['adc_channel'] = adc_idx; print(f"Channel '{name}' updated.")
                    else: current_config_data['channels'].append({"name": name, "adc_channel": adc_idx}); print(f"Channel '{name}' added.")
                except ValueError: print("Invalid ADC index.")
            else: print("Name and ADC index required.")
        elif choice == '3' and channels_list:
            try:
                idx = int(input("Channel number to remove: ")) - 1
                if 0 <= idx < len(channels_list): current_config_data['channels'].pop(idx); print("Channel removed.")
                else: print("Invalid number.")
            except ValueError: print("Invalid input.")
        elif choice == '4':
            configure_current_channel_offsets(current_config_data)
        elif choice == 'B': break
        else: print("Invalid choice.")

# Example of how this module might be used
if __name__ == "__main__":
    current_config = load_config()
    should_start = run_config_menu(current_config)
    if should_start:
        print("\nConfiguration finalized. Starting data collection logic (simulated).")
        display_config(current_config)
    else:
        print("\nConfiguration menu exited.")
