"""전설이 키우기 핵심 게임 로직 (봇·웹 공용 단일 소스).

디스코드 봇(cogs/petsystem)과 웹앱(webapp)이 모두 이 모듈을 호출합니다.
보상·확률·비용을 바꿀 땐 여기만 고치면 양쪽에 동시 반영됩니다.
모든 변경 함수는 utils.locks 의 유저 락으로 감싸 연타에 안전합니다.
"""

import time
import random
from datetime import datetime, timezone, timedelta

from utils.data import ITEMS_INFO, EXP_TABLE, get_pet_total_stats
from utils.database import (get_or_migrate_data, save_legend_data, get_active_buffs,
                            consume_item, add_item, update_max_star,
                            start_expedition, get_expedition, clear_expedition,
                            add_quest_progress, get_quest_row, set_quest_claimed)
from utils.stats import add_points, spend_points
from utils.locks import get_user_lock

KST = timezone(timedelta(hours=9))


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


# ==========================================
# 일일 퀘스트 정의
# ==========================================
QUESTS = [
    ("walk",   "🚶 산책 30회",           30, 30, 1),
    ("care",   "🍚 돌보기 3회 (밥/샤워)",  3,  20, 2),
    ("battle", "⚔️ 배틀 1회 참여",         1,  50, 4),
]
ALL_CLEAR_BONUS = 100
ALL_CLEAR_BIT = 8


async def quest_progress(user_id: int, field: str, amount: int = 1):
    """산책/돌보기/배틀 진행도 누적 (실패해도 본 기능은 계속되도록 예외 무시)."""
    try:
        await add_quest_progress(user_id, today_kst(), field, amount)
    except Exception as e:
        print(f"⚠️ 일일 퀘스트 진행도 기록 실패({field}): {e}")


async def get_quest_status(user_id: int) -> dict:
    """일일 퀘스트 진행 현황 (표시용)."""
    row = await get_quest_row(user_id, today_kst())
    claimed = (row['claimed'] if row else 0) or 0
    quests, done_count = [], 0
    for field, title, goal, reward, bit in QUESTS:
        cur = min((row[field] if row else 0) or 0, goal)
        done = cur >= goal
        if done:
            done_count += 1
        quests.append({"field": field, "title": title, "cur": cur, "goal": goal,
                       "reward": reward, "done": done, "claimed": bool(claimed & bit)})
    return {"date": today_kst(), "quests": quests,
            "all_clear": done_count == len(QUESTS),
            "all_clear_claimed": bool(claimed & ALL_CLEAR_BIT),
            "all_clear_bonus": ALL_CLEAR_BONUS}


async def claim_daily_quests(user_id: int) -> dict:
    """완료했지만 아직 안 받은 퀘스트 보상을 전부 수령합니다."""
    qdate = today_kst()
    async with get_user_lock(user_id):
        row = await get_quest_row(user_id, qdate)
        if not row:
            return {"ok": False, "error": "오늘 진행한 퀘스트가 없습니다."}
        claimed = row['claimed'] or 0
        total_eggs, gained, done_count = 0, [], 0
        for field, title, goal, reward, bit in QUESTS:
            if (row[field] or 0) >= goal:
                done_count += 1
                if not claimed & bit:
                    total_eggs += reward
                    claimed |= bit
                    gained.append(f"{title} → 서사급 알 +{reward}")
        if done_count == len(QUESTS) and not claimed & ALL_CLEAR_BIT:
            total_eggs += ALL_CLEAR_BONUS
            claimed |= ALL_CLEAR_BIT
            gained.append(f"🌟 올클리어 보너스 → 서사급 알 +{ALL_CLEAR_BONUS}")
        if not gained:
            return {"ok": False, "error": "수령할 완료 보상이 없습니다. (미완료거나 이미 수령함)"}
        await add_item(user_id, "서사급 알", total_eggs)
        await set_quest_claimed(user_id, qdate, claimed)
    return {"ok": True, "gained": gained, "total_eggs": total_eggs}


# ==========================================
# 돌보기: 밥주기 / 샤워
# ==========================================
async def feed_pet(user_id: int, pet_idx: int) -> dict:
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "펫 데이터가 없습니다."}
        data = pets[pet_idx]
        if data.get('level', 0) == 0:
            return {"ok": False, "error": "알은 아직 밥을 먹을 수 없습니다."}
        if not await spend_points(user_id, 5):
            return {"ok": False, "error": "❌ 밥값(5P)이 부족합니다!"}
        data['fullness'] = min(100, data.get('fullness', 0) + 20)
        await save_legend_data(user_id, wrapper)
        await quest_progress(user_id, 'care', 1)
        return {"ok": True, "name": data.get('name', '이름없음'), "fullness": data['fullness'], "data": data}


async def shower_pet(user_id: int, pet_idx: int) -> dict:
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "펫 데이터가 없습니다."}
        data = pets[pet_idx]
        if data.get('level', 0) == 0:
            return {"ok": False, "error": "알은 아직 샤워할 수 없습니다."}
        if not await spend_points(user_id, 10):
            return {"ok": False, "error": "❌ 수도세(10P)가 부족합니다!"}
        data['cleanliness'] = min(100, data.get('cleanliness', 0) + 20)
        await save_legend_data(user_id, wrapper)
        await quest_progress(user_id, 'care', 1)
        return {"ok": True, "name": data.get('name', '이름없음'), "cleanliness": data['cleanliness'], "data": data}


# ==========================================
# 산책
# ==========================================
async def do_walk(user_id: int, pet_idx: int, num_walks: int) -> dict:
    """산책 실행. 비용/버프/스탯 변화/알·아이템 발견/경험치까지 봇과 동일 로직."""
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "펫 데이터가 없습니다."}
        data = pets[pet_idx]
        if data.get('level', 0) == 0:
            return {"ok": False, "error": "알은 산책할 수 없습니다."}

        if num_walks == 100:
            has_ticket = await consume_item(user_id, "100회 산책 할인권", 1)
            cost = 30 if has_ticket else 100
        else:
            has_ticket = False
            cost = num_walks * 1

        if not await spend_points(user_id, cost):
            if has_ticket:
                await add_item(user_id, "100회 산책 할인권", 1)
            return {"ok": False, "error": f"❌ 산책 유지비({cost}P)가 부족합니다!"}

        active_buffs = await get_active_buffs(user_id)
        buffs = {b[0] for b in active_buffs}

        data['total_walk_count'] = data.get('total_walk_count', 0) + num_walks
        data['walk_count'] = data.get('walk_count', 0) + num_walks
        stat_triggers = data['walk_count'] // 20
        data['walk_count'] %= 20
        stat_msgs = []

        if stat_triggers > 0:
            stat_msgs.append(f"✨ {stat_triggers * 20}회 산책 분량 달성!")
            if "신비한 알약" in buffs or "배부름을 부르는 약" in buffs:
                data['fullness'] = 100; stat_msgs.append("💊 [배부름 약] 효과로 포만도가 100으로 유지되었습니다!")
            else: data['fullness'] = max(0, data.get('fullness', 100) - (20 * stat_triggers))

            if "신비한 알약" in buffs or "트위치 나가라약" in buffs:
                data['cleanliness'] = 100; stat_msgs.append("💊 [나가라 약] 효과로 청결도가 100으로 유지되었습니다!")
            else: data['cleanliness'] = max(0, data.get('cleanliness', 100) - (20 * stat_triggers))

            if "신비한 알약" in buffs or "아무무도 인싸로 만드는 약" in buffs:
                data['intimacy'] = 100; stat_msgs.append("💊 [인싸 약] 효과로 친밀도가 100으로 유지되었습니다!")
            else: data['intimacy'] = min(100, data.get('intimacy', 50) + (20 * stat_triggers))

            if "신비한 알약" in buffs or "쌩쌩한약" in buffs:
                data['fatigue'] = 0; stat_msgs.append("💊 [쌩쌩한약] 효과로 피로도가 0으로 유지되었습니다!")
            else: data['fatigue'] = min(100, data.get('fatigue', 0) + (20 * stat_triggers))

        found_eggs, found_items = [], []
        epic_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '서사']
        legend_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '전설']
        mythic_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '신화']
        prestige_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '프레스티지']

        for _ in range(num_walks):
            r_egg = random.random()
            # 초월급 알은 산책으로 획득 불가(합성 전용). 고귀급 알만 극악 확률로 등장.
            if r_egg < 0.000005: found_eggs.append("고귀")
            elif r_egg < 0.0001: found_eggs.append("프레스티지")
            elif r_egg < 0.0021: found_eggs.append("신화")
            elif r_egg < 0.0221: found_eggs.append("전설")
            elif r_egg < 0.1221: found_eggs.append("서사")

            r_item = random.random()
            if r_item < 0.0001 and prestige_items: found_items.append(("프레스티지", random.choice(prestige_items)))
            elif r_item < 0.0005 and mythic_items: found_items.append(("신화", random.choice(mythic_items)))
            elif r_item < 0.0015 and legend_items: found_items.append(("전설", random.choice(legend_items)))
            elif r_item < 0.1015 and epic_items: found_items.append(("서사", random.choice(epic_items)))

        gained_exp = 0
        if 0 < data.get('level', 0) < 3:
            gained_exp = num_walks
            data['exp'] = data.get('exp', 0) + gained_exp
            rarity = data.get('rarity', '서사')
            # 통화방 레벨업(core.py)과 동일한 EXP_TABLE 단일 기준
            while data.get('level', 0) < 3:
                curr_level = data.get('level', 0)
                req_exp = EXP_TABLE.get(rarity, {}).get(curr_level, 100)
                if data.get('exp', 0) >= req_exp:
                    data['level'] = curr_level + 1
                    data['exp'] -= req_exp
                else:
                    break
            if data.get('level', 0) >= 3:
                await update_max_star(user_id, 3)

        for egg in found_eggs:
            await add_item(user_id, f"{egg}급 알", 1)
        for _, item_name in found_items:
            await add_item(user_id, item_name, 1)

        await save_legend_data(user_id, wrapper)
        await quest_progress(user_id, 'walk', num_walks)

        return {"ok": True, "name": data.get('name', '이름없음'), "num_walks": num_walks,
                "cost": cost, "has_ticket": has_ticket, "stat_msgs": stat_msgs,
                "found_eggs": found_eggs, "found_items": found_items,
                "gained_exp": gained_exp, "level": data.get('level', 0), "data": data}


# ==========================================
# 원정
# ==========================================
EXPEDITION_DURATIONS = [1, 4, 8, 24]

HOURLY_EGG_ROLLS = [
    ("고귀", 0.0003),
    ("프레스티지", 0.0025),
    ("신화", 0.012),
    ("전설", 0.05),
]


def calc_expedition_rewards(power: int, hours: int):
    """원정 보상: (서사급 알, [상위 알 목록], 포인트)"""
    epic_eggs = hours * (5 + power // 200)
    bonus_eggs = []
    for _ in range(hours):
        r = random.random()
        acc = 0.0
        for rarity, prob in HOURLY_EGG_ROLLS:
            acc += prob
            if r < acc:
                bonus_eggs.append(rarity)
                break
    points = hours * 20
    return epic_eggs, bonus_eggs, points


async def get_expedition_status(user_id: int) -> dict | None:
    """원정 상태 (없으면 None)."""
    exp = await get_expedition(user_id)
    if not exp:
        return None
    end_ts = exp['start_ts'] + exp['duration_h'] * 3600
    return {"pet_name": exp['pet_name'], "pet_type": exp['pet_type'],
            "pet_level": exp['pet_level'], "power": exp['power'],
            "duration_h": exp['duration_h'], "end_ts": end_ts,
            "done": time.time() >= end_ts,
            "remain_sec": max(0, int(end_ts - time.time()))}


async def start_expedition_for(user_id: int, pet_idx: int, hours: int, power_fn) -> dict:
    """원정 시작. power_fn(pet)로 전투력을 계산해 스냅샷으로 저장합니다."""
    if hours not in EXPEDITION_DURATIONS:
        return {"ok": False, "error": "원정 시간은 1/4/8/24시간 중 선택하세요."}
    async with get_user_lock(user_id):
        if await get_expedition(user_id):
            return {"ok": False, "error": "이미 진행 중인 원정이 있습니다!"}
        wrapper = await get_or_migrate_data(user_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "펫 데이터가 변경되었습니다. 다시 시도해주세요."}
        pet = pets[pet_idx]
        if pet.get('level', 0) == 0:
            return {"ok": False, "error": "알은 원정을 갈 수 없습니다!"}
        power = power_fn(pet)
        await start_expedition(user_id, pet.get('name', '이름없음'), pet.get('type', '?'),
                               pet.get('level', 1), power, hours)
    return {"ok": True, "name": pet.get('name'), "type": pet.get('type'),
            "level": pet.get('level'), "power": power, "hours": hours,
            "est_eggs": hours * (5 + power // 200)}


async def claim_expedition(user_id: int) -> dict:
    """원정 보상 수령 (시간 미도달/이중 수령 방지)."""
    async with get_user_lock(user_id):
        exp = await get_expedition(user_id)
        if not exp:
            return {"ok": False, "error": "진행 중인 원정이 없습니다."}
        end_ts = exp['start_ts'] + exp['duration_h'] * 3600
        if time.time() < end_ts:
            remain = int((end_ts - time.time()) // 60) + 1
            return {"ok": False, "error": f"⏰ 아직 원정 중입니다! (남은 시간: 약 {remain}분)"}
        epic_eggs, bonus_eggs, points = calc_expedition_rewards(exp['power'], exp['duration_h'])
        await add_item(user_id, "서사급 알", epic_eggs)
        for rarity in bonus_eggs:
            await add_item(user_id, f"{rarity}급 알", 1)
        await add_points(user_id, points)
        await clear_expedition(user_id)
    return {"ok": True, "pet_name": exp['pet_name'], "hours": exp['duration_h'],
            "epic_eggs": epic_eggs, "bonus_eggs": bonus_eggs, "points": points}
