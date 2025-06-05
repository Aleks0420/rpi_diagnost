# led_indicator.py
import RPi.GPIO as GPIO
import time
import threading


class LEDIndicator:
    def __init__(self, green_pin, blue_pin, yellow_pin, red_pin, white_pin):
        self.green_pin = green_pin
        self.blue_pin = blue_pin
        self.yellow_pin = yellow_pin
        self.red_pin = red_pin
        self.white_pin = white_pin

        # Events to control the blinking threads
        self.mqtt_connecting_event = threading.Event()
        self.mqtt_error_event = threading.Event()

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.green_pin, GPIO.OUT)
        GPIO.setup(self.blue_pin, GPIO.OUT)
        GPIO.setup(self.yellow_pin, GPIO.OUT)
        GPIO.setup(self.red_pin, GPIO.OUT)
        GPIO.setup(self.white_pin, GPIO.OUT)

        # Green LED is always ON indicating that the system is working.
        self.set_green(True)

    # ---------------- LED CONTROL METHODS ----------------

    def set_green(self, on):
        GPIO.output(self.green_pin, GPIO.HIGH if on else GPIO.LOW)

    def set_blue(self, on):
        GPIO.output(self.blue_pin, GPIO.HIGH if on else GPIO.LOW)

    def set_yellow(self, on):
        GPIO.output(self.yellow_pin, GPIO.HIGH if on else GPIO.LOW)

    def set_red(self, on):
        GPIO.output(self.red_pin, GPIO.HIGH if on else GPIO.LOW)

    def set_white(self, on):
        GPIO.output(self.white_pin, GPIO.HIGH if on else GPIO.LOW)

    # ---------------- BLINKING METHODS ----------------

    def mqtt_connecting_blink(self):
        """
        Blink blue LED at 0.5Hz (1 second ON, 1 second OFF) to indicate MQTT connecting.
        """
        while not self.mqtt_connecting_event.is_set():
            self.set_blue(True)
            time.sleep(1.0)  # 1 second ON
            self.set_blue(False)
            time.sleep(1.0)  # 1 second OFF

    def mqtt_error_blink(self):
        """
        Blink blue LED fast at 5Hz (100ms ON, 100ms OFF) to indicate MQTT error.
        """
        while not self.mqtt_error_event.is_set():
            self.set_blue(True)
            time.sleep(0.1)  # 100ms ON
            self.set_blue(False)
            time.sleep(0.1)  # 100ms OFF

    def flash_yellow(self):
        """
        Flash yellow LED once for 100ms to indicate successful data sending.
        """
        self.set_yellow(True)
        time.sleep(0.1)
        self.set_yellow(False)

    def flash_red(self):
        """
        Flash red LED once for 100ms to indicate a sending error (data saved to buffer).
        """
        self.set_red(True)
        time.sleep(0.1)
        self.set_red(False)

    # ---------------- THREAD CONTROL METHODS ----------------

    def start_mqtt_connecting(self):
        """
        Start the blue LED blink to indicate that MQTT connection is in progress.
        """
        self.mqtt_connecting_event.clear()  # Reset event
        self.mqtt_connecting_thread = threading.Thread(target=self.mqtt_connecting_blink)
        self.mqtt_connecting_thread.daemon = True
        self.mqtt_connecting_thread.start()

    def stop_mqtt_connecting(self):
        """
        Stop the MQTT connecting blink and switch off blue LED.
        """
        self.mqtt_connecting_event.set()
        self.set_blue(False)

    def start_mqtt_error(self):
        """
        Start the fast blinking blue LED to indicate an MQTT error.
        """
        self.mqtt_error_event.clear()
        self.mqtt_error_thread = threading.Thread(target=self.mqtt_error_blink)
        self.mqtt_error_thread.daemon = True
        self.mqtt_error_thread.start()

    def stop_mqtt_error(self):
        """
        Stop the MQTT error blinking and switch off blue LED.
        """
        self.mqtt_error_event.set()
        self.set_blue(False)

    # ---------------- CLEAN UP ----------------

    def cleanup(self):
        """
        Clean up GPIO settings.
        """
        GPIO.cleanup()
