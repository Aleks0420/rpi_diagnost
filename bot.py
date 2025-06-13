# telegram_bot.py
# Bot for monitoring and visualization of diagnostics data from InfluxDB/Grafana
import os
import time
import datetime
import asyncio
import json
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, \
    MessageHandler, filters

# Configuration
TELEGRAM_TOKEN = "7882919864:AAH9wV2YYW625b9RsQPrzl87wpv8cgPFWVA"  # Token from BotFather
GRAFANA_URL = "http://192.168.0.93:3000"  # URL of your Grafana server
GRAFANA_API_KEY = "YOUR_GRAFANA_API_KEY"  # Grafana API key with viewer permissions
DASHBOARD_UID = "fel05uc12gdtsc"  # UID of the dashboard from grafana.json
# DASHBOARD_UID = "eeij2wsy8z11ca"  # UID of the dashboard from grafana.json
INFLUXDB_URL = "http://192.168.0.93:8086"  # URL of your InfluxDB server
INFLUXDB_TOKEN = "mXoOpm9EAmECOpkeDDU7CJh56PYtjYoS-oeOrx2F3X3mErSvileOwl6n-8rSXcWC_eXuh2nm3qWdCI5mDwXUzA=="  # InfluxDB access token
INFLUXDB_ORG = "i"  # Organization in InfluxDB
INFLUXDB_BUCKET = "eng_bucket"  # Data bucket

# List of user IDs allowed to receive notifications and interact with the bot
ALLOWED_USER_IDS = [703548391]  # Replace with your Telegram ID

# Threshold values for different types of sensors
# You can extend this configuration according to your needs
THRESHOLDS = {
    "vibration": {
        "total_rms": 2.0,  # g (total RMS vibration value)
        "rms_x": 1.5,  # g (RMS on X axis)
        "rms_y": 1.5,  # g (RMS on Y axis)
        "rms_z": 1.5  # g (RMS on Z axis)
    },
    "temperature": {
        "engine_temp": 80.0,  # °C (engine temperature)
        "gearbox_temp": 70.0  # °C (gearbox temperature)
    },
    "current": {
        "phase_a": 15.0,  # A (phase A current)
        "phase_b": 15.0,  # A (phase B current)
        "phase_c": 15.0  # A (phase C current)
    }
}

# Check interval in seconds
CHECK_INTERVAL = 300  # Check every 5 minutes

# States for ConversationHandler
SELECTING_DEVICE, SELECTING_DATE_RANGE, SELECTING_SENSOR, SETTING_THRESHOLD = range(4)

# Temporary user data cache
user_data_cache = {}

# Dictionary for tracking sent alerts
# Structure: {device_id: {sensor_type: {field: last_alert_time}}}
alert_history = {}


# Function to load saved threshold values
def load_thresholds():
    """Load threshold values from file or return defaults if file not found"""
    try:
        with open('thresholds.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # If file not found, use default values
        return THRESHOLDS
    except json.JSONDecodeError:
        print("Error parsing thresholds.json")
        return THRESHOLDS


# Function to save threshold values
def save_thresholds(thresholds):
    """Save threshold values to file"""
    with open('thresholds.json', 'w') as f:
        json.dump(thresholds, f, indent=2)


# Load threshold values at startup
THRESHOLDS = load_thresholds()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start interaction with the bot"""
    user_id = update.effective_user.id

    # Check if user is authorized
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text("Sorry, you don't have access to this bot.")
        return ConversationHandler.END

    user_data_cache[user_id] = {}

    # Get available devices from InfluxDB via Grafana API
    devices = await get_available_devices()

    keyboard = []
    for device in devices:
        keyboard.append([InlineKeyboardButton(device, callback_data=f"device_{device}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Select a device to get data:",
        reply_markup=reply_markup
    )

    return SELECTING_DEVICE


async def get_available_devices():
    """Get list of available devices from InfluxDB"""
    try:
        # Query Grafana API to get list of device_id variable values
        headers = {"Authorization": f"Bearer {GRAFANA_API_KEY}"}
        response = requests.get(
            f"{GRAFANA_URL}/api/datasources/proxy/1/query?db=eng_bucket&q=SHOW+TAG+VALUES+FROM+vibration_metrics+WITH+KEY%3Ddevice_id",
            headers=headers
        )

        if response.status_code == 200:
            data = response.json()
            # Extract device_id values from response
            devices = [value[1] for series in data.get("results", [{}])[0].get("series", [{}])
                       for value in series.get("values", [])]
            return devices or ["station_1"]  # Return default if list is empty
        return ["station_1"]  # Return default in case of error
    except Exception as e:
        print(f"Error getting devices: {e}")
        return ["station_1"]  # Return default in case of exception


async def device_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle device selection"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    selected_device = query.data.replace("device_", "")
    user_data_cache[user_id]["device_id"] = selected_device

    # Offer to select a time period
    keyboard = [
        [InlineKeyboardButton("Last hour", callback_data="period_1h")],
        [InlineKeyboardButton("Last 6 hours", callback_data="period_6h")],
        [InlineKeyboardButton("Last 24 hours", callback_data="period_24h")],
        [InlineKeyboardButton("Last 7 days", callback_data="period_7d")],
        [InlineKeyboardButton("Custom period", callback_data="period_custom")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"Device: {selected_device}\nSelect data period:",
        reply_markup=reply_markup
    )

    return SELECTING_DATE_RANGE


async def period_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle period selection"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    period = query.data.replace("period_", "")

    if period == "custom":
        await query.edit_message_text(
            "Enter period in format: YYYY-MM-DD HH:MM:SS to YYYY-MM-DD HH:MM:SS"
        )
        return SELECTING_DATE_RANGE

    user_data_cache[user_id]["period"] = period

    # Get available sensors for selected device
    sensors = await get_available_sensors(user_data_cache[user_id]["device_id"])

    keyboard = []
    for sensor in sensors:
        keyboard.append([InlineKeyboardButton(sensor, callback_data=f"sensor_{sensor}")])

    keyboard.append([InlineKeyboardButton("All graphs", callback_data="sensor_all")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"Device: {user_data_cache[user_id]['device_id']}\n"
        f"Period: {period}\n"
        f"Select sensor:",
        reply_markup=reply_markup
    )

    return SELECTING_SENSOR


async def get_available_sensors(device_id):
    """Get list of available sensors for a device"""
    try:
        headers = {"Authorization": f"Bearer {GRAFANA_API_KEY}"}
        response = requests.get(
            f"{GRAFANA_URL}/api/datasources/proxy/1/query?db=eng_bucket&q=SHOW+TAG+VALUES+FROM+vibration_metrics+WITH+KEY%3Dsensor_name+WHERE+device_id%3D%27{device_id}%27",
            headers=headers
        )

        if response.status_code == 200:
            data = response.json()
            sensors = [value[1] for series in data.get("results", [{}])[0].get("series", [{}])
                       for value in series.get("values", [])]
            return sensors or ["engine", "gearbox"]
        return ["engine", "gearbox"]
    except Exception as e:
        print(f"Error getting sensors: {e}")
        return ["engine", "gearbox"]


async def custom_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom period input"""
    user_id = update.effective_user.id
    period_text = update.message.text

    # Simple format check
    try:
        parts = period_text.split(" to ")
        from_time = datetime.datetime.strptime(parts[0].strip(), "%Y-%m-%d %H:%M:%S")
        to_time = datetime.datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M:%S")

        user_data_cache[user_id]["custom_from"] = from_time.isoformat()
        user_data_cache[user_id]["custom_to"] = to_time.isoformat()
        user_data_cache[user_id]["period"] = "custom"

        # Get and display list of sensors
        sensors = await get_available_sensors(user_data_cache[user_id]["device_id"])

        keyboard = []
        for sensor in sensors:
            keyboard.append([InlineKeyboardButton(sensor, callback_data=f"sensor_{sensor}")])

        keyboard.append([InlineKeyboardButton("All graphs", callback_data="sensor_all")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Device: {user_data_cache[user_id]['device_id']}\n"
            f"Period: from {parts[0]} to {parts[1]}\n"
            f"Select sensor:",
            reply_markup=reply_markup
        )

        return SELECTING_SENSOR

    except Exception as e:
        await update.message.reply_text(
            "Invalid date format. Please enter period in format: "
            "YYYY-MM-DD HH:MM:SS to YYYY-MM-DD HH:MM:SS"
        )
        return SELECTING_DATE_RANGE


async def sensor_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle sensor selection"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    selected_sensor = query.data.replace("sensor_", "")
    user_data_cache[user_id]["sensor"] = selected_sensor

    await query.edit_message_text("Generating graph, please wait...")

    # Get and send graph
    image = await generate_grafana_image(user_id)
    if image:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=image,
            caption=f"Graph for device {user_data_cache[user_id]['device_id']}, "
                    f"sensor: {selected_sensor}, "
                    f"period: {user_data_cache[user_id]['period']}"
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Error generating graph. Please try again."
        )

    # Offer to start new request
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="To get a new graph, send /start command"
    )

    return ConversationHandler.END


async def generate_grafana_image(user_id):
    """Generate graph image from Grafana"""
    try:
        device_id = user_data_cache[user_id]["device_id"]
        period = user_data_cache[user_id]["period"]
        selected_sensor = user_data_cache[user_id]["sensor"]

        # Setup time range
        if period == "custom":
            from_time = user_data_cache[user_id]["custom_from"]
            to_time = user_data_cache[user_id]["custom_to"]
        else:
            to_time = int(time.time() * 1000)  # Current time in milliseconds

            # Calculate from_time based on selected period
            if period == "1h":
                from_time = to_time - (60 * 60 * 1000)  # -1 hour
            elif period == "6h":
                from_time = to_time - (6 * 60 * 60 * 1000)  # -6 hours
            elif period == "24h":
                from_time = to_time - (24 * 60 * 60 * 1000)  # -24 hours
            elif period == "7d":
                from_time = to_time - (7 * 24 * 60 * 60 * 1000)  # -7 days
            else:
                from_time = to_time - (6 * 60 * 60 * 1000)  # Default -6 hours

        # Form URL for panel rendering
        panel_id = 1  # Default panel ID

        if selected_sensor == "all":
            # Render entire dashboard
            render_url = f"{GRAFANA_URL}/render/d/{DASHBOARD_UID}"
            url_params = {
                "orgId": 1,
                "from": from_time,
                "to": to_time,
                "var-device_id": device_id,
                "var-sensor_name": user_data_cache[user_id].get("sensor", "engine"),
                "width": 1000,
                "height": 500,
                "tz": "UTC"
            }
        else:
            # Render specific panel based on selected sensor
            if selected_sensor in ["engine", "gearbox"]:
                panel_id = 1  # Total RMS panel
            elif selected_sensor in ["engine_temp", "gearbox_temp"]:
                panel_id = 3  # Temperature panel
            elif selected_sensor in ["phase_a", "phase_b", "phase_c"]:
                panel_id = 4  # Phase Currents panel

            render_url = f"{GRAFANA_URL}/render/d-solo/{DASHBOARD_UID}"
            url_params = {
                "orgId": 1,
                "from": from_time,
                "to": to_time,
                "panelId": panel_id,
                "var-device_id": device_id,
                "var-sensor_name": selected_sensor,
                "width": 800,
                "height": 400,
                "tz": "UTC"
            }

            # Form full URL with parameters
            param_string = "&".join([f"{k}={v}" for k, v in url_params.items()])
            full_url = f"{render_url}?{param_string}"

            # Make request to Grafana to get image
            headers = {"Authorization": f"Bearer {GRAFANA_API_KEY}"}
            response = requests.get(full_url, headers=headers)

            if response.status_code == 200:
                return response.content
            else:
                print(f"Error rendering Grafana image: {response.status_code}, {response.text}")
                return None

    except Exception as e:
        print(f"Error generating Grafana image: {e}")
        return None

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel operation and end conversation"""
    await update.message.reply_text(
        "Operation cancelled. To get a graph, send /start command"
    )
    return ConversationHandler.END

    # Add new command for setting thresholds

async def set_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start threshold setting process"""
    user_id = update.effective_user.id

    # Check if user is authorized
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text("You don't have permission to change threshold values.")
        return ConversationHandler.END

    user_data_cache[user_id] = {}

    # Get list of available devices
    devices = await get_available_devices()

    keyboard = []
    for device in devices:
        keyboard.append([InlineKeyboardButton(device, callback_data=f"thdev_{device}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Select device for threshold settings:",
        reply_markup=reply_markup
    )

    return SELECTING_DEVICE

async def threshold_device_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle device selection for threshold setting"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    selected_device = query.data.replace("thdev_", "")
    user_data_cache[user_id]["device_id"] = selected_device

    # Offer to select sensor type for threshold setting
    keyboard = [
        [InlineKeyboardButton("Vibration", callback_data="thtype_vibration")],
        [InlineKeyboardButton("Temperature", callback_data="thtype_temperature")],
        [InlineKeyboardButton("Current", callback_data="thtype_current")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"Device: {selected_device}\nSelect sensor type for threshold setting:",
        reply_markup=reply_markup
    )

    return SELECTING_SENSOR

async def threshold_sensor_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle sensor type selection for threshold setting"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    sensor_type = query.data.replace("thtype_", "")
    user_data_cache[user_id]["sensor_type"] = sensor_type

    # Show current threshold values and offer to select field
    keyboard = []

    if sensor_type in THRESHOLDS:
        for field, value in THRESHOLDS[sensor_type].items():
            keyboard.append([InlineKeyboardButton(f"{field}: {value}", callback_data=f"thfield_{field}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"Device: {user_data_cache[user_id]['device_id']}\n"
        f"Sensor type: {sensor_type}\n"
        f"Select field to change threshold value:",
        reply_markup=reply_markup
    )

    return SETTING_THRESHOLD

async def threshold_field_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle field selection for threshold setting"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    field = query.data.replace("thfield_", "")
    user_data_cache[user_id]["field"] = field

    sensor_type = user_data_cache[user_id]["sensor_type"]
    current_value = THRESHOLDS[sensor_type][field]

    await query.edit_message_text(
        f"Device: {user_data_cache[user_id]['device_id']}\n"
        f"Sensor type: {sensor_type}\n"
        f"Field: {field}\n"
        f"Current threshold value: {current_value}\n\n"
        f"Enter new threshold value:"
    )

    return SETTING_THRESHOLD

async def set_new_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set new threshold value"""
    user_id = update.effective_user.id
    new_value_text = update.message.text

    try:
        new_value = float(new_value_text)

        device_id = user_data_cache[user_id]["device_id"]
        sensor_type = user_data_cache[user_id]["sensor_type"]
        field = user_data_cache[user_id]["field"]

        # Update threshold value
        THRESHOLDS[sensor_type][field] = new_value

        # Save updated thresholds
        save_thresholds(THRESHOLDS)

        await update.message.reply_text(
            f"Threshold value updated:\n"
            f"Device: {device_id}\n"
            f"Sensor type: {sensor_type}\n"
            f"Field: {field}\n"
            f"New value: {new_value}\n\n"
            f"To set other thresholds, use /set_threshold command"
        )

        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text(
            "Error: please enter a numeric value.\n"
            "Try again:"
        )
        return SETTING_THRESHOLD

    # Function to check data and send alerts

async def check_thresholds_and_alert(context: ContextTypes.DEFAULT_TYPE):
    """Periodically check data for threshold violations"""
    try:
        # Get list of devices
        devices = await get_available_devices()

        for device_id in devices:
            # Check vibration
            await check_vibration_thresholds(context, device_id)

            # Check temperature
            await check_temperature_thresholds(context, device_id)

            # Check current
            await check_current_thresholds(context, device_id)

    except Exception as e:
        print(f"Error in threshold checking: {e}")

async def check_vibration_thresholds(context, device_id):
    """Check vibration threshold values"""
    try:
        # Form query to InfluxDB
        query = f"""
                    from(bucket: "{INFLUXDB_BUCKET}")
                      |> range(start: -5m)
                      |> filter(fn: (r) => r._measurement == "vibration_metrics" and r.device_id == "{device_id}")
                      |> filter(fn: (r) => r._field == "total_rms" or r._field == "rms_x" or r._field == "rms_y" or r._field == "rms_z")
                      |> last()
                    """

        # Execute query via InfluxDB API
        headers = {
            "Authorization": f"Token {INFLUXDB_TOKEN}",
            "Content-Type": "application/vnd.flux"
        }

        response = requests.post(
            f"{INFLUXDB_URL}/api/v2/query?org={INFLUXDB_ORG}",
            headers=headers,
            data=query
        )

        if response.status_code != 200:
            print(f"Error querying InfluxDB for vibration: {response.text}")
            return

        # Process query result
        # InfluxDB response is in CSV format, so we parse it line by line
        lines = response.text.strip().split("\n")
        if len(lines) <= 1:
            return  # No data

        # Initialize dictionary for device in alert history if it doesn't exist
        if device_id not in alert_history:
            alert_history[device_id] = {}
        if "vibration" not in alert_history[device_id]:
            alert_history[device_id]["vibration"] = {}

        # Current time for checking alert frequency
        current_time = time.time()

        # Parse results and check for threshold violations
        headers = lines[0].split(",")
        for line in lines[1:]:
            if line.startswith("#"):
                continue  # Skip comments

            values = line.split(",")
            if len(values) < len(headers):
                continue

            # Convert to dictionary
            data = {headers[i]: values[i] for i in range(len(headers))}

            # Get field and value
            field = data.get("_field")
            value_str = data.get("_value")

            if not field or not value_str:
                continue

            try:
                value = float(value_str)

                # Check threshold violation
                if field in THRESHOLDS["vibration"] and value > THRESHOLDS["vibration"][field]:
                    # Check if we already sent an alert recently (within the last hour)
                    last_alert_time = alert_history[device_id]["vibration"].get(field, 0)
                    if current_time - last_alert_time > 3600:  # 1 hour in seconds
                        # Send alert
                        for user_id in ALLOWED_USER_IDS:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=f"⚠️ ALERT! Vibration threshold exceeded!\n"
                                     f"Device: {device_id}\n"
                                     f"Parameter: {field}\n"
                                     f"Value: {value:.4f} (threshold: {THRESHOLDS['vibration'][field]})\n"
                                     f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            )

                            # Send graph for visualization
                            image = await generate_alert_graph(device_id, "vibration", field)
                            if image:
                                await context.bot.send_photo(
                                    chat_id=user_id,
                                    photo=image,
                                    caption=f"Graph of {field} for device {device_id}"
                                )

                        # Update last alert time
                        alert_history[device_id]["vibration"][field] = current_time

            except ValueError:
                continue

    except Exception as e:
        print(f"Error checking vibration thresholds for {device_id}: {e}")

async def check_temperature_thresholds(context, device_id):
    """Check temperature threshold values"""
    try:
        # Form query to InfluxDB
        query = f"""
                    from(bucket: "{INFLUXDB_BUCKET}")
                      |> range(start: -5m)
                      |> filter(fn: (r) => r._measurement == "temperature" and r.device_id == "{device_id}")
                      |> filter(fn: (r) => r._field == "engine_temp" or r._field == "gearbox_temp")
                      |> last()
                    """

        headers = {
            "Authorization": f"Token {INFLUXDB_TOKEN}",
            "Content-Type": "application/vnd.flux"
        }

        response = requests.post(
            f"{INFLUXDB_URL}/api/v2/query?org={INFLUXDB_ORG}",
            headers=headers,
            data=query
        )

        if response.status_code != 200:
            print(f"Error querying InfluxDB for temperature: {response.text}")
            return

        # Process query result
        lines = response.text.strip().split("\n")
        if len(lines) <= 1:
            return  # No data

        # Initialize dictionary for device in alert history
        if device_id not in alert_history:
            alert_history[device_id] = {}
        if "temperature" not in alert_history[device_id]:
            alert_history[device_id]["temperature"] = {}

        current_time = time.time()

        # Parse results and check for threshold violations
        headers = lines[0].split(",")
        for line in lines[1:]:
            if line.startswith("#"):
                continue

            values = line.split(",")
            if len(values) < len(headers):
                continue

            data = {headers[i]: values[i] for i in range(len(headers))}

            field = data.get("_field")
            value_str = data.get("_value")

            if not field or not value_str:
                continue

            try:
                value = float(value_str)

                if field in THRESHOLDS["temperature"] and value > THRESHOLDS["temperature"][field]:
                    last_alert_time = alert_history[device_id]["temperature"].get(field, 0)
                    if current_time - last_alert_time > 3600:  # 1 hour
                        # Send alert
                        for user_id in ALLOWED_USER_IDS:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=f"🔥 ALERT! Temperature threshold exceeded!\n"
                                     f"Device: {device_id}\n"
                                     f"Sensor: {field}\n"
                                     f"Value: {value:.1f}°C (threshold: {THRESHOLDS['temperature'][field]}°C)\n"
                                     f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            )

                            # Send graph
                            image = await generate_alert_graph(device_id, "temperature", field)
                            if image:
                                await context.bot.send_photo(
                                    chat_id=user_id,
                                    photo=image,
                                    caption=f"Temperature graph of {field} for device {device_id}"
                                )

                        # Update last alert time
                        alert_history[device_id]["temperature"][field] = current_time

            except ValueError:
                continue

    except Exception as e:
        print(f"Error checking temperature thresholds for {device_id}: {e}")

async def check_current_thresholds(context, device_id):
    """Check current threshold values"""
    try:
        # Form query to InfluxDB
        query = f"""
                from(bucket: "{INFLUXDB_BUCKET}")
                  |> range(start: -5m)
                  |> filter(fn: (r) => r._measurement == "current" and r.device_id == "{device_id}")
                  |> filter(fn: (r) => r._field == "phase_a" or r._field == "phase_b" or r._field == "phase_c")
                  |> last()
                """

        headers = {
            "Authorization": f"Token {INFLUXDB_TOKEN}",
            "Content-Type": "application/vnd.flux"
        }

        response = requests.post(
            f"{INFLUXDB_URL}/api/v2/query?org={INFLUXDB_ORG}",
            headers=headers,
            data=query
        )

        if response.status_code != 200:
            print(f"Error querying InfluxDB for current: {response.text}")
            return

        # Process query result
        lines = response.text.strip().split("\n")
        if len(lines) <= 1:
            return  # No data

        # Initialize dictionary for device in alert history
        if device_id not in alert_history:
            alert_history[device_id] = {}
        if "current" not in alert_history[device_id]:
            alert_history[device_id]["current"] = {}

        current_time = time.time()

        # Parse results and check for threshold violations
        headers = lines[0].split(",")
        for line in lines[1:]:
            if line.startswith("#"):
                continue

            values = line.split(",")
            if len(values) < len(headers):
                continue

            data = {headers[i]: values[i] for i in range(len(headers))}

            field = data.get("_field")
            value_str = data.get("_value")

            if not field or not value_str:
                continue

            try:
                value = float(value_str)

                if field in THRESHOLDS["current"] and value > THRESHOLDS["current"][field]:
                    last_alert_time = alert_history[device_id]["current"].get(field, 0)
                    if current_time - last_alert_time > 3600:  # 1 hour
                        # Send alert
                        for user_id in ALLOWED_USER_IDS:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=f"⚡ ALERT! Current threshold exceeded!\n"
                                     f"Device: {device_id}\n"
                                     f"Phase: {field}\n"
                                     f"Value: {value:.2f}A (threshold: {THRESHOLDS['current'][field]}A)\n"
                                     f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            )

                            # Send graph
                            image = await generate_alert_graph(device_id, "current", field)
                            if image:
                                await context.bot.send_photo(
                                    chat_id=user_id,
                                    photo=image,
                                    caption=f"Current graph of {field} for device {device_id}"
                                )

                        # Update last alert time
                        alert_history[device_id]["current"][field] = current_time

            except ValueError:
                continue

    except Exception as e:
        print(f"Error checking current thresholds for {device_id}: {e}")

async def generate_alert_graph(device_id, measurement_type, field):
    """Generate graph for threshold violation alert"""
    try:
        # Define parameters for Grafana graph request
        panel_id = 1  # Default panel ID

        if measurement_type == "vibration":
            panel_id = 1 if field == "total_rms" else 2  # Use RMS X/Y/Z panel for other fields
        elif measurement_type == "temperature":
            panel_id = 3  # Temperature panel
        elif measurement_type == "current":
            panel_id = 4  # Phase Currents panel

        # Form URL for panel rendering
        render_url = f"{GRAFANA_URL}/render/d-solo/{DASHBOARD_UID}"

        # Current time in milliseconds for Grafana
        to_time = int(time.time() * 1000)
        from_time = to_time - (3 * 60 * 60 * 1000)  # -3 hours

        url_params = {
            "orgId": 1,
            "from": from_time,
            "to": to_time,
            "panelId": panel_id,
            "var-device_id": device_id,
            "var-sensor_name": field.split("_")[0] if "_" in field else field,  # Approximate matching
            "width": 800,
            "height": 400,
            "tz": "UTC"
        }

        # Form full URL with parameters
        param_string = "&".join([f"{k}={v}" for k, v in url_params.items()])
        full_url = f"{render_url}?{param_string}"

        # Make request to Grafana to get image
        headers = {"Authorization": f"Bearer {GRAFANA_API_KEY}"}
        response = requests.get(full_url, headers=headers)

        if response.status_code == 200:
            return response.content
        else:
            print(f"Error rendering Grafana image for alert: {response.status_code}, {response.text}")
            return None

    except Exception as e:
        print(f"Error generating alert graph: {e}")
        return None

    # Command to view current thresholds

async def show_thresholds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display current threshold values"""
    user_id = update.effective_user.id

    # Check if user is authorized
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text("You don't have permission to view threshold values.")
        return

    # Form message with current thresholds
    message = "📊 Current threshold values:\n\n"

    # Vibration
    message += "🔵 Vibration:\n"
    for field, value in THRESHOLDS["vibration"].items():
        message += f"  • {field}: {value} g\n"

    # Temperature
    message += "\n🔴 Temperature:\n"
    for field, value in THRESHOLDS["temperature"].items():
        message += f"  • {field}: {value}°C\n"

    # Current
    message += "\n⚡ Current:\n"
    for field, value in THRESHOLDS["current"].items():
        message += f"  • {field}: {value}A\n"

    message += "\nTo change thresholds, use /set_threshold command"

    await update.message.reply_text(message)

def main():
    """Main function to start the bot"""
    # Create application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Configure command handlers
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_DEVICE: [
                CallbackQueryHandler(device_selected, pattern=r"^device_")
            ],
            SELECTING_DATE_RANGE: [
                CallbackQueryHandler(period_selected, pattern=r"^period_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_period)
            ],
            SELECTING_SENSOR: [
                CallbackQueryHandler(sensor_selected, pattern=r"^sensor_")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Handler for threshold settings
    threshold_handler = ConversationHandler(
        entry_points=[CommandHandler("set_threshold", set_threshold)],
        states={
            SELECTING_DEVICE: [
                CallbackQueryHandler(threshold_device_selected, pattern=r"^thdev_")
            ],
            SELECTING_SENSOR: [
                CallbackQueryHandler(threshold_sensor_type_selected, pattern=r"^thtype_")
            ],
            SETTING_THRESHOLD: [
                CallbackQueryHandler(threshold_field_selected, pattern=r"^thfield_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_new_threshold)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(threshold_handler)
    application.add_handler(CommandHandler("show_thresholds", show_thresholds))

    # Start periodic threshold checking task
    job_queue = application.job_queue
    job_queue.run_repeating(check_thresholds_and_alert, interval=CHECK_INTERVAL, first=10)

    # Start the bot
    print(f"Telegram bot started. Checking thresholds every {CHECK_INTERVAL} seconds.")
    application.run_polling()

if __name__ == "__main__":
    main()