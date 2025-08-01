import pytz

# --- InfluxDB настройки ---
INFLUXDB_URL = "http://192.168.0.93:8086"
INFLUXDB_TOKEN = "mXoOpm9EAmECOpkeDDU7CJh56PYtjYoS-oeOrx2F3X3mErSvileOwl6n-8rSXcWC_eXuh2nm3qWdCI5mDwXUzA=="
INFLUXDB_ORG = "i"
INFLUXDB_BUCKET = "eng_bucket"

# --- Telegram настройки ---
TELEGRAM_TOKEN = "7882919864:AAH9wV2YYW625b9RsQPrzl87wpv8cgPFWVA"
ALLOWED_USER_IDS = [703548391, ]

# --- Список устройств ---
DEVICES = ["station_1", "station_2", "station_3"]

# --- Часовой пояс Москвы ---
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# --- Дефолтные пороги для графиков ---
DEFAULT_THRESHOLDS = {
    "vibration": {"total_rms": 1.25},
    "temperature": {"engine_temp": 80.0},
    "current": {"phase_a": 8.0}
}

# --- Файл для хранения пользовательских порогов ---
SETTINGS_FILE = "thresholds.json"