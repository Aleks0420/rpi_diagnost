from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import DEVICES, ALLOWED_USER_IDS
from state import (
    SELECTING_DEVICE, SELECTING_SENSORS, SELECTING_RANGE,
    user_data_cache
)
from handlers.settings_handlers import settings_selected
from handlers.plot_handlers import generate_and_send_plot, generate_current_plot_with_phase, current_selected
from handlers.plot_handlers import current_phase_selected
from handlers.plot_handlers import generate_current_plot

# Сброс состояния пользователя
async def reset_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    user_data_cache.pop(user_id, None)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Пользователь: {username} (ID: {user_id})\nСостояние сброшено. Вы можете начать новую команду."
    )

# Стартовый обработчик
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    user_data_cache.pop(user_id, None)
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text("Access denied.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(dev, callback_data=f"device_{dev}")] for dev in DEVICES]
    keyboard.append([
        InlineKeyboardButton("Новый запрос", callback_data="new_request"),
        InlineKeyboardButton("Настройки", callback_data="settings")
    ])
    await update.message.reply_text(
        f"Здравствуйте, {username}! (ID: {user_id})\nВыберите устройство:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_DEVICE

# Обработчик выбора устройства
async def device_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    device_id = query.data.replace("device_", "")
    user_data_cache[user_id] = {"device_id": device_id}
    keyboard = [
        [InlineKeyboardButton("Vibration", callback_data="sensor_vibration")],
        [InlineKeyboardButton("Temperature", callback_data="sensor_temp")],
        [InlineKeyboardButton("Current", callback_data="sensor_current")],
        [InlineKeyboardButton("All Sensors", callback_data="sensor_all")]
    ]
    keyboard.append([
        InlineKeyboardButton("Новый запрос", callback_data="new_request"),
        InlineKeyboardButton("Настройки", callback_data="settings")
    ])
    await query.edit_message_text(
        f"Пользователь: {username} (ID: {user_id})\nУстройство: {device_id}\nВыберите группу датчиков:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_SENSORS

# Обработчик выбора группы сенсоров
async def sensors_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    sensor_group = query.data.replace("sensor_", "")
    user_data_cache[user_id]["sensor_group"] = sensor_group

    if sensor_group == "current":
        # Переходим к выбору фаз тока
        return await current_selected(update, context)

    keyboard = [
        [InlineKeyboardButton("Last 1 hour", callback_data="range_-1h")],
        [InlineKeyboardButton("Last 24 hours", callback_data="range_-24h")],
        [InlineKeyboardButton("Last 7 days", callback_data="range_-7d")],
        [InlineKeyboardButton("Custom range", callback_data="range_custom")]
    ]
    keyboard.append([
        InlineKeyboardButton("Новый запрос", callback_data="new_request"),
        InlineKeyboardButton("Настройки", callback_data="settings")
    ])
    await query.edit_message_text(
        f"Пользователь: {username} (ID: {user_id})\nГруппа датчиков: {sensor_group}\nВыберите временной диапазон:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_RANGE

# Обработчик выбора диапазона
async def range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    time_range = query.data.replace("range_", "")
    user_data_cache[user_id]["time_range"] = time_range

    if time_range == "custom":
        kb = [
            [InlineKeyboardButton("Календарь", callback_data="start_option_calendar")],
            [InlineKeyboardButton("Ручной ввод", callback_data="start_option_manual")]
        ]
        await query.edit_message_text(
            f"Пользователь: {username} (ID: {user_id})\nВыберите способ ввода начальной даты:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        from state import SELECTING_START_DATE_OPTION
        return SELECTING_START_DATE_OPTION

    device_id = user_data_cache[user_id]["device_id"]
    sensor_group = user_data_cache[user_id]["sensor_group"]

    await query.edit_message_text(f"Пользователь: {username} (ID: {user_id})\nГенерирую график(и)...")

    # Проверяем, был ли выбор фазы тока
    if sensor_group == "current" and "current_phase_selected" in user_data_cache[user_id]:
        selected_phase = user_data_cache[user_id]["current_phase_selected"]
        await generate_current_plot_with_phase(update, context, device_id, selected_phase, time_range)
    elif sensor_group == "all":
        await generate_and_send_plot(update, context, device_id, "vibration", time_range)
        await generate_and_send_plot(update, context, device_id, "temperature", time_range)
        await generate_and_send_plot(update, context, device_id, "current", time_range)
    else:
        await generate_and_send_plot(update, context, device_id, sensor_group, time_range)

    return SELECTING_DEVICE

# Новый запрос (аналогично /start)
async def new_request_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    user_data_cache.pop(user_id, None)
    keyboard = [[InlineKeyboardButton(dev, callback_data=f"device_{dev}")] for dev in DEVICES]
    keyboard.append([
        InlineKeyboardButton("Новый запрос", callback_data="new_request"),
        InlineKeyboardButton("Настройки", callback_data="settings")
    ])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Пользователь: {username} (ID: {user_id})\nВыберите устройство:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_DEVICE

# Отмена/выход
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    if update.message:
        await update.message.reply_text(f"Пользователь: {username} (ID: {user_id})\nOperation cancelled.")
    return ConversationHandler.END