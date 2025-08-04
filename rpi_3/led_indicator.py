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
        self.heartbeat_timeout_event = threading.Event()
        self.calibration_event = threading.Event()

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.green_pin, GPIO.OUT)
        GPIO.setup(self.blue_pin, GPIO.OUT)
        GPIO.setup(self.yellow_pin, GPIO.OUT)
        GPIO.setup(self.red_pin, GPIO.OUT)
        GPIO.setup(self.white_pin, GPIO.OUT)

        # Green LED is always ON indicating that the system is working
        self.set_green(True)

    # ---------------- BASIC LED CONTROL METHODS ----------------
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
        """Blink blue LED at 0.5Hz (2 seconds per cycle) to indicate MQTT connecting."""
        while not self.mqtt_connecting_event.is_set():
            self.set_blue(True)
            time.sleep(1.0)  # 1 second ON
            self.set_blue(False)
            time.sleep(1.0)  # 1 second OFF

    def mqtt_error_blink(self):
        """Blink blue LED fast at 5Hz (100ms ON, 100ms OFF) to indicate MQTT error."""
        while not self.mqtt_error_event.is_set():
            self.set_blue(True)
            time.sleep(0.1)  # 100ms ON
            self.set_blue(False)
            time.sleep(0.1)  # 100ms OFF

    def heartbeat_timeout_blink(self):
        """Solid yellow LED to indicate heartbeat timeout."""
        while not self.heartbeat_timeout_event.is_set():
            self.set_yellow(True)
            time.sleep(0.1)  # Small sleep to prevent CPU overload

    def calibration_indicator(self):
        """Solid white LED to indicate calibration in progress."""
        while not self.calibration_event.is_set():
            self.set_white(True)
            time.sleep(0.1)  # Small sleep to prevent CPU overload

    # ---------------- PUBLIC INTERFACE METHODS ----------------
    def start_mqtt_connecting(self):
        """Start the blue LED blink to indicate that MQTT connection is in progress."""
        self.stop_all_blinking()  # Stop any previous blinking
        self.mqtt_connecting_event.clear()
        self.mqtt_connecting_thread = threading.Thread(target=self.mqtt_connecting_blink)
        self.mqtt_connecting_thread.daemon = True
        self.mqtt_connecting_thread.start()

    def stop_mqtt_connecting(self):
        """Stop the MQTT connecting blink."""
        self.mqtt_connecting_event.set()
        self.set_blue(False)

    def start_mqtt_connected(self):
        """Solid blue LED to indicate successful MQTT connection."""
        self.stop_all_blinking()
        self.set_blue(True)

    def start_mqtt_error(self):
        """Start the fast blinking blue LED to indicate an MQTT error."""
        self.stop_all_blinking()
        self.mqtt_error_event.clear()
        self.mqtt_error_thread = threading.Thread(target=self.mqtt_error_blink)
        self.mqtt_error_thread.daemon = True
        self.mqtt_error_thread.start()

    def stop_mqtt_error(self):
        """Stop the MQTT error blinking."""
        self.mqtt_error_event.set()
        self.set_blue(False)

    def data_sent_success(self):
        """Short yellow flash to indicate successful data transmission."""
        self.set_yellow(True)
        time.sleep(0.1)  # 100ms ON
        self.set_yellow(False)

    def data_sent_failed(self):
        """Short red flash to indicate failed data transmission."""
        self.set_red(True)
        time.sleep(0.1)  # 100ms ON
        self.set_red(False)

    def start_heartbeat_timeout(self):
        """Solid yellow LED to indicate heartbeat timeout."""
        self.stop_all_blinking()
        self.heartbeat_timeout_event.clear()
        self.heartbeat_timeout_thread = threading.Thread(target=self.heartbeat_timeout_blink)
        self.heartbeat_timeout_thread.daemon = True
        self.heartbeat_timeout_thread.start()

    def stop_heartbeat_timeout(self):
        """Stop the heartbeat timeout indicator."""
        self.heartbeat_timeout_event.set()
        self.set_yellow(False)

    def start_calibration(self):
        """Solid white LED to indicate calibration in progress."""
        self.stop_all_blinking()
        self.calibration_event.clear()
        self.calibration_thread = threading.Thread(target=self.calibration_indicator)
        self.calibration_thread.daemon = True
        self.calibration_thread.start()

    def stop_calibration(self):
        """Stop the calibration indicator."""
        self.calibration_event.set()
        self.set_white(False)

    def stop_all_blinking(self):
        """Stop all blinking indicators."""
        self.stop_mqtt_connecting()
        self.stop_mqtt_error()
        self.stop_heartbeat_timeout()
        self.stop_calibration()
        # Turn off all LEDs except green
        self.set_blue(False)
        self.set_yellow(False)
        self.set_red(False)
        self.set_white(False)

    def cleanup(self):
        """Clean up GPIO settings."""
        self.stop_all_blinking()
        GPIO.cleanup()
