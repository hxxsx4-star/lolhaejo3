import aiosqlite
import time
import json

DB_PATH = 'legends.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # 봇과 웹서버(별개 프로세스)가 같은 DB를 동시에 읽고 써도 서로 막히지 않도록 WAL 모드 사용.
        # WAL 은 DB 헤더에 저장되어 영구 적용되며, 읽기는 쓰기를 막지 않아 동기화가 즉각적입니다.
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA busy_timeout=5000")
        # 💡 기존 전설이/유저 관련 테이블
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
        await db.execute('''CREATE TABLE IF NOT EXISTS user_achievements
                     (user_id INTEGER PRIMARY KEY, synth_count INTEGER DEFAULT 0)''')

        # 💡 원정 시스템: 유저당 1개의 진행 중 원정
        await db.execute('''CREATE TABLE IF NOT EXISTS expeditions
                     (user_id INTEGER PRIMARY KEY, pet_name TEXT, pet_type TEXT,
                     pet_level INTEGER, power INTEGER, start_ts REAL, duration_h INTEGER)''')

        # 💡 일일 퀘스트: 유저·날짜별 진행도 (claimed = 수령한 퀘스트 비트마스크)
        await db.execute('''CREATE TABLE IF NOT EXISTS daily_quests
                     (user_id INTEGER, qdate TEXT, walk INTEGER DEFAULT 0,
                     care INTEGER DEFAULT 0, battle INTEGER DEFAULT 0,
                     claimed INTEGER DEFAULT 0, PRIMARY KEY (user_id, qdate))''')

        # 💡 출석체크: 유저별 마지막 출석일·연속 출석·누적 출석일
        await db.execute('''CREATE TABLE IF NOT EXISTS attendance
                     (user_id INTEGER PRIMARY KEY, last_date TEXT,
                     streak INTEGER DEFAULT 0, total_days INTEGER DEFAULT 0)''')

        # 💡 승부예측 시스템 관련 테이블
        await db.execute('''CREATE TABLE IF NOT EXISTS betting_sessions
                     (topic TEXT PRIMARY KEY, option_a TEXT, option_b TEXT, status TEXT, message_id INTEGER, channel_id INTEGER)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS betting_records
                     (topic TEXT, user_id INTEGER, option TEXT, amount INTEGER, PRIMARY KEY (topic, user_id))''')

        # 💡 예약 마감 업데이트 (기존 테이블에 마감 시간 칼럼 추가)
        try:
            await db.execute("ALTER TABLE betting_sessions ADD COLUMN close_at REAL")
        except Exception:
            pass # 이미 칼럼이 추가되어 있으면 오류를 무시하고 넘어갑니다.

        await db.commit()

# ==========================================
# 💡 기존 유저 및 전설이 관련 함수
# ==========================================

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
        # 조건부 UPDATE 한 번으로 '보유량 확인 + 차감'을 원자적으로 처리합니다.
        # amount >= ? 조건 덕분에 동시에 여러 번 눌러도 보유량을 초과해 차감되지 않습니다.
        cursor = await db.execute(
            "UPDATE user_items SET amount = amount - ? WHERE user_id = ? AND item_name = ? AND amount >= ?",
            (amount, user_id, item_name, amount),
        )
        success = cursor.rowcount > 0
        if success:
            await db.execute("DELETE FROM user_items WHERE amount <= 0")
        await db.commit()
        return success

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

# ==========================================
# 💡 원정 시스템 전용 함수
# ==========================================

async def start_expedition(user_id, pet_name, pet_type, pet_level, power, duration_h):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''INSERT OR REPLACE INTO expeditions
                     (user_id, pet_name, pet_type, pet_level, power, start_ts, duration_h)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, pet_name, pet_type, pet_level, power, time.time(), duration_h))
        await db.commit()

async def get_expedition(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM expeditions WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def clear_expedition(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM expeditions WHERE user_id = ?", (user_id,))
        await db.commit()

# ==========================================
# 💡 일일 퀘스트 전용 함수
# ==========================================

async def add_quest_progress(user_id, qdate: str, field: str, amount: int = 1):
    """일일 퀘스트 진행도를 누적합니다. field는 walk/care/battle 중 하나."""
    if field not in ("walk", "care", "battle"):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f'''INSERT INTO daily_quests (user_id, qdate, {field})
                     VALUES (?, ?, ?)
                     ON CONFLICT(user_id, qdate) DO UPDATE SET {field} = {field} + ?''',
                     (user_id, qdate, amount, amount))
        await db.commit()

async def get_quest_row(user_id, qdate: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM daily_quests WHERE user_id = ? AND qdate = ?", (user_id, qdate)) as cursor:
            return await cursor.fetchone()

async def set_quest_claimed(user_id, qdate: str, claimed_mask: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''INSERT INTO daily_quests (user_id, qdate, claimed) VALUES (?, ?, ?)
                     ON CONFLICT(user_id, qdate) DO UPDATE SET claimed = ?''',
                     (user_id, qdate, claimed_mask, claimed_mask))
        await db.commit()

# ==========================================
# 💡 출석체크 전용 함수
# ==========================================

async def get_attendance(user_id):
    """유저의 출석 기록(last_date/streak/total_days)을 반환. 없으면 None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM attendance WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def set_attendance(user_id, last_date: str, streak: int, total_days: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''INSERT INTO attendance (user_id, last_date, streak, total_days)
                     VALUES (?, ?, ?, ?)
                     ON CONFLICT(user_id) DO UPDATE SET last_date = ?, streak = ?, total_days = ?''',
                     (user_id, last_date, streak, total_days, last_date, streak, total_days))
        await db.commit()

# ==========================================
# 💡 승부예측 전용 함수 모음
# ==========================================

async def create_bet_session(topic, opt_a, opt_b, msg_id, ch_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO betting_sessions (topic, option_a, option_b, status, message_id, channel_id) VALUES (?, ?, ?, 'active', ?, ?)",
                         (topic, opt_a, opt_b, msg_id, ch_id))
        await db.commit()

async def get_bet_session(topic):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM betting_sessions WHERE topic = ?", (topic,)) as cursor:
            return await cursor.fetchone()

# 💡 신규 추가: 메시지 ID로 세션 조회
async def get_bet_session_by_message_id(message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM betting_sessions WHERE message_id = ?", (message_id,)) as cursor:
            return await cursor.fetchone()

async def update_bet_status(topic, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE betting_sessions SET status = ? WHERE topic = ?", (status, topic))
        await db.commit()

async def add_bet_record(topic, user_id, option, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''INSERT INTO betting_records (topic, user_id, option, amount)
                          VALUES (?, ?, ?, ?)
                          ON CONFLICT(topic, user_id) DO UPDATE SET amount = amount + ?''',
                       (topic, user_id, option, amount, amount))
        await db.commit()

async def get_bet_totals(topic):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT option, SUM(amount) FROM betting_records WHERE topic = ? GROUP BY option", (topic,)) as cursor:
            rows = await cursor.fetchall()

        totals = {'A': 0, 'B': 0}
        for row in rows:
            totals[row[0]] = row[1]
        return totals

async def get_bet_winners(topic, win_option):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, amount FROM betting_records WHERE topic = ? AND option = ?", (topic, win_option)) as cursor:
            return await cursor.fetchall()

async def get_user_bet(topic, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT option, amount FROM betting_records WHERE topic = ? AND user_id = ?", (topic, user_id)) as cursor:
            return await cursor.fetchone()

async def get_user_all_bets(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT r.topic, r.option, r.amount, s.status, s.option_a, s.option_b
            FROM betting_records r
            JOIN betting_sessions s ON r.topic = s.topic
            WHERE r.user_id = ?
        ''', (user_id,)) as cursor:
            return await cursor.fetchall()

# ==========================================
# 💡 승부예측 자동 마감(예약) 전용 함수
# ==========================================

async def set_bet_close_time(topic, close_at):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE betting_sessions SET close_at = ? WHERE topic = ?", (close_at, topic))
        await db.commit()

async def get_expired_bets():
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # 현재 시간보다 예약된 마감 시간이 지났고, 아직 'active' 상태인 베팅만 가져옴
        async with db.execute("SELECT * FROM betting_sessions WHERE status = 'active' AND close_at IS NOT NULL AND close_at <= ?", (now,)) as cursor:
            return await cursor.fetchall()

async def get_user_items(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT item_name, amount FROM user_items WHERE user_id = ? AND amount > 0", (user_id,)) as cursor:
            rows = await cursor.fetchall()
        return rows