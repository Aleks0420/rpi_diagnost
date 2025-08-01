from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from db import query_influx_data
from plotting import generate_multi_sensor_plot
from settings import device_thresholds
from config import DEFAULT_THRESHOLDS
from state import user_data_cache

def add_global_buttons(keyboard):
    keyboard.append([
        InlineKeyboardButton("Новый запрос", callback_data="new_request"),
        InlineKeyboardButton("Настройки", callback_data="settings")
    ])
    return keyboard

async def generate_and_send_plot(update: Update, context: ContextTypes.DEFAULT_TYPE, device_id, sensor_group, time_range):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"

    import datetime
    moscow_tz = datetime.timezone(datetime.timedelta(hours=3))
    if isinstance(time_range, dict) and "start" in time_range and "stop" in time_range:
        try:
            start_time = datetime.datetime.fromisoformat(time_range["start"].replace("Z", "+00:00"))
            stop_time = datetime.datetime.fromisoformat(time_range["stop"].replace("Z", "+00:00"))
            start_time_moscow = start_time.astimezone(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
            stop_time_moscow = stop_time.astimezone(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
            display_range = f"с {start_time_moscow} по {stop_time_moscow} (Moscow time)"
        except ValueError:
            display_range = "Invalid custom time range"
    elif isinstance(time_range, str):
        display_range = f"Last {time_range.replace('-', '')} (Moscow time)"
    else:
        display_range = "Unknown time range"

    current_thresholds = device_thresholds.get(device_id, {
        "vibration": {
            "engine": DEFAULT_THRESHOLDS["vibration"]["total_rms"],
            "gearbox": DEFAULT_THRESHOLDS["vibration"]["total_rms"]
        },
        "temperature": {
            "engine_temp": DEFAULT_THRESHOLDS["temperature"]["engine_temp"],
            "gearbox_temp": DEFAULT_THRESHOLDS["temperature"]["engine_temp"]
        },
        "current": {
            "phase_a": DEFAULT_THRESHOLDS["current"]["phase_a"],
            "phase_b": DEFAULT_THRESHOLDS["current"]["phase_a"],
            "phase_c": DEFAULT_THRESHOLDS["current"]["phase_a"],
        }
    })

    # --- Ток ---
    if sensor_group == "current":
        if "current_phase_selected" in user_data_cache.get(user_id, {}):
            selected_phase = user_data_cache[user_id]["current_phase_selected"]
            await generate_current_plot_with_phase(update, context, device_id, selected_phase, time_range)
            return

        data_dict = {}
        thresholds = current_thresholds.get("current", DEFAULT_THRESHOLDS["current"])
        for sensor_name in ["phase_a", "phase_b", "phase_c"]:
            data = query_influx_data(
                measurement="current",
                field=sensor_name,
                device_id=device_id,
                time_range=time_range
            )
            data_dict[sensor_name] = data
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
            caption=f"Пользователь: {username} (ID: {user_id})\nCurrent data for {device_id}\nTime range: {display_range}",
            reply_markup=InlineKeyboardMarkup(add_global_buttons([]))
        )

    # --- Вибрация ---
    elif sensor_group == "vibration":
        for sensor_name in ["engine", "gearbox"]:
            data = query_influx_data(
                measurement="vibration_metrics",
                field="total_rms",
                device_id=device_id,
                sensor_name=sensor_name,
                time_range=time_range
            )
            data_dict = {sensor_name: data}
            thresholds = {sensor_name: current_thresholds["vibration"][sensor_name]}
            plot_buf = generate_multi_sensor_plot(
                data_dict,
                title=f"Vibration Data - {sensor_name.capitalize()} ({device_id})",
                ylabel="Acceleration (g)",
                thresholds=thresholds,
                time_range=time_range
            )
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=plot_buf,
                caption=(
                    f"Пользователь: {username} (ID: {user_id})\nVibration data for {sensor_name.capitalize()} ({device_id})\nTime range: {display_range}" +
                    (f"\nNo data available in this time range." if data.empty else "")),
                reply_markup=InlineKeyboardMarkup(add_global_buttons([]))
            )

    # --- Температура ---
    elif sensor_group in ["temp", "temperature"]:
        for sensor_field in ["engine_temp", "gearbox_temp"]:
            data = query_influx_data(
                measurement="temperature",
                field=sensor_field,
                device_id=device_id,
                time_range=time_range
            )
            data_dict = {sensor_field: data}
            thresholds = {sensor_field: current_thresholds["temperature"][sensor_field]}
            plot_buf = generate_multi_sensor_plot(
                data_dict,
                title=f"Temperature Data - {sensor_field.replace('_', ' ').capitalize()} ({device_id})",
                ylabel="Temperature (°C)",
                thresholds=thresholds,
                time_range=time_range
            )
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=plot_buf,
                caption=(
                    f"Пользователь: {username} (ID: {user_id})\nTemperature data for {sensor_field.replace('_', ' ').capitalize()} ({device_id})\nTime range: {display_range}" +
                    (f"\nNo data available in this time range." if data.empty else "")),
                reply_markup=InlineKeyboardMarkup(add_global_buttons([]))
            )

    # --- Неизвестная группа ---
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Пользователь: {username} (ID: {user_id})\nUnknown sensor group: {sensor_group}",
            reply_markup=InlineKeyboardMarkup(add_global_buttons([]))
        )

async def generate_current_plot_with_phase(update: Update, context: ContextTypes.DEFAULT_TYPE, device_id, phase, time_range):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"

    import datetime
    moscow_tz = datetime.timezone(datetime.timedelta(hours=3))
    if isinstance(time_range, dict) and "start" in time_range and "stop" in time_range:
        try:
            start_time = datetime.datetime.fromisoformat(time_range["start"].replace("Z", "+00:00"))
            stop_time = datetime.datetime.fromisoformat(time_range["stop"].replace("Z", "+00:00"))
            start_time_moscow = start_time.astimezone(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
            stop_time_moscow = stop_time.astimezone(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
            display_range = f"с {start_time_moscow} по {stop_time_moscow} (Moscow time)"
        except ValueError:
            display_range = "Invalid custom time range"
    elif isinstance(time_range, str):
        display_range = f"Last {time_range.replace('-', '')} (Moscow time)"
    else:
        display_range = "Unknown time range"

    curr_thresh = device_thresholds.get(device_id, {}).get("current", DEFAULT_THRESHOLDS["current"])
    if not isinstance(curr_thresh, dict):
        curr_thresh = {
            "phase_a": curr_thresh,
            "phase_b": curr_thresh,
            "phase_c": curr_thresh
        }

    if phase == "all":
        data_dict = {}
        for phase_name in ["phase_a", "phase_b", "phase_c"]:
            data = query_influx_data(
                measurement="current",
                field=phase_name,
                device_id=device_id,
                time_range=time_range
            )
            data_dict[phase_name] = data
        thresholds = {phase_name: curr_thresh.get(phase_name, DEFAULT_THRESHOLDS["current"]["phase_a"])
                      for phase_name in ["phase_a", "phase_b", "phase_c"]}
        plot_buf = generate_multi_sensor_plot(
            data_dict,
            title=f"Current Data - All Phases ({device_id})",
            ylabel="Current (A)",
            thresholds=thresholds,
            time_range=time_range
        )
        caption = f"Пользователь: {username} (ID: {user_id})\nCurrent data for all phases ({device_id})\nTime range: {display_range}"
    else:
        data = query_influx_data(
            measurement="current",
            field=phase,
            device_id=device_id,
            time_range=time_range
        )
        threshold = curr_thresh.get(phase, DEFAULT_THRESHOLDS["current"]["phase_a"])
        plot_buf = generate_multi_sensor_plot(
            data_dict={phase: data},
            title=f"Current Data - {phase.replace('phase_', 'Phase ').upper()} ({device_id})",
            ylabel="Current (A)",
            thresholds={phase: threshold},
            time_range=time_range
        )
        caption = f"Пользователь: {username} (ID: {user_id})\nCurrent data for {phase.replace('phase_', 'Phase ')} ({device_id})\nTime range: {display_range}"
        if data.empty:
            caption += "\nNo data available in this time range."

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=plot_buf,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(add_global_buttons([]))
    )

async def current_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    device_id = user_data_cache[user_id]["device_id"]
    user_data_cache[user_id]["sensor_group"] = "current"
    keyboard = [
        [InlineKeyboardButton("Все фазы", callback_data="current_all")],
        [InlineKeyboardButton("Фаза A", callback_data="current_phase_a")],
        [InlineKeyboardButton("Фаза B", callback_data="current_phase_b")],
        [InlineKeyboardButton("Фаза C", callback_data="current_phase_c")],
    ]
    keyboard = add_global_buttons(keyboard)
    await query.edit_message_text(f"Выбрано устройство: {device_id}\nВыберите фазу тока:",
                                  reply_markup=InlineKeyboardMarkup(keyboard))
    from state import SELECTING_CURRENT_PHASE
    return SELECTING_CURRENT_PHASE

async def current_phase_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    phase = query.data.replace("current_", "")
    user_data_cache[user_id]["current_phase_selected"] = phase
    keyboard = [
        [InlineKeyboardButton("Last 1 hour", callback_data="range_-1h")],
        [InlineKeyboardButton("Last 24 hours", callback_data="range_-24h")],
        [InlineKeyboardButton("Last 7 days", callback_data="range_-7d")],
        [InlineKeyboardButton("Custom range", callback_data="range_custom")]
    ]
    keyboard = add_global_buttons(keyboard)
    await query.edit_message_text(f"Выбрана фаза: {phase}\nВыберите временной диапазон:",
                                  reply_markup=InlineKeyboardMarkup(keyboard))
    from state import SELECTING_RANGE
    return SELECTING_RANGE

async def generate_current_plot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    phase = query.data.replace("current_", "")
    user_data_cache[user_id]["current_phase_selected"] = phase
    keyboard = [
        [InlineKeyboardButton("Last 1 hour", callback_data="range_-1h")],
        [InlineKeyboardButton("Last 24 hours", callback_data="range_-24h")],
        [InlineKeyboardButton("Last 7 days", callback_data="range_-7d")],
        [InlineKeyboardButton("Custom range", callback_data="range_custom")]
    ]
    keyboard = add_global_buttons(keyboard)
    phase_display = "всех фаз" if phase == "all" else f"фазы {phase.replace('phase_', '').upper()}"
    await query.edit_message_text(
        f"Выбрано отображение {phase_display}\nВыберите временной диапазон:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    from state import SELECTING_RANGE
    return SELECTING_RANGE