# mqtt_utils.py
# -*- coding: utf-8 -*-

import time
import traceback
import paho.mqtt.client as mqtt

# --- MQTT Client Setup ---
# Use a global or pass it around; global for simplicity in callbacks here
# Client will be created in main and passed to connect_mqtt
mqtt_connected_flag = False # Use a distinct name to avoid conflict if client is passed

def create_mqtt_client(client_id=""):
    """
    Creates an MQTT client instance.
    Client ID will be set from config before connecting.
    """
    # Use CallbackAPIVersion.VERSION2 for paho-mqtt >= 2.0
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id.encode('utf-8'))
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    return client

def on_connect(client, userdata, flags, rc, properties=None):
    """Callback function for MQTT connection."""
    global mqtt_connected_flag
    if rc == 0:
        mqtt_connected_flag = True
        print("Connected to MQTT broker")
        if hasattr(userdata, 'set_blue'):
            userdata.set_blue(True) # Solid blue when connected
    else:
        print(f"Failed to connect to MQTT broker (code {rc})")
        mqtt_connected_flag = False  # Ensure flag is false on failure
        if hasattr(userdata, 'start_mqtt_error'):
            userdata.start_mqtt_error() # Start error blink

def on_disconnect(client, userdata, rc, properties=None, reason_code=None):
    """Callback function for MQTT disconnection."""
    global mqtt_connected_flag
    mqtt_connected_flag = False
    print(f"Disconnected from MQTT broker (rc: {rc}, reason: {reason_code})")
    # loop_start handles reconnection automatically if disconnect was not explicit
    if hasattr(userdata, 'start_mqtt_error'):
        userdata.start_mqtt_error() # Start error blink

def is_mqtt_connected():
    """Returns the current MQTT connection status."""
    global mqtt_connected_flag
    return mqtt_connected_flag

def connect_mqtt(client, broker, port, client_id, stop_event, led_indicator=None):
    """
    Connects to the MQTT broker asynchronously and starts the network loop.
    Returns True if initial connection attempt seems successful, False otherwise.
    The loop_start() will handle reconnections in the background.
    """
    global mqtt_connected_flag
    mqtt_connected_flag = False # Reset flag before attempting connection

    if led_indicator:
       led_indicator.start_mqtt_connecting() # Start blinking blue LED

    if client._client_id != client_id.encode('utf-8'):
         client._client_id = client_id.encode('utf-8')

    print(f"Connecting to MQTT broker {broker}:{port} with client ID '{client_id}'...")
    try:
        # Use connect_async to avoid blocking the main thread
        client.connect_async(broker, port, keepalive=60)
        # Start the background thread for MQTT network operations
        client.loop_start()

        # Wait for connection with a timeout or until stop event is set
        timeout = 10  # seconds
        start_time = time.time()
        while not mqtt_connected_flag and (time.time() - start_time) < timeout and not stop_event.is_set():
            time.sleep(0.1)

        if stop_event.is_set():
            print("Connection attempt interrupted by stop signal.")
            if led_indicator:
                led_indicator.stop_mqtt_connecting() # Stop blinking if interrupted
            return False

        if not mqtt_connected_flag:
            print("MQTT connection attempt timed out or failed. Background loop will retry.")
            # loop_start will continue trying to reconnect in the background
            if led_indicator:
                led_indicator.stop_mqtt_connecting()
                led_indicator.start_mqtt_error() # Start error blink
            return False # Indicate initial connection attempt didn't succeed immediately

        print("MQTT connection successful.")
        if led_indicator:
            led_indicator.stop_mqtt_connecting()
            led_indicator.set_blue(True) # Solid blue for connected
        return True

    except Exception as e:
        print(f"MQTT connection error during connect_async/loop_start: {e}")
        traceback.print_exc()
        # loop_start will continue trying to reconnect in the background
        if led_indicator:
           led_indicator.stop_mqtt_connecting()
           led_indicator.start_mqtt_error() # Start error blink
        return False # Indicate initial connection attempt failed