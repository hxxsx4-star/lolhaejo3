from typing import Optional
import json
import os
import asyncio
from filelock import FileLock, Timeout
from datetime import datetime, timedelta, timezone

SHARED_FILE_PATH = "/home/hxxsx4/shared_data/stats.json"
LOCK_FILE_PATH = "/home/hxxsx4/shared_data/stats.json.lock"

os.makedirs(os.path.dirname(SHARED_FILE_PATH), exist_ok=True)
# 다른 봇이 파일을 쥐고 있을 때 무한정 대기하지 않도록 timeout(5초) 설정
lock = FileLock(LOCK_FILE_PATH, timeout=5)

# --- Lock 내부용 헬퍼 함수 (직접 호출 금지 / 동기 유지) ---
def _load_stats_nolock() -> dict:
    if not os.path.exists(SHARED_FILE_PATH):
        return {}
    try:
        with open(SHARED_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def _save_stats_nolock(stats: dict):
    with open(SHARED_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4, ensure_ascii=False)

def ensure_user(stats: dict, user_id: str) -> dict:
    if user_id not in stats:
        stats[user_id] = {"포인트": 0, "경고": 0}
    return stats[user_id]

def format_num(n: int) -> str:
    return f"{n:,}"

# --- 비동기(Async) 유틸리티 함수 ---
async def load_stats() -> dict:
    def _task():
        with lock:
            return _load_stats_nolock()
    return await asyncio.to_thread(_task)

async def save_stats(stats: dict):
    def _task():
        with lock:
            _save_stats_nolock(stats)
    await asyncio.to_thread(_task)

# --- 비동기(Async) 경제 시스템 ---
async def get_points(user_id: int) -> int:
    def _task():
        with lock:
            stats = _load_stats_nolock()
            return int(ensure_user(stats, str(user_id)).get("포인트", 0))
    return await asyncio.to_thread(_task)

async def add_points(user_id: int, amount: int):
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            rec["포인트"] = int(rec.get("포인트", 0)) + amount
            _save_stats_nolock(stats)
    await asyncio.to_thread(_task)

async def spend_points(user_id: int, amount: int) -> bool:
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            current_points = int(rec.get("포인트", 0))
            if current_points < amount:
                return False  # 잔액 부족
            rec["포인트"] = current_points - amount
            _save_stats_nolock(stats)
            return True
    return await asyncio.to_thread(_task)

async def process_attendance(user_id: int, reward: int, attend_key: str, today_str: str) -> bool:
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))

            if rec.get(attend_key) == today_str:
                return False  # 이미 출석함

            rec["포인트"] = int(rec.get("포인트", 0)) + reward
            rec[attend_key] = today_str
            _save_stats_nolock(stats)
            return True
    return await asyncio.to_thread(_task)

# ===== 비동기(Async) 내전 정지 관련 함수 =====
async def set_match_ban(user_id: int, days: int) -> Optional[datetime]:
    def _task():
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
    return await asyncio.to_thread(_task)

async def get_match_ban_expiry(user_id: int) -> Optional[datetime]:
    def _task():
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
    return await asyncio.to_thread(_task)

# ===== ✨ 추가: 경고 부여/차감 원자적(Atomic) 처리 함수 =====
async def add_warning(user_id: int, count: int) -> tuple[int, int]:
    """경고를 부여하고 (이전 경고 수, 새로운 경고 수)를 반환합니다."""
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            old_warn = int(rec.get("경고", 0))
            new_warn = old_warn + count
            rec["경고"] = new_warn
            _save_stats_nolock(stats)
            return old_warn, new_warn
    return await asyncio.to_thread(_task)

async def reduce_warning(user_id: int, count: int) -> tuple[int, int]:
    """경고를 차감하고 (이전 경고 수, 새로운 경고 수)를 반환합니다."""
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            old_warn = int(rec.get("경고", 0))
            new_warn = max(0, old_warn - count)
            rec["경고"] = new_warn
            _save_stats_nolock(stats)
            return old_warn, new_warn
    return await asyncio.to_thread(_task)