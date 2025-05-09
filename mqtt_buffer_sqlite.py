# mqtt_buffer_sqlite.py
# -*- coding: utf-8 -*-
import sqlite3
import json
import time
import os
import threading

DB_FILE = "mqtt_buffer.db"
MAX_MESSAGES = 1000  # max message
LOCK = threading.Lock()


def init_db():
    """create db."""
    with LOCK:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS buffered_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                payload TEXT
            )
        ''')
        conn.commit()
        conn.close()


def buffer_message(payload):
    """Saves the message to the database. Cuts off the old ones if the limit is exceeded."""
    with LOCK:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        timestamp = time.time()
        payload_str = json.dumps(payload)
        c.execute('INSERT INTO buffered_messages (timestamp, payload) VALUES (?, ?)', (timestamp, payload_str))

        # Ограничим размер буфера
        c.execute('SELECT COUNT(*) FROM buffered_messages')
        count = c.fetchone()[0]
        if count > MAX_MESSAGES:
            to_delete = count - MAX_MESSAGES
            c.execute(
                'DELETE FROM buffered_messages WHERE id IN (SELECT id FROM buffered_messages ORDER BY id ASC LIMIT ?)',
                (to_delete,))

        conn.commit()
        conn.close()


def get_all_messages():
    """Returns a list (id, payload) from the buffer."""
    with LOCK:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, payload FROM buffered_messages ORDER BY id ASC')
        rows = c.fetchall()
        conn.close()
        return [(row[0], json.loads(row[1])) for row in rows]


def delete_messages(ids):
    """Deletes messages by ID after successful sending."""
    if not ids:
        return
    with LOCK:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.executemany('DELETE FROM buffered_messages WHERE id = ?', [(id_,) for id_ in ids])
        conn.commit()
        conn.close()


def flush_if_connected(mqtt_client, topic, qos, is_connected_func):
    """If connected, it sends all messages from the buffer."""
    if not is_connected_func():
        return

    messages = get_all_messages()
    if not messages:
        return

    success_ids = []
    for msg_id, payload in messages:
        try:
            mqtt_client.publish(topic, json.dumps(payload), qos=qos)
            success_ids.append(msg_id)
        except Exception as e:
            print(f"[Buffer] Error sending buffer message: {e}")
            break

    delete_messages(success_ids)