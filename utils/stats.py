import json
import os
from filelock import FileLock

# --- 핵심 설정: 두 봇이 공통으로 바라볼 절대 경로 ---
SHARED_FILE_PATH = "/home/hxxsx4/shared_data/stats.json"
LOCK_FILE_PATH = "/home/hxxsx4/shared_data/stats.json.lock"

# 폴더가 혹시 없다면 자동으로 생성해주는 안전장치
os.makedirs(os.path.dirname(SHARED_FILE_PATH), exist_ok=True)

# 파일 락(Lock) 객체 생성
lock = FileLock(LOCK_FILE_PATH)

def load_stats() -> dict:
    """포인트 데이터를 불러옵니다. 파일이 겹치지 않게 Lock을 사용합니다."""
    # 파일이 아예 없으면 빈 딕셔너리 반환
    if not os.path.exists(SHARED_FILE_PATH):
        return {}

    # 누군가 파일을 쓰고 있다면 대기하다가 읽음
    with lock:
        try:
            with open(SHARED_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("[ERROR] stats.json 파일이 손상되었습니다. 빈 데이터로 시작합니다.")
            return {}

def save_stats(data: dict):
    """포인트 데이터를 저장합니다. 봇 2개가 동시에 접근해도 꼬이지 않게 줄을 세웁니다."""
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