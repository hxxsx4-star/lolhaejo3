"""전설이 키우기 핵심 게임 로직 (봇·웹 공용 단일 소스).

디스코드 봇(cogs/petsystem)과 웹앱(webapp)이 모두 이 모듈을 호출합니다.
보상·확률·비용을 바꿀 땐 여기만 고치면 양쪽에 동시 반영됩니다.
모든 변경 함수는 utils.locks 의 유저 락으로 감싸 연타에 안전합니다.
"""

import time
import random
from datetime import datetime, timezone, timedelta

from utils.data import (ITEMS_INFO, EXP_TABLE, PET_POOLS, EQUIPMENTS, EQUIP_PRICE,
                        MAX_EQUIP_PER_PET, RARITY_ORDER, format_equip_effect,
                        get_pet_total_stats, get_equipment_bonus)
from utils.database import (get_or_migrate_data, save_legend_data, get_active_buffs,
                            consume_item, add_item, get_item_amount, add_synth_count,
                            update_max_star,
                            start_expedition, get_expedition, clear_expedition,
                            add_quest_progress, get_quest_row, set_quest_claimed,
                            get_attendance, set_attendance)
from utils.stats import add_points, spend_points
from utils.locks import get_user_lock

KST = timezone(timedelta(hours=9))


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def yesterday_kst() -> str:
    return (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")


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


# ==========================================
# 장비 장착 / 해제 (봇 /장비 와 동일 규칙)
# ==========================================
async def equip_pet(user_id: int, pet_idx: int, equip_name: str) -> dict:
    """인벤토리의 장비를 전설이에게 장착 (최대 MAX_EQUIP_PER_PET 개)."""
    if equip_name not in EQUIPMENTS:
        return {"ok": False, "error": "존재하지 않는 장비입니다."}
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "전설이 데이터가 변경되었습니다. 다시 시도하세요."}
        pet = pets[pet_idx]
        equipped = pet.get('equipment', []) or []
        if len(equipped) >= MAX_EQUIP_PER_PET:
            return {"ok": False, "error": f"장비는 최대 {MAX_EQUIP_PER_PET}개까지 장착할 수 있습니다."}
        if not await consume_item(user_id, equip_name, 1):
            return {"ok": False, "error": "해당 장비를 보유하고 있지 않습니다."}
        equipped.append(equip_name)
        pet['equipment'] = equipped
        await save_legend_data(user_id, wrapper)
    return {"ok": True, "name": pet.get('name', '이름없음'), "equip": equip_name,
            "equipped": equipped}


async def unequip_pet(user_id: int, pet_idx: int, equip_name: str) -> dict:
    """장착된 장비를 해제하고 인벤토리로 반환. 특수 장비 누적 스택은 초기화."""
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "전설이 데이터가 변경되었습니다. 다시 시도하세요."}
        pet = pets[pet_idx]
        equipped = pet.get('equipment', []) or []
        if equip_name not in equipped:
            return {"ok": False, "error": "이미 해제된 장비입니다."}
        equipped.remove(equip_name)
        pet['equipment'] = equipped
        stacks = pet.get('equip_stacks', {})
        if equip_name in stacks:
            del stacks[equip_name]
        await add_item(user_id, equip_name, 1)
        await save_legend_data(user_id, wrapper)
    return {"ok": True, "name": pet.get('name', '이름없음'), "equip": equip_name,
            "equipped": equipped}


# ==========================================
# 알 상점 (서사급 알로 장비/합성 방어권 구매)
# ==========================================
SHOP_CURRENCY = "서사급 알"
PROTECT_TICKET = "합성 방어권"
PROTECT_TICKET_PRICE = 100000


def shop_price(item_name: str):
    if item_name == PROTECT_TICKET:
        return PROTECT_TICKET_PRICE
    info = EQUIPMENTS.get(item_name)
    return EQUIP_PRICE[info["rarity"]] if info else None


def shop_catalog() -> list:
    """상점 진열 목록 (등급별 장비 + 합성 방어권)을 웹 표시용으로 반환."""
    cats = [{"rarity": "특수", "items": [
        {"name": PROTECT_TICKET, "price": PROTECT_TICKET_PRICE,
         "effect": "합성 실패 시 재료 전설이 보존"}]}]
    for rarity in RARITY_ORDER:
        names = [n for n, i in EQUIPMENTS.items() if i["rarity"] == rarity]
        if not names:
            continue
        cats.append({"rarity": rarity, "items": [
            {"name": n, "price": EQUIP_PRICE[rarity], "effect": format_equip_effect(n)}
            for n in names]})
    return cats


async def buy_shop_item(user_id: int, item_name: str) -> dict:
    """서사급 알로 상점 아이템 1개 구매 (원자적 차감)."""
    price = shop_price(item_name)
    if price is None:
        return {"ok": False, "error": "알 수 없는 아이템입니다."}
    async with get_user_lock(user_id):
        owned = await get_item_amount(user_id, SHOP_CURRENCY)
        if owned < price:
            return {"ok": False, "error": f"서사급 알이 부족합니다! (필요 {price:,} / 보유 {owned:,})"}
        if not await consume_item(user_id, SHOP_CURRENCY, price):
            return {"ok": False, "error": "결제에 실패했습니다. 잔여 수량을 확인해주세요."}
        await add_item(user_id, item_name, 1)
        remain = owned - price
    return {"ok": True, "item": item_name, "price": price, "remain": remain,
            "is_equip": item_name in EQUIPMENTS}


# ==========================================
# 알까기(가챠) / 합성
# ==========================================
MAX_PETS = 5
HATCH_COST = 1000
# 확률 순서: 서사, 전설, 신화, 프레스티지, 고귀, 초월
# 고귀=0.001%, 초월은 알까기로 획득 불가(합성 전용)
HATCH_WEIGHTS = [85, 14, 0.9, 0.1, 0.001, 0.0]

# 합성: 등급 → (상위 등급, 성공 확률)
SYNTH_TARGET = {
    "서사": ("전설", 0.8), "전설": ("신화", 0.5), "신화": ("프레스티지", 0.2),
    "프레스티지": ("고귀", 0.05), "고귀": ("초월", 0.01),
}


def _new_pet(name: str, ptype: str, rarity: str) -> dict:
    return {'name': name, 'type': ptype, 'rarity': rarity, 'level': 0, 'exp': 0,
            'fullness': 100, 'intimacy': 50, 'fatigue': 0, 'cleanliness': 100,
            'walk_count': 0, 'total_walk_count': 0, 'last_fatigue_calc': time.time()}


async def hatch_roll(user_id: int, name: str) -> dict:
    """알까기 1단계: 포인트 차감 후 등급을 뽑고, 선택할 종류 목록을 돌려줍니다.
    (첫 마리는 무료, 이후 1000P). 뽑힌 등급은 pending 으로 저장되어 pick 에서만 사용됩니다."""
    name = (name or "").strip()[:20] or "이름없는 전설이"
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        pets = wrapper.get('pets', [])
        if len(pets) >= MAX_PETS:
            return {"ok": False, "error": f"전설이는 최대 {MAX_PETS}마리까지만 파티에 둘 수 있습니다."}
        is_first = (len(pets) == 0)
        cost = 0 if is_first else HATCH_COST
        if cost and not await spend_points(user_id, cost):
            return {"ok": False, "error": f"가챠 비용이 부족합니다! (필요 {cost:,}P)"}
        rarity = random.choices(RARITY_ORDER, weights=HATCH_WEIGHTS, k=1)[0]
        wrapper['pending_hatch'] = {"rarity": rarity, "name": name, "ts": time.time()}
        await save_legend_data(user_id, wrapper)
    return {"ok": True, "rarity": rarity, "name": name, "cost": cost,
            "pool": list(PET_POOLS[rarity])}


async def hatch_pick(user_id: int, ptype: str) -> dict:
    """알까기 2단계: pending 등급 안에서 원하는 종류를 골라 알을 생성합니다."""
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        pend = wrapper.get('pending_hatch')
        if not pend:
            return {"ok": False, "error": "먼저 알까기를 진행해주세요."}
        rarity = pend["rarity"]
        if ptype not in PET_POOLS.get(rarity, []):
            return {"ok": False, "error": "해당 등급에 없는 전설이입니다."}
        if len(wrapper.get('pets', [])) >= MAX_PETS:
            return {"ok": False, "error": f"전설이는 최대 {MAX_PETS}마리까지만 둘 수 있습니다."}
        pet = _new_pet(pend["name"], ptype, rarity)
        wrapper.setdefault('pets', []).append(pet)
        wrapper['active_idx'] = len(wrapper['pets']) - 1
        wrapper.pop('pending_hatch', None)
        await save_legend_data(user_id, wrapper)
    return {"ok": True, "rarity": rarity, "type": ptype, "name": pend["name"]}


async def synth_candidates(user_id: int) -> dict:
    """합성 가능한 등급별 3성 전설이 목록 (웹 선택 UI 용)."""
    wrapper = await get_or_migrate_data(user_id)
    pets = wrapper.get('pets', [])
    by_rarity = {}
    for i, p in enumerate(pets):
        if p.get('level', 0) == 3 and p.get('rarity') in SYNTH_TARGET:
            by_rarity.setdefault(p['rarity'], []).append(
                {"idx": i, "name": p.get('name', '이름없음'), "type": p.get('type', '?')})
    grades = []
    for rarity, (target, prob) in SYNTH_TARGET.items():
        cand = by_rarity.get(rarity, [])
        grades.append({"rarity": rarity, "target": target, "prob": prob,
                       "candidates": cand, "enough": len(cand) >= 2})
    protect = await get_item_amount(user_id, PROTECT_TICKET)
    return {"grades": grades, "protect_tickets": protect}


async def synthesize(user_id: int, idx1: int, idx2: int) -> dict:
    """3성 2마리를 합성. 성공 시 상위 등급 알 획득, 실패 시 합성 방어권으로 보존 가능."""
    if idx1 == idx2:
        return {"ok": False, "error": "서로 다른 두 마리를 선택하세요."}
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        pets = wrapper.get('pets', [])
        if max(idx1, idx2) >= len(pets):
            return {"ok": False, "error": "전설이 데이터가 변경되었습니다. 다시 시도하세요."}
        p1, p2 = pets[idx1], pets[idx2]
        if p1.get('rarity') != p2.get('rarity') or p1.get('rarity') not in SYNTH_TARGET:
            return {"ok": False, "error": "같은 등급의 합성 가능한 두 마리를 선택하세요."}
        if p1.get('level', 0) != 3 or p2.get('level', 0) != 3:
            return {"ok": False, "error": "두 마리 모두 3성이어야 합니다."}
        if p1.get('type') == p2.get('type'):
            return {"ok": False, "error": "합성에 쓰이는 두 전설이는 서로 다른 종류여야 합니다."}

        rarity = p1['rarity']
        target, prob = SYNTH_TARGET[rarity]
        success = random.random() < prob

        protected = False
        if not success:
            protected = await consume_item(user_id, PROTECT_TICKET, 1)

        new_type = None
        if success or not protected:
            for i in sorted([idx1, idx2], reverse=True):
                wrapper['pets'].pop(i)
            wrapper['active_idx'] = max(0, len(wrapper['pets']) - 1)

        if success:
            new_type = random.choice(PET_POOLS[target])
            wrapper.setdefault('pets', []).append(_new_pet(f"합성된 {new_type} 알", new_type, target))
            await add_synth_count(user_id)

        await save_legend_data(user_id, wrapper)

    return {"ok": True, "success": success, "protected": protected,
            "rarity": rarity, "target": target, "new_type": new_type}


# ==========================================
# 출석체크 (연속 출석 보너스, 7일 주기)
# ==========================================
# 7일 주기 보상. 연속 출석일이 늘수록 커지고, 7일차는 대박(전설급 알 포함).
ATTENDANCE_REWARDS = [
    {"eggs": 10,  "points": 100},                      # 1일차
    {"eggs": 15,  "points": 150},                      # 2일차
    {"eggs": 20,  "points": 200},                      # 3일차
    {"eggs": 25,  "points": 250},                      # 4일차
    {"eggs": 30,  "points": 300},                      # 5일차
    {"eggs": 40,  "points": 400},                      # 6일차
    {"eggs": 100, "points": 1000, "bonus_egg": "전설"},  # 7일차 (대박)
]
ATTENDANCE_CYCLE = len(ATTENDANCE_REWARDS)


def _cycle_pos(streak: int) -> int:
    """연속 출석일(1부터)을 7일 주기 인덱스(0~6)로 변환."""
    return (max(1, streak) - 1) % ATTENDANCE_CYCLE


async def check_in(user_id: int) -> dict:
    """오늘 출석을 처리하고 보상을 지급합니다. (하루 1회, KST 기준)"""
    today = today_kst()
    async with get_user_lock(user_id):
        row = await get_attendance(user_id)
        last = row["last_date"] if row else None
        prev_streak = (row["streak"] if row else 0) or 0
        total = (row["total_days"] if row else 0) or 0

        if last == today:
            return {"ok": False, "already": True, "error": "오늘은 이미 출석했습니다!",
                    "streak": prev_streak, "total": total}

        # 어제 출석했으면 연속 유지, 아니면 끊겨서 1일차부터 다시
        continued = (last == yesterday_kst())
        streak = prev_streak + 1 if continued else 1
        total += 1

        rw = ATTENDANCE_REWARDS[_cycle_pos(streak)]
        await add_item(user_id, "서사급 알", rw["eggs"])
        if rw.get("bonus_egg"):
            await add_item(user_id, f"{rw['bonus_egg']}급 알", 1)
        await add_points(user_id, rw["points"])
        await set_attendance(user_id, today, streak, total)

    return {"ok": True, "streak": streak, "total": total,
            "cycle_day": _cycle_pos(streak) + 1,
            "eggs": rw["eggs"], "points": rw["points"],
            "bonus_egg": rw.get("bonus_egg"),
            "reset": (prev_streak > 1 and not continued)}


async def get_attendance_status(user_id: int) -> dict:
    """출석 현황 (표시용): 오늘 출석 여부·연속·누적·보상표·다음 보상일."""
    row = await get_attendance(user_id)
    today = today_kst()
    checked = bool(row and row["last_date"] == today)
    streak = (row["streak"] if row else 0) or 0
    total = (row["total_days"] if row else 0) or 0

    if checked:
        cur_day = _cycle_pos(streak) + 1
    else:
        # 다음 출석 시 적용될 연속일수 예측 (어제 출석했으면 +1, 아니면 1일차)
        next_streak = streak + 1 if (row and row["last_date"] == yesterday_kst()) else 1
        cur_day = _cycle_pos(next_streak) + 1

    return {"checked_today": checked, "streak": streak, "total": total, "today": today,
            "cycle": ATTENDANCE_CYCLE, "today_day": cur_day,
            "rewards": ATTENDANCE_REWARDS}
