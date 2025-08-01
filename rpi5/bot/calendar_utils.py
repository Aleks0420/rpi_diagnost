from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import calendar

def generate_calendar(year: int, month: int, prefix: str) -> InlineKeyboardMarkup:
    """
    Генерирует inline-календарь для выбора даты.
    :param year: Год календаря
    :param month: Месяц календаря
    :param prefix: Префикс для callback_data (например, "startcal" или "endcal")
    :return: InlineKeyboardMarkup с календарём
    """
    keyboard = []

    # Заголовок с месяцем и годом
    header = [InlineKeyboardButton(f"{calendar.month_name[month]} {year}", callback_data="IGNORE")]
    keyboard.append(header)

    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(day, callback_data="IGNORE") for day in week_days])

    # Календарь месяца
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

    # Кнопки навигации по месяцам
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