import aiosqlite
import time
import json

DB_PATH = 'legends.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY, points INTEGER, max_star_reached INTEGER,
                     egg_legendary INTEGER, egg_mythic INTEGER, egg_prestige INTEGER)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS user_legends
                     (user_id INTEGER PRIMARY KEY, name TEXT, rarity TEXT,
                     level INTEGER, exp INTEGER, fullness INTEGER, intimacy INTEGER, fatigue INTEGER,
                     cleanliness INTEGER, low_clean_since REAL, low_full_since REAL)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS user_multi_pets
                     (user_id INTEGER PRIMARY KEY, pet_data TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS user_items
                     (user_id INTEGER, item_name TEXT, amount INTEGER,
                     PRIMARY KEY (user_id, item_name))''')
        await db.execute('''CREATE TABLE IF NOT EXISTS active_buffs
                     (user_id INTEGER, buff_name TEXT, expires_at REAL, vc_seconds_left REAL,
                     PRIMARY KEY (user_id, buff_name))''')
        # 업적 테이블 추가
        await db.execute('''CREATE TABLE IF NOT EXISTS user_achievements
                     (user_id INTEGER PRIMARY KEY, synth_count INTEGER DEFAULT 0)''')
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            data = await cursor.fetchone()
        if not data:
            await db.execute("INSERT INTO users VALUES (?, 3000, 0, 0, 0, 0)", (user_id,))
            await db.commit()
            data = (user_id, 3000, 0, 0, 0, 0)
        return data

async def update_user_points(user_id, points_change):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET points = MAX(0, points + ?) WHERE user_id = ?", (points_change, user_id))
        await db.commit()

async def update_max_star(user_id, star):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET max_star_reached = MAX(max_star_reached, ?) WHERE user_id = ?", (star, user_id))
        await db.commit()

async def get_legend_data(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT pet_data FROM user_multi_pets WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row['pet_data']:
                try: return json.loads(row['pet_data'])
                except json.JSONDecodeError: pass
        async with db.execute("SELECT * FROM user_legends WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

async def save_legend_data(user_id, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        json_data = json.dumps(data, ensure_ascii=False)
        await db.execute('''INSERT OR REPLACE INTO user_multi_pets (user_id, pet_data)
                     VALUES (?, ?)''', (user_id, json_data))
        await db.commit()

async def add_item(user_id, item_name, amount=1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO user_items (user_id, item_name, amount) VALUES (?, ?, ?) ON CONFLICT(user_id, item_name) DO UPDATE SET amount = amount + ?", (user_id, item_name, amount, amount))
        await db.commit()

async def consume_item(user_id, item_name, amount=1) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT amount FROM user_items WHERE user_id = ? AND item_name = ?", (user_id, item_name)) as cursor:
            row = await cursor.fetchone()
        if not row or row[0] < amount: return False
        await db.execute("UPDATE user_items SET amount = amount - ? WHERE user_id = ? AND item_name = ?", (amount, user_id, item_name))
        await db.execute("DELETE FROM user_items WHERE amount <= 0")
        await db.commit()
        return True

async def add_buff(user_id, buff_name, duration_sec=0, vc_sec=0):
    async with aiosqlite.connect(DB_PATH) as db:
        expires_at = time.time() + duration_sec if duration_sec > 0 else 0
        await db.execute('''INSERT OR REPLACE INTO active_buffs (user_id, buff_name, expires_at, vc_seconds_left)
                     VALUES (?, ?, ?, ?)''', (user_id, buff_name, expires_at, vc_sec))
        await db.commit()

async def get_active_buffs(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        now = time.time()
        await db.execute("DELETE FROM active_buffs WHERE expires_at > 0 AND expires_at < ?", (now,))
        await db.execute("DELETE FROM active_buffs WHERE expires_at = 0 AND vc_seconds_left <= 0")
        await db.commit()
        async with db.execute("SELECT buff_name, expires_at, vc_seconds_left FROM active_buffs WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
        return rows

async def get_or_migrate_data(user_id):
    data = await get_legend_data(user_id)
    if not data: return {'pets': [], 'active_idx': 0}
    if 'pets' not in data: return {'pets': [data], 'active_idx': 0}
    return data

# ✨ 업적/베팅을 위해 새롭게 추가된 기능들
async def get_item_amount(user_id, item_name):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT amount FROM user_items WHERE user_id = ? AND item_name = ?", (user_id, item_name)) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

async def set_item_amount(user_id, item_name, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        if amount <= 0:
            await db.execute("DELETE FROM user_items WHERE user_id = ? AND item_name = ?", (user_id, item_name))
        else:
            await db.execute("INSERT INTO user_items (user_id, item_name, amount) VALUES (?, ?, ?) ON CONFLICT(user_id, item_name) DO UPDATE SET amount = ?", (user_id, item_name, amount, amount))
        await db.commit()

async def add_synth_count(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO user_achievements (user_id, synth_count) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET synth_count = synth_count + 1", (user_id,))
        await db.commit()

async def get_synth_count(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT synth_count FROM user_achievements WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

async def get_top_epic_egg_owners():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, amount FROM user_items WHERE item_name = '서사급 알' ORDER BY amount DESC LIMIT 5") as cursor:
            return await cursor.fetchall()