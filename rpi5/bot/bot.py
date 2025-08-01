from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from config import TELEGRAM_TOKEN
from state import (
    SELECTING_DEVICE, SELECTING_SENSORS, SELECTING_RANGE,
    ENTERING_START_DATE, ENTERING_START_TIME,
    ENTERING_END_DATE, ENTERING_END_TIME,
    SELECTING_START_DATE_OPTION, SELECTING_START_DATE_CALENDAR,
    SELECTING_END_DATE_OPTION, SELECTING_END_DATE_CALENDAR,
    SETTINGS, EDIT_VIBRATION, EDIT_TEMPERATURE, EDIT_CURRENT,
    SELECTING_CURRENT_PHASE
)

from settings import load_thresholds
load_thresholds()

from handlers.main_handlers import (
    start, device_selected, sensors_selected, range_selected,
    reset_state, new_request_selected, cancel
)
from handlers.settings_handlers import (
    settings_selected, edit_vibration_selected, select_vib_sensor, process_edit_vibration,
    edit_temperature_selected, select_temp_sensor, process_edit_temperature,
    edit_current_selected, select_current_phase, process_edit_current, settings_back
)
from handlers.plot_handlers import (
    generate_and_send_plot, generate_current_plot_with_phase,
    current_selected, current_phase_selected, generate_current_plot
)
from handlers.calendar_handlers import (
    start_date_option_selected, start_calendar_callback, enter_start_date, enter_start_time,
    end_date_option_selected, end_calendar_callback, enter_end_date, enter_end_time,
    ask_end_date_option
)

import warnings
from influxdb_client.client.warnings import MissingPivotFunction

# Отключаем предупреждение о pivot() от InfluxDB
warnings.simplefilter("ignore", MissingPivotFunction)

async def global_error_handler(update, context):
    # Глобальный обработчик ошибок
    user_id = getattr(update.effective_user, 'id', 'Unknown')
    username = getattr(update.effective_user, 'username', 'Unknown')
    print(f"[ERROR] Ошибка для пользователя {user_id} ({username}): {context.error}")
    import traceback
    traceback.print_exc()
    if update and getattr(update, 'effective_message', None):
        try:
            await update.effective_message.reply_text(
                f"Пользователь: {username} (ID: {user_id})\nВозникла ошибка. Попробуйте повторить позже.")
        except Exception as e:
            print(f"[ERROR] Не удалось отправить сообщение об ошибке: {e}")

def main():
    print("[DEBUG] Запуск Telegram-бота")
    # load_thresholds()  # Загружаем сохраненные пороги

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
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
                CallbackQueryHandler(settings_selected, pattern=r"^settings$"),
                CallbackQueryHandler(current_selected, pattern="^current_"),
            ],
            SELECTING_CURRENT_PHASE: [
                CallbackQueryHandler(current_phase_selected, pattern="^current_"),
                CallbackQueryHandler(new_request_selected, pattern=r"^new_request$"),
                CallbackQueryHandler(settings_selected, pattern=r"^settings$")
            ],
            SELECTING_RANGE: [
                CallbackQueryHandler(new_request_selected, pattern=r"^new_request$"),
                CallbackQueryHandler(range_selected, pattern=r"^range_"),
                CallbackQueryHandler(settings_selected, pattern=r"^settings$"),
                CallbackQueryHandler(generate_current_plot, pattern="^current_"),
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
                CallbackQueryHandler(select_vib_sensor, pattern=r"^edit_vib_(engine|gearbox)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_vibration)
            ],
            EDIT_TEMPERATURE: [
                CallbackQueryHandler(select_temp_sensor, pattern=r"^edit_temp_(engine|gearbox)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_temperature)
            ],
            EDIT_CURRENT: [
                CallbackQueryHandler(select_current_phase, pattern=r"^edit_curr_phase_(phase_a|phase_b|phase_c)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_current)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("reset", reset_state),
            CallbackQueryHandler(new_request_selected, pattern=r"^new_request$"),
            CallbackQueryHandler(settings_selected, pattern=r"^settings$")
        ]
    )

    app.add_handler(conv_handler)
    app.add_error_handler(global_error_handler)

    print("[DEBUG] Бот запущен и готов к работе")
    app.run_polling()

if __name__ == "__main__":
    main()
