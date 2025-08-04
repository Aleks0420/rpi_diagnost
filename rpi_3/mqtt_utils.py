# mqtt_utils.py
# -*- coding: utf-8 -*-

import time
import traceback
import paho.mqtt.client as mqtt

# --- MQTT Client Setup ---
mqtt_connected_flag = False  # Флаг для отслеживания состояния подключения

def create_mqtt_client(client_id=""):
    """
    Создает MQTT-клиент и настраивает обработчики событий.
    """
    client = mqtt.Client(client_id=client_id.encode('utf-8'))
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message  # Для обработки входящих сообщений, если нужно
    return client

def on_connect(client, userdata, flags, rc, properties=None):
    """
    Обработчик события подключения к брокеру.
    """
    global mqtt_connected_flag
    if rc == 0:
        mqtt_connected_flag = True
        print("Connected to MQTT broker")
    else:
        mqtt_connected_flag = False
        print(f"Failed to connect to MQTT broker (code {rc})")

def on_disconnect(client, userdata, rc, properties=None, *args):
    """
    Обработчик события отключения от брокера.
    """
    global mqtt_connected_flag
    mqtt_connected_flag = False
    print(f"Disconnected from MQTT broker (rc: {rc})")

def on_message(client, userdata, message):
    """
    Обработчик входящих сообщений (если требуется).
    """
    print(f"Received message on topic {message.topic}: {message.payload.decode()}")

def is_mqtt_connected():
    """
    Проверяет, подключен ли клиент к MQTT-брокеру.
    """
    global mqtt_connected_flag
    return mqtt_connected_flag

def connect_mqtt(client, broker, port, device_id, stop_event, led_indicator=None):
    """
    Подключение к MQTT-брокеру с оптимизированной обработкой разрыва соединения.
    """
    global mqtt_connected_flag
    mqtt_connected_flag = False

    if led_indicator:
        led_indicator.start_mqtt_connecting()  # Медленное мигание синим

    try:
        client.connect_async(broker, port, keepalive=15)  # Уменьшен keepalive до 15 секунд
        client.loop_start()  # Асинхронная обработка событий

        # Ожидание подключения с таймаутом
        timeout = 10  # Максимальное время ожидания подключения
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

        if led_indicator:
            led_indicator.start_mqtt_connected()  # Постоянный синий свет

        return True

    except Exception as e:
        if led_indicator:
            led_indicator.stop_mqtt_connecting()
            led_indicator.start_mqtt_error()
        print(f"MQTT connection error: {e}")
        return False

def monitor_mqtt_connection(client, stop_event, led_indicator=None):
    """
    Функция для мониторинга соединения с брокером. Если соединение теряется, пытается переподключиться.
    """
    while not stop_event.is_set():
        if not is_mqtt_connected():
            print("Connection lost. Attempting to reconnect...")
            if led_indicator:
                led_indicator.start_mqtt_error()
            try:
                client.reconnect()  # Попытка переподключения
                print("Reconnected to MQTT broker.")
                if led_indicator:
                    led_indicator.start_mqtt_connected()
            except Exception as e:
                print(f"Reconnection failed: {e}")
                time.sleep(5)  # Задержка перед следующей попыткой
        time.sleep(1)
