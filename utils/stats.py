import json
import os
from typing import Dict, Any

# --- 상수 정의 ---
STATS_FILE = "stats.json"
DEFAULT_POINTS = 10000  # 새 사용자의 기본 포인트

# --- 데이터 관리 함수 ---
def load_stats() -> Dict[str, Any]:
    """stats.json 파일에서 데이터를 불러옵니다. 파일이 없으면 빈 딕셔너리를 반환합니다."""
    if not os.path.exists(STATS_FILE):
        return {}
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            # 파일이 비어있는 경우 JSONDecodeError 방지
            content = f.read()
            if not content:
                return {}
            return json.loads(content)
    except (json.JSONDecodeError, IOError):
        # 파일이 손상되었거나 읽기 오류 발생 시
        return {}

def save_stats(stats: Dict[str, Any]):
    """데이터를 stats.json 파일에 저장합니다."""
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)
    except IOError as e:
        print(f"Error saving stats: {e}")

def ensure_user(stats: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    데이터 딕셔너리에서 사용자를 찾아 반환합니다.
    사용자가 없으면 기본값으로 새로 생성하고 반환합니다.
    """
    if user_id not in stats:
        stats[user_id] = {"포인트": DEFAULT_POINTS}
    # 사용자는 있지만 '포인트' 키가 없는 경우 대비
    elif "포인트" not in stats[user_id]:
        stats[user_id]["포인트"] = DEFAULT_POINTS
    return stats[user_id]

# --- 포인트 관리 API (economy.py와 호환) ---
def get_points(user_id: int) -> int:
    """특정 사용자의 포인트를 조회합니다."""
    stats = load_stats()
    user_record = ensure_user(stats, str(user_id))
    # ensure_user가 '포인트' 키를 보장하므로 .get() 대신 직접 접근 가능
    return user_record["포인트"]

def add_points(user_id: int, amount: int):
    """특정 사용자에게 포인트를 추가합니다."""
    if amount <= 0:
        return
    stats = load_stats()
    user_record = ensure_user(stats, str(user_id))
    user_record["포인트"] += amount
    save_stats(stats)

def spend_points(user_id: int, amount: int) -> bool:
    """
    특정 사용자의 포인트를 사용(차감)합니다.
    포인트가 충분하면 True, 부족하면 False를 반환합니다.
    """
    if amount <= 0:
        return True
    stats = load_stats()
    user_record = ensure_user(stats, str(user_id))
    
    if user_record["포인트"] < amount:
        return False  # 포인트 부족

    user_record["포인트"] -= amount
    save_stats(stats)
    return True

# --- 유틸리티 함수 ---
def format_num(num: int) -> str:
    """숫자를 콤마가 포함된 문자열로 변환합니다."""
    return f"{num:,}"
