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
    ConversationHandler,
    MessageHandler,
    filters
)

# --- InfluxDB Configuration ---
INFLUXDB_URL = "http://192.168.0.93:8086"  # URL вашего InfluxDB сервера
INFLUXDB_TOKEN = ""  # Токен доступа
INFLUXDB_ORG = "i"  # Организация
INFLUXDB_BUCKET = "eng_bucket"  # Бакет с данными

# --- Telegram Bot Configuration ---
TELEGRAM_TOKEN = ""
ALLOWED_USER_IDS = [703548391]  # ID пользователей с доступом

# --- Thresholds for Alerts ---
THRESHOLDS = {
    "vibration": {"total_rms": 2.0},
    "temperature": {"engine_temp": 80.0},
    "current": {"phase_a": 15.0}
}

# --- Conversation States ---
SELECTING_DEVICE, SELECTING_SENSOR = range(2)
user_data_cache = {}  # Temporary storage for user selections


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

def generate_time_series_plot(data, title, ylabel, threshold=None):
    """
    Generate a matplotlib time series plot from InfluxDB data.
    Args:
        data: DataFrame with '_time' and '_value' columns
        title: Plot title
        ylabel: Y-axis label
        threshold: Optional threshold line value
    Returns:
        BytesIO buffer with PNG image
    """
    plt.figure(figsize=(10, 5))

    # Plot main data
    plt.plot(data['_time'], data['_value'],
             label='Data',
             linewidth=2,
             color='blue')

    # Add threshold line if provided
    if threshold is not None:
        plt.axhline(y=threshold,
                    color='red',
                    linestyle='--',
                    label=f'Threshold ({threshold})')

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

    # Show sensor type selection
    keyboard = [
        [InlineKeyboardButton("Vibration", callback_data="sensor_vibration")],
        [InlineKeyboardButton("Temperature", callback_data="sensor_temp")],
        [InlineKeyboardButton("Current", callback_data="sensor_current")]
    ]

    await query.edit_message_text(
        f"Device: {device_id}\nSelect sensor type:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_SENSOR


async def sensor_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle sensor type selection and show data."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    sensor_type = query.data.replace("sensor_", "")
    device_id = user_data_cache[user_id]["device_id"]

    await query.edit_message_text("Generating plot...")

    # Fetch data and generate appropriate plot
    if sensor_type == "vibration":
        data = query_influx_data(
            measurement="vibration_metrics",
            field="total_rms",
            device_id=device_id,
            sensor_name="engine"  # Or let user select
        )
        plot_buf = generate_time_series_plot(
            data,
            title=f"Vibration (RMS) - {device_id}",
            ylabel="Acceleration (g)",
            threshold=THRESHOLDS["vibration"]["total_rms"]
        )

    elif sensor_type == "temp":
        data = query_influx_data(
            measurement="temperature",
            field="engine_temp",
            device_id=device_id
        )
        plot_buf = generate_time_series_plot(
            data,
            title=f"Temperature - {device_id}",
            ylabel="Temperature (°C)",
            threshold=THRESHOLDS["temperature"]["engine_temp"]
        )

    elif sensor_type == "current":
        data = query_influx_data(
            measurement="current",
            field="phase_a",
            device_id=device_id
        )
        plot_buf = generate_time_series_plot(
            data,
            title=f"Current - {device_id}",
            ylabel="Current (A)",
            threshold=THRESHOLDS["current"]["phase_a"]
        )

    # Send the plot
    if data.empty:
        await query.edit_message_text("No data available.")
    else:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=plot_buf,
            caption=f"{sensor_type.capitalize()} data for {device_id}"
        )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


# =============================================
# Alert Checking Function
# =============================================

async def check_thresholds(context: ContextTypes.DEFAULT_TYPE):
    """Periodically check thresholds and send alerts."""
    for user_id in ALLOWED_USER_IDS:
        # Check vibration
        vib_data = query_influx_data(
            measurement="vibration_metrics",
            field="total_rms",
            device_id="station_1",
            time_range="-5m"
        )

        if not vib_data.empty and vib_data["_value"].iloc[-1] > THRESHOLDS["vibration"]["total_rms"]:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⚠️ Vibration threshold exceeded! Current: {vib_data['_value'].iloc[-1]:.2f}g"
            )

        # Similar checks for temperature and current...


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
            SELECTING_SENSOR: [CallbackQueryHandler(sensor_selected, pattern=r"^sensor_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv_handler)

    # Add periodic threshold checking
    job_queue = app.job_queue
    job_queue.run_repeating(check_thresholds, interval=300.0, first=10)

    print("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
