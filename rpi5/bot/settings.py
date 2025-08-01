import os
import json
from config import SETTINGS_FILE

# Глобальный словарь порогов для устройств
device_thresholds = {}

def load_thresholds():
    """
    Загружает пороги из файла SETTINGS_FILE в device_thresholds.
    Если файл не найден или повреждён — используется пустой словарь.
    """
    global device_thresholds
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                device_thresholds = json.load(f)
            print(f"[DEBUG] Настройки порогов успешно загружены из файла {SETTINGS_FILE}.")
        except Exception as e:
            print(f"[DEBUG] Ошибка загрузки настроек из {SETTINGS_FILE}: {e}")
            device_thresholds = {}
    else:
        device_thresholds = {}
        print(f"[DEBUG] Файл настроек {SETTINGS_FILE} не найден, используется пустой словарь.")

def save_thresholds():
    """
    Сохраняет текущие device_thresholds в файл SETTINGS_FILE.
    """
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(device_thresholds, f, indent=4)
        print(f"[DEBUG] Настройки порогов сохранены в файл {SETTINGS_FILE}.")
    except Exception as e:
        print(f"[DEBUG] Ошибка при сохранении настроек в {SETTINGS_FILE}: {e}")