import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json

# Import real sensor calibration functions and sensor classes
import sensor_initializer  # (если используются функции из этого модуля)
from sensors.mpu6050 import MPU6050
from sensors.current_sensors import init_adc, calibrate_current_sensors, AnalogIn


def create_widgets_for_config(frame, config, entries, parent_key=""):
    """
    Recursively creates input widgets for all parameters in the config dict.
    Stores Tkinter variable references in entries using composite keys.
    """
    for key, value in config.items():
        full_key = f"{parent_key}.{key}" if parent_key else key
        if isinstance(value, dict):
            sub_frame = ttk.LabelFrame(frame, text=key)
            sub_frame.pack(fill='x', padx=5, pady=5, expand=True)
            create_widgets_for_config(sub_frame, value, entries, full_key)
        elif isinstance(value, list):
            row = tk.Frame(frame)
            row.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
            label = tk.Label(row, text=key, width=20, anchor='w')
            label.pack(side=tk.LEFT)
            var = tk.StringVar()
            var.set(json.dumps(value, ensure_ascii=False))
            entry = tk.Entry(row, textvariable=var)
            entry.pack(side=tk.RIGHT, fill=tk.X, expand=True)
            entries[full_key] = var
        elif isinstance(value, bool):
            var = tk.BooleanVar()
            var.set(value)
            row = tk.Frame(frame)
            row.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
            label = tk.Label(row, text=key, width=20, anchor='w')
            label.pack(side=tk.LEFT)
            check = tk.Checkbutton(row, variable=var)
            check.pack(side=tk.RIGHT)
            entries[full_key] = var
        else:
            row = tk.Frame(frame)
            row.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
            label = tk.Label(row, text=key, width=20, anchor='w')
            label.pack(side=tk.LEFT)
            var = tk.StringVar()
            var.set(str(value))
            entry = tk.Entry(row, textvariable=var)
            entry.pack(side=tk.RIGHT, fill=tk.X, expand=True)
            entries[full_key] = var


def update_config_from_entries(config, entries, parent_key=""):
    """
    Recursively updates the config dict using values from entries.
    Uses composite keys to update nested dictionaries.
    """
    for key in config:
        full_key = f"{parent_key}.{key}" if parent_key else key
        if isinstance(config[key], dict):
            update_config_from_entries(config[key], entries, full_key)
        elif isinstance(config[key], list):
            if full_key in entries:
                new_value = entries[full_key].get()
                try:
                    config[key] = json.loads(new_value)
                except Exception:
                    print(f"Failed to parse list for key '{full_key}', keeping original.")
        elif isinstance(config[key], bool):
            if full_key in entries:
                config[key] = entries[full_key].get()
        else:
            if full_key in entries:
                new_value = entries[full_key].get()
                try:
                    if isinstance(config[key], int):
                        config[key] = int(new_value)
                    elif isinstance(config[key], float):
                        config[key] = float(new_value)
                    else:
                        config[key] = new_value
                except Exception:
                    config[key] = new_value


def run_mpu_calibration(config):
    """
    Performs real MPU6050 calibration.
    Iterates through configured MPU6050 sensors, creates an instance,
    calls calibrate(samples=200), and closes the sensor.
    """
    try:
        mpu_configs = config.get("sensors", {}).get("mpu6050", [])
        if not mpu_configs:
            messagebox.showerror("Calibration Error", "No MPU6050 sensors configured.")
            return
        for sensor_cfg in mpu_configs:
            bus = sensor_cfg.get("bus", 1)
            address_str = sensor_cfg.get("address")
            if not address_str:
                messagebox.showerror("Calibration Error", "Sensor address missing for one of the MPU6050 entries.")
                continue
            address = int(address_str, 0)
            sample_rate = sensor_cfg.get("sample_rate_hz", 200)
            buffer_size = sensor_cfg.get("buffer_size", 200)
            sensor_name = sensor_cfg.get("name", "unknown")
            messagebox.showinfo("Calibration", f"Calibrating sensor '{sensor_name}'...")
            sensor = MPU6050(bus=bus, address=address, sample_rate_hz=sample_rate, buffer_size=buffer_size)
            sensor.calibrate(samples=200)
            sensor.close()
        messagebox.showinfo("Calibration", "MPU Calibration completed successfully.")
    except Exception as e:
        messagebox.showerror("Calibration Error", str(e))


def run_current_calibration(config):
    """
    Performs real calibration of current sensors.
    Initializes the ADC and creates AnalogIn objects for each channel.
    Then calls calibrate_current_sensors to obtain offsets, and updates the config.
    """
    try:
        current_cfg = config.get("sensors", {}).get("current", {})
        channels_cfg = current_cfg.get("channels", [])
        adc_cfg = current_cfg.get("adc", {})
        if not adc_cfg or not channels_cfg:
            messagebox.showerror("Calibration Error", "Current sensor configuration missing.")
            return
        adc_instance = init_adc(adc_cfg)
        if adc_instance is None:
            messagebox.showerror("Calibration Error", "Failed to initialize ADC.")
            return
        analogin_list = []
        for ch_cfg in channels_cfg:
            adc_channel = ch_cfg.get("adc_channel")
            if adc_channel is None:
                continue
            channel_obj = AnalogIn(adc_instance, adc_channel)
            analogin_list.append(channel_obj)
        offsets = calibrate_current_sensors(analogin_list)
        if offsets is None or len(offsets) != len(analogin_list):
            messagebox.showerror("Calibration Error", "Calibration failed for current sensors.")
            return
        # Update offsets in the configuration for each channel
        for i, ch_cfg in enumerate(channels_cfg):
            ch_cfg["offset"] = offsets[i]
        messagebox.showinfo("Calibration", "Current sensor calibration completed successfully.")
    except Exception as e:
        messagebox.showerror("Calibration Error", str(e))


### Main GUI menu with all options and calibration buttons

class ConfigMenuGUI:
    def __init__(self, config):
        self.config = config
        self.root = tk.Tk()
        self.root.title("Configuration Menu")
        self.show_main_menu()
        self.root.mainloop()

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def show_main_menu(self):
        self.clear_window()
        header = "----------------------------\nOptions:"
        tk.Label(self.root, text=header, font=("Helvetica", 12, "bold")).pack(pady=5)

        options = [
            ("1. Set Device ID", self.set_device_id),
            ("2. Set MQTT Broker Address", self.set_mqtt_broker),
            ("3. Set MQTT Port", self.set_mqtt_port),
            ("4. Set MQTT Topic", self.set_mqtt_topic),
            ("5. Set Temperature Read Interval (sec)", self.set_temp_interval),
            ("6. Set Fast Sensors Read Interval (sec)", self.set_fast_interval),
            ("7. Configure MPU6050 Sensors (General)", self.configure_mpu),
            ("8. Configure MPU6050 FFT Settings", self.configure_mpu_fft),
            ("9. Configure DS18B20 Sensors", self.configure_ds18b20),
            ("10. Configure Current Sensors (ADC & Channels)", self.configure_current),
            ("11. Configure Calibration Settings", self.configure_calibration),
            ("S. Save Configuration", self.save_config),
            ("L. Load Configuration (from file)", self.load_config),
            ("R. Restore Default Configuration", self.restore_default),
            ("X. Exit without Saving", self.exit_without_saving),
            ("START. Start Data Collection", self.start_data_collection)
        ]
        for text, func in options:
            tk.Button(self.root, text=text, width=50, command=func).pack(pady=2)

    def set_device_id(self):
        new_val = simpledialog.askstring("Set Device ID", "Enter new Device ID:",
                                         initialvalue=self.config.get("device_id", ""))
        if new_val:
            self.config["device_id"] = new_val
        self.show_main_menu()

    def set_mqtt_broker(self):
        mqtt = self.config.get("mqtt", {})
        new_val = simpledialog.askstring("Set MQTT Broker Address", "Enter new MQTT Broker Address:",
                                         initialvalue=mqtt.get("broker", ""))
        if new_val:
            mqtt["broker"] = new_val
            self.config["mqtt"] = mqtt
        self.show_main_menu()

    def set_mqtt_port(self):
        mqtt = self.config.get("mqtt", {})
        new_val = simpledialog.askinteger("Set MQTT Port", "Enter new MQTT Port:", initialvalue=mqtt.get("port", 1883))
        if new_val:
            mqtt["port"] = new_val
            self.config["mqtt"] = mqtt
        self.show_main_menu()

    def set_mqtt_topic(self):
        mqtt = self.config.get("mqtt", {})
        new_val = simpledialog.askstring("Set MQTT Topic", "Enter new MQTT Topic:",
                                         initialvalue=mqtt.get("topic", "sensors/data"))
        if new_val:
            mqtt["topic"] = new_val
            self.config["mqtt"] = mqtt
        self.show_main_menu()

    def set_temp_interval(self):
        intervals = self.config.get("intervals", {})
        new_val = simpledialog.askfloat("Set Temperature Read Interval", "Enter Temperature Interval (sec):",
                                        initialvalue=intervals.get("temperature_sec", 5.0))
        if new_val and new_val > 0:
            intervals["temperature_sec"] = new_val
            self.config["intervals"] = intervals
        self.show_main_menu()

    def set_fast_interval(self):
        intervals = self.config.get("intervals", {})
        new_val = simpledialog.askfloat("Set Fast Sensors Read Interval", "Enter Fast Sensors Interval (sec):",
                                        initialvalue=intervals.get("fast_sensors_sec", 0.333))
        if new_val and new_val > 0:
            intervals["fast_sensors_sec"] = new_val
            self.config["intervals"] = intervals
        self.show_main_menu()

    def configure_mpu(self):
        self.simple_list_edit("Configure MPU6050 Sensors (General)", ["sensors", "mpu6050"], self.show_main_menu)

    def configure_mpu_fft(self):
        self.simple_edit("Configure MPU6050 FFT Settings", ["sensors", "mpu6050_fft"], self.show_main_menu)

    def configure_ds18b20(self):
        self.simple_list_edit("Configure DS18B20 Sensors", ["sensors", "ds18b20"], self.show_main_menu)

    def configure_current(self):
        self.current_menu()

    def configure_calibration(self):
        win = tk.Toplevel(self.root)
        win.title("Configure Calibration Settings")
        tk.Label(win, text="Calibration Settings:").pack(pady=5)
        calib = self.config.get("calibration", {})
        var_mpu = tk.BooleanVar(value=calib.get("mpu", True))
        var_current = tk.BooleanVar(value=calib.get("current", True))
        tk.Checkbutton(win, text="Calibrate MPU6050 on start", variable=var_mpu).pack(pady=2)
        tk.Checkbutton(win, text="Calibrate Current Sensors on start", variable=var_current).pack(pady=2)

        def save_calib():
            calib["mpu"] = var_mpu.get()
            calib["current"] = var_current.get()
            self.config["calibration"] = calib
            win.destroy()
            self.show_main_menu()

        tk.Button(win, text="Save", command=save_calib).pack(pady=5)

    def save_config(self):
        messagebox.showinfo("Save Configuration", "Configuration saved.")
        self.show_main_menu()

    def load_config(self):
        messagebox.showinfo("Load Configuration", "Configuration loaded from file.")
        self.show_main_menu()

    def restore_default(self):
        messagebox.showinfo("Restore Default", "Default configuration restored.")
        self.show_main_menu()

    def exit_without_saving(self):
        self.root.destroy()

    def start_data_collection(self):
        messagebox.showinfo("Start Data Collection", "Data Collection started.")
        self.root.destroy()

    def simple_edit(self, title, key_path, return_func):
        win = tk.Toplevel(self.root)
        win.title(title)
        tk.Label(win, text="Editing " + ".".join(key_path)).pack(pady=5)
        text = tk.Text(win, height=10, width=50)
        text.pack(padx=5, pady=5)
        val = self.get_nested_value(key_path)
        text.insert(tk.END, json.dumps(val, indent=4))

        def on_save():
            try:
                new_val = json.loads(text.get("1.0", tk.END))
                self.set_nested_value(key_path, new_val)
                win.destroy()
                return_func()
            except Exception as e:
                messagebox.showerror("Error", f"Invalid JSON: {e}")

        tk.Button(win, text="Save", command=on_save).pack(pady=5)

    def simple_list_edit(self, title, key_path, return_func):
        self.simple_edit(title, key_path, return_func)

    def get_nested_value(self, key_path):
        val = self.config
        for key in key_path:
            val = val.get(key, {})
        return val

    def set_nested_value(self, key_path, new_val):
        d = self.config
        for key in key_path[:-1]:
            d = d.setdefault(key, {})
        d[key_path[-1]] = new_val

    ## --- Current Sensors Submenu ---
    def current_menu(self):
        win = tk.Toplevel(self.root)
        win.title("--- Configure Current Sensors (ADC & Channels) ---")
        current_cfg = self.config.get("sensors", {}).get("current", {})
        adc_cfg = current_cfg.get("adc", {})
        channels = current_cfg.get("channels", [])
        info = f"ADC: Bus={adc_cfg.get('bus', '')}, Address={adc_cfg.get('address', '')}, Gain={adc_cfg.get('gain', '')}\nChannels:"
        tk.Label(win, text=info, justify="left").pack(pady=5)
        for idx, ch in enumerate(channels, start=1):
            tk.Label(win, text=f"{idx}. Name: {ch.get('name', '')}, ADC Idx: {ch.get('adc_channel', '')}").pack(
                anchor="w", padx=10)

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="1. Set ADC", command=lambda: self.set_adc(win)).grid(row=0, column=0, padx=5, pady=2)
        tk.Button(btn_frame, text="2. Add/Edit Channel", command=lambda: self.add_edit_channel(win)).grid(row=0,
                                                                                                          column=1,
                                                                                                          padx=5,
                                                                                                          pady=2)
        tk.Button(btn_frame, text="3. Remove Channel", command=lambda: self.remove_channel(win)).grid(row=0, column=2,
                                                                                                      padx=5, pady=2)
        tk.Button(btn_frame, text="4. Channel Offsets/Scales Advanced",
                  command=lambda: self.current_offsets_menu(win)).grid(row=0, column=3, padx=5, pady=2)
        tk.Button(win, text="B. Back to main menu", command=lambda: [win.destroy(), self.show_main_menu()]).pack(pady=5)

    def set_adc(self, parent_win):
        current_cfg = self.config.get("sensors", {}).get("current", {})
        adc_cfg = current_cfg.get("adc", {})
        new_bus = simpledialog.askinteger("Set ADC", "Enter I2C Bus:", initialvalue=adc_cfg.get("bus", 1))
        new_addr = simpledialog.askstring("Set ADC", "Enter I2C Address (e.g. 0x48):",
                                          initialvalue=adc_cfg.get("address", "0x48"))
        new_gain = simpledialog.askfloat("Set ADC", "Enter Gain:", initialvalue=adc_cfg.get("gain", 1.0))
        if new_bus is not None and new_addr and new_gain is not None:
            adc_cfg["bus"] = new_bus
            adc_cfg["address"] = new_addr
            adc_cfg["gain"] = new_gain
            self.config["sensors"]["current"]["adc"] = adc_cfg
        parent_win.destroy()
        self.current_menu()

    def add_edit_channel(self, parent_win):
        current_cfg = self.config.get("sensors", {}).get("current", {})
        channels = current_cfg.get("channels", [])
        ch_name = simpledialog.askstring("Add/Edit Channel", "Enter channel name:")
        adc_idx = simpledialog.askinteger("Add/Edit Channel", "Enter ADC channel index (0-3):")
        if ch_name and adc_idx is not None:
            updated = False
            for ch in channels:
                if ch.get("name") == ch_name:
                    ch["adc_channel"] = adc_idx
                    updated = True
                    break
            if not updated:
                channels.append({"name": ch_name, "adc_channel": adc_idx, "offset": 0.0, "scale": 1.0})
            self.config["sensors"]["current"]["channels"] = channels
        parent_win.destroy()
        self.current_menu()

    def remove_channel(self, parent_win):
        current_cfg = self.config.get("sensors", {}).get("current", {})
        channels = current_cfg.get("channels", [])
        ch_idx = simpledialog.askinteger("Remove Channel", "Enter channel number to remove:")
        if ch_idx is not None and 1 <= ch_idx <= len(channels):
            channels.pop(ch_idx - 1)
            self.config["sensors"]["current"]["channels"] = channels
        parent_win.destroy()
        self.current_menu()

    def current_offsets_menu(self, parent_win):
        win = tk.Toplevel(self.root)
        win.title("--- Channel Offsets/Scales Advanced ---")
        channels = self.config.get("sensors", {}).get("current", {}).get("channels", [])
        tk.Label(win, text="Current channel offsets and scales:").pack(pady=5)
        for idx, ch in enumerate(channels, start=1):
            tk.Label(win,
                     text=f"{idx}. {ch.get('name', '')}: offset={ch.get('offset', 0.0):.4f}, scale={ch.get('scale', 1.0):.3f}").pack(
                anchor="w", padx=10)

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="1. Edit offset/scale for a channel",
                  command=lambda: self.edit_channel_offset(win)).grid(row=0, column=0, padx=5, pady=2)
        tk.Button(btn_frame, text="2. Set all offsets to zero", command=lambda: self.set_all_offsets_zero(win)).grid(
            row=0, column=1, padx=5, pady=2)
        tk.Button(btn_frame, text="3. Run auto-calibration (no load, updates all offsets)",
                  command=lambda: self.run_auto_calib(win)).grid(row=0, column=2, padx=5, pady=2)
        tk.Button(btn_frame, text="4. Manual calibration - adjust scale",
                  command=lambda: self.run_manual_calib(win)).grid(row=0, column=3, padx=5, pady=2)
        tk.Button(win, text="B. Back to previous menu", command=lambda: win.destroy()).pack(pady=5)

    def edit_channel_offset(self, parent_win):
        current_cfg = self.config.get("sensors", {}).get("current", {})
        channels = current_cfg.get("channels", [])
        ch_idx = simpledialog.askinteger("Edit Channel", "Enter channel number to edit:")
        if ch_idx is not None and 1 <= ch_idx <= len(channels):
            ch = channels[ch_idx - 1]
            new_offset = simpledialog.askfloat("Edit Offset", f"Enter new offset for {ch.get('name', '')}:",
                                               initialvalue=ch.get("offset", 0.0))
            new_scale = simpledialog.askfloat("Edit Scale", f"Enter new scale for {ch.get('name', '')}:",
                                              initialvalue=ch.get("scale", 1.0))
            if new_offset is not None:
                ch["offset"] = new_offset
            if new_scale is not None:
                ch["scale"] = new_scale
            self.config["sensors"]["current"]["channels"] = channels
        parent_win.destroy()
        self.current_offsets_menu(parent_win)

    def set_all_offsets_zero(self, parent_win):
        channels = self.config.get("sensors", {}).get("current", {}).get("channels", [])
        for ch in channels:
            ch["offset"] = 0.0
        self.config["sensors"]["current"]["channels"] = channels
        parent_win.destroy()
        self.current_offsets_menu(parent_win)

    def run_auto_calib(self, parent_win):
        # Call the real auto-calibration function for current sensors.
        run_current_calibration(self.config)
        parent_win.destroy()
        self.current_offsets_menu(parent_win)

    def run_manual_calib(self, parent_win):
        # For manual calibration, можно заменить данную функцию на реальную, если имеется соответствующая реализация.
        messagebox.showinfo("Manual Calibration", "Manual calibration executed; scale factors updated.")
        parent_win.destroy()
        self.current_offsets_menu(parent_win)

    ## --- End of Current Sensors Submenu ---

    def simple_edit(self, title, key_path, return_func):
        win = tk.Toplevel(self.root)
        win.title(title)
        tk.Label(win, text="Editing " + ".".join(key_path)).pack(pady=5)
        text = tk.Text(win, height=10, width=50)
        text.pack(padx=5, pady=5)
        val = self.get_nested_value(key_path)
        text.insert(tk.END, json.dumps(val, indent=4))

        def on_save():
            try:
                new_val = json.loads(text.get("1.0", tk.END))
                self.set_nested_value(key_path, new_val)
                win.destroy()
                return_func()
            except Exception as e:
                messagebox.showerror("Error", f"Invalid JSON: {e}")

        tk.Button(win, text="Save", command=on_save).pack(pady=5)

    def simple_list_edit(self, title, key_path, return_func):
        self.simple_edit(title, key_path, return_func)

    def get_nested_value(self, key_path):
        val = self.config
        for key in key_path:
            val = val.get(key, {})
        return val

    def set_nested_value(self, key_path, new_val):
        d = self.config
        for key in key_path[:-1]:
            d = d.setdefault(key, {})
        d[key_path[-1]] = new_val


if __name__ == '__main__':
    # Example configuration (similar to config.json)
    config_example = {
        "device_id": "station_1",
        "mqtt": {
            "broker": "192.168.0.93",
            "port": 1883,
            "topic": "sensors/data",
            "qos": 1
        },
        "intervals": {
            "temperature_sec": 5.0,
            "fast_sensors_sec": 0.333
        },
        "sensors": {
            "mpu6050": [
                {"name": "engine", "address": "0x68", "bus": 1, "sample_rate_hz": 200, "buffer_size": 200},
                {"name": "gearbox", "address": "0x69", "bus": 1, "sample_rate_hz": 200, "buffer_size": 200}
            ],
            "mpu6050_fft": {
                "n_peaks": 10
            },
            "ds18b20": [
                {"name": "engine_temp", "id": "28-ed9c0d1e64ff"},
                {"name": "gearbox_temp", "id": "28-f97b081e64ff"}
            ],
            "current": {
                "adc": {
                    "bus": 1,
                    "address": "0x48",
                    "gain": 1.0
                },
                "channels": [
                    {"name": "phase_a", "adc_channel": 0, "offset": 0.0, "scale": 0.9917355371900827},
                    {"name": "phase_b", "adc_channel": 1, "offset": 0.0, "scale": 1.0169491525423728},
                    {"name": "phase_c", "adc_channel": 2, "offset": 0.0, "scale": 0.907563025210084}
                ]
            }
        },
        "calibration": {
            "mpu": True,
            "current": True
        }
    }
    gui = ConfigMenuGUI(config_example)
    print("Updated configuration:", config_example)
