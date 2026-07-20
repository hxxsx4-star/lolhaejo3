"""유저별 동시성 제어.

실제 구현은 utils/locks.py 로 이동했습니다 (봇·웹이 같은 락을 공유).
기존 `from .locks import get_user_lock` 호출부 호환을 위해 재노출합니다.
"""

from utils.locks import get_user_lock  # noqa: F401
