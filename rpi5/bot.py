import os
import time
import datetime
import pytz
import asyncio
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

# --- InfluxDB Configuration ---
INFLUXDB_URL = "http://192.168.0.93:8086"
INFLUXDB_TOKEN = "mXoOpm9EAmECOpkeDDU7CJh56PYtjYoS-oeOrx2F3X3mErSvileOwl6n-8rSXcWC_eXuh2nm3qWdCI5mDwXUzA=="
INFLUXDB_ORG = "i"
INFLUXDB_BUCKET = "eng_bucket"

# --- Telegram Bot Configuration ---
TELEGRAM_TOKEN = "7882919864:AAH9wV2YYW625b9RsQPrzl87wpv8cgPFWVA"
ALLOWED_USER_IDS = [703548391]

# --- Timezone Configuration ---
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# --- Thresholds for Alerts ---
THRESHOLDS = {
    "vibration": {"total_rms": 1.25},
    "temperature": {"engine_temp": 80.0},
    "current": {"phase_a": 8.0}
}

# --- States for Conversation ---
(SELECTING_DEVICE, SELECTING_SENSORS, SELECTING_RANGE,
 ENTERING_START_DATE, ENTERING_START_TIME,
 ENTERING_END_DATE, ENTERING_END_TIME) = range(7)

user_data_cache = {}  # Cache for user selections

# --------------------------------------------
# InfluxDB Data Fetching and Plot Functions
# --------------------------------------------
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

    # Определяем московский часовой пояс
    moscow_tz = datetime.timezone(datetime.timedelta(hours=3))

    # Определяем границы временного диапазона
    now = datetime.datetime.now(moscow_tz)
    if isinstance(time_range, dict) and "start" in time_range and "stop" in time_range:
        try:
            start_time = datetime.datetime.fromisoformat(time_range["start"].replace("Z", "+00:00")).astimezone(
                moscow_tz)
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

    # Отрисовка данных для каждого датчика
    for i, (sensor_name, data) in enumerate(data_dict.items()):
        if data.empty:
            continue
        # Преобразуем столбец времени в datetime и затем в московское время
        try:
            times = [pd.to_datetime(t).replace(tzinfo=datetime.timezone.utc).astimezone(moscow_tz) for t in
                     data['_time']]
        except Exception as e:
            print(f"Ошибка преобразования времени для {sensor_name}: {e}")
            continue
        values = data['_value'].values

        # Создадим списки с возможными разрывами: если разница между соседними точками больше порога, вставляем NaN
        new_times = []
        new_values = []
        # Рассчитываем средний интервал (если больше одной точки)
        if len(times) > 1:
            deltas = [(times[j + 1] - times[j]).total_seconds() for j in range(len(times) - 1)]
            avg_interval = np.mean(deltas)
        else:
            avg_interval = 0

        # Порог: если интервал > 1.5 * среднего (или, если avg_interval == 0, можно задать фиксированный порог, например, 60 сек)
        gap_threshold = 1.5 * avg_interval if avg_interval > 0 else 60

        for j in range(len(times) - 1):
            new_times.append(times[j])
            new_values.append(values[j])
            delta = (times[j + 1] - times[j]).total_seconds()
            if delta > gap_threshold:
                # Вставляем NaN в качестве разрыва
                # Для временной метки можно взять среднее время между точками
                gap_time = times[j] + (times[j + 1] - times[j]) / 2
                new_times.append(gap_time)
                new_values.append(np.nan)
        # Добавим последнюю точку
        new_times.append(times[-1])
        new_values.append(values[-1])

        plt.plot(new_times, new_values, label=sensor_name, color=colors(i))
        has_plot_elements = True

        if thresholds and sensor_name in thresholds:
            plt.axhline(y=thresholds[sensor_name],
                        color=colors(i),
                        linestyle='--',
                        label=f"{sensor_name} Threshold ({thresholds[sensor_name]})")

    # Устанавливаем границы оси X, чтобы даже если данных не хватает они выставлялись
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

    # Сохраняем график в буфер
    from io import BytesIO
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close()
    return buf


# --------------------------------------------
# Telegram Bot Handlers
# --------------------------------------------
def add_new_request_button(keyboard):
    """Добавляет дополнительную кнопку 'Новый запрос' в нижнюю строку клавиатуры."""
    keyboard.append([InlineKeyboardButton("Новый запрос", callback_data="new_request")])
    return keyboard

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        await update.message.reply_text("Access denied.")
        return ConversationHandler.END
    devices = ["station_1"]
    keyboard = [[InlineKeyboardButton(dev, callback_data=f"device_{dev}")] for dev in devices]
    keyboard = add_new_request_button(keyboard)
    await update.message.reply_text(
        "Select device:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
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
    keyboard = add_new_request_button(keyboard)
    await query.edit_message_text(
        f"Device: {device_id}\nSelect sensor group:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
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
    keyboard = add_new_request_button(keyboard)
    await query.edit_message_text(
        f"Sensor group: {sensor_group}\nSelect time range:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_RANGE

async def range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    time_range = query.data.replace("range_", "")
    if time_range == "custom":
        await query.edit_message_text("Please enter the start date in format YYYY-MM-DD:")
        return ENTERING_START_DATE
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
    return ConversationHandler.END

async def enter_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    start_date_str = update.message.text
    try:
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        user_data_cache[user_id]["start_date"] = start_date
        await update.message.reply_text("Please enter the start time in format HH:MM (Moscow time):")
        return ENTERING_START_TIME
    except ValueError:
        await update.message.reply_text("Invalid date format. Please enter the start date in format YYYY-MM-DD (Moscow time):")
        return ENTERING_START_DATE


async def enter_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    start_time_str = update.message.text
    try:
        start_time = datetime.datetime.strptime(start_time_str, "%H:%M").time()

        # Combine date and time, localize to Moscow timezone, then convert to UTC
        start_date = user_data_cache[user_id]["start_date"]
        start_datetime_moscow = MOSCOW_TZ.localize(datetime.datetime.combine(start_date, start_time))
        start_datetime_utc = start_datetime_moscow.astimezone(pytz.utc)

        user_data_cache[user_id]["start_datetime_utc"] = start_datetime_utc # Save datetime object
        await update.message.reply_text("Please enter the end date in format YYYY-MM-DD (Moscow time):")
        return ENTERING_END_DATE

    except ValueError:
        await update.message.reply_text("Invalid time format. Please enter the start time in format HH:MM (Moscow time):")
        return ENTERING_START_TIME


async def enter_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    end_date_str = update.message.text
    try:
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        user_data_cache[user_id]["end_date"] =  end_date
        await update.message.reply_text("Please enter the end time in format HH:MM (Moscow time):")
        return ENTERING_END_TIME
    except ValueError:
        await update.message.reply_text("Invalid date format. Please enter the end date in format YYYY-MM-DD (Moscow time):")
        return ENTERING_END_DATE


async def enter_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    end_time_str = update.message.text
    try:
        end_time = datetime.datetime.strptime(end_time_str, "%H:%M").time()

        # Combine date and time, localize to Moscow timezone, then convert to UTC
        end_date = user_data_cache[user_id]["end_date"]
        end_datetime_moscow = MOSCOW_TZ.localize(datetime.datetime.combine(end_date, end_time))
        end_datetime_utc = end_datetime_moscow.astimezone(pytz.utc)

        user_data_cache[user_id]["end_datetime_utc"] = end_datetime_utc # Save datetime object

        # Generate the time range for InfluxDB
        time_range = {
            "start": user_data_cache[user_id]["start_datetime_utc"].isoformat().replace("+00:00", "Z"),
            "stop": user_data_cache[user_id]["end_datetime_utc"].isoformat().replace("+00:00", "Z")
        }
        user_data_cache[user_id]["time_range"] = time_range # Save to cache in correct format


        device_id = user_data_cache[user_id]["device_id"]
        sensor_group = user_data_cache[user_id]["sensor_group"]

        await update.message.reply_text("Generating plot(s)...")
        if sensor_group == "all":
            await generate_and_send_plot(update, context, device_id, "vibration", time_range)
            await generate_and_send_plot(update, context, device_id, "temperature", time_range)
            await generate_and_send_plot(update, context, device_id, "current", time_range)
        else:
            await generate_and_send_plot(update, context, device_id, sensor_group, time_range)
        return ConversationHandler.END


    except ValueError:
        await update.message.reply_text("Invalid time format. Please enter the end time in format HH:MM (Moscow time):")
        return ENTERING_END_TIME


async def generate_and_send_plot(update: Update, context: ContextTypes.DEFAULT_TYPE, device_id, sensor_group,
                                 time_range):
    data_dict = {}
    thresholds = {}
    if sensor_group == "vibration":
        for sensor_name in ["engine", "gearbox"]:
            data = query_influx_data(
                measurement="vibration_metrics",
                field="total_rms",
                device_id=device_id,
                sensor_name=sensor_name,
                time_range=time_range
            )
            data_dict[sensor_name] = data
            thresholds[sensor_name] = THRESHOLDS["vibration"]["total_rms"]
    elif sensor_group in ["temp", "temperature"]:
        temp_fields = ["engine_temp", "gearbox_temp"]
        for field in temp_fields:
            data = query_influx_data(
                measurement="temperature",
                field=field,
                device_id=device_id,
                time_range=time_range
            )
            data_dict[field] = data  # Добавляем даже пустые данные
            thresholds[field] = THRESHOLDS["temperature"]["engine_temp"]
    elif sensor_group == "current":
        for sensor_name in ["phase_a", "phase_b", "phase_c"]:
            data = query_influx_data(
                measurement="current",
                field=sensor_name,
                device_id=device_id,
                time_range=time_range
            )
            data_dict[sensor_name] = data
            thresholds[sensor_name] = THRESHOLDS["current"]["phase_a"]

    plot_buf = generate_multi_sensor_plot(
        data_dict,
        title=f"{sensor_group.capitalize()} Data - {device_id}",
        ylabel="Value",
        thresholds=thresholds,
        time_range=time_range  # Передаем time_range в функцию
    )

    # Форматирование диапазона времени для подписи
    moscow_tz = datetime.timezone(datetime.timedelta(hours=3))
    if isinstance(time_range, dict) and "start" in time_range and "stop" in time_range:
        try:
            start_time = datetime.datetime.fromisoformat(time_range["start"].replace("Z", "+00:00"))
            stop_time = datetime.datetime.fromisoformat(time_range["stop"].replace("Z", "+00:00"))
            start_time_moscow = start_time.astimezone(MOSCOW_TZ).strftime('%Y-%m-%d %H:%M:%S')
            stop_time_moscow = stop_time.astimezone(MOSCOW_TZ).strftime('%Y-%m-%d %H:%M:%S')

            display_range = f"from {start_time_moscow} to {stop_time_moscow} (Moscow time)"

        except ValueError:
            display_range = "Invalid custom time range"
    elif isinstance(time_range, str):
        display_range = f"Last {time_range.replace('-', '')} (Moscow time)"
    else:
        display_range = "Unknown time range"

    # Модифицируем только отправку фото, добавив reply_markup
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=plot_buf,
        caption=(f"{sensor_group.capitalize()} data for {device_id}\n"
                f"Time range: {display_range}" +
                (f"\nNo data available in this time range." if not any(not data.empty for data in data_dict.values()) else "")),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Новый запрос", callback_data="new_request")]])
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


async def new_request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Эта функция запускается по команде /new
    return await start(update, context)

# --------------------------------------------
# Обработчик для кнопки "Новый запрос"
# --------------------------------------------
async def new_request_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Полностью очищаем кеш пользователя
    user_id = update.effective_user.id
    if user_id in user_data_cache:
        del user_data_cache[user_id]

    # Удаляем предыдущее сообщение (чтобы избежать дублирования интерфейса)
    try:
        await query.delete_message()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")

    # Запускаем новый запрос через команду /start (полный сброс FSM)
    await start(update, context)
    return SELECTING_DEVICE

# --------------------------------------------
# Глобальный обработчик ошибок
# --------------------------------------------
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Произошла ошибка: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("Возникла ошибка. Попробуйте повторить позже.")
        except Exception:
            pass


async def restart_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полностью перезапускает беседу, создавая новый контекст"""
    await update.callback_query.answer()

    # Очищаем данные пользователя
    user_id = update.effective_user.id
    if user_id in user_data_cache:
        user_data_cache.pop(user_id)

    # Отправляем новое сообщение
    devices = ["station_1"]
    keyboard = [[InlineKeyboardButton(dev, callback_data=f"device_{dev}")] for dev in devices]
    keyboard = add_new_request_button(keyboard)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Starting new request. Select device:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # Возвращаем начальное состояние
    return SELECTING_DEVICE

# --------------------------------------------
# Главная функция с автоперезапуском
# --------------------------------------------
def main():
    while True:
        try:
            app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
            conv_handler = ConversationHandler(
                entry_points=[CommandHandler("start", start)],  # Только /start,
                states={
                    SELECTING_DEVICE: [
                        CallbackQueryHandler(device_selected, pattern=r"^device_"),  # Обрабатывает station_1
                        CallbackQueryHandler(new_request_selected, pattern=r"^new_request$")
                    ],
                    SELECTING_SENSORS: [
                        CallbackQueryHandler(new_request_selected, pattern=r"^new_request$"),
                        CallbackQueryHandler(sensors_selected, pattern=r"^sensor_")
                    ],
                    SELECTING_RANGE: [
                        CallbackQueryHandler(new_request_selected, pattern=r"^new_request$"),
                        CallbackQueryHandler(range_selected, pattern=r"^range_")
                    ],
                    ENTERING_START_DATE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, enter_start_date)
                    ],
                    ENTERING_START_TIME: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, enter_start_time)
                    ],
                    ENTERING_END_DATE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, enter_end_date)
                    ],
                    ENTERING_END_TIME: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, enter_end_time)
                    ]
                },
                fallbacks=[
                    CommandHandler("cancel", cancel),
                    CallbackQueryHandler(new_request_selected, pattern=r"^new_request$")  # Добавляем fallback
                ]
            )
            # Добавляем глобальный обработчик ошибок
            app.add_handler(CallbackQueryHandler(restart_conversation, pattern=r"^new_request$"))
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
