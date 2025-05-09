# vibration_processor.py

import math
from collections import deque

class VibrationProcessor:
    def __init__(self, window_size=10):
        """
        Initialize vibration processor with buffers for engine and gearbox.
        Also includes calibration offsets to remove gravity and static bias.
        """
        self.window_size = window_size

        # Buffers to store acceleration vector magnitudes
        self.engine_buffer = deque(maxlen=window_size)
        self.gearbox_buffer = deque(maxlen=window_size)

        # Offset values for calibration (gravity, sensor bias)
        self.engine_offset = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.gearbox_offset = {"x": 0.0, "y": 0.0, "z": 0.0}

        # Flags and storage for calibration process
        self.calibrated = False
        self.calibration_samples = {
            "engine": {"x": [], "y": [], "z": []},
            "gearbox": {"x": [], "y": [], "z": []}
        }
        
    def _safe_float(self, value):
        """
        Safely convert a value to float. Return 0.0 if conversion fails.
        """
        try:
            return float(value) if isinstance(value, (int, float)) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _vector_magnitude(self, x, y, z):
        """
        Compute the magnitude of a 3D vector.
        Used to combine x, y, z into a single vibration value.
        """
        return math.sqrt(x**2 + y**2 + z**2)

    def _calculate_rms(self, buffer):
        """
        Calculate the Root Mean Square (RMS) of values in the buffer.
        """
        if not buffer:
            return 0.0
        squares = [v ** 2 for v in buffer]
        return math.sqrt(sum(squares) / len(squares))

    def calibrate(self, vibration_data):
        """
        Collect samples for calibration and calculate offset
        after enough samples (e.g., 50).
        """
        engine = vibration_data.get("engine", {}).get("accel", {})
        gearbox = vibration_data.get("gearbox", {}).get("accel", {})

        for axis in ["x", "y", "z"]:
            self.calibration_samples["engine"][axis].append(self._safe_float(engine.get(axis)))
            self.calibration_samples["gearbox"][axis].append(self._safe_float(gearbox.get(axis)))

        # When enough calibration samples are collected
        if len(self.calibration_samples["engine"]["x"]) >= 50:
            for axis in ["x", "y", "z"]:
                self.engine_offset[axis] = sum(self.calibration_samples["engine"][axis]) / 50
                self.gearbox_offset[axis] = sum(self.calibration_samples["gearbox"][axis]) / 50

            self.calibrated = True
            print("??? Calibration complete.")

    def update(self, vibration_data):
        """
        Process new vibration data and return current RMS values.
        If not calibrated yet, perform calibration first.
        Returns:
            {
                "engine_vibration_rms": float,
                "gearbox_vibration_rms": float
            }
        """
        if not self.calibrated:
            self.calibrate(vibration_data)
            return {
                "engine_vibration_rms": 0.0,
                "gearbox_vibration_rms": 0.0
            }

        engine = vibration_data.get("engine", {}).get("accel", {})
        gearbox = vibration_data.get("gearbox", {}).get("accel", {})

        # Subtract offsets to remove gravity and static components
        engine_vec = self._vector_magnitude(
            self._safe_float(engine.get("x")) - self.engine_offset["x"],
            self._safe_float(engine.get("y")) - self.engine_offset["y"],
            self._safe_float(engine.get("z")) - self.engine_offset["z"]
        )
        gearbox_vec = self._vector_magnitude(
            self._safe_float(gearbox.get("x")) - self.gearbox_offset["x"],
            self._safe_float(gearbox.get("y")) - self.gearbox_offset["y"],
            self._safe_float(gearbox.get("z")) - self.gearbox_offset["z"]
        )

        # Add to buffer
        self.engine_buffer.append(engine_vec)
        self.gearbox_buffer.append(gearbox_vec)

        # Calculate RMS from buffer
        engine_rms = self._calculate_rms(self.engine_buffer)
        gearbox_rms = self._calculate_rms(self.gearbox_buffer)

        return {
            "engine_vibration_rms": round(engine_rms, 4),
            "gearbox_vibration_rms": round(gearbox_rms, 4)
        }
