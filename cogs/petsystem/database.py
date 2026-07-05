import aiosqlite
import time
import json  # 딕셔너리를 통째로 저장하기 위해 JSON 모듈 추가

DB_PATH = 'legends.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY, points INTEGER, max_star_reached INTEGER,
                     egg_legendary INTEGER, egg_mythic INTEGER, egg_prestige INTEGER)''')

        # 기존 단일 펫 테이블 (과거 데이터 복원/마이그레이션용으로 안전하게 남겨둡니다)
        await db.execute('''CREATE TABLE IF NOT EXISTS user_legends
                     (user_id INTEGER PRIMARY KEY, name TEXT, rarity TEXT,
                     level INTEGER, exp INTEGER, fullness INTEGER, intimacy INTEGER, fatigue INTEGER,
                     cleanliness INTEGER, low_clean_since REAL, low_full_since REAL)''')

        # 🚀 신규 다중 펫 저장용 테이블 생성 (여기에 다중 펫 데이터를 통째로 넣습니다)
        await db.execute('''CREATE TABLE IF NOT EXISTS user_multi_pets
                     (user_id INTEGER PRIMARY KEY, pet_data TEXT)''')

        await db.execute('''CREATE TABLE IF NOT EXISTS user_items
                     (user_id INTEGER, item_name TEXT, amount INTEGER,
                     PRIMARY KEY (user_id, item_name))''')

        await db.execute('''CREATE TABLE IF NOT EXISTS active_buffs
                     (user_id INTEGER, buff_name TEXT, expires_at REAL, vc_seconds_left REAL,
                     PRIMARY KEY (user_id, buff_name))''')
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

async def get_legend_data(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # 1. 먼저 신규 테이블(다중 펫 시스템)에 저장된 데이터가 있는지 확인합니다.
        async with db.execute("SELECT pet_data FROM user_multi_pets WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row['pet_data']:
                try:
                    return json.loads(row['pet_data'])  # JSON 문자열을 딕셔너리로 변환하여 반환
                except json.JSONDecodeError:
                    pass

        # 2. 신규 테이블에 데이터가 없다면, 기존(구버전) 단일 펫 테이블에서 데이터를 가져옵니다.
        # 가져온 데이터는 cog.py의 get_or_migrate_data 함수에서 자동으로 신규 다중 펫 구조로 포장(마이그레이션)해줍니다.
        async with db.execute("SELECT * FROM user_legends WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

async def save_legend_data(user_id, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        # cog.py에서 전달받은 거대한 딕셔너리(wrapper)를 하나의 문자열(JSON)로 묶습니다.
        json_data = json.dumps(data, ensure_ascii=False)

        # 묶어낸 문자열을 신규 다중 펫 테이블에 통째로 저장합니다! (각각의 칸을 찾을 필요가 없어져 에러가 해결됩니다)
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
        if not row or row[0] < amount:
            return False
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