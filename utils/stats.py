from typing import Optional
import json
import os
from filelock import FileLock, Timeout
from datetime import datetime, timedelta, timezone

SHARED_FILE_PATH = "/home/hxxsx4/shared_data/stats.json"
LOCK_FILE_PATH = "/home/hxxsx4/shared_data/stats.json.lock"

os.makedirs(os.path.dirname(SHARED_FILE_PATH), exist_ok=True)
# 다른 봇이 파일을 쥐고 있을 때 무한정 대기하지 않도록 timeout(5초) 설정
lock = FileLock(LOCK_FILE_PATH, timeout=5)

# --- Lock 내부용 헬퍼 함수 (직접 호출 금지) ---
def _load_stats_nolock() -> dict:
    """Lock이 걸린 상태에서만 호출되는 내부 읽기 함수"""
    if not os.path.exists(SHARED_FILE_PATH):
        return {}
    try:
        with open(SHARED_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def _save_stats_nolock(stats: dict):
    """Lock이 걸린 상태에서만 호출되는 내부 쓰기 함수"""
    with open(SHARED_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4, ensure_ascii=False)

# --- 기본 유틸리티 ---
def ensure_user(stats: dict, user_id: str) -> dict:
    if user_id not in stats:
        stats[user_id] = {"포인트": 0, "경고": 0}
    return stats[user_id]

def format_num(n: int) -> str:
    return f"{n:,}"

def load_stats() -> dict:
    """읽기 전용으로 통계 데이터를 가져옵니다. (순위표 등에서 사용)"""
    with lock:
        return _load_stats_nolock()

def save_stats(stats: dict):
    """외부에서 통계 데이터를 덮어쓸 때 사용하는 안전한 저장 함수"""
    with lock:
        _save_stats_nolock(stats)

# --- 경제 시스템 (트랜잭션 안전 보장) ---
def get_points(user_id: int) -> int:
    with lock:
        stats = _load_stats_nolock()
        return int(ensure_user(stats, str(user_id)).get("포인트", 0))

def add_points(user_id: int, amount: int):
    with lock:
        stats = _load_stats_nolock()
        rec = ensure_user(stats, str(user_id))
        rec["포인트"] = int(rec.get("포인트", 0)) + amount
        _save_stats_nolock(stats)

def spend_points(user_id: int, amount: int) -> bool:
    with lock:
        stats = _load_stats_nolock()
        rec = ensure_user(stats, str(user_id))
        current_points = int(rec.get("포인트", 0))
        if current_points < amount:
            return False  # 잔액 부족
        rec["포인트"] = current_points - amount
        _save_stats_nolock(stats)
        return True

def process_attendance(user_id: int, reward: int, attend_key: str, today_str: str) -> bool:
    """출석 처리를 Lock 안에서 안전하게 수행합니다."""
    with lock:
        stats = _load_stats_nolock()
        rec = ensure_user(stats, str(user_id))

        if rec.get(attend_key) == today_str:
            return False  # 이미 출석함

        rec["포인트"] = int(rec.get("포인트", 0)) + reward
        rec[attend_key] = today_str
        _save_stats_nolock(stats)
        return True

# ===== 내전 정지 관련 함수 =====
def set_match_ban(user_id: int, days: int) -> Optional[datetime]:
    with lock:
        stats = _load_stats_nolock()
        rec = ensure_user(stats, str(user_id))

        if days > 0:
            expiry = datetime.now(timezone.utc) + timedelta(days=days)
            rec["내전정지"] = expiry.isoformat()
            _save_stats_nolock(stats)
            return expiry
        else:
            if "내전정지" in rec:
                del rec["내전정지"]
                _save_stats_nolock(stats)
            return None

def get_match_ban_expiry(user_id: int) -> Optional[datetime]:
    with lock:
        stats = _load_stats_nolock()
        rec = ensure_user(stats, str(user_id))

        expiry_str = rec.get("내전정지")
        if not expiry_str:
            return None

        expiry_dt = datetime.fromisoformat(expiry_str)
        if datetime.now(timezone.utc) > expiry_dt:
            del rec["내전정지"]
            _save_stats_nolock(stats)
            return None

        return expiry_dt