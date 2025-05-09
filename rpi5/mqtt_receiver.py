# mqtt_receiver.py
# -*- coding: utf-8 -*-

import json
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import time  # Import time for timestamp conversion

# InfluxDB Configuration
# Replace with your actual InfluxDB details
INFLUX_URL = "http://localhost:8086"
#INFLUX_TOKEN = "mXoOpm9EAmECOpkeDDU7CJh56PYtjYoS-oeOrx2F3X3mErSvileOwl6n-8rSXcWC_eXuh2nm3qWzCI5mDwXUzA=="
INFLUX_TOKEN = "mXoOpm9EAmECOpkeDDU7CJh56PYtjYoS-oeOrx2F3X3mErSvileOwl6n-8rSXcWC_eXuh2nm3qWdCI5mDwXUzA=="# !!! REPLACE WITH YOUR TOKEN !!!
INFLUX_ORG = "i"  # !!! REPLACE WITH YOUR ORGANIZATION !!!
INFLUX_BUCKET = "eng_bucket"  # !!! REPLACE WITH YOUR BUCKET !!!

# MQTT Configuration
# Ensure this matches the broker RPi Zero sends data to
MQTT_BROKER = "192.168.1.117"  # Or "192.168.0.93" if broker is on RPi Zero, or actual broker IP
#MQTT_BROKER = "192.168.0.93"  # Or "192.168.0.93" if broker is on RPi Zero, or actual broker IP
MQTT_PORT = 1883
MQTT_TOPIC = "sensors/data"  # Topic subscribed to

# === Initialize InfluxDB client ===
try:
    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
    print("InfluxDB client initialized.")
except Exception as e:
    print(f"Error initializing InfluxDB client: {e}")
    influx_client = None
    write_api = None


def safe_float(value):
    """
    Convert input to float safely. Return 0.0 if conversion fails or input is None.
    Handles potential errors like non-numeric strings or non-existent keys (None).
    """
    if value is None:
        return 0.0
    try:
        # Attempt direct float conversion, which handles int and float types
        return float(value)
    except (TypeError, ValueError):
        # Handle strings or other types that cannot be converted
        print(f"Warning: Could not convert value '{value}' (type {type(value)}) to float. Using 0.0.")
        return 0.0


def on_message(client, userdata, msg):
    """
    Called when a new MQTT message is received.
    Parses the message, extracts sensor data and writes it to InfluxDB.
    Handles the specific nested JSON structure from the RPi Zero sender.
    """
    try:
        # Decode payload and parse JSON
        payload_str = msg.payload.decode("utf-8")
        data = json.loads(payload_str)

        # Extract primary identifiers and timestamp
        device_id = data.get("device_id", "unknown_device")
        timestamp_float = data.get("timestamp", time.time())  # Use current time if timestamp is missing
        # Convert the float timestamp to nanoseconds (required by InfluxDB 2.x default precision)
        timestamp_ns = int(timestamp_float * 1e9)

        print(f"Received data from '{device_id}' at {timestamp_float:.2f}")

        if write_api is None:
            print("InfluxDB write API not initialized. Skipping data write.")
            return

        # === Process Temperature Data ===
        temp_data = data.get("temperature", {})
        # Expected format: {"sensor_name_1": value, "sensor_name_2": value, ...}
        if isinstance(temp_data, dict) and temp_data:  # Check if it's a non-empty dictionary
            # Create a point for temperature measurements
            point_temp = Point("temperature").tag("device_id", device_id).time(timestamp_ns)

            # Iterate through each temperature sensor reported in the payload
            for sensor_name, value in temp_data.items():
                # Add each sensor's value as a field, using the sensor name as the field key
                # Use safe_float to handle potential non-numeric values or errors reported
                point_temp.field(sensor_name, safe_float(value))

            # Write the point if it has any fields added
            if point_temp._fields:
                write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point_temp)
                print(f" - Wrote temperature data for '{device_id}'")
            else:
                print(f" - No valid temperature fields found for '{device_id}'")

        # === Process Vibration Data ===
        vib_data = data.get("vibration", {})
        # Expected format: {"sensor_name_1": {metrics_dict}, "sensor_name_2": {metrics_dict}, ..., "general": {error_dict}}
        if isinstance(vib_data, dict) and vib_data:  # Check if it's a non-empty dictionary
            # Iterate through each vibration sensor reported in the payload (keys like "engine", "gearbox")
            for sensor_name, metrics_dict in vib_data.items():
                # Skip the "general" error key if it exists at the top level of vibration data
                if sensor_name == "general" and isinstance(metrics_dict, dict) and "error" in metrics_dict:
                    print(f" - Received general vibration error for '{device_id}': {metrics_dict.get('error')}")
                    # Optionally, write this general error to a separate measurement or log it
                    continue  # Skip to the next item in vib_data

                # Process individual sensor metrics (keys like "engine", "gearbox")
                if isinstance(metrics_dict, dict):
                    # Create a point for vibration metrics for THIS specific sensor
                    # Tag with both device_id and the specific sensor_name
                    point_vib = Point("vibration_metrics").tag("device_id", device_id).tag("sensor_name",
                                                                                           sensor_name).time(
                        timestamp_ns)

                    # Add scalar metrics as fields
                    # Use safe_float for all values
                    point_vib.field("total_rms", safe_float(metrics_dict.get("total_rms")))
                    point_vib.field("rms_x", safe_float(metrics_dict.get("rms_x")))
                    point_vib.field("rms_y", safe_float(metrics_dict.get("rms_y")))
                    point_vib.field("rms_z", safe_float(metrics_dict.get("rms_z")))
                    point_vib.field("peak_x", safe_float(metrics_dict.get("peak_x")))
                    point_vib.field("peak_y", safe_float(metrics_dict.get("peak_y")))
                    point_vib.field("peak_z", safe_float(metrics_dict.get("peak_z")))
                    point_vib.field("peak_to_peak_x", safe_float(metrics_dict.get("peak_to_peak_x")))
                    point_vib.field("peak_to_peak_y", safe_float(metrics_dict.get("peak_to_peak_y")))
                    point_vib.field("peak_to_peak_z", safe_float(metrics_dict.get("peak_to_peak_z")))

                    # Handle FFT peaks - store as a JSON string field
                    fft_peaks_list = metrics_dict.get("fft_peaks")
                    if isinstance(fft_peaks_list, list):
                        try:
                            # Convert list of peak dicts to a JSON string
                            point_vib.field("fft_peaks_json", json.dumps(fft_peaks_list))
                        except Exception as e_fft:
                            print(
                                f"Warning: Could not serialize FFT peaks for sensor '{sensor_name}' on device '{device_id}': {e_fft}")
                            # Optionally store an error indicator or empty list string
                            point_vib.field("fft_peaks_json", "[]")
                    elif fft_peaks_list is not None:  # If fft_peaks exists but isn't a list
                        print(
                            f"Warning: Unexpected type for fft_peaks for sensor '{sensor_name}' on device '{device_id}': {type(fft_peaks_list)}")
                        point_vib.field("fft_peaks_json", "[]")  # Store empty array string

                    # Check if the metrics_dict itself contains an error key (e.g., "initialization_failed", "metrics_failed")
                    if "error" in metrics_dict and isinstance(metrics_dict, dict):
                        error_state = metrics_dict.get("error")
                        error_details = metrics_dict.get("details", "")
                        point_vib.field("status_error", f"{error_state}: {error_details}")
                        print(
                            f" - Received vibration error for sensor '{sensor_name}' on device '{device_id}': {error_state}")
                        # Note: Error field is added alongside any successfully read metrics

                    # Write the point if it has any fields added (either metrics or error status)
                    if point_vib._fields:
                        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point_vib)
                        print(f" - Wrote vibration data for sensor '{sensor_name}' on device '{device_id}'")
                    else:
                        print(f" - No valid vibration fields found for sensor '{sensor_name}' on device '{device_id}'")

                elif isinstance(metrics_dict, dict) and "error" in metrics_dict:
                    # This handles cases like {"sensor_name": {"error": "..."}} where there are no metrics, just an error state
                    point_vib_error = Point("vibration_metrics").tag("device_id", device_id).tag("sensor_name",
                                                                                                 sensor_name).time(
                        timestamp_ns)
                    error_state = metrics_dict.get("error")
                    error_details = metrics_dict.get("details", "")
                    point_vib_error.field("status_error", f"{error_state}: {error_details}")
                    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point_vib_error)
                    print(
                        f" - Wrote vibration error status for sensor '{sensor_name}' on device '{device_id}': {error_state}")

                else:
                    # Handle unexpected structure for a sensor entry
                    print(
                        f"Warning: Unexpected vibration data structure for key '{sensor_name}' on device '{device_id}': {metrics_dict}")

        # === Process Current Data ===
        current_data = data.get("current", {})
        # Expected format: {"channel_name_1": value, "channel_name_2": value, ..., "general": {error_dict}}
        if isinstance(current_data, dict) and current_data:  # Check if it's a non-empty dictionary
            # Create a point for current measurements
            point_current = Point("current").tag("device_id", device_id).time(timestamp_ns)

            # Iterate through each current channel reported in the payload (keys like "phase_a", "phase_b")
            for channel_name, value_or_error in current_data.items():
                # Skip the "general" error key if it exists at the top level of current data
                if channel_name == "general" and isinstance(value_or_error, dict) and "error" in value_or_error:
                    print(f" - Received general current error for '{device_id}': {value_or_error.get('error')}")
                    # Optionally, write this general error to a separate measurement or log it
                    continue  # Skip to the next item in current_data

                # Process individual channel data
                if isinstance(value_or_error, (int, float)):
                    # Add the current value as a field, using the channel name as the field key
                    point_current.field(channel_name, safe_float(value_or_error))
                elif isinstance(value_or_error, dict) and "error" in value_or_error:
                    # If the value is an error dictionary for a specific channel
                    error_state = value_or_error.get("error")
                    error_details = value_or_error.get("details", "")
                    # Store channel-specific errors as fields, e.g., "phase_a_status"
                    point_current.field(f"{channel_name}_status", f"{error_state}: {error_details}")
                    print(
                        f" - Received current error for channel '{channel_name}' on device '{device_id}': {error_state}")
                else:
                    # Handle unexpected structure for a channel entry
                    print(
                        f"Warning: Unexpected current data structure for key '{channel_name}' on device '{device_id}': {value_or_error}")

            # Write the point if it has any fields added (either values or status errors)
            if point_current._fields:
                write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point_current)
                print(f" - Wrote current data for '{device_id}'")
            else:
                print(f" - No valid current fields found for '{device_id}'")

        # Add print for overall message processing success (optional, can be verbose)
        # print(f"Finished processing data from '{device_id}'.")

    except json.JSONDecodeError:
        print(f"Error decoding JSON payload: {msg.payload}")
    except Exception as e:
        print(f"Error processing MQTT message: {e}")
        # traceback.print_exc() # Uncomment for detailed debugging


def on_connect(client, userdata, flags, rc):
    """
    Called when the MQTT client connects to the broker.
    Subscribes to the topic upon successful connection.
    """
    if rc == 0:
        print("Connected to MQTT broker.")
        client.subscribe(MQTT_TOPIC)
        print(f"Subscribed to topic: {MQTT_TOPIC}")
    else:
        print(f"MQTT connection failed with code {rc}. Reason: {mqtt.connack_string(rc)}")


def on_disconnect(client, userdata, rc):
    """
    Called when the MQTT client disconnects from the broker.
    """
    print(f"Disconnected from MQTT broker with code {rc}.")
    # The loop_forever() will attempt to reconnect automatically


# === MQTT Setup ===
# Use CallbackAPIVersion.VERSION1 or VERSION2 depending on paho-mqtt version
# VERSION1 is usually sufficient for basic callbacks.
# client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
client = mqtt.Client()  # Default uses VERSION1 for now, compatible with most installations

client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect  # Add disconnect callback

print(f"Attempting to connect to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")

# --- Connect and loop ---
try:
    # Use connect() for blocking connection, loop_forever() handles reconnects
    client.connect(MQTT_BROKER, MQTT_PORT, 60)  # 60 second keepalive
    print("MQTT loop starting...")
    client.loop_forever()  # This call blocks and handles reconnects

except ConnectionRefusedError:
    print(f"Connection refused by MQTT broker at {MQTT_BROKER}:{MQTT_PORT}. Is the broker running?")
except OSError as e:
    print(f"OS error during MQTT connection (e.g., network unreachable): {e}")
except Exception as e:
    print(f"An unexpected error occurred during MQTT setup: {e}")
    # traceback.print_exc() # Uncomment for detailed debugging

print("MQTT receiver script finished.")

