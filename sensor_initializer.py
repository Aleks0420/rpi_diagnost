# sensor_initializer.py
# -*- coding: utf-8 -*-

import traceback
import sys
import board # Import board if needed for I2C initialization (depends on current_sensors.py)

# --- Sensor Modules (Import with try-except) ---
try:
    from sensors.mpu6050 import MPU6050
    print("MPU6050 module loaded.")
except ImportError:
    MPU6050 = None
    print("MPU6050 module not found. Vibration data features will be limited.")

try:
    from sensors.ds18b20 import DS18B20
    print("DS18B20 module loaded.")
except ImportError:
    DS18B20 = None
    print("DS18B20 module not found. Temperature data features will be limited.")

try:
    from sensors.current_sensors import init_adc, calibrate_current_sensors, measure_all_currents, AnalogIn
    print("current_sensors module and its components loaded.")
    CURRENT_SENSORS_AVAILABLE = True
except ImportError:
    init_adc = None
    calibrate_current_sensors = None
    measure_all_currents = None
    AnalogIn = None
    CURRENT_SENSORS_AVAILABLE = False
    print("current_sensors module/functions not found. Current data features will be limited.")


def initialize_mpu_sensors(mpu_config_list, latest_vibration_data_ref, calibrate_flag=None):
    """
    Initializes MPU6050 sensors.
    Updates latest_vibration_data_ref with specific errors or removes error on success.
    :param mpu_config_list: List of MPU sensor configurations.
    :param latest_vibration_data_ref: Reference to the shared vibration data dictionary.
    :param calibrate_flag: None (auto), True (force), False (skip).
    :return: Dictionary of {name: MPU6050_object}.
    """
    initialized_sensors = {}
    if not MPU6050:
        # Error already set in main based on module availability
        return initialized_sensors

    if not mpu_config_list:
        # Error already set in main if configured but list is empty (unlikely)
        # or "not_configured" if mpu_configs was empty in main.
        return initialized_sensors

    for sensor_cfg in mpu_config_list:
        name = sensor_cfg.get('name', 'unknown_mpu')
        address_str = sensor_cfg.get('address')
        bus = sensor_cfg.get('bus', 1)

        # Get MPU specific params from config, with defaults
        # These defaults should ideally match the MPU6050 class constructor defaults
        # if you want to allow omitting them in config.json
        sample_rate = float(sensor_cfg.get('sample_rate_hz', 100.0))
        buffer_size_cfg = int(sensor_cfg.get('buffer_size', 100))

        if not name or not address_str:
            # ... (обработка ошибок конфигурации) ...
            continue

        try:
            address = int(address_str, 0)
            print(f"Initializing MPU6050 '{name}' at bus {bus}, address 0x{address:02x} "
                  f"with SR={sample_rate}Hz, Buffer={buffer_size_cfg}...")

            # Pass configured sample_rate and buffer_size to constructor
            sensor = MPU6050(bus=bus, address=address,
                             sample_rate_hz=sample_rate, buffer_size=buffer_size_cfg)

            if calibrate_flag is not False:  # calibrate_flag can be None (use default), True, or False
                print(f"Calibrating MPU6050 '{name}'...")
                sensor.calibrate(samples=200)  # You can make 'samples' configurable too
            else:
                print(f"Skipping calibration for MPU6050 '{name}'.")

            print(f"MPU6050 '{name}' initialized successfully.")
            initialized_sensors[name] = sensor

            # If initialization successful, remove any pre-set error for this sensor
            if name in latest_vibration_data_ref and isinstance(latest_vibration_data_ref[name], dict) and "error" in latest_vibration_data_ref[name]:
                del latest_vibration_data_ref[name]
            # Or ensure it's an empty dict if we want to populate it later
            # latest_vibration_data_ref[name] = {} # For RMS, it will be name_rms

        except Exception as e:
            print(f"Error initializing MPU6050 '{name}' at bus {bus}, address 0x{address:02x}: {e}")
            traceback.print_exc()
            latest_vibration_data_ref[name] = {"error": "initialization_failed", "details": str(e)}
            if led_indicator:
                led_indicator.set_red(True)  # permanent red, critical error


    return initialized_sensors


def initialize_ds18b20_sensors(ds_config_list, latest_temperature_data_ref):
    """
    Initializes DS18B20 sensors.
    Updates latest_temperature_data_ref with specific errors or removes error on success.
    :param ds_config_list: List of DS18B20 sensor configurations.
    :param latest_temperature_data_ref: Reference to the shared temperature data dictionary.
    :return: Dictionary of {name: DS18B20_object}.
    """
    initialized_sensors = {}
    if not DS18B20:
        return initialized_sensors

    if not ds_config_list:
        return initialized_sensors

    for sensor_cfg in ds_config_list:
        name = sensor_cfg.get('name', 'unknown_ds18b20')
        sensor_id = sensor_cfg.get('id')

        if not name or not sensor_id:
            print(f"DS18B20 config missing name or id: {sensor_cfg}, skipping.")
            if name:
                latest_temperature_data_ref[name] = {"error": "config_incomplete", "details": "Missing name or ID"}
            continue

        try:
            print(f"Initializing DS18B20 '{name}' ({sensor_id})...")
            sensor = DS18B20(sensor_id=sensor_id)
            # Optional: Test read, but can be slow. Assume constructor success implies basic functionality.
            # temp = sensor.get_temperature()
            print(f"DS18B20 '{name}' initialized successfully.")
            initialized_sensors[name] = sensor

            if name in latest_temperature_data_ref and isinstance(latest_temperature_data_ref[name], dict) and "error" in latest_temperature_data_ref[name]:
                del latest_temperature_data_ref[name]
            # Or set to a placeholder if needed, e.g., for when first read occurs
            # latest_temperature_data_ref[name] = None # Will be updated by temp thread

        except Exception as e:
            print(f"Error initializing DS18B20 '{name}' ({sensor_id}): {e}")
            traceback.print_exc()
            latest_temperature_data_ref[name] = {"error": "initialization_failed", "details": str(e)}

    return initialized_sensors


def initialize_current_sensors(current_config_data, latest_current_data_ref, calibrate_flag=None):
    """
    Initializes current sensors (ADC, calibration, individual offsets/scales).
    Updates latest_current_data_ref with errors or removes errors on success.
    Returns a dictionary with initialized ADC instance, channel_analogin_map, channel_offset_map, channel_scale_map.
    Updates config (current_config_data['channels']) with new offsets after calibration.
    """
    initialized_cs_data = {
        'adc_instance': None,
        'channel_analogin_map': {},
        'channel_offset_map': {},
        'channel_scale_map': {}
    }

    if not CURRENT_SENSORS_AVAILABLE:
        return None

    adc_cfg = current_config_data.get('adc')
    channels_cfg = current_config_data.get('channels')  # List of dicts

    if not adc_cfg:
        print("Current sensor ADC configuration missing.")
        return None
    if not channels_cfg:
        print("Current sensor channel configurations missing.")
        return None

    try:
        print("Initializing ADC for current sensors...")
        adc_instance = init_adc(adc_cfg)
        if not adc_instance:
            raise Exception("ADC initialization via init_adc() failed.")
        initialized_cs_data['adc_instance'] = adc_instance
        print("ADC initialized successfully.")

        # --- Prepare channel maps and calibration lists ---
        channel_analogin_map_temp = {}
        channel_offset_map_temp = {}
        channel_scale_map_temp = {}
        channels_to_calibrate_list = []
        channel_name_order = []

        for channel_cfg in channels_cfg:
            name = channel_cfg.get('name')
            adc_channel_index = channel_cfg.get('adc_channel')
            offset = channel_cfg.get('offset', 0.0)
            scale = channel_cfg.get('scale', 1.0)

            if not name or adc_channel_index is None:
                print(f"Current channel config missing name or adc_channel: {channel_cfg}, skipping.")
                if name:
                    latest_current_data_ref[name] = {"error": "config_incomplete", "details": "Missing name or adc_channel"}
                continue

            if not isinstance(adc_channel_index, int) or not (0 <= adc_channel_index <= 3):
                print(f"Invalid ADC channel index {adc_channel_index} for channel '{name}'. Must be 0-3. Skipping.")
                latest_current_data_ref[name] = {"error": "invalid_channel_index", "details": f"Index {adc_channel_index} out of range"}
                continue

            try:
                analog_in_obj = AnalogIn(adc_instance, adc_channel_index)
                channel_analogin_map_temp[name] = analog_in_obj
                channel_offset_map_temp[name] = offset
                channel_scale_map_temp[name] = scale
                channels_to_calibrate_list.append(analog_in_obj)
                channel_name_order.append(name)
                if name in latest_current_data_ref and isinstance(latest_current_data_ref[name], dict) and "error" in latest_current_data_ref[name]:
                    del latest_current_data_ref[name]
                if name not in latest_current_data_ref:
                    latest_current_data_ref[name] = 0.0
            except Exception as e_analog:
                print(f"Error creating AnalogIn for channel '{name}' (ADC index {adc_channel_index}): {e_analog}")
                traceback.print_exc()
                latest_current_data_ref[name] = {"error": "analogin_creation_failed", "details": str(e_analog)}

        if not channels_to_calibrate_list:
            print("No valid current sensor channels configured or initialized to proceed with ADC.")
            if "general" not in latest_current_data_ref:
                latest_current_data_ref["general"] = {"error": "no_valid_channels_for_adc"}
            return None

        # --- Calibration ---
        if calibrate_flag is False:
            print("Calibration skipped (--no-calibrate or config). Using offset from config for all channels.")
        else:
            print("Calibrating current sensors (zero current expected)...")
            offset_voltages_list = calibrate_current_sensors(channels_to_calibrate_list)
            if not offset_voltages_list or len(offset_voltages_list) != len(channels_to_calibrate_list):
                print("Current sensor calibration failed or returned incorrect number of offsets.")
                for name in channel_name_order:
                    if name not in latest_current_data_ref or not (isinstance(latest_current_data_ref[name], dict) and "error" in latest_current_data_ref[name]):
                        latest_current_data_ref[name] = {
                            "error": "calibration_failed_group",
                            "details": "Mismatch in offset count or calibration process error"
                        }
                if "general" not in latest_current_data_ref:
                    latest_current_data_ref["general"] = {"error": "calibration_process_failed"}
                return None
            # Update offset maps and config with new offsets
            for i, name in enumerate(channel_name_order):
                channel_offset_map_temp[name] = offset_voltages_list[i]
                # Update config for this channel
                for ch_cfg in channels_cfg:
                    if ch_cfg.get('name') == name:
                        ch_cfg['offset'] = offset_voltages_list[i]

        initialized_cs_data['channel_analogin_map'] = channel_analogin_map_temp
        initialized_cs_data['channel_offset_map'] = channel_offset_map_temp
        initialized_cs_data['channel_scale_map'] = channel_scale_map_temp

        print("Current sensors initialized successfully (ADC and channels).")
        return initialized_cs_data

    except Exception as e_main:
        print(f"Critical error during current sensor initialization: {e_main}")
        traceback.print_exc()
        if "general" not in latest_current_data_ref:
            latest_current_data_ref["general"] = {"error": "initialization_failed_critical", "details": str(e_main)}
        if channels_cfg:
            for channel_cfg in channels_cfg:
                name = channel_cfg.get('name')
                if name and (name not in latest_current_data_ref or not (isinstance(latest_current_data_ref[name], dict) and "error" in latest_current_data_ref[name])):
                    latest_current_data_ref[name] = {"error": "initialization_failed_due_to_critical_error"}
        return None
