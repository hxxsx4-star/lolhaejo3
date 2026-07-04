import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    # 유저 기본 정보 (알 보유량)
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, max_star_reached INTEGER,
                  egg_legendary INTEGER, egg_mythic INTEGER, egg_prestige INTEGER)''')
    # 펫 상세 스탯 (상태 시간 추적용 컬럼 추가)
    c.execute('''CREATE TABLE IF NOT EXISTS user_legends
                 (user_id INTEGER PRIMARY KEY, name TEXT, rarity TEXT,
                  level INTEGER, exp INTEGER, fullness INTEGER, intimacy INTEGER, fatigue INTEGER, cleanliness INTEGER,
                  last_updated INTEGER, last_fed INTEGER, last_cleaned INTEGER)''')
    # 유저 아이템 인벤토리
    c.execute('''CREATE TABLE IF NOT EXISTS user_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT, quantity INTEGER,
                  UNIQUE(user_id, item_name))''')
    # 유저 버프 상태
    c.execute('''CREATE TABLE IF NOT EXISTS user_buffs
                 (user_id INTEGER, buff_name TEXT, end_timestamp INTEGER,
                  UNIQUE(user_id, buff_name))''')
    conn.commit()
    conn.close()

# --- User Pet Data ---
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

# --- Legend Data ---
def get_legend(user_id):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("SELECT * FROM user_legends WHERE user_id = ?", (user_id,))
    data = c.fetchone()
    conn.close()
    return data

def save_legend(user_id, name, rarity, level, exp, fullness, intimacy, fatigue, cleanliness, is_new=False):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    now = int(datetime.now().timestamp())
    if is_new: # 새로 생성될 때만 last_fed, last_cleaned를 현재로
        c.execute('''INSERT OR REPLACE INTO user_legends VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, name, rarity, level, exp, fullness, intimacy, fatigue, cleanliness, now, now, now))
    else: # 업데이트 시에는 last_fed, last_cleaned는 유지
        c.execute('''UPDATE user_legends SET name=?, rarity=?, level=?, exp=?, fullness=?, intimacy=?, fatigue=?, cleanliness=?, last_updated=?
                     WHERE user_id=?''',
                  (name, rarity, level, exp, fullness, intimacy, fatigue, cleanliness, now, user_id))
    conn.commit()
    conn.close()

def update_legend_specific(user_id, **kwargs):
    """특정 스탯만 업데이트. 예: update_legend_specific(123, fullness=100, last_fed=167...)"""
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    
    # last_updated는 항상 현재 시간으로 갱신
    kwargs['last_updated'] = int(datetime.now().timestamp())
    
    set_clause = ', '.join([f"{key} = ?" for key in kwargs])
    values = list(kwargs.values()) + [user_id]
    
    c.execute(f"UPDATE user_legends SET {set_clause} WHERE user_id = ?", values)
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

# --- Item Data ---
def get_user_items(user_id):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("SELECT item_name, quantity FROM user_items WHERE user_id = ? AND quantity > 0", (user_id,))
    items = c.fetchall()
    conn.close()
    return items

def add_user_item(user_id, item_name, quantity=1):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO user_items (user_id, item_name, quantity) VALUES (?, ?, 0)", (user_id, item_name))
    c.execute("UPDATE user_items SET quantity = quantity + ? WHERE user_id = ? AND item_name = ?", (quantity, user_id, item_name))
    conn.commit()
    conn.close()

def remove_user_item(user_id, item_name, quantity=1):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("UPDATE user_items SET quantity = MAX(0, quantity - ?) WHERE user_id = ? AND item_name = ?", (quantity, user_id, item_name))
    conn.commit()
    conn.close()
