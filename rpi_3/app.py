#!/usr/bin/env python3
# restart_app.py
"""Как использовать:
Сохраните этот код в файл restart_app.py
Сделайте файл исполняемым:

chmod +x restart_app.py
Запустите вместо обычного mqtt_sender.py:

python3 restart_app.py
Этот скрипт будет:

Запускать ваше основное приложение mqtt_sender.py
Ждать его завершения
Автоматически перезапускать его через 3 секунды
Корректно обрабатывать сигналы прерывания (Ctrl+C)
Вы можете настроить параметры в начале скрипта:

APP_SCRIPT - имя основного скрипта
RESTART_DELAY - задержка между перезапусками в секундах"""

import os
import sys
import time
import subprocess
import signal

# Путь к основному приложению
APP_SCRIPT = "mqtt_sender.py"
# Время задержки между перезапусками (секунды)
RESTART_DELAY = 3


def run_app():
    """Запускает основное приложение и ждет его завершения"""
    print(f"\n{'=' * 50}")
    print(f"Запуск приложения {APP_SCRIPT}...")
    print(f"{'=' * 50}\n")

    try:
        # Запускаем приложение и ждем его завершения
        process = subprocess.Popen([sys.executable, APP_SCRIPT])
        process.wait()

        # Получаем код возврата
        return_code = process.returncode
        print(f"\n{'=' * 50}")
        print(f"Приложение завершилось с кодом {return_code}")
        print(f"Перезапуск через {RESTART_DELAY} секунд...")
        print(f"{'=' * 50}\n")

        return return_code

    except KeyboardInterrupt:
        # Если пользователь нажал Ctrl+C, передаем сигнал дочернему процессу
        print("\nПолучен сигнал прерывания, завершение приложения...")
        if process.poll() is None:  # Если процесс еще работает
            process.send_signal(signal.SIGINT)
            process.wait()  # Ждем завершения процесса
        return 130  # Стандартный код возврата для SIGINT

    except Exception as e:
        print(f"\nОшибка при запуске приложения: {e}")
        return 1


def main():
    """Основная функция, запускает приложение в цикле"""
    print("Запуск менеджера автоматического перезапуска")
    print("Нажмите Ctrl+C для завершения\n")

    try:
        while True:
            return_code = run_app()

            # Если возвращен код 0, это штатное завершение
            # Если код 130, это SIGINT (Ctrl+C), выходим из цикла
            if return_code == 130:
                print("Получен сигнал завершения. Выход из программы.")
                break

            # Задержка перед перезапуском
            time.sleep(RESTART_DELAY)

    except KeyboardInterrupt:
        print("\nМенеджер перезапуска завершен пользователем")

    print("Программа завершена")


if __name__ == "__main__":
    main()
