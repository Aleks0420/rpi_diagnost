from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from settings import device_thresholds, save_thresholds
from config import DEFAULT_THRESHOLDS
from state import (
    SETTINGS, EDIT_VIBRATION, EDIT_TEMPERATURE, EDIT_CURRENT,
    user_data_cache, SELECTING_DEVICE
)

# --- Главное меню настроек ---
async def settings_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
    else:
        query = None

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    device_id = user_data_cache.get(user_id, {}).get("device_id")

    if not device_id:
        if query:
            await query.edit_message_text(
                f"Пользователь: {username} (ID: {user_id})\nОшибка: Устройство не выбрано. Начните с команды /start.")
        else:
            await update.message.reply_text(
                f"Пользователь: {username} (ID: {user_id})\nОшибка: Устройство не выбрано. Начните с команды /start.")
        return SELECTING_DEVICE

    # Инициализация порогов по умолчанию, если их нет
    if device_id not in device_thresholds:
        device_thresholds[device_id] = {
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
        }

    current_settings = device_thresholds[device_id]
    text = (f"Пользователь: {username} (ID: {user_id})\n"
            f"Настройки для {device_id}:\n"
            f"Вибрация (engine): {current_settings['vibration'].get('engine')}\n"
            f"Вибрация (gearbox): {current_settings['vibration'].get('gearbox')}\n"
            f"Температура (engine_temp): {current_settings['temperature'].get('engine_temp')}\n"
            f"Температура (gearbox_temp): {current_settings['temperature'].get('gearbox_temp')}\n"
            f"Ток (phase_a): {current_settings['current'].get('phase_a')}\n"
            f"Ток (phase_b): {current_settings['current'].get('phase_b')}\n"
            f"Ток (phase_c): {current_settings['current'].get('phase_c')}\n"
            "Выберите параметр для изменения:")
    kb = [
        [InlineKeyboardButton("Изменить вибрацию", callback_data="edit_vib")],
        [InlineKeyboardButton("Изменить температуру", callback_data="edit_temp")],
        [InlineKeyboardButton("Изменить ток", callback_data="edit_curr")],
        [InlineKeyboardButton("Вернуться", callback_data="settings_back")]
    ]
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return SETTINGS

# --- Меню выбора датчика вибрации ---
async def edit_vibration_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("Изменить порог для engine", callback_data="edit_vib_engine")],
        [InlineKeyboardButton("Изменить порог для gearbox", callback_data="edit_vib_gearbox")],
        [InlineKeyboardButton("Вернуться", callback_data="settings_back")]
    ]
    await query.edit_message_text("Выберите датчик для изменения порога вибрации:", reply_markup=InlineKeyboardMarkup(kb))
    return EDIT_VIBRATION

# --- Выбор конкретного датчика вибрации ---
async def select_vib_sensor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # "edit_vib_engine" или "edit_vib_gearbox"
    sensor_type = "engine" if "engine" in data else "gearbox"
    user_id = update.effective_user.id
    user_data_cache.setdefault(user_id, {})["vib_sensor"] = sensor_type
    await query.edit_message_text(f"Введите новое значение порога вибрации для {sensor_type}:")
    return EDIT_VIBRATION

# --- Обработка ввода нового порога вибрации ---
async def process_edit_vibration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    device_id = user_data_cache.get(user_id, {}).get("device_id")
    vib_sensor = user_data_cache.get(user_id, {}).get("vib_sensor")

    if not device_id or not vib_sensor:
        await update.message.reply_text(
            f"Пользователь: {username} (ID: {user_id})\nОшибка: не выбран датчик или устройство. Начните с команды /start.")
        return SELECTING_DEVICE
    try:
        new_val = float(update.message.text)
        device_thresholds[device_id]["vibration"][vib_sensor] = new_val
        await update.message.reply_text(
            f"Пользователь: {username} (ID: {user_id})\nПорог вибрации для {vib_sensor} на {device_id} обновлён до {new_val}.")
        save_thresholds()
    except ValueError:
        await update.message.reply_text(f"Пользователь: {username} (ID: {user_id})\nНеверное значение. Введите число:")
        return EDIT_VIBRATION
    return await settings_selected(update, context)

# --- Меню выбора датчика температуры ---
async def edit_temperature_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("Изменить порог для engine_temp", callback_data="edit_temp_engine")],
        [InlineKeyboardButton("Изменить порог для gearbox_temp", callback_data="edit_temp_gearbox")],
        [InlineKeyboardButton("Вернуться", callback_data="settings_back")]
    ]
    await query.edit_message_text("Выберите датчик для изменения порога температуры:", reply_markup=InlineKeyboardMarkup(kb))
    return EDIT_TEMPERATURE

# --- Выбор конкретного датчика температуры ---
async def select_temp_sensor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # "edit_temp_engine" или "edit_temp_gearbox"
    sensor_type = "engine_temp" if "engine" in data else "gearbox_temp"
    user_id = update.effective_user.id
    user_data_cache.setdefault(user_id, {})["temp_sensor"] = sensor_type
    await query.edit_message_text(f"Введите новое значение порога температуры для {sensor_type}:")
    return EDIT_TEMPERATURE

# --- Обработка ввода нового порога температуры ---
async def process_edit_temperature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    device_id = user_data_cache.get(user_id, {}).get("device_id")
    temp_sensor = user_data_cache.get(user_id, {}).get("temp_sensor")

    if not device_id or not temp_sensor:
        await update.message.reply_text(
            f"Пользователь: {username} (ID: {user_id})\nОшибка: не выбран датчик или устройство. Начните с команды /start.")
        return SELECTING_DEVICE
    try:
        new_val = float(update.message.text)
        device_thresholds[device_id]["temperature"][temp_sensor] = new_val
        await update.message.reply_text(
            f"Пользователь: {username} (ID: {user_id})\nПорог температуры для {temp_sensor} на {device_id} обновлён до {new_val}.")
        save_thresholds()
    except ValueError:
        await update.message.reply_text(f"Пользователь: {username} (ID: {user_id})\nНеверное значение. Введите число:")
        return EDIT_TEMPERATURE
    return await settings_selected(update, context)

# --- Меню выбора фазы тока ---
async def edit_current_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("Изменить порог для phase_a", callback_data="edit_curr_phase_phase_a")],
        [InlineKeyboardButton("Изменить порог для phase_b", callback_data="edit_curr_phase_phase_b")],
        [InlineKeyboardButton("Изменить порог для phase_c", callback_data="edit_curr_phase_phase_c")],
        [InlineKeyboardButton("Вернуться", callback_data="settings_back")]
    ]
    await query.edit_message_text("Выберите фазу для изменения порога тока:", reply_markup=InlineKeyboardMarkup(kb))
    return EDIT_CURRENT

# --- Выбор конкретной фазы тока ---
async def select_current_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # "edit_curr_phase_phase_a", "edit_curr_phase_phase_b", "edit_curr_phase_phase_c"
    if "phase_a" in data:
        phase = "phase_a"
    elif "phase_b" in data:
        phase = "phase_b"
    elif "phase_c" in data:
        phase = "phase_c"
    else:
        phase = None
    user_id = update.effective_user.id
    user_data_cache.setdefault(user_id, {})["current_phase"] = phase
    try:
        if query.message.photo:
            await query.edit_message_caption(f"Введите новое значение порога тока для {phase}:")
        else:
            await query.edit_message_text(f"Введите новое значение порога тока для {phase}:")
    except Exception:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Введите новое значение порога тока для {phase}:")
    return EDIT_CURRENT

# --- Обработка ввода нового порога тока ---
async def process_edit_current(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    device_id = user_data_cache.get(user_id, {}).get("device_id")
    current_phase = user_data_cache.get(user_id, {}).get("current_phase")

    if not device_id or not current_phase:
        await update.message.reply_text(
            f"Пользователь: {username} (ID: {user_id})\nОшибка: не выбрана фаза или устройство. Начните с команды /start.")
        return SELECTING_DEVICE
    try:
        new_val = float(update.message.text)
        device_thresholds[device_id]["current"][current_phase] = new_val
        await update.message.reply_text(
            f"Пользователь: {username} (ID: {user_id})\nПорог тока для {current_phase} на {device_id} обновлён до {new_val}.")
        save_thresholds()
    except ValueError:
        await update.message.reply_text(f"Пользователь: {username} (ID: {user_id})\nНеверное значение. Введите число:")
        return EDIT_CURRENT
    return await settings_selected(update, context)

# --- Возврат в меню выбора устройства ---
async def settings_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from config import DEVICES
    keyboard = [[InlineKeyboardButton(dev, callback_data=f"device_{dev}")] for dev in DEVICES]
    keyboard.append([
        InlineKeyboardButton("Новый запрос", callback_data="new_request"),
        InlineKeyboardButton("Настройки", callback_data="settings")
    ])
    await query.edit_message_text("Select device:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECTING_DEVICE