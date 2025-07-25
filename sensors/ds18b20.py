import glob
import time

class DS18B20:
    def __init__(self, sensor_id=None):
        base_dir = '/sys/bus/w1/devices/'
        if sensor_id:
            self.device_file = f"{base_dir}{sensor_id}/w1_slave"
        else:
            folders = glob.glob(base_dir + '28*')
            if not folders:
                raise RuntimeError("DS18B20 sensor not found")
            self.device_file = folders[0] + '/w1_slave'

    def read_temp_raw(self):
        with open(self.device_file, 'r') as f:
            return f.readlines()

    def get_temperature(self):
        max_attempts = 3
        attempt = 0
        while attempt < max_attempts:
            lines = self.read_temp_raw()
            if len(lines) >= 2 and lines[0].strip()[-3:] == 'YES':
                equals_pos = lines[1].find('t=')
                if equals_pos != -1:
                    temp_string = lines[1][equals_pos + 2:]
                    try:
                        temp_c = float(temp_string) / 1000.0
                        return temp_c
                    except ValueError:
                        pass  # Если преобразование не удалось, пробуем заново.
            attempt += 1
            time.sleep(0.3)  # Задержка перед повторной попыткой
        # Если не удалось получить корректное значение за несколько попыток – можно вернуть ошибку или None.
        raise RuntimeError("Не удалось получить корректное значение температуры")
