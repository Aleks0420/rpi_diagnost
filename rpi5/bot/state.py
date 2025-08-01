# Список всех состояний для ConversationHandler
(
    SELECTING_DEVICE,           # 0
    SELECTING_SENSORS,          # 1
    SELECTING_RANGE,            # 2
    ENTERING_START_DATE,        # 3
    ENTERING_START_TIME,        # 4
    ENTERING_END_DATE,          # 5
    ENTERING_END_TIME,          # 6
    SELECTING_START_DATE_OPTION,# 7
    SELECTING_START_DATE_CALENDAR, # 8
    SELECTING_END_DATE_OPTION,  # 9
    SELECTING_END_DATE_CALENDAR,# 10
    SETTINGS,                   # 11
    EDIT_VIBRATION,             # 12
    EDIT_TEMPERATURE,           # 13
    EDIT_CURRENT,               # 14
    SELECTING_CURRENT_PHASE     # 15
) = range(16)

# Кэш пользовательских данных (выборы пользователя, временные значения и т.д.)
user_data_cache = {}