# 임시 포인트 저장을 위한 메모리 내 딕셔너리
_user_points = {}

# 기본 포인트
DEFAULT_POINTS = 10000

def get_points(user_id: int) -> int:
    """사용자의 포인트를 반환합니다. 없으면 기본 포인트를 부여합니다."""
    if user_id not in _user_points:
        _user_points[user_id] = DEFAULT_POINTS
    return _user_points[user_id]

def spend_points(user_id: int, amount: int) -> bool:
    """사용자의 포인트를 차감합니다. 포인트가 충분해야 합니다."""
    current_points = get_points(user_id)
    if current_points < amount:
        return False
    _user_points[user_id] -= amount
    return True

def add_points(user_id: int, amount: int):
    """사용자의 포인트를 증가시킵니다."""
    _user_points[user_id] = get_points(user_id) + amount

def format_num(num: int) -> str:
    """숫자를 읽기 쉽게 콤마를 추가하여 포맷팅합니다."""
    return f"{num:,}"
