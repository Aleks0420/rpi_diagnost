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
    global mqtt_connected_flag
    if rc == 0:
        mqtt_connected_flag = True
        print("Connected to MQTT broker")
        if hasattr(userdata, 'start_mqtt_connected'):  # Новый вызов
            userdata.start_mqtt_connected()  # Синий постоянный
    else:
        mqtt_connected_flag = False
        print(f"Failed to connect to MQTT broker (code {rc})")
        if hasattr(userdata, 'start_mqtt_error'):  # Новый вызов
            userdata.start_mqtt_error()  # Быстрое мигание синим


def on_disconnect(client, userdata, rc, properties=None):
    global mqtt_connected_flag
    mqtt_connected_flag = False
    print(f"Disconnected from MQTT broker (rc: {rc})")
    if hasattr(userdata, 'start_mqtt_error'):  # Новый вызов
        userdata.start_mqtt_error()


def is_mqtt_connected():
    """Returns the current MQTT connection status."""
    global mqtt_connected_flag
    return mqtt_connected_flag





def connect_mqtt(client, broker, port, device_id, stop_event, led_indicator=None):
    global mqtt_connected_flag
    mqtt_connected_flag = False

    if led_indicator:
        led_indicator.start_mqtt_connecting()  # Медленное мигание синим

    try:
        client.connect_async(broker, port, keepalive=60)
        client.loop_start()

        # Ожидание подключения с таймаутом
        timeout = 10
        start_time = time.time()
        while not mqtt_connected_flag and (time.time() - start_time) < timeout and not stop_event.is_set():
            time.sleep(0.1)

        if stop_event.is_set():
            if led_indicator:
                led_indicator.stop_mqtt_connecting()
            return False

        if not mqtt_connected_flag:
            if led_indicator:
                led_indicator.stop_mqtt_connecting()
                led_indicator.start_mqtt_error()
            return False

        return True

    except Exception as e:
        if led_indicator:
            led_indicator.stop_mqtt_connecting()
            led_indicator.start_mqtt_error()
        print(f"MQTT connection error: {e}")
        return False
