import sqlite3

# ==========================================
# DB 헬퍼 함수
# ==========================================
def init_db():
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, max_star_reached INTEGER,
                  egg_legendary INTEGER, egg_mythic INTEGER, egg_prestige INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_legends
                 (user_id INTEGER PRIMARY KEY, name TEXT, rarity TEXT,
                  level INTEGER, exp INTEGER, fullness INTEGER, intimacy INTEGER, fatigue INTEGER)''')
    conn.commit()
    conn.close()

def get_user_pet_data(user_id):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    data = c.fetchone()
    if not data:
        c.execute("INSERT INTO users VALUES (?, 0, 0, 0, 0)", (user_id,))
        conn.commit()
        data = (user_id, 0, 0, 0, 0)
    conn.close()
    return data

def update_user_egg(user_id, rarity, amount=1):
    if rarity == "서사": return
    column = {"전설": "egg_legendary", "신화": "egg_mythic", "프레스티지": "egg_prestige"}[rarity]
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute(f"UPDATE users SET {column} = MAX(0, {column} + ?) WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_legend(user_id):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("SELECT name, rarity, level, exp, fullness, intimacy, fatigue FROM user_legends WHERE user_id = ?", (user_id,))
    data = c.fetchone()
    conn.close()
    return data

def save_legend(user_id, name, rarity, level, exp, fullness, intimacy, fatigue):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO user_legends
                 (user_id, name, rarity, level, exp, fullness, intimacy, fatigue)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (user_id, name, rarity, level, exp, fullness, intimacy, fatigue))
    conn.commit()
    conn.close()

def check_and_update_max_star(user_id, level):
    user_data = get_user_pet_data(user_id)
    if level > user_data[1]:
        conn = sqlite3.connect('legends.db')
        c = conn.cursor()
        c.execute("UPDATE users SET max_star_reached = ? WHERE user_id = ?", (level, user_id))
        conn.commit()
        conn.close()
