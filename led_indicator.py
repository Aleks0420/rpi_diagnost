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
        self.mqtt_connecting_event = threading.Event()
        self.mqtt_error_event = threading.Event()

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.green_pin, GPIO.OUT)
        GPIO.setup(self.blue_pin, GPIO.OUT)
        GPIO.setup(self.yellow_pin, GPIO.OUT)
        GPIO.setup(self.red_pin, GPIO.OUT)
        GPIO.setup(self.white_pin, GPIO.OUT)

        self.set_green(True)  # Power/Working indication

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

    def mqtt_connecting_blink(self):
        """Blinks blue LED slowly until stopped."""
        while not self.mqtt_connecting_event.is_set():
            self.set_blue(True)
            time.sleep(0.5)
            self.set_blue(False)
            time.sleep(0.5)

    def mqtt_error_blink(self):
        """Blinks blue LED quickly until stopped."""
        while not self.mqtt_error_event.is_set():
            self.set_blue(True)
            time.sleep(0.1)
            self.set_blue(False)
            time.sleep(0.1)

    def start_mqtt_connecting(self):
        self.mqtt_connecting_event.clear()  # Ensure event is cleared
        self.mqtt_connecting_thread = threading.Thread(target=self.mqtt_connecting_blink)
        self.mqtt_connecting_thread.daemon = True
        self.mqtt_connecting_thread.start()

    def stop_mqtt_connecting(self):
        self.mqtt_connecting_event.set()
        self.set_blue(False)  # Ensure LED is off after stopping

    def start_mqtt_error(self):
        self.mqtt_error_event.clear()
        self.mqtt_error_thread = threading.Thread(target=self.mqtt_error_blink)
        self.mqtt_error_thread.daemon = True
        self.mqtt_error_thread.start()

    def stop_mqtt_error(self):
        self.mqtt_error_event.set()
        self.set_blue(False) # Ensure LED is off after stopping

    def cleanup(self):
        """Clean up GPIO settings."""
        GPIO.cleanup()