import pandas as pd
from influxdb_client import InfluxDBClient
from config import INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET

def query_influx_data(measurement, field, device_id, sensor_name=None, time_range="-1h"):
    """
    Запрашивает данные из InfluxDB по заданным параметрам.
    :param measurement: имя измерения (measurement)
    :param field: поле (например, 'total_rms', 'engine_temp', 'phase_a')
    :param device_id: идентификатор устройства
    :param sensor_name: имя сенсора (например, 'engine', 'gearbox') — опционально
    :param time_range: диапазон времени (например, "-1h", "-24h" или dict с 'start' и 'stop')
    :return: DataFrame с результатами или пустой DataFrame при ошибке
    """
    # Формируем range-клауза
    if isinstance(time_range, dict) and "start" in time_range and "stop" in time_range:
        range_clause = f'range(start: {time_range["start"]}, stop: {time_range["stop"]})'
    elif isinstance(time_range, str) and time_range.startswith("range("):
        range_clause = time_range
    else:
        range_clause = f'range(start: {time_range})'

    # Формируем Flux-запрос
    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> {range_clause}
          |> filter(fn: (r) => r._measurement == "{measurement}")
          |> filter(fn: (r) => r._field == "{field}")
          |> filter(fn: (r) => r.device_id == "{device_id}")
    '''
    if sensor_name:
        query += f'|> filter(fn: (r) => r.sensor_name == "{sensor_name}")'

    try:
        client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        result = client.query_api().query_data_frame(query)
        client.close()
        if isinstance(result, list):
            result = pd.concat(result)
        return result
    except Exception as e:
        print(f"[DEBUG] Ошибка запроса к InfluxDB: {e}")
        return pd.DataFrame()  # Возвращаем пустой DataFrame в случае ошибки