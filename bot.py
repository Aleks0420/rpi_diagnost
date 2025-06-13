import os
import time
import datetime
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
    ConversationHandler
)

# --- InfluxDB Configuration ---
INFLUXDB_URL = "http://192.168.0.93:8086"
INFLUXDB_TOKEN = ""  # Access token
INFLUXDB_ORG = "i"  # Organization
INFLUXDB_BUCKET = "eng_bucket"  # Data bucket

# --- Telegram Bot Configuration ---
TELEGRAM_TOKEN = ""
ALLOWED_USER_IDS = [703548391]  # Allowed user IDs

# --- Thresholds for Alerts ---
THRESHOLDS = {
    "vibration": {"total_rms": 2.0},
    "temperature": {"engine_temp": 80.0},
    "current": {"phase_a": 15.0}
}

# --- States for Conversation ---
SELECTING_DEVICE, SELECTING_SENSORS, SELECTING_RANGE = range(3)
user_data_cache = {}  # Cache for user selections


# =============================================
# InfluxDB Data Fetching Functions
# =============================================

def query_influx_data(measurement, field, device_id, sensor_name=None, time_range="-1h"):
    """
    Query data from InfluxDB and return as DataFrame.
    Args:
        measurement: e.g., "vibration_metrics"
        field: e.g., "total_rms"
        device_id: e.g., "station_1"
        sensor_name: Optional (for vibration sensors)
        time_range: Influx time range syntax (e.g., "-1h")
    Returns:
        pandas.DataFrame with '_time' and '_value' columns
    """
    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: {time_range})
          |> filter(fn: (r) => r._measurement == "{measurement}")
          |> filter(fn: (r) => r._field == "{field}")
          |> filter(fn: (r) => r.device_id == "{device_id}")
    '''
    if sensor_name:
        query += f'|> filter(fn: (r) => r.sensor_name == "{sensor_name}")'

    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    result = client.query_api().query_data_frame(query)
    client.close()

    # Ensure consistent column names
    if isinstance(result, list):
        result = pd.concat(result)
    return result


# =============================================
# Plot Generation Functions
# =============================================

def generate_multi_sensor_plot(data_dict, title, ylabel, thresholds=None):
    """
    Generate a matplotlib plot for multiple sensors.
    Args:
        data_dict: Dictionary where keys are sensor names and values are DataFrames.
        title: Plot title.
        ylabel: Y-axis label.
        thresholds: Optional dictionary of thresholds for each sensor.
    Returns:
        BytesIO buffer with PNG image.
    """
    plt.figure(figsize=(12, 6))

    colors = plt.cm.get_cmap("tab10")  # Use matplotlib's colormap for different colors

    for i, (sensor_name, data) in enumerate(data_dict.items()):
        if data.empty:
            continue
        plt.plot(data['_time'], data['_value'], label=sensor_name, color=colors(i))

        if thresholds and sensor_name in thresholds:
            plt.axhline(y=thresholds[sensor_name],
                        color=colors(i),
                        linestyle='--',
                        label=f"{sensor_name} Threshold ({thresholds[sensor_name]})")

    plt.title(title)
    plt.xlabel('Time')
    plt.ylabel(ylabel)
    plt.grid(True)
    plt.legend()

    # Rotate x-axis labels for better readability
    plt.xticks(rotation=45)
    plt.tight_layout()

    # Save to buffer
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close()
    return buf


# =============================================
# Telegram Bot Handlers
# =============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - show device selection menu."""
    if update.effective_user.id not in ALLOWED_USER_IDS:
        await update.message.reply_text("Access denied.")
        return ConversationHandler.END

    # Get available devices from InfluxDB
    devices = ["station_1"]  # In production: query InfluxDB for unique device_id values

    keyboard = [
        [InlineKeyboardButton(dev, callback_data=f"device_{dev}")]
        for dev in devices
    ]

    await update.message.reply_text(
        "Select device:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_DEVICE


async def device_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle device selection."""
    query = update.callback_query
    await query.answer()

    device_id = query.data.replace("device_", "")
    user_data_cache[update.effective_user.id] = {"device_id": device_id}

    # Show sensor selection menu
    keyboard = [
        [InlineKeyboardButton("Vibration", callback_data="sensor_vibration")],
        [InlineKeyboardButton("Temperature", callback_data="sensor_temp")],
        [InlineKeyboardButton("Current", callback_data="sensor_current")],
        [InlineKeyboardButton("All Sensors", callback_data="sensor_all")]
    ]

    await query.edit_message_text(
        f"Device: {device_id}\nSelect sensor group:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_SENSORS


async def sensors_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle sensor group selection and show time range options."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    sensor_group = query.data.replace("sensor_", "")
    user_data_cache[user_id]["sensor_group"] = sensor_group

    # Show time range selection
    keyboard = [
        [InlineKeyboardButton("Last 1 hour", callback_data="range_-1h")],
        [InlineKeyboardButton("Last 24 hours", callback_data="range_-24h")],
        [InlineKeyboardButton("Last 7 days", callback_data="range_-7d")],
        [InlineKeyboardButton("Custom range", callback_data="range_custom")]  # Custom range not implemented yet
    ]

    await query.edit_message_text(
        f"Sensor group: {sensor_group}\nSelect time range:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_RANGE


async def range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle time range selection and generate plot."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    time_range = query.data.replace("range_", "")
    user_data_cache[user_id]["time_range"] = time_range

    device_id = user_data_cache[user_id]["device_id"]
    sensor_group = user_data_cache[user_id]["sensor_group"]

    await query.edit_message_text("Generating plot...")

    # Fetch data for selected sensors
    data_dict = {}
    thresholds = {}

    if sensor_group in ["vibration", "all"]:
        for sensor_name in ["engine", "gearbox"]:  # Example vibration sensors
            data = query_influx_data(
                measurement="vibration_metrics",
                field="total_rms",
                device_id=device_id,
                sensor_name=sensor_name,
                time_range=time_range
            )
            data_dict[sensor_name] = data
            thresholds[sensor_name] = THRESHOLDS["vibration"]["total_rms"]

    if sensor_group in ["temperature", "all"]:
        for sensor_name in ["engine_temp", "gearbox_temp"]:
            data = query_influx_data(
                measurement="temperature",
                field=sensor_name,
                device_id=device_id,
                time_range=time_range
            )
            data_dict[sensor_name] = data
            thresholds[sensor_name] = THRESHOLDS["temperature"]["engine_temp"]

    if sensor_group in ["current", "all"]:
        for sensor_name in ["phase_a", "phase_b", "phase_c"]:
            data = query_influx_data(
                measurement="current",
                field=sensor_name,
                device_id=device_id,
                time_range=time_range
            )
            data_dict[sensor_name] = data
            thresholds[sensor_name] = THRESHOLDS["current"]["phase_a"]

    # Generate plot
    plot_buf = generate_multi_sensor_plot(
        data_dict,
        title=f"{sensor_group.capitalize()} Data - {device_id}",
        ylabel="Value",
        thresholds=thresholds
    )

    # Send the plot
    if not any(not data.empty for data in data_dict.values()):
        await query.edit_message_text("No data available.")
    else:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=plot_buf,
            caption=f"{sensor_group.capitalize()} data for {device_id} (Range: {time_range})"
        )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


# =============================================
# Main Application Setup
# =============================================

def main():
    """Start the bot."""
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Conversation handler for data selection
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_DEVICE: [CallbackQueryHandler(device_selected, pattern=r"^device_")],
            SELECTING_SENSORS: [CallbackQueryHandler(sensors_selected, pattern=r"^sensor_")],
            SELECTING_RANGE: [CallbackQueryHandler(range_selected, pattern=r"^range_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv_handler)

    print("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
