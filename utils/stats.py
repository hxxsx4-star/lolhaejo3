# utils/stats.py
# ✨ 포인트 저장소를 '공유 파일(stats.json)'에서 이 봇 전용 로컬 DB(legends.db)로 교체했습니다.
#    함수 이름/시그니처는 그대로 유지되어 펫 시스템 등 기존 코드는 수정 없이 동작합니다.
#    => 포인트가 더 이상 다른 봇과 공유되지 않고, 이 봇 안에서 전부 처리됩니다.
import aiosqlite
from utils.database import DB_PATH, get_user, update_user_points


def format_num(num) -> str:
    """숫자에 3자리마다 콤마를 찍어주는 유틸 함수입니다."""
    try:
        return f"{int(num):,}"
    except (TypeError, ValueError):
        return str(num)


async def get_points(user_id: int) -> int:
    """유저의 보유 포인트를 반환합니다. (없으면 기본값으로 유저 생성)"""
    data = await get_user(user_id)
    return int(data[1] or 0)


async def add_points(user_id: int, amount: int):
    """유저에게 포인트를 지급합니다."""
    await get_user(user_id)  # 유저 행이 없으면 먼저 생성
    await update_user_points(user_id, amount)


async def spend_points(user_id: int, amount: int) -> bool:
    """유저의 포인트를 차감합니다. 잔액이 부족하면 False를 반환합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT points FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            # 유저가 없으면 기본값으로 생성 후 잔액 확인
            await db.execute("INSERT INTO users VALUES (?, 3000, 0, 0, 0, 0)", (user_id,))
            await db.commit()
            current = 3000
        else:
            current = int(row[0] or 0)

        if current < amount:
            return False

        await db.execute(
            "UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?",
            (amount, user_id),
        )
        await db.commit()
        return True
