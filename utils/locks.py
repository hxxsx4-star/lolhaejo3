"""유저별 동시성 제어 (봇·웹 공용).

같은 user_id 의 '읽기-수정-저장'을 직렬화해 데이터 유실을 방지합니다.
(asyncio.Lock 이므로 같은 프로세스 안에서만 유효합니다.
봇과 웹서버는 별개 프로세스라, 두 곳을 정확히 동시에 조작하는 극히
드문 경우엔 한쪽 스탯 변경이 덮일 수 있습니다 — 아이템/포인트는
DB 원자 연산·파일락이라 안전합니다.)
"""

import asyncio
from collections import defaultdict

_user_locks: "defaultdict[int, asyncio.Lock]" = defaultdict(asyncio.Lock)


def get_user_lock(user_id: int) -> asyncio.Lock:
    return _user_locks[user_id]
