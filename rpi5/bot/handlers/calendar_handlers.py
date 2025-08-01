from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from calendar_utils import generate_calendar
from state import (
    SELECTING_START_DATE_OPTION, SELECTING_START_DATE_CALENDAR,
    ENTERING_START_DATE, ENTERING_START_TIME,
    SELECTING_END_DATE_OPTION, SELECTING_END_DATE_CALENDAR,
    ENTERING_END_DATE, ENTERING_END_TIME,
    user_data_cache
)
import datetime
from config import MOSCOW_TZ

# --- Выбор способа ввода начальной даты ---
async def start_date_option_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "start_option_manual":
        await query.edit_message_text("Введите начальную дату в формате YYYY-MM-DD:")
        return ENTERING_START_DATE
    elif query.data == "start_option_calendar":
        today = datetime.date.today()
        kb = generate_calendar(today.year, today.month, prefix="startcal")
        await query.edit_message_text("Выберите начальную дату:", reply_markup=kb)
        return SELECTING_START_DATE_CALENDAR

# --- Обработка inline-календаря для начальной даты ---
async def start_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

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
        try:
            selected_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            user_data_cache[user_id]["start_date"] = selected_date
            await query.edit_message_text(f"Начальная дата выбрана: {selected_date.isoformat()}")
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="Введите начальное время в формате HH:MM (Moscow time):")
            return ENTERING_START_TIME
        except Exception:
            await query.edit_message_text("Неверный формат даты. Попробуйте еще раз.")
            return SELECTING_START_DATE_CALENDAR

# --- Ручной ввод начальной даты ---
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

# --- Ввод начального времени ---
async def enter_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    start_time_str = update.message.text
    try:
        start_time = datetime.datetime.strptime(start_time_str, "%H:%M").time()
        start_date = user_data_cache[user_id]["start_date"]
        start_dt = MOSCOW_TZ.localize(datetime.datetime.combine(start_date, start_time))
        user_data_cache[user_id]["start_datetime_utc"] = start_dt.astimezone(datetime.timezone.utc)
        # Переход к выбору способа ввода конечной даты
        kb = [
            [InlineKeyboardButton("Календарь", callback_data="end_option_calendar")],
            [InlineKeyboardButton("Ручной ввод", callback_data="end_option_manual")]
        ]
        await update.message.reply_text("Выберите способ ввода конечной даты:", reply_markup=InlineKeyboardMarkup(kb))
        return SELECTING_END_DATE_OPTION
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Введите время в формате HH:MM (Moscow time):")
        return ENTERING_START_TIME

# --- Выбор способа ввода конечной даты ---
async def end_date_option_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "end_option_manual":
        await query.edit_message_text("Введите конечную дату в формате YYYY-MM-DD:")
        return ENTERING_END_DATE
    elif query.data == "end_option_calendar":
        today = datetime.date.today()
        kb = generate_calendar(today.year, today.month, prefix="endcal")
        await query.edit_message_text("Выберите конечную дату:", reply_markup=kb)
        return SELECTING_END_DATE_CALENDAR

# --- Обработка inline-календаря для конечной даты ---
async def end_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

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
        try:
            selected_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            user_data_cache[user_id]["end_date"] = selected_date
            await query.edit_message_text(f"Конечная дата выбрана: {selected_date.isoformat()}")
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="Введите конечное время в формате HH:MM (Moscow time):")
            return ENTERING_END_TIME
        except Exception:
            await query.edit_message_text("Неверный формат даты. Попробуйте еще раз.")
            return SELECTING_END_DATE_CALENDAR

# --- Ручной ввод конечной даты ---
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

# --- Ввод конечного времени и завершение выбора диапазона ---
async def enter_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    end_time_str = update.message.text
    try:
        end_time = datetime.datetime.strptime(end_time_str, "%H:%M").time()
        end_date = user_data_cache[user_id]["end_date"]
        end_dt = MOSCOW_TZ.localize(datetime.datetime.combine(end_date, end_time))
        user_data_cache[user_id]["end_datetime_utc"] = end_dt.astimezone(datetime.timezone.utc)
        time_range = {
            "start": user_data_cache[user_id]["start_datetime_utc"].isoformat().replace("+00:00", "Z"),
            "stop": user_data_cache[user_id]["end_datetime_utc"].isoformat().replace("+00:00", "Z")
        }
        user_data_cache[user_id]["time_range"] = time_range
        device_id = user_data_cache[user_id]["device_id"]
        sensor_group = user_data_cache[user_id]["sensor_group"]

        await update.message.reply_text(f"Пользователь: {username} (ID: {user_id})\nГенерирую график(и)...")

        # Импортируем здесь, чтобы избежать циклических импортов
        from handlers.plot_handlers import generate_and_send_plot, generate_current_plot_with_phase

        if sensor_group == "current" and "current_phase_selected" in user_data_cache[user_id]:
            selected_phase = user_data_cache[user_id]["current_phase_selected"]
            await generate_current_plot_with_phase(update, context, device_id, selected_phase, time_range)
        elif sensor_group == "all":
            await generate_and_send_plot(update, context, device_id, "vibration", time_range)
            await generate_and_send_plot(update, context, device_id, "temperature", time_range)
            await generate_and_send_plot(update, context, device_id, "current", time_range)
        else:
            await generate_and_send_plot(update, context, device_id, sensor_group, time_range)

        from state import SELECTING_DEVICE
        return SELECTING_DEVICE
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Введите время в формате HH:MM (Moscow time):")
        return ENTERING_END_TIME

# --- (Необязательный) обработчик для перехода к выбору конечной даты после ввода начальной ---
async def ask_end_date_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("Календарь", callback_data="end_option_calendar")],
        [InlineKeyboardButton("Ручной ввод", callback_data="end_option_manual")]
    ]
    await update.message.reply_text("Выберите способ ввода конечной даты:", reply_markup=InlineKeyboardMarkup(kb))
    return SELECTING_END_DATE_OPTION