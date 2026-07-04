import sqlite3
import time

def init_db():
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, points INTEGER, max_star_reached INTEGER,
                 egg_legendary INTEGER, egg_mythic INTEGER, egg_prestige INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_legends
                 (user_id INTEGER PRIMARY KEY, name TEXT, rarity TEXT,
                 level INTEGER, exp INTEGER, fullness INTEGER, intimacy INTEGER, fatigue INTEGER,
                 cleanliness INTEGER, low_clean_since REAL, low_full_since REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_items
                 (user_id INTEGER, item_name TEXT, amount INTEGER,
                 PRIMARY KEY (user_id, item_name))''')
    c.execute('''CREATE TABLE IF NOT EXISTS active_buffs
                 (user_id INTEGER, buff_name TEXT, expires_at REAL, vc_seconds_left REAL,
                 PRIMARY KEY (user_id, buff_name))''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    data = c.fetchone()
    if not data:
        c.execute("INSERT INTO users VALUES (?, 3000, 0, 0, 0, 0)", (user_id,))
        conn.commit()
        data = (user_id, 3000, 0, 0, 0, 0)
    conn.close()
    return data

def update_user_points(user_id, points_change):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("UPDATE users SET points = MAX(0, points + ?) WHERE user_id = ?", (points_change, user_id))
    conn.commit()
    conn.close()

def get_legend_data(user_id):
    conn = sqlite3.connect('legends.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM user_legends WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def save_legend_data(user_id, data: dict):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO user_legends
                 (user_id, name, rarity, level, exp, fullness, intimacy, fatigue,
                  cleanliness, low_clean_since, low_full_since)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (user_id, data['name'], data['rarity'], data['level'], data['exp'],
               data['fullness'], data['intimacy'], data['fatigue'],
               data.get('cleanliness', 100), data.get('low_clean_since', 0), data.get('low_full_since', 0)))
    conn.commit()
    conn.close()

def add_item(user_id, item_name, amount=1):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("INSERT INTO user_items (user_id, item_name, amount) VALUES (?, ?, ?) ON CONFLICT(user_id, item_name) DO UPDATE SET amount = amount + ?", (user_id, item_name, amount, amount))
    conn.commit()
    conn.close()

def consume_item(user_id, item_name, amount=1) -> bool:
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("SELECT amount FROM user_items WHERE user_id = ? AND item_name = ?", (user_id, item_name))
    row = c.fetchone()
    if not row or row[0] < amount:
        conn.close()
        return False
    c.execute("UPDATE user_items SET amount = amount - ? WHERE user_id = ? AND item_name = ?", (amount, user_id, item_name))
    c.execute("DELETE FROM user_items WHERE amount <= 0")
    conn.commit()
    conn.close()
    return True

def add_buff(user_id, buff_name, duration_sec=0, vc_sec=0):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    expires_at = time.time() + duration_sec if duration_sec > 0 else 0
    c.execute('''INSERT OR REPLACE INTO active_buffs (user_id, buff_name, expires_at, vc_seconds_left)
                 VALUES (?, ?, ?, ?)''', (user_id, buff_name, expires_at, vc_sec))
    conn.commit()
    conn.close()

def get_active_buffs(user_id):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    now = time.time()
    c.execute("DELETE FROM active_buffs WHERE expires_at > 0 AND expires_at < ?", (now,))
    c.execute("DELETE FROM active_buffs WHERE expires_at = 0 AND vc_seconds_left <= 0")
    conn.commit()
    c.execute("SELECT buff_name, expires_at, vc_seconds_left FROM active_buffs WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows