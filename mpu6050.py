# sensors/mpu6050.py
# (Assuming this file is placed in a 'sensors' subdirectory)
import smbus2
import time
import math
import numpy as np
# For FFT, if scipy is available and preferred for peak finding:
# from scipy.signal import find_peaks # Example: for more advanced peak finding
# from scipy.fft import rfft, rfftfreq # Alternative to numpy.fft if using scipy

class MPU6050:
    def __init__(self, bus=1, address=0x68, buffer_size=100, sample_rate_hz=100):
        """
        Initialize MPU6050 sensor.
        :param bus: I2C bus number (e.g., 1 for Raspberry Pi default).
        :param address: I2C address of the MPU6050 (e.g., 0x68 or 0x69).
        :param buffer_size: Number of samples to store for RMS, Peak, and FFT calculations.
        :param sample_rate_hz: Desired sample rate in Hz (e.g., 100, 200, 500, 1000).
                               Actual rate may vary slightly based on hardware limits.
        """
        self.bus_num = bus # Store bus number for SMBus initialization
        self.address = address
        self.buffer_size = int(buffer_size) # Ensure integer
        self.configured_sample_rate_hz = float(sample_rate_hz) # Store user-requested rate
        self.actual_sample_rate_hz = self.configured_sample_rate_hz # Will be updated after sensor init

        if self.buffer_size <= 0:
            print(f"Warning: Invalid buffer_size ({self.buffer_size}), defaulting to 100.")
            self.buffer_size = 100

        # Creating numpy arrays filled with zeros for buffers
        self.accel_buffer_x = np.zeros(self.buffer_size)
        self.accel_buffer_y = np.zeros(self.buffer_size)
        self.accel_buffer_z = np.zeros(self.buffer_size)
        self._buffer_index = 0  # Index for cyclic writing to the buffer
        self._buffer_filled_once = False # Track if buffer has been filled at least once

        # Offset values calculated during calibration (in 'g')
        self.accel_offset = {'x': 0.0, 'y': 0.0, 'z': 0.0}

        # Accelerometer sensitivity (LSB/g for +/- 2g range by default)
        self.accel_sensitivity = 16384.0
        # Gyroscope sensitivity (LSB/deg/s for +/- 250 deg/s range by default)
        self.gyro_sensitivity = 131.0

        self._initialize_sensor()
        print(f"MPU6050 '{self.address:02x}' initialized on bus {self.bus_num}.")


    def _initialize_sensor(self):
        try:
            self.bus = smbus2.SMBus(self.bus_num) # Initialize SMBus here
        except FileNotFoundError:
            print(f"Error: I2C bus {self.bus_num} not found. Check Raspberry Pi I2C configuration.")
            raise

        # Check WHO_AM_I register
        try:
            who_am_i = self.bus.read_byte_data(self.address, 0x75)
            # Common MPU6050 WHO_AM_I values are 0x68. Some clones might differ.
            # Address itself might be read on some boards.
            if who_am_i not in [0x68, 0x72, self.address]: # 0x72 for MPU6000, 0x68 for MPU6050
                 print(f"Warning: MPU6050 at 0x{self.address:02x} returned WHO_AM_I=0x{who_am_i:02x}. Expected 0x68.")
            # print(f"MPU6050 connection successful at address 0x{self.address:02x}")
        except Exception as e:
            print(f"Error: MPU6050 not found or connection failed at 0x{self.address:02x} on bus {self.bus_num}. {e}")
            if self.bus: self.bus.close()
            raise ConnectionError(f"MPU6050 communication error at 0x{self.address:02x}") from e

        # Wake up MPU6050 (clear sleep bit)
        self.bus.write_byte_data(self.address, 0x6B, 0) # PWR_MGMT_1 register
        time.sleep(0.1) # Wait for sensor to stabilize

        # Set Digital Low Pass Filter (DLPF)
        # 0x01: Accel BW 184Hz, Gyro BW 188Hz. Internal sample rate becomes 1kHz.
        # Other values offer different bandwidths. 184Hz is a good starting point.
        self.bus.write_byte_data(self.address, 0x1A, 0x01) # CONFIG register

        # Set Sample Rate Divider (SMPLRT_DIV)
        # Sample Rate = Gyroscope Output Rate / (1 + SMPLRT_DIV)
        # Gyroscope Output Rate is 8kHz when DLPF_CFG = 0 or 7 (DLPF disabled)
        # Gyroscope Output Rate is 1kHz when DLPF_CFG is 1-6 (DLPF enabled)
        # We set DLPF_CFG=0x01, so Gyro Output Rate = 1kHz.
        if self.configured_sample_rate_hz <= 0:
            print(f"Warning: Invalid configured_sample_rate_hz ({self.configured_sample_rate_hz}), defaulting to 100Hz.")
            self.configured_sample_rate_hz = 100.0

        # SMPLRT_DIV = (1000 / Desired Sample Rate) - 1
        smplrt_div = int((1000.0 / self.configured_sample_rate_hz) - 1)

        if smplrt_div < 0: smplrt_div = 0      # Max sample rate is 1kHz
        if smplrt_div > 255: smplrt_div = 255  # Min sample rate approx 3.9Hz
        self.bus.write_byte_data(self.address, 0x19, smplrt_div)
        self.actual_sample_rate_hz = 1000.0 / (1 + smplrt_div)

        print(f"MPU6050 at 0x{self.address:02x}: Configured DLPF Accel BW ~184Hz. Actual SampleRate ~{self.actual_sample_rate_hz:.2f}Hz.")


    def read_raw_data(self, reg):
        # Read two bytes (high and low) and combine them
        high = self.bus.read_byte_data(self.address, reg)
        low = self.bus.read_byte_data(self.address, reg + 1)
        value = (high << 8) + low
        # Convert to signed 16-bit integer
        if value >= 0x8000: # or value > 32767
            value -= 65536
        return value

    def get_accel_data_raw(self):
        """Reads raw 16-bit accelerometer data for X, Y, Z axes."""
        ax_raw = self.read_raw_data(0x3B) # ACCEL_XOUT_H
        ay_raw = self.read_raw_data(0x3D) # ACCEL_YOUT_H
        az_raw = self.read_raw_data(0x3F) # ACCEL_ZOUT_H
        return {'x': ax_raw, 'y': ay_raw, 'z': az_raw}

    def get_accel_data(self):
        """
        Reads accelerometer data and converts it to 'g's, applying calibration offsets.
        Default sensitivity is for +/- 2g range (AFS_SEL=0).
        """
        raw_data = self.get_accel_data_raw()
        ax = raw_data['x'] / self.accel_sensitivity - self.accel_offset['x']
        ay = raw_data['y'] / self.accel_sensitivity - self.accel_offset['y']
        az = raw_data['z'] / self.accel_sensitivity - self.accel_offset['z']
        return {'x': ax, 'y': ay, 'z': az}

    def get_gyro_data(self):
        """
        Reads gyroscope data and converts it to degrees/second.
        Default sensitivity is for +/- 250 deg/s range (FS_SEL=0).
        """
        gx = self.read_raw_data(0x43) / self.gyro_sensitivity # GYRO_XOUT_H
        gy = self.read_raw_data(0x45) / self.gyro_sensitivity # GYRO_YOUT_H
        gz = self.read_raw_data(0x47) / self.gyro_sensitivity # GYRO_ZOUT_H
        return {'x': gx, 'y': gy, 'z': gz}

    def calibrate(self, samples=200):
        """
        Performs accelerometer calibration by averaging 'samples' readings
        while the sensor is stationary. The calculated averages (including gravity)
        are stored as offsets.
        """
        print(f"Calibrating MPU6050 at 0x{self.address:02x}... Ensure sensor is STABLE.")
        print(f"Collecting {samples} samples for accelerometer offset calibration...")
        sum_accel_scaled = {'x': 0.0, 'y': 0.0, 'z': 0.0}

        # Calculate delay based on actual sample rate for collecting samples
        # Add a small margin (e.g., 10%) to ensure sensor has time to update its registers
        sample_interval = 1.0 / self.actual_sample_rate_hz
        delay = sample_interval * 1.1 # Wait slightly longer than one sample period

        for i in range(samples):
            # Read raw data, convert to 'g' but *without* applying existing offsets yet
            raw = self.get_accel_data_raw()
            sum_accel_scaled['x'] += raw['x'] / self.accel_sensitivity
            sum_accel_scaled['y'] += raw['y'] / self.accel_sensitivity
            sum_accel_scaled['z'] += raw['z'] / self.accel_sensitivity
            time.sleep(delay)
            if (i + 1) % (samples // 10 or 1) == 0:
                print(f"Calibration progress: {i+1}/{samples} samples collected...")


        # Calculate average 'g' values and store them as offsets
        self.accel_offset['x'] = sum_accel_scaled['x'] / samples
        self.accel_offset['y'] = sum_accel_scaled['y'] / samples
        self.accel_offset['z'] = sum_accel_scaled['z'] / samples

        print(f"MPU6050 at 0x{self.address:02x} calibration completed.")
        print(f"Calculated offsets (g): x={self.accel_offset['x']:.4f}, y={self.accel_offset['y']:.4f}, z={self.accel_offset['z']:.4f}")
        print("These offsets (including gravity component) will be subtracted from subsequent readings.")

        # Clear data buffers after calibration
        self.accel_buffer_x.fill(0)
        self.accel_buffer_y.fill(0)
        self.accel_buffer_z.fill(0)
        self._buffer_index = 0
        self._buffer_filled_once = False

    def update_buffer(self):
        """
        Reads corrected acceleration data (in 'g's) and updates cyclic buffers.
        """
        accel = self.get_accel_data() # This already applies offsets

        self.accel_buffer_x[self._buffer_index] = accel['x']
        self.accel_buffer_y[self._buffer_index] = accel['y']
        self.accel_buffer_z[self._buffer_index] = accel['z']

        self._buffer_index += 1
        if self._buffer_index >= self.buffer_size:
            self._buffer_index = 0
            self._buffer_filled_once = True # Mark buffer as filled at least once

    def _perform_fft(self, data_buffer, n_peaks=5):
        """
        Performs FFT on the given data buffer and returns the top N peaks.
        :param data_buffer: Numpy array of time-domain data.
        :param n_peaks: Number of dominant peaks (frequency, amplitude) to return.
        :return: List of dictionaries, e.g., [{"freq": HZ, "amp": G}, ...]
        """
        # Ensure buffer has meaningful data
        # Allow FFT even if not fully filled, but results might be less stable
        current_data_length = self.buffer_size if self._buffer_filled_once else self._buffer_index
        if current_data_length < self.buffer_size * 0.5: # Require at least half buffer for some stability
             # print(f"FFT: Not enough data ({current_data_length}/{self.buffer_size}), skipping.")
             return []

        # Use the actual data collected so far if buffer is not full yet
        # For FFT, it's best if N is a power of 2, but numpy handles other sizes.
        # Using the full buffer (even if part is zeros before first fill) simplifies frequency scaling.
        # So, we'll always use self.buffer_size for FFT length and self.actual_sample_rate_hz.

        # Apply Hanning window to reduce spectral leakage
        # Window should be applied to the actual signal part if not fully filled,
        # but for simplicity and if buffer fills quickly, apply to whole buffer.
        window = np.hanning(self.buffer_size)
        windowed_data = data_buffer * window # Element-wise multiplication

        # Perform FFT (Fast Fourier Transform)
        # N_fft is the number of points for FFT, typically buffer size
        N_fft = self.buffer_size
        # For real-valued input, rfft is more efficient (returns half spectrum)
        yf = np.fft.rfft(windowed_data)
        # Calculate corresponding frequencies for the rfft output
        xf = np.fft.rfftfreq(N_fft, 1.0 / self.actual_sample_rate_hz)

        # Calculate amplitude spectrum
        # Magnitudes are scaled: divide by N_fft, then multiply by 2 for single-sided spectrum.
        # The DC component (xf[0]) and Nyquist component (if N_fft is even, xf[-1]) are not doubled.
        amplitudes = np.abs(yf) / N_fft
        if N_fft > 1 : # Avoid index error for tiny buffers, though unlikely
            amplitudes[1:len(amplitudes)-(1 if N_fft%2==0 else 0)] *= 2.0


        # Find peaks (simple approach: sort by amplitude)
        # We typically ignore the DC component (xf[0], amplitudes[0]) for vibration.
        # Create pairs of (frequency, amplitude) excluding DC
        spectrum_data = []
        for i in range(1, len(xf)): # Start from index 1 to skip DC
            spectrum_data.append({'freq': xf[i], 'amp': amplitudes[i]})

        # Sort by amplitude in descending order
        spectrum_data.sort(key=lambda item: item['amp'], reverse=True)

        # Select top N peaks
        fft_peaks_result = []
        for i in range(min(n_peaks, len(spectrum_data))):
            peak_freq = spectrum_data[i]['freq']
            peak_amp = spectrum_data[i]['amp']
            # Optional: filter out very low amplitude peaks if desired
            # if peak_amp < 0.0001: continue # Example threshold
            fft_peaks_result.append({"freq": round(peak_freq, 2), "amp": round(peak_amp, 5)})

        return fft_peaks_result

    def get_vibration_metrics(self, n_fft_peaks=5):
        """
        Computes RMS, Peak, Peak-to-Peak for each axis, and FFT peaks
        for the axis with the highest RMS value, from the current buffer content.
        :param n_fft_peaks: Number of dominant FFT peaks to report.
        :return: Dictionary containing all computed metrics.
        """
        # Create local references to buffers for readability (no copy needed for numpy read)
        buf_x, buf_y, buf_z = self.accel_buffer_x, self.accel_buffer_y, self.accel_buffer_z

        # Calculate RMS for each axis
        rms_x = np.sqrt(np.mean(buf_x**2))
        rms_y = np.sqrt(np.mean(buf_y**2))
        rms_z = np.sqrt(np.mean(buf_z**2))

        # Calculate Total RMS (Overall Vibration Level)
        total_rms = np.sqrt(rms_x**2 + rms_y**2 + rms_z**2)

        # Calculate Peak (Maximum Absolute Value) for each axis
        peak_x = np.max(np.abs(buf_x))
        peak_y = np.max(np.abs(buf_y))
        peak_z = np.max(np.abs(buf_z))

        # Calculate Peak-to-Peak (Maximum - Minimum) for each axis
        peak_to_peak_x = np.max(buf_x) - np.min(buf_x)
        peak_to_peak_y = np.max(buf_y) - np.min(buf_y)
        peak_to_peak_z = np.max(buf_z) - np.min(buf_z)

        # Perform FFT on the axis with the highest RMS value
        # This gives a general idea of dominant frequencies in the overall vibration.
        dominant_axis_data = buf_z # Default to Z-axis
        max_rms = rms_z
        if rms_x > max_rms:
            dominant_axis_data = buf_x
            max_rms = rms_x
        if rms_y > max_rms:
            dominant_axis_data = buf_y

        fft_peaks = self._perform_fft(dominant_axis_data, n_peaks=n_fft_peaks)

        # Round values for cleaner output
        dp_metrics = 4 # Decimal places for RMS, Peak, PTP
        metrics = {
            "total_rms": round(total_rms, dp_metrics),
            "rms_x": round(rms_x, dp_metrics),
            "rms_y": round(rms_y, dp_metrics),
            "rms_z": round(rms_z, dp_metrics),
            "peak_x": round(peak_x, dp_metrics),
            "peak_y": round(peak_y, dp_metrics),
            "peak_z": round(peak_z, dp_metrics),
            "peak_to_peak_x": round(peak_to_peak_x, dp_metrics),
            "peak_to_peak_y": round(peak_to_peak_y, dp_metrics),
            "peak_to_peak_z": round(peak_to_peak_z, dp_metrics),
            "fft_peaks": fft_peaks # Already rounded in _perform_fft
        }
        return metrics

    def close(self):
        """Closes the I2C bus connection."""
        if hasattr(self, 'bus') and self.bus:
            try:
                self.bus.close()
                print(f"I2C bus for MPU6050 at 0x{self.address:02x} closed.")
            except Exception as e:
                print(f"Error closing I2C bus for MPU6050 at 0x{self.address:02x}: {e}")
        self.bus = None


# Example Usage (for testing mpu6050.py directly):
if __name__ == '__main__':
    try:
        # Test with default address 0x68, buffer 200 samples, sample rate 200Hz
        mpu = MPU6050(bus=1, address=0x68, buffer_size=200, sample_rate_hz=200)
        # mpu2 = MPU6050(bus=1, address=0x69, buffer_size=100, sample_rate_hz=100) # For second sensor

        print("\nAttempting calibration (keep sensor still)...")
        mpu.calibrate(samples=200)
        # mpu2.calibrate(samples=100)

        print("\nStarting data acquisition loop (Ctrl+C to stop)...")
        publish_interval = 1.0 # seconds, how often to get and print metrics
        last_publish_time = time.time()

        # Determine how often to call update_buffer based on its internal sample rate
        # update_buffer itself is quick, it just reads and stores one sample.
        # The mpu's internal registers update at self.actual_sample_rate_hz
        update_loop_delay = 1.0 / mpu.actual_sample_rate_hz # Call update_buffer at sensor's rate

        while True:
            start_loop_time = time.time()

            mpu.update_buffer()
            # mpu2.update_buffer()

            current_time = time.time()
            if (current_time - last_publish_time) >= publish_interval:
                print("-" * 30)
                print(f"Timestamp: {current_time:.2f}")

                metrics1 = mpu.get_vibration_metrics(n_fft_peaks=5)
                print(f"Metrics for MPU at 0x{mpu.address:02x}:")
                for key, value in metrics1.items():
                    if key == "fft_peaks":
                        print(f"  {key}:")
                        for peak in value:
                            print(f"    - Freq: {peak['freq']:.2f} Hz, Amp: {peak['amp']:.5f} g")
                    else:
                        print(f"  {key}: {value}")

                # metrics2 = mpu2.get_vibration_metrics(n_fft_peaks=3)
                # print(f"Metrics for MPU at 0x{mpu2.address:02x}: {metrics2}")

                last_publish_time = current_time
                print("-" * 30)

            # Sleep to control the rate of update_buffer calls
            loop_duration = time.time() - start_loop_time
            sleep_time = update_loop_delay - loop_duration
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\nStopping data acquisition.")
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'mpu' in locals() and mpu:
            mpu.close()
        # if 'mpu2' in locals() and mpu2:
        #     mpu2.close()