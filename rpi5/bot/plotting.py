import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import datetime
from io import BytesIO
from config import MOSCOW_TZ

def generate_multi_sensor_plot(data_dict, title, ylabel, thresholds=None, time_range=None):
    """
    Строит график для нескольких сенсоров (например, фаз тока или датчиков вибрации/температуры).
    :param data_dict: dict, ключ — имя сенсора, значение — DataFrame с данными
    :param title: str, заголовок графика
    :param ylabel: str, подпись оси Y
    :param thresholds: dict, ключ — имя сенсора, значение — порог
    :param time_range: dict или str, диапазон времени (для подписи и оси X)
    :return: BytesIO с PNG-графиком
    """
    plt.figure(figsize=(12, 6))
    colors = plt.get_cmap("tab10")
    has_plot_elements = False
    moscow_tz = MOSCOW_TZ
    now = datetime.datetime.now(moscow_tz)

    # Определяем временной диапазон для оси X
    if isinstance(time_range, dict) and "start" in time_range and "stop" in time_range:
        try:
            start_time = datetime.datetime.fromisoformat(time_range["start"].replace("Z", "+00:00")).astimezone(moscow_tz)
            stop_time = datetime.datetime.fromisoformat(time_range["stop"].replace("Z", "+00:00")).astimezone(moscow_tz)
        except Exception:
            start_time = now - datetime.timedelta(hours=1)
            stop_time = now
    elif isinstance(time_range, str):
        if time_range == "-1h":
            start_time = now - datetime.timedelta(hours=1)
            stop_time = now
        elif time_range == "-24h":
            start_time = now - datetime.timedelta(hours=24)
            stop_time = now
        elif time_range == "-7d":
            start_time = now - datetime.timedelta(days=7)
            stop_time = now
        else:
            start_time = now - datetime.timedelta(hours=1)
            stop_time = now
    else:
        start_time = now - datetime.timedelta(hours=1)
        stop_time = now

    # Рисуем данные для каждого сенсора
    for i, (sensor_name, data) in enumerate(data_dict.items()):
        if data.empty:
            continue
        try:
            times = [pd.to_datetime(t).replace(tzinfo=datetime.timezone.utc).astimezone(moscow_tz) for t in data['_time']]
        except Exception:
            continue
        values = data['_value'].values

        # Обработка разрывов (если нужно)
        new_times = []
        new_values = []
        if len(times) > 1:
            deltas = [(times[j + 1] - times[j]).total_seconds() for j in range(len(times) - 1)]
            avg_interval = np.mean(deltas)
        else:
            avg_interval = 0
        gap_threshold = 1.5 * avg_interval if avg_interval > 0 else 60
        for j in range(len(times) - 1):
            new_times.append(times[j])
            new_values.append(values[j])
            delta = (times[j + 1] - times[j]).total_seconds()
            if delta > gap_threshold:
                gap_time = times[j] + (times[j + 1] - times[j]) / 2
                new_times.append(gap_time)
                new_values.append(np.nan)
        if times:
            new_times.append(times[-1])
            new_values.append(values[-1])

        plt.plot(new_times, new_values, label=sensor_name, color=colors(i))
        has_plot_elements = True

        # Рисуем порог, если задан
        if thresholds and sensor_name in thresholds:
            threshold_value = thresholds[sensor_name]
            plt.axhline(y=threshold_value, color=colors(i), linestyle='--', label=f"{sensor_name} Threshold ({threshold_value})")

    plt.xlim(start_time, stop_time)

    if not has_plot_elements:
        mid_time = start_time + (stop_time - start_time) / 2
        plt.plot([mid_time], [0], alpha=0)
        plt.text(0.5, 0.5, 'No data available for selected period',
                 horizontalalignment='center', verticalalignment='center',
                 transform=plt.gca().transAxes, fontsize=14, color='gray')

    if has_plot_elements:
        plt.legend()

    plt.title(title)
    plt.xlabel('Time (Moscow, UTC+3)')
    plt.ylabel(ylabel)
    plt.grid(True)
    plt.gca().xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y-%m-%d %H:%M:%S', tz=moscow_tz))
    plt.gcf().autofmt_xdate()
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close()

    return buf