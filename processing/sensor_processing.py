# sensor_processing.py
# -*- coding: utf-8 -*-

import threading
import time
import json
import copy
import traceback

# from mqtt_buffer import append_to_buffer, read_and_clear_buffer
from mqtt_buffer_sqlite import buffer_message, flush_if_connected

# Assuming these are imported in sensor_initializer and passed if needed,
# or imported here if directly used.
# For measure_all_currents, it's cleaner to import it here if this module handles current reading.
try:
    from sensors.current_sensors import measure_all_currents
    CURRENT_SENSORS_MEASUREMENT_AVAILABLE = True
except ImportError:
    measure_all_currents = None
    CURRENT_SENSORS_MEASUREMENT_AVAILABLE = False
    print("Warning: 'measure_all_currents' not found in sensor_processing.py. Current reading will fail if attempted.")

EARTBEAT_TIMEOUT = 30


def mpu_processing_and_publish_loop(
        mpu_sensors,  # dict of {name: MPU6050_object}
        config,
        mqtt_client,
        stop_event,
        latest_vibration_data_ref,  # Shared dict to store/reflect MPU states and metrics
        latest_temperature_data_ref,
        latest_current_data_ref,
        is_mqtt_connected_func,
        led_indicator=None
):
    print("MPU processing and publishing thread started.")

    device_id = config.get('device_id', 'unknown_device')
    mqtt_topic = config.get('mqtt', {}).get('topic', 'sensors/data')
    mqtt_qos = config.get('mqtt', {}).get('qos', 1)

    # Interval for computing metrics and publishing
    publish_interval_sec = config.get('intervals', {}).get('fast_sensors_sec', 0.333)

    # Number of FFT peaks from config
    fft_config = config.get('sensors', {}).get('mpu6050_fft', {})
    n_fft_peaks_to_report = fft_config.get('n_peaks', 5)  # Default if not in config

    # Interval for calling sensor.update_buffer()
    update_call_interval_sec = 0.004  # ~4ms (250Hz call rate for update_buffer)

    # Heartbeat monitoring
    HEARTBEAT_TIMEOUT = 30  # seconds without data = connection lost
    last_data_time = time.time()
    last_publish_time = time.time()

    if not mpu_sensors:
        print("No MPU sensors configured or initialized. MPU processing loop will not run effectively.")

    while not stop_event.is_set():
        loop_start_time = time.time()

        # --- High-frequency MPU buffer update ---
        if mpu_sensors:  # Only if there are MPU sensors
            for name, sensor in mpu_sensors.items():
                try:
                    sensor.update_buffer()  # Updates internal buffer of the MPU object
                except Exception as e:
                    error_msg = f"Buffer update error for MPU '{name}': {e}"
                    print(error_msg)
                    if name in latest_vibration_data_ref and isinstance(latest_vibration_data_ref[name], dict):
                        if latest_vibration_data_ref[name].get("error") != "buffer_update_failed":
                            latest_vibration_data_ref[name] = {"error": "buffer_update_failed", "details": str(e)}
                    else:
                        latest_vibration_data_ref[name] = {"error": "buffer_update_failed", "details": str(e)}

        # --- Check if it's time to compute metrics and publish ---
        current_time = time.time()
        if (current_time - last_publish_time) >= publish_interval_sec:
            # --- VIBRATION Metrics ---
            vibration_mqtt_payload = {}
            if mpu_sensors:
                for mpu_cfg_item in config.get('sensors', {}).get('mpu6050', []):
                    mpu_name_from_config = mpu_cfg_item.get('name')
                    if mpu_name_from_config in mpu_sensors:
                        try:
                            metrics = mpu_sensors[mpu_name_from_config].get_vibration_metrics(
                                n_fft_peaks=n_fft_peaks_to_report)
                            vibration_mqtt_payload[mpu_name_from_config] = metrics
                        except Exception as e:
                            error_msg = f"Metrics computation error for MPU '{mpu_name_from_config}': {e}"
                            print(error_msg)
                            vibration_mqtt_payload[mpu_name_from_config] = {
                                "error": "metrics_failed",
                                "details": str(e)
                            }

            # Include general vibration error if it exists
            if "general" in latest_vibration_data_ref:
                vibration_mqtt_payload["general"] = latest_vibration_data_ref["general"]

            # --- Prepare final MQTT payload ---
            payload = {
                "device_id": device_id,
                "timestamp": current_time,
                "vibration": copy.deepcopy(vibration_mqtt_payload),
                "temperature": copy.deepcopy(latest_temperature_data_ref),
                "current": copy.deepcopy(latest_current_data_ref)
            }

            # --- Publish Data ---
            try:
                if is_mqtt_connected_func():
                    # First flush any buffered messages
                    flush_if_connected(mqtt_client, mqtt_topic, mqtt_qos, is_mqtt_connected_func)

                    # Publish current data
                    mqtt_client.publish(mqtt_topic, json.dumps(payload), qos=mqtt_qos)

                    # Update last data time and indicate success
                    last_data_time = current_time
                    if led_indicator:
                        led_indicator.data_sent_success()  # Short yellow flash
                else:
                    # Save to buffer and indicate failure
                    buffer_message(payload)
                    if led_indicator:
                        led_indicator.data_sent_failed()  # Short red flash
            except Exception as e_pub:
                print(f"Error sending MQTT, save to buffer: {e_pub}")
                buffer_message(payload)
                if led_indicator:
                    led_indicator.data_sent_failed()

            last_publish_time = loop_start_time

        # --- Heartbeat Monitoring ---
        if current_time - last_data_time > HEARTBEAT_TIMEOUT:
            if led_indicator:
                led_indicator.start_heartbeat_timeout()  # Solid yellow for timeout
        else:
            if led_indicator:
                led_indicator.stop_heartbeat_timeout()

        # --- Sleep to control update rate ---
        elapsed_since_loop_start = time.time() - loop_start_time
        sleep_duration = update_call_interval_sec - elapsed_since_loop_start
        if sleep_duration > 0:
            stop_event.wait(sleep_duration)

    print("MPU processing and publishing thread stopped.")


def mqtt_watchdog_loop(mqtt_client, config, stop_event, is_connected_func):
    """Periodically checks the connection and sends the buffer."""
    print("MQTT Watchdog thread started.")
    mqtt_topic = config.get("mqtt", {}).get("topic", "sensors/data")
    mqtt_qos = config.get("mqtt", {}).get("qos", 1)
    interval = 10  # second

    while not stop_event.is_set():
        try:
            flush_if_connected(mqtt_client, mqtt_topic, mqtt_qos, is_connected_func)
        except Exception as e:
            print(f"Watchdog error: {e}")
        stop_event.wait(interval)

    print("MQTT Watchdog thread stopped.")


def temperature_thread_loop(temp_sensors_dict, config, stop_event, latest_temperature_data_ref, led_indicator=None):
    """
    Thread function to read temperature sensors periodically and update shared data.
    """
    print("Temperature thread started.")
    # Get the set of all configured temperature sensor names from config
    configured_names = {cfg.get('name') for cfg in config.get('sensors', {}).get('ds18b20', []) if cfg.get('name')}
    read_interval = config.get('intervals', {}).get('temperature_sec', 5.0)

    while not stop_event.is_set():
        start_time = time.time()
        current_reads_this_cycle = {} # Store reads for this cycle

        # Read from successfully initialized sensors
        for name, sensor in temp_sensors_dict.items():
            try:
                temp = sensor.get_temperature() # DS18B20 class method
                # Round if it's a float, else keep as is (e.g. if it returns error dict)
                current_reads_this_cycle[name] = round(temp, 3) if isinstance(temp, float) else temp
            except Exception as e:
                print(f"Temperature read error for '{name}': {e}")
                current_reads_this_cycle[name] = {"error": "read_failed", "details": str(e)}
                if led_indicator:
                    # Indicate sensor read failure, maybe blink yellow and red
                    led_indicator.set_yellow(True)
                    time.sleep(0.05)
                    led_indicator.set_yellow(False)
                    led_indicator.set_red(True)
                    time.sleep(0.05)
                    led_indicator.set_red(False)

        # Update shared data for *all* configured sensors.
        # If a sensor wasn't in temp_sensors_dict (failed init), its state remains as set by init.
        # If read succeeded, update with value; if read failed, update with read_failed error.
        with threading.Lock(): # Assuming latest_temperature_data_ref is shared, lock it
            for name in configured_names:
                if name in current_reads_this_cycle:
                    latest_temperature_data_ref[name] = current_reads_this_cycle[name]
                # else: retain existing state in latest_temperature_data_ref
                # (e.g., "initialization_failed", "not_configured_type", etc.)
                elif name not in latest_temperature_data_ref:
                     # This case should ideally be covered by main's pre-population
                     latest_temperature_data_ref[name] = {"error": "sensor_not_polled"}


        # Calculate sleep time and wait
        elapsed_time = time.time() - start_time
        sleep_time = read_interval - elapsed_time
        if sleep_time > 0:
            stop_event.wait(sleep_time)

    print("Temperature thread stopped.")


def current_thread_loop(current_sensor_data, config, stop_event, latest_current_data_ref, led_indicator=None):
    """
    Thread function to read current sensors periodically and update shared data.
    current_sensor_data should be the dict returned by initialize_current_sensors.
    """
    print("Current thread started.")

    if not CURRENT_SENSORS_MEASUREMENT_AVAILABLE:
        print("Current sensor measurement function not available. Current thread exiting.")
        # Errors related to module loading should already be in latest_current_data_ref from main
        return

    # Check if initialization data is available and valid
    if not current_sensor_data or \
       'channel_analogin_map' not in current_sensor_data or \
       'channel_offset_map' not in current_sensor_data:
        print("Current sensor data not available (initialization failed/incomplete). Current thread exiting.")
        # Errors should already be set in latest_current_data_ref
        return

    channel_analogin_map = current_sensor_data['channel_analogin_map']
    channel_offset_map = current_sensor_data['channel_offset_map']
    channel_scale_map = current_sensor_data.get('channel_scale_map', {})

    if not channel_analogin_map: # No channels were successfully mapped
        print("Current sensor channel map is empty. Current thread exiting.")
        # Errors should already be set.
        return

    # Get the set of all configured current channel names from config
    configured_names = {cfg.get('name') for cfg in config.get('sensors', {}).get('current', {}).get('channels', []) if cfg.get('name')}
    read_interval = config.get('intervals', {}).get('fast_sensors_sec', 0.333) # Using fast_sensors_sec for current

    while not stop_event.is_set():
        start_time = time.time()
        current_reads_this_cycle = {}

        try:
            # measure_all_currents should take channel_analogin_map and channel_offset_map
            # and return a dictionary like { 'channel_name1': value1, 'channel_name2': value2_or_error_dict }
            measured_data = measure_all_currents(channel_analogin_map, channel_offset_map, channel_scale_map)

            if not isinstance(measured_data, dict):
                # This indicates a problem with measure_all_currents implementation
                print(f"Error: measure_all_currents did not return a dictionary. Got: {type(measured_data)}")
                # Mark all expected channels as having a measurement system error
                for name in channel_analogin_map.keys(): # Iterate over channels we tried to measure
                     current_reads_this_cycle[name] = {"error": "measurement_system_fault", "details": "measure_all_currents bad return type"}
            else:
                current_reads_this_cycle = measured_data # Use the returned dictionary

        except Exception as e:
            print(f"Current sensor read error (measure_all_currents call): {e}")
            traceback.print_exc()
            # If a global read error occurs, set read_failed error for all channels that were initialized.
            for name in channel_analogin_map.keys():
                current_reads_this_cycle[name] = {"error": "read_failed_group", "details": str(e)}

            if led_indicator:
                led_indicator.set_red(True)  # Red during error
                time.sleep(0.1)
                led_indicator.set_red(False)

        # Update shared data for *all* configured channels.
        with threading.Lock(): # Assuming latest_current_data_ref is shared
            for name in configured_names:
                if name in current_reads_this_cycle:
                    latest_current_data_ref[name] = current_reads_this_cycle[name]
                elif name not in latest_current_data_ref:
                    latest_current_data_ref[name] = {"error": "sensor_not_polled"}


        elapsed_time = time.time() - start_time
        sleep_time = read_interval - elapsed_time
        if sleep_time > 0:
            stop_event.wait(sleep_time)

    print("Current thread stopped.")
