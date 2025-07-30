import os
import time
import datetime
import json
import pytz
from io import BytesIO
import matplotlib.pyplot as plt
import pandas as pd
from influxdb_client import InfluxDBClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

# --- Конфигурация InfluxDB ---
INFLUXDB_URL = "http://192.168.0.93:8086"
INFLUXDB_TOKEN = "mXoOpm9EAmECOpkeDDU7CJh56PYtjYoS-oeOrx2F3X3mErSvileOwl6n-8rSXcWC_eXuh2nm3qWdCI5mDwXUzA=="
INFLUXDB_ORG = "i"
INFLUXDB_BUCKET = "eng_bucket"

# --- Конфигурация Telegram бота ---
TELEGRAM_TOKEN = "7882919864:AAH9wV2YYW625b9RsQPrzl87wpv8cgPFWVA"
ALLOWED_USER_IDS = [703548391]

# --- Таймзона ---
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# --- Дефолтные пороги для графиков ---
DEFAULT_THRESHOLDS = {
    "vibration": {"total_rms": 1.25},
    "temperature": {"engine_temp": 80.0},
    "current": {"phase_a": 8.0}
}

# --- Файл настроек ---
SETTINGS_FILE = "thresholds.json"

# --- Глобальный словарь настроек для устройств ---
device_thresholds = {}

# --- States for Conversation ---
(SELECTING_DEVICE, SELECTING_SENSORS, SELECTING_RANGE,
 ENTERING_START_DATE, ENTERING_START_TIME,
 ENTERING_END_DATE, ENTERING_END_TIME,
 SELECTING_START_DATE_OPTION, SELECTING_START_DATE_CALENDAR,
 SELECTING_END_DATE_OPTION, SELECTING_END_DATE_CALENDAR,
 SETTINGS, EDIT_VIBRATION, EDIT_TEMPERATURE, EDIT_CURRENT) = range(15)

user_data_cache = {}  # Сохраняет выборы пользователя

# --------------------------------------------
# Функции загрузки/сохранения настроек
def load_thresholds():
    global device_thresholds
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                device_thresholds = json.load(f)
            print("Настройки порогов успешно загружены из файла.")
        except Exception as e:
            print("Ошибка загрузки настроек:", e)
            device_thresholds = {}
    else:
        device_thresholds = {}
        print("Файл настроек не найден, используется пустой словарь.")

def save_thresholds():
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(device_thresholds, f, indent=4)
        print("Настройки порогов сохранены.")
    except Exception as e:
        print("Ошибка при сохранении настроек:", e)

# --------------------------------------------
# Универсальная функция редактирования/отправки
async def edit_or_send(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    if update.callback_query:
        query = update.callback_query
        try:
            await query.answer()
            await query.edit_message_text(text=text, reply_markup=reply_markup)
        except Exception as e:
            print("Ошибка редактирования сообщения:", e)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup)

# --------------------------------------------
# InfluxDB Data Fetching и функции построения графиков
def query_influx_data(measurement, field, device_id, sensor_name=None, time_range="-1h"):
    if isinstance(time_range, dict) and "start" in time_range and "stop" in time_range:
        range_clause = f'range(start: {time_range["start"]}, stop: {time_range["stop"]})'
    elif isinstance(time_range, str) and time_range.startswith("range("):
        range_clause = time_range
    else:
        range_clause = f'range(start: {time_range})'
    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> {range_clause}
          |> filter(fn: (r) => r._measurement == "{measurement}")
          |> filter(fn: (r) => r._field == "{field}")
          |> filter(fn: (r) => r.device_id == "{device_id}")
    '''
    if sensor_name:
        query += f'|> filter(fn: (r) => r.sensor_name == "{sensor_name}")'
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    result = client.query_api().query_data_frame(query)
    client.close()
    if isinstance(result, list):
        result = pd.concat(result)
    return result

def generate_multi_sensor_plot(data_dict, title, ylabel, thresholds=None, time_range=None):
    import numpy as np
    import matplotlib.pyplot as plt
    import datetime
    plt.figure(figsize=(12, 6))
    colors = plt.cm.get_cmap("tab10")
    has_plot_elements = False
    moscow_tz = datetime.timezone(datetime.timedelta(hours=3))
    now = datetime.datetime.now(moscow_tz)
    if isinstance(time_range, dict) and "start" in time_range and "stop" in time_range:
        try:
            start_time = datetime.datetime.fromisoformat(time_range["start"].replace("Z", "+00:00")).astimezone(moscow_tz)
            stop_time = datetime.datetime.fromisoformat(time_range["stop"].replace("Z", "+00:00")).astimezone(moscow_tz)
        except Exception as e:
            print(f"Ошибка парсинга диапазона времени: {e}")
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
    for i, (sensor_name, data) in enumerate(data_dict.items()):
        if data.empty:
            continue
        try:
            times = [pd.to_datetime(t).replace(tzinfo=datetime.timezone.utc).astimezone(moscow_tz) for t in data['_time']]
        except Exception as e:
            print(f"Ошибка преобразования времени для {sensor_name}: {e}")
            continue
        values = data['_value'].values
        new_times = []
        new_values = []
        if len(times) > 1:
            deltas = [(times[j+1]-times[j]).total_seconds() for j in range(len(times)-1)]
            avg_interval = np.mean(deltas)
        else:
            avg_interval = 0
        gap_threshold = 1.5 * avg_interval if avg_interval > 0 else 60
        for j in range(len(times)-1):
            new_times.append(times[j])
            new_values.append(values[j])
            delta = (times[j+1]-times[j]).total_seconds()
            if delta > gap_threshold:
                gap_time = times[j] + (times[j+1]-times[j])/2
                new_times.append(gap_time)
                new_values.append(np.nan)
        new_times.append(times[-1])
        new_values.append(values[-1])
        plt.plot(new_times, new_values, label=sensor_name, color=colors(i))
        has_plot_elements = True
        if thresholds and sensor_name in thresholds:
            plt.axhline(y=thresholds[sensor_name],
                        color=colors(i),
                        linestyle='--',
                        label=f"{sensor_name} Threshold ({thresholds[sensor_name]})")
    plt.xlim(start_time, stop_time)
    if not has_plot_elements:
        mid_time = start_time + (stop_time - start_time)/2
        plt.plot([mid_time],[0],alpha=0)
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
    from io import BytesIO
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close()
    return buf

# --------------------------------------------
# Функция генерации inline-календаря
def generate_calendar(year: int, month: int, prefix: str) -> InlineKeyboardMarkup:
    import calendar
    keyboard = []
    header = [InlineKeyboardButton(f"{calendar.month_name[month]} {year}", callback_data="IGNORE")]
    keyboard.append(header)
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(day, callback_data="IGNORE") for day in week_days])
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="IGNORE"))
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
                row.append(InlineKeyboardButton(str(day), callback_data=f"{prefix}_{date_str}"))
        keyboard.append(row)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    nav = [
        InlineKeyboardButton("<", callback_data=f"{prefix}_NAV_{prev_year}-{prev_month:02d}"),
        InlineKeyboardButton(" ", callback_data="IGNORE"),
        InlineKeyboardButton(">", callback_data=f"{prefix}_NAV_{next_year}-{next_month:02d}")
    ]
    keyboard.append(nav)
    return InlineKeyboardMarkup(keyboard)

# Функция добавления глобальных кнопок (Новый запрос и Настройки)
def add_global_buttons(keyboard):
    keyboard.append([
        InlineKeyboardButton("Новый запрос", callback_data="new_request"),
        InlineKeyboardButton("Настройки", callback_data="settings")
    ])
    return keyboard

# --------------------------------------------
# Telegram Bot Handlers

async def reset_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбрасывает состояние пользователя и очищает кэш."""
    user_id = update.effective_user.id
    user_data_cache.pop(user_id, None)  # Очистка пользовательских данных
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Состояние сброшено. Вы можете начать новую команду."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start. Всегда начинает новый сеанс."""
    # Сбрасываем состояние пользователя
    await reset_state(update, context)

    # Проверяем, разрешён ли доступ пользователю
    if update.effective_user.id not in ALLOWED_USER_IDS:
        await update.message.reply_text("Access denied.")
        return ConversationHandler.END

    devices = ["station_1", "station_2", "station_3"]
    keyboard = [[InlineKeyboardButton(dev, callback_data=f"device_{dev}")] for dev in devices]
    keyboard = add_global_buttons(keyboard)
    await update.message.reply_text("Select device:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECTING_DEVICE

async def device_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    device_id = query.data.replace("device_", "")
    user_data_cache[update.effective_user.id] = {"device_id": device_id}
    keyboard = [
        [InlineKeyboardButton("Vibration", callback_data="sensor_vibration")],
        [InlineKeyboardButton("Temperature", callback_data="sensor_temp")],
        [InlineKeyboardButton("Current", callback_data="sensor_current")],
        [InlineKeyboardButton("All Sensors", callback_data="sensor_all")]
    ]
    keyboard = add_global_buttons(keyboard)
    await query.edit_message_text(f"Device: {device_id}\nSelect sensor group:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECTING_SENSORS

async def sensors_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    sensor_group = query.data.replace("sensor_", "")
    user_data_cache[user_id]["sensor_group"] = sensor_group
    keyboard = [
        [InlineKeyboardButton("Last 1 hour", callback_data="range_-1h")],
        [InlineKeyboardButton("Last 24 hours", callback_data="range_-24h")],
        [InlineKeyboardButton("Last 7 days", callback_data="range_-7d")],
        [InlineKeyboardButton("Custom range", callback_data="range_custom")]
    ]
    keyboard = add_global_buttons(keyboard)
    await query.edit_message_text(f"Sensor group: {sensor_group}\nSelect time range:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECTING_RANGE

async def range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    time_range = query.data.replace("range_", "")
    if time_range == "custom":
        kb = [
            [InlineKeyboardButton("Календарь", callback_data="start_option_calendar")],
            [InlineKeyboardButton("Ручной ввод", callback_data="start_option_manual")]
        ]
        await query.edit_message_text("Выберите способ ввода начальной даты:", reply_markup=InlineKeyboardMarkup(kb))
        return SELECTING_START_DATE_OPTION
    user_data_cache[user_id]["time_range"] = time_range
    device_id = user_data_cache[user_id]["device_id"]
    sensor_group = user_data_cache[user_id]["sensor_group"]
    await query.edit_message_text("Generating plot(s)...")
    if sensor_group == "all":
        await generate_and_send_plot(update, context, device_id, "vibration", time_range)
        await generate_and_send_plot(update, context, device_id, "temperature", time_range)
        await generate_and_send_plot(update, context, device_id, "current", time_range)
    else:
        await generate_and_send_plot(update, context, device_id, sensor_group, time_range)
    return SELECTING_DEVICE

# --- Начальная дата ---
async def start_date_option_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "start_option_manual":
        await query.edit_message_text("Введите начальную дату в формате YYYY-MM-DD:")
        return ENTERING_START_DATE
    elif query.data == "start_option_calendar":
        today = datetime.date.today()
        kb = generate_calendar(today.year, today.month, prefix="startcal")
        await query.edit_message_text("Выберите начальную дату:", reply_markup=kb)
        return SELECTING_START_DATE_CALENDAR

async def start_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("startcal_NAV_"):
        date_part = data.split("_")[-1]
        year_str, month_str = date_part.split("-")
        year = int(year_str)
        month = int(month_str)
        kb = generate_calendar(year, month, prefix="startcal")
        await query.edit_message_reply_markup(reply_markup=kb)
        return SELECTING_START_DATE_CALENDAR
    else:
        _, date_str = data.split("_", 1)
        user_id = update.effective_user.id
        try:
            selected_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception as e:
            await query.edit_message_text("Неверный формат даты. Попробуйте еще раз.")
            return SELECTING_START_DATE_CALENDAR
        user_data_cache[user_id]["start_date"] = selected_date
        await query.edit_message_text(f"Начальная дата выбрана: {selected_date.isoformat()}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Введите начальное время в формате HH:MM (Moscow time):")
        return ENTERING_START_TIME

# --- Конечная дата ---
async def ask_end_date_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("Календарь", callback_data="end_option_calendar")],
        [InlineKeyboardButton("Ручной ввод", callback_data="end_option_manual")]
    ]
    await update.message.reply_text("Выберите способ ввода конечной даты:", reply_markup=InlineKeyboardMarkup(kb))
    return SELECTING_END_DATE_OPTION

async def end_date_option_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "end_option_manual":
        await query.edit_message_text("Введите конечную дату в формате YYYY-MM-DD:")
        return ENTERING_END_DATE
    elif query.data == "end_option_calendar":
        today = datetime.date.today()
        kb = generate_calendar(today.year, today.month, prefix="endcal")
        await query.edit_message_text("Выберите конечную дату:", reply_markup=kb)
        return SELECTING_END_DATE_CALENDAR

async def end_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("endcal_NAV_"):
        date_part = data.split("_")[-1]
        year_str, month_str = date_part.split("-")
        year = int(year_str)
        month = int(month_str)
        kb = generate_calendar(year, month, prefix="endcal")
        await query.edit_message_reply_markup(reply_markup=kb)
        return SELECTING_END_DATE_CALENDAR
    else:
        _, date_str = data.split("_", 1)
        user_id = update.effective_user.id
        try:
            selected_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception as e:
            await query.edit_message_text("Неверный формат даты. Попробуйте еще раз.")
            return SELECTING_END_DATE_CALENDAR
        user_data_cache[user_id]["end_date"] = selected_date
        await query.edit_message_text(f"Конечная дата выбрана: {selected_date.isoformat()}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Введите конечное время в формате HH:MM (Moscow time):")
        return ENTERING_END_TIME

async def enter_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    start_date_str = update.message.text
    try:
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        user_data_cache[user_id]["start_date"] = start_date
        await update.message.reply_text("Введите начальное время в формате HH:MM (Moscow time):")
        return ENTERING_START_TIME
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Введите дату в формате YYYY-MM-DD:")
        return ENTERING_START_DATE

async def enter_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    start_time_str = update.message.text
    try:
        start_time = datetime.datetime.strptime(start_time_str, "%H:%M").time()
        start_date = user_data_cache[user_id]["start_date"]
        start_dt = MOSCOW_TZ.localize(datetime.datetime.combine(start_date, start_time))
        user_data_cache[user_id]["start_datetime_utc"] = start_dt.astimezone(pytz.utc)
        await update.message.reply_text("Теперь выберите метод ввода конечной даты:")
        kb = [
            [InlineKeyboardButton("Календарь", callback_data="end_option_calendar")],
            [InlineKeyboardButton("Ручной ввод", callback_data="end_option_manual")]
        ]
        await update.message.reply_text("Выберите способ ввода конечной даты:", reply_markup=InlineKeyboardMarkup(kb))
        return SELECTING_END_DATE_OPTION
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Введите время в формате HH:MM (Moscow time):")
        return ENTERING_START_TIME

async def enter_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    end_date_str = update.message.text
    try:
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        user_data_cache[user_id]["end_date"] = end_date
        await update.message.reply_text("Введите конечное время в формате HH:MM (Moscow time):")
        return ENTERING_END_TIME
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Введите дату в формате YYYY-MM-DD:")
        return ENTERING_END_DATE

async def enter_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    end_time_str = update.message.text
    try:
        end_time = datetime.datetime.strptime(end_time_str, "%H:%M").time()
        end_date = user_data_cache[user_id]["end_date"]
        end_dt = MOSCOW_TZ.localize(datetime.datetime.combine(end_date, end_time))
        user_data_cache[user_id]["end_datetime_utc"] = end_dt.astimezone(pytz.utc)
        time_range = {
            "start": user_data_cache[user_id]["start_datetime_utc"].isoformat().replace("+00:00", "Z"),
            "stop": user_data_cache[user_id]["end_datetime_utc"].isoformat().replace("+00:00", "Z")
        }
        user_data_cache[user_id]["time_range"] = time_range
        device_id = user_data_cache[user_id]["device_id"]
        sensor_group = user_data_cache[user_id]["sensor_group"]
        await update.message.reply_text("Generating plot(s)...")
        if sensor_group == "all":
            await generate_and_send_plot(update, context, device_id, "vibration", time_range)
            await generate_and_send_plot(update, context, device_id, "temperature", time_range)
            await generate_and_send_plot(update, context, device_id, "current", time_range)
        else:
            await generate_and_send_plot(update, context, device_id, sensor_group, time_range)
        return SELECTING_DEVICE
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Введите время в формате HH:MM (Moscow time):")
        return ENTERING_END_TIME


async def generate_and_send_plot(update: Update, context: ContextTypes.DEFAULT_TYPE, device_id, sensor_group, time_range):
    """Генерирует и отправляет графики по выбранной группе сенсоров."""
    # Проверяем настройки для выбранного устройства
    if device_id in device_thresholds:
        current_thresholds = device_thresholds[device_id]
    else:
        current_thresholds = {
            "vibration": DEFAULT_THRESHOLDS["vibration"]["total_rms"],
            "temperature": DEFAULT_THRESHOLDS["temperature"]["engine_temp"],
            "current": DEFAULT_THRESHOLDS["current"]["phase_a"]
        }

    # Графики по вибрации для каждого сенсора отдельно
    if sensor_group == "vibration":
        for sensor_name in ["engine", "gearbox"]:
            # Подготовка данных для текущего сенсора
            data = query_influx_data(
                measurement="vibration_metrics",
                field="total_rms",
                device_id=device_id,
                sensor_name=sensor_name,
                time_range=time_range
            )
            data_dict = {sensor_name: data}
            thresholds = {sensor_name: current_thresholds["vibration"]}

            # Генерация графика
            plot_buf = generate_multi_sensor_plot(
                data_dict,
                title=f"Vibration Data - {sensor_name.capitalize()} ({device_id})",
                ylabel="Acceleration (g)",
                thresholds=thresholds,
                time_range=time_range
            )

            # Отправка графика
            moscow_tz = datetime.timezone(datetime.timedelta(hours=3))
            if isinstance(time_range, dict) and "start" in time_range and "stop" in time_range:
                try:
                    start_time = datetime.datetime.fromisoformat(time_range["start"].replace("Z", "+00:00"))
                    stop_time = datetime.datetime.fromisoformat(time_range["stop"].replace("Z", "+00:00"))
                    start_time_moscow = start_time.astimezone(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
                    stop_time_moscow = stop_time.astimezone(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
                    display_range = f"from {start_time_moscow} to {stop_time_moscow} (Moscow time)"
                except ValueError:
                    display_range = "Invalid custom time range"
            elif isinstance(time_range, str):
                display_range = f"Last {time_range.replace('-', '')} (Moscow time)"
            else:
                display_range = "Unknown time range"

            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=plot_buf,
                caption=(f"Vibration data for {sensor_name.capitalize()} ({device_id})\nTime range: {display_range}" +
                         (f"\nNo data available in this time range." if data.empty else "")),
                reply_markup=InlineKeyboardMarkup(add_global_buttons([]))
            )

    # Графики для температурных сенсоров
    elif sensor_group in ["temp", "temperature"]:
        data_dict = {}
        thresholds = {}
        for field in ["engine_temp", "gearbox_temp"]:
            data = query_influx_data(
                measurement="temperature",
                field=field,
                device_id=device_id,
                time_range=time_range
            )
            data_dict[field] = data
            thresholds[field] = current_thresholds["temperature"]

        plot_buf = generate_multi_sensor_plot(
            data_dict,
            title=f"Temperature Data ({device_id})",
            ylabel="Temperature (°C)",
            thresholds=thresholds,
            time_range=time_range
        )

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=plot_buf,
            caption=f"Temperature data for {device_id}\nTime range: {time_range}",
            reply_markup=InlineKeyboardMarkup(add_global_buttons([]))
        )

    # Графики для токовых сенсоров
    elif sensor_group == "current":
        data_dict = {}
        thresholds = {}
        for sensor_name in ["phase_a", "phase_b", "phase_c"]:
            data = query_influx_data(
                measurement="current",
                field=sensor_name,
                device_id=device_id,
                time_range=time_range
            )
            data_dict[sensor_name] = data
            thresholds[sensor_name] = current_thresholds["current"]

        plot_buf = generate_multi_sensor_plot(
            data_dict,
            title=f"Current Data ({device_id})",
            ylabel="Current (A)",
            thresholds=thresholds,
            time_range=time_range
        )

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=plot_buf,
            caption=f"Current data for {device_id}\nTime range: {time_range}",
            reply_markup=InlineKeyboardMarkup(add_global_buttons([]))
        )
# Обработчик "Новый запрос"
async def new_request_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для начала нового запроса. Аналогично /start."""
    query = update.callback_query
    await query.answer()
    await reset_state(update, context)

    devices = ["station_1", "station_2", "station_3"]
    keyboard = [[InlineKeyboardButton(dev, callback_data=f"device_{dev}")] for dev in devices]
    keyboard = add_global_buttons(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Select device:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_DEVICE

# --- Обработчик "Настройки" и редактирования порогов ---
async def settings_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для перехода в настройки устройства."""
    if update.callback_query:
        query = update.callback_query
        try:
            await query.answer()
        except Exception as e:
            print("Ошибка в settings_selected:", e)

    # Получаем ID пользователя и устройство
    user_id = update.effective_user.id
    device_id = user_data_cache.get(user_id, {}).get("device_id")

    # Если device_id отсутствует, возвращаем сообщение об ошибке
    if not device_id:
        await update.callback_query.edit_message_text(
            "Ошибка: Устройство не выбрано. Начните с команды /start."
        )
        return SELECTING_DEVICE

    # Проверяем, есть ли настройки для устройства, если нет — создаём с дефолтными значениями
    if device_id not in device_thresholds:
        device_thresholds[device_id] = {
            "vibration": DEFAULT_THRESHOLDS["vibration"]["total_rms"],
            "temperature": DEFAULT_THRESHOLDS["temperature"]["engine_temp"],
            "current": DEFAULT_THRESHOLDS["current"]["phase_a"]
        }

    # Отображаем текущие настройки
    current_settings = device_thresholds[device_id]
    text = (f"Настройки для {device_id}:\n"
            f"Вибрация (total_rms): {current_settings['vibration']}\n"
            f"Температура (engine_temp): {current_settings['temperature']}\n"
            f"Ток (phase_a): {current_settings['current']}\n"
            "Выберите параметр для изменения:")

    kb = [
        [InlineKeyboardButton("Изменить вибрацию", callback_data="edit_vib")],
        [InlineKeyboardButton("Изменить температуру", callback_data="edit_temp")],
        [InlineKeyboardButton("Изменить ток", callback_data="edit_curr")],
        [InlineKeyboardButton("Вернуться", callback_data="settings_back")]
    ]
    reply_markup = InlineKeyboardMarkup(kb)

    await edit_or_send(update, context, text, reply_markup)
    return SETTINGS

async def edit_vibration_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите новое значение порога вибрации (total_rms):")
    return EDIT_VIBRATION

async def edit_temperature_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите новое значение порога температуры (engine_temp):")
    return EDIT_TEMPERATURE

async def edit_current_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите новое значение порога тока (phase_a):")
    return EDIT_CURRENT

async def process_edit_vibration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    device_id = user_data_cache.get(user_id, {}).get("device_id")

    # Если device_id отсутствует
    if not device_id:
        await update.message.reply_text("Ошибка: Устройство не выбрано. Начните с команды /start.")
        return SELECTING_DEVICE

    try:
        new_val = float(update.message.text)
        device_thresholds[device_id]["vibration"] = new_val
        await update.message.reply_text(f"Порог вибрации для {device_id} обновлён до {new_val}.")
        save_thresholds()  # Сохранение в файл
    except ValueError:
        await update.message.reply_text("Неверное значение. Введите число:")
        return EDIT_VIBRATION

    return await settings_selected(update, context)

async def process_edit_temperature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    device_id = user_data_cache.get(user_id, {}).get("device_id")

    if not device_id:
        await update.message.reply_text("Ошибка: Устройство не выбрано. Начните с команды /start.")
        return SELECTING_DEVICE

    try:
        new_val = float(update.message.text)
        device_thresholds[device_id]["temperature"] = new_val
        await update.message.reply_text(f"Порог температуры для {device_id} обновлён до {new_val}.")
        save_thresholds()
    except ValueError:
        await update.message.reply_text("Неверное значение. Введите число:")
        return EDIT_TEMPERATURE

    return await settings_selected(update, context)

async def process_edit_current(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    device_id = user_data_cache.get(user_id, {}).get("device_id")

    if not device_id:
        await update.message.reply_text("Ошибка: Устройство не выбрано. Начните с команды /start.")
        return SELECTING_DEVICE

    try:
        new_val = float(update.message.text)
        device_thresholds[device_id]["current"] = new_val
        await update.message.reply_text(f"Порог тока для {device_id} обновлён до {new_val}.")
        save_thresholds()
    except ValueError:
        await update.message.reply_text("Неверное значение. Введите число:")
        return EDIT_CURRENT

    return await settings_selected(update, context)

async def settings_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    devices = ["station_1", "station_2", "station_3"]
    keyboard = [[InlineKeyboardButton(dev, callback_data=f"device_{dev}")] for dev in devices]
    keyboard = add_global_buttons(keyboard)
    await query.edit_message_text("Select device:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECTING_DEVICE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Произошла ошибка: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("Возникла ошибка. Попробуйте повторить позже.")
        except Exception:
            pass


def main():
    load_thresholds()  # Загружаем сохраненные пороговые значения

    while True:
        try:
            app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

            conv_handler = ConversationHandler(
                entry_points=[
                    CommandHandler("start", start),  # Обработчик команды /start
                ],
                states={
                    SELECTING_DEVICE: [
                        CallbackQueryHandler(device_selected, pattern=r"^device_"),
                        CallbackQueryHandler(new_request_selected, pattern=r"^new_request$"),
                        CallbackQueryHandler(settings_selected, pattern=r"^settings$")
                    ],
                    SELECTING_SENSORS: [
                        CallbackQueryHandler(new_request_selected, pattern=r"^new_request$"),
                        CallbackQueryHandler(sensors_selected, pattern=r"^sensor_"),
                        CallbackQueryHandler(settings_selected, pattern=r"^settings$")
                    ],
                    SELECTING_RANGE: [
                        CallbackQueryHandler(new_request_selected, pattern=r"^new_request$"),
                        CallbackQueryHandler(range_selected, pattern=r"^range_"),
                        CallbackQueryHandler(settings_selected, pattern=r"^settings$")
                    ],
                    SELECTING_START_DATE_OPTION: [
                        CallbackQueryHandler(start_date_option_selected, pattern=r"^start_option_"),
                        CallbackQueryHandler(settings_selected, pattern=r"^settings$")
                    ],
                    SELECTING_START_DATE_CALENDAR: [
                        CallbackQueryHandler(start_calendar_callback, pattern=r"^startcal_"),
                        CallbackQueryHandler(settings_selected, pattern=r"^settings$")
                    ],
                    ENTERING_START_DATE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, enter_start_date)
                    ],
                    ENTERING_START_TIME: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, enter_start_time)
                    ],
                    SELECTING_END_DATE_OPTION: [
                        CallbackQueryHandler(end_date_option_selected, pattern=r"^end_option_"),
                        CallbackQueryHandler(settings_selected, pattern=r"^settings$")
                    ],
                    SELECTING_END_DATE_CALENDAR: [
                        CallbackQueryHandler(end_calendar_callback, pattern=r"^endcal_"),
                        CallbackQueryHandler(settings_selected, pattern=r"^settings$")
                    ],
                    ENTERING_END_DATE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, enter_end_date)
                    ],
                    ENTERING_END_TIME: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, enter_end_time)
                    ],
                    SETTINGS: [
                        CallbackQueryHandler(edit_vibration_selected, pattern=r"^edit_vib$"),
                        CallbackQueryHandler(edit_temperature_selected, pattern=r"^edit_temp$"),
                        CallbackQueryHandler(edit_current_selected, pattern=r"^edit_curr$"),
                        CallbackQueryHandler(settings_back, pattern=r"^settings_back$"),
                        CallbackQueryHandler(new_request_selected, pattern=r"^new_request$"),
                        CallbackQueryHandler(settings_selected, pattern=r"^settings$")
                    ],
                    EDIT_VIBRATION: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_vibration)
                    ],
                    EDIT_TEMPERATURE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_temperature)
                    ],
                    EDIT_CURRENT: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_current)
                    ]
                },
                fallbacks=[
                    CommandHandler("cancel", cancel),
                    CommandHandler("start", start),  # Позволяет сбросить состояние через /start
                    CallbackQueryHandler(new_request_selected, pattern=r"^new_request$"),
                    CallbackQueryHandler(settings_selected, pattern=r"^settings$")
                ]
            )

            app.add_handler(conv_handler)
            app.add_error_handler(global_error_handler)

            print("Bot started")
            app.run_polling()

        except Exception as e:
            print("Бот обнаружил фатальную ошибку и перезапускается:", e)
            time.sleep(5)
            print("Перезапуск бота...")

if __name__ == "__main__":
    main()
