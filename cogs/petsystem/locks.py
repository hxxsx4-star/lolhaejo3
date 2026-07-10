"""유저별 동시성 제어.

버튼을 빠르게 여러 번 누르거나 여러 명령을 동시에 실행하면,
'전설이 데이터 읽기 -> 수정 -> 저장' 사이에 다른 처리가 끼어들어
변경이 유실(lost update)되거나 중복 처리될 수 있습니다.

같은 user_id 의 요청을 이 잠금으로 직렬화하여 그 문제를 방지합니다.
(서로 다른 유저는 각자 다른 잠금을 쓰므로 동시에 처리되어 성능 저하가 없습니다.)
"""

import asyncio
from collections import defaultdict

_user_locks: "defaultdict[int, asyncio.Lock]" = defaultdict(asyncio.Lock)


def get_user_lock(user_id: int) -> asyncio.Lock:
    """해당 유저 전용 asyncio.Lock 을 돌려줍니다. (없으면 생성)"""
    return _user_locks[user_id]
