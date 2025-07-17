import glob

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
        lines = self.read_temp_raw()
        while lines[0].strip()[-3:] != 'YES':
            lines = self.read_temp_raw()
        equals_pos = lines[1].find('t=')
        if equals_pos != -1:
            temp_string = lines[1][equals_pos + 2:]
            temp_c = float(temp_string) / 1000.0
            return temp_c
