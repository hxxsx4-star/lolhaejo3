import json
import os
from filelock import FileLock

SHARED_FILE_PATH = "/home/hxxsx4/shared_data/stats.json"
LOCK_FILE_PATH = "/home/hxxsx4/shared_data/stats.json.lock"
os.makedirs(os.path.dirname(SHARED_FILE_PATH), exist_ok=True)
lock = FileLock(LOCK_FILE_PATH)

# 폴더가 혹시 없다면 자동으로 생성해주는 안전장치
os.makedirs(os.path.dirname(SHARED_FILE_PATH), exist_ok=True)

# 파일 락(Lock) 객체 생성
lock = FileLock(LOCK_FILE_PATH)

def load_stats() -> dict:
    if not os.path.exists(SHARED_FILE_PATH):
        return {}
    with lock:
        try:
            with open(SHARED_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_stats(data: dict):
    with lock:
        with open(SHARED_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

# ---------------------------------------------------------
# 아래부터는 기존에 쓰시던 유저 관리 및 포인트 연산 함수들입니다.
# (예시로 작성해 둔 것이니, 원래 쓰시던 로직이 있다면 그대로 유지하셔도 됩니다.)
# ---------------------------------------------------------

def ensure_user(stats: dict, user_id: str) -> dict:
    if user_id not in stats:
        stats[user_id] = {"포인트": 0}
    return stats[user_id]

def format_num(num: int) -> str:
    return f"{num:,}"

def get_points(user_id: int) -> int:
    stats = load_stats()
    user_id_str = str(user_id)
    if user_id_str in stats:
        return int(stats[user_id_str].get("포인트", 0))
    return 0

def add_points(user_id: int, amount: int):
    stats = load_stats()
    user_id_str = str(user_id)
    ensure_user(stats, user_id_str)
    stats[user_id_str]["포인트"] = int(stats[user_id_str].get("포인트", 0)) + amount
    save_stats(stats)

def spend_points(user_id: int, amount: int) -> bool:
    stats = load_stats()
    user_id_str = str(user_id)
    ensure_user(stats, user_id_str)

    current_points = int(stats[user_id_str].get("포인트", 0))
    if current_points >= amount:
        stats[user_id_str]["포인트"] = current_points - amount
        save_stats(stats)
        return True
    return False