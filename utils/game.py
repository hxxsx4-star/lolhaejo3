"""전설이 키우기 핵심 게임 로직 (봇·웹 공용 단일 소스).

디스코드 봇(cogs/petsystem)과 웹앱(webapp)이 모두 이 모듈을 호출합니다.
보상·확률·비용을 바꿀 땐 여기만 고치면 양쪽에 동시 반영됩니다.
모든 변경 함수는 utils.locks 의 유저 락으로 감싸 연타에 안전합니다.
"""

import time
import random
from datetime import datetime, timezone, timedelta

from utils.data import (ITEMS_INFO, EXP_TABLE, PET_POOLS, EQUIPMENTS, EQUIP_PRICE,
                        MAX_EQUIP_PER_PET, RARITY_ORDER, EGG_EXCHANGE_RATE,
                        egg_item_name, prev_rarity, format_equip_effect,
                        get_pet_total_stats, get_equipment_bonus)
from utils.database import (get_or_migrate_data, save_legend_data, get_active_buffs,
                            consume_item, add_item, get_item_amount, add_synth_count,
                            get_synth_count, add_buff, update_max_star,
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


def egg_rarity(egg_name: str):
    """'서사급 알' → '서사'. 유효한 알이 아니면 None."""
    if not egg_name or "급 알" not in egg_name:
        return None
    rarity = egg_name.replace("급 알", "").strip()
    return rarity if rarity in PET_POOLS else None


async def hatch_egg_item(user_id: int, egg_name: str, pet_type: str, pet_name: str) -> dict:
    """보관함의 '○○급 알' 아이템을 사용해 그 등급의 전설이(알)를 파티에 추가합니다.
    알까기 가챠와 달리 등급은 알로 고정되며, 종류/이름은 유저가 선택합니다."""
    rarity = egg_rarity(egg_name)
    if not rarity:
        return {"ok": False, "error": "부화할 수 있는 알이 아닙니다."}
    if pet_type not in PET_POOLS.get(rarity, []):
        return {"ok": False, "error": "해당 등급에 없는 전설이입니다."}
    pet_name = (pet_name or "").strip()[:20] or f"{rarity} 전설이"
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        if len(wrapper.get('pets', [])) >= MAX_PETS:
            return {"ok": False, "error": f"전설이는 최대 {MAX_PETS}마리까지만 파티에 둘 수 있습니다. (박스에 보관 후 사용하세요)"}
        # 실제 생성 직전에 원자적으로 알 1개 소모 (동시 사용 시 초과 부화 방지)
        if not await consume_item(user_id, egg_name, 1):
            return {"ok": False, "error": "해당 알을 보유하고 있지 않습니다."}
        pet = _new_pet(pet_name, pet_type, rarity)
        wrapper.setdefault('pets', []).append(pet)
        wrapper['active_idx'] = len(wrapper['pets']) - 1
        await save_legend_data(user_id, wrapper)
    return {"ok": True, "rarity": rarity, "type": pet_type, "name": pet_name}


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
# 7일 주기 보상. 서사급 알만 지급(포인트 없음). 특정 일차엔 상위 알 보너스.
ATTENDANCE_REWARDS = [
    {"eggs": 200},                     # 1일차
    {"eggs": 300},                     # 2일차
    {"eggs": 400, "bonus": ["전설"]},   # 3일차 (전설급 알 +1)
    {"eggs": 500},                     # 4일차
    {"eggs": 600},                     # 5일차
    {"eggs": 800},                     # 6일차
    {"eggs": 2000, "bonus": ["신화"]},  # 7일차 (신화급 알 +1)
]
ATTENDANCE_CYCLE = len(ATTENDANCE_REWARDS)

# 연속 출석 N일마다 지급하는 마일스톤 보너스 알 (주기 무관, 연속일수 기준)
STREAK_MILESTONES = {14: "프레스티지"}


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
        eggs = rw["eggs"]
        await add_item(user_id, "서사급 알", eggs)
        bonus_eggs = list(rw.get("bonus", []))
        # 연속 출석 마일스톤(14일마다 프레스티지 등)
        for n, rarity in STREAK_MILESTONES.items():
            if streak % n == 0:
                bonus_eggs.append(rarity)
        for rarity in bonus_eggs:
            await add_item(user_id, f"{rarity}급 알", 1)
        await set_attendance(user_id, today, streak, total)

    return {"ok": True, "streak": streak, "total": total,
            "cycle_day": _cycle_pos(streak) + 1,
            "eggs": eggs, "bonus_eggs": bonus_eggs,
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
            "rewards": ATTENDANCE_REWARDS,
            "milestones": [{"days": n, "rarity": r} for n, r in STREAK_MILESTONES.items()]}


# ==========================================
# 알 환전 / 분해 (봇 /알환전·/알분해 와 동일)
# ==========================================
EGG_TIERS = [r for r in RARITY_ORDER if r in EGG_EXCHANGE_RATE]


def egg_exchange_info() -> list:
    """환전/분해 표시용 정보 (등급, 비용알, 개당 비율)."""
    info = []
    for r in EGG_TIERS:
        info.append({"rarity": r, "egg": egg_item_name(r),
                     "prev": prev_rarity(r), "prev_egg": egg_item_name(prev_rarity(r)),
                     "rate": EGG_EXCHANGE_RATE[r]})
    return info


async def exchange_egg(user_id: int, target_rarity: str, count: int = 1) -> dict:
    """하위 등급 알 여러 개 → 상위 등급 알 1개(×count). (원자적 차감)"""
    if count <= 0:
        return {"ok": False, "error": "개수는 1개 이상이어야 합니다."}
    if target_rarity not in EGG_EXCHANGE_RATE:
        return {"ok": False, "error": "환전할 수 없는 등급입니다."}
    per = EGG_EXCHANGE_RATE[target_rarity]
    src_egg = egg_item_name(prev_rarity(target_rarity))
    tgt_egg = egg_item_name(target_rarity)
    total_cost = per * count
    async with get_user_lock(user_id):
        if not await consume_item(user_id, src_egg, total_cost):
            return {"ok": False, "error": f"{src_egg}이(가) 부족합니다. (필요 {total_cost}개)"}
        await add_item(user_id, tgt_egg, count)
    return {"ok": True, "src_egg": src_egg, "spent": total_cost,
            "tgt_egg": tgt_egg, "gained": count}


async def decompose_egg(user_id: int, src_rarity: str, count: int = 1) -> dict:
    """상위 등급 알 count개 → 하위 등급 알 여러 개. (원자적 차감)"""
    if count <= 0:
        return {"ok": False, "error": "개수는 1개 이상이어야 합니다."}
    if src_rarity not in EGG_EXCHANGE_RATE:
        return {"ok": False, "error": "분해할 수 없는 등급입니다."}
    per = EGG_EXCHANGE_RATE[src_rarity]
    src_egg = egg_item_name(src_rarity)
    result_egg = egg_item_name(prev_rarity(src_rarity))
    async with get_user_lock(user_id):
        if not await consume_item(user_id, src_egg, count):
            return {"ok": False, "error": f"{src_egg}이(가) 부족합니다. (보유량 {count}개 미만)"}
        gained = per * count
        await add_item(user_id, result_egg, gained)
    return {"ok": True, "src_egg": src_egg, "spent": count,
            "result_egg": result_egg, "gained": gained}


# ==========================================
# 아이템 사용 (버프약 / 이름변경권) — 알 부화는 hatch_egg_item 사용
# ==========================================
BUFF_ITEMS_24H = ["배부름을 부르는 약", "쌩쌩한약", "트위치 나가라약", "아무무도 인싸로 만드는 약"]
BUFF_EXP_ITEMS = ["경험치 부스터 X2", "경험치 부스터 X5", "경험치 부스터 X10"]


def is_egg_item(name: str) -> bool:
    return egg_rarity(name) is not None


async def use_item(user_id: int, item_name: str, amount: int = 1, pet_idx: int = 0,
                   new_name: str = "") -> dict:
    """보관함 아이템 사용. 버프약/신비한알약/경험치부스터/이름변경권 지원.
    (알 아이템은 웹에서 hatch_egg_item 흐름을 쓰므로 여기서 거부)"""
    if amount <= 0:
        return {"ok": False, "error": "수량은 1개 이상이어야 합니다."}
    if is_egg_item(item_name):
        return {"ok": False, "error": "알은 '부화' 기능으로 사용하세요."}

    async with get_user_lock(user_id):
        # 이름 변경권: 대상 펫 + 새 이름 필요
        if item_name == "전설이 이름 변경권":
            wrapper = await get_or_migrate_data(user_id)
            pets = wrapper.get('pets', [])
            if pet_idx >= len(pets):
                return {"ok": False, "error": "이름을 바꿀 전설이를 선택하세요."}
            new_name = (new_name or "").strip()[:20]
            if not new_name:
                return {"ok": False, "error": "새 이름을 입력하세요."}
            if not await consume_item(user_id, item_name, 1):
                return {"ok": False, "error": "'전설이 이름 변경권'이 부족합니다."}
            old = pets[pet_idx].get('name', '이름없음')
            pets[pet_idx]['name'] = new_name
            await save_legend_data(user_id, wrapper)
            return {"ok": True, "kind": "rename", "old": old, "new": new_name}

        if item_name == "100회 산책 할인권":
            return {"ok": False, "error": "이 아이템은 100회 산책 시 자동으로 사용됩니다."}

        # 경험치 부스터: 중복 방지
        if item_name in BUFF_EXP_ITEMS:
            active = await get_active_buffs(user_id)
            if any("경험치 부스터" in b[0] for b in active):
                return {"ok": False, "error": "이미 적용 중인 경험치 부스터가 있습니다."}

        # 버프 계열 처리
        if item_name in BUFF_ITEMS_24H:
            if not await consume_item(user_id, item_name, amount):
                return {"ok": False, "error": "아이템이 부족합니다."}
            await add_buff(user_id, buff_name=item_name, duration_sec=86400 * amount)
            return {"ok": True, "kind": "buff", "item": item_name, "amount": amount,
                    "desc": f"{24 * amount}시간 동안 해당 스탯 고정"}
        if item_name == "신비한 알약":
            if not await consume_item(user_id, item_name, amount):
                return {"ok": False, "error": "아이템이 부족합니다."}
            await add_buff(user_id, buff_name=item_name, duration_sec=1209600 * amount)
            return {"ok": True, "kind": "buff", "item": item_name, "amount": amount,
                    "desc": f"{14 * amount}일 동안 모든 스탯 최상 고정"}
        if item_name in BUFF_EXP_ITEMS:
            if not await consume_item(user_id, item_name, amount):
                return {"ok": False, "error": "아이템이 부족합니다."}
            await add_buff(user_id, buff_name=item_name, duration_sec=0, vc_sec=10800 * amount)
            return {"ok": True, "kind": "buff", "item": item_name, "amount": amount,
                    "desc": f"통화방에서 {3 * amount}시간 경험치 증가"}

    return {"ok": False, "error": "사용할 수 없는 아이템입니다. (장비는 장비 탭에서 장착)"}


# ==========================================
# 박스 (파티 ↔ 보관)
# ==========================================
async def box_store(user_id: int, pet_idx: int) -> dict:
    """파티의 전설이를 박스에 보관 (스탯 최대치로 보존)."""
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "보관할 전설이를 선택하세요."}
        pet = pets.pop(pet_idx)
        pet['fullness'] = 100; pet['cleanliness'] = 100
        pet['fatigue'] = 0; pet['intimacy'] = 100
        pet['last_fatigue_calc'] = time.time()
        wrapper.setdefault('box', []).append(pet)
        wrapper['active_idx'] = max(0, len(pets) - 1)
        await save_legend_data(user_id, wrapper)
    return {"ok": True, "name": pet.get('name', '이름없음')}


async def box_retrieve(user_id: int, box_idx: int) -> dict:
    """박스의 전설이를 파티로 복귀 (파티 최대 MAX_PETS)."""
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        box = wrapper.get('box', [])
        if box_idx >= len(box):
            return {"ok": False, "error": "복귀할 전설이를 선택하세요."}
        if len(wrapper.get('pets', [])) >= MAX_PETS:
            return {"ok": False, "error": f"파티가 꽉 찼습니다! (최대 {MAX_PETS}마리)"}
        pet = box.pop(box_idx)
        pet['last_fatigue_calc'] = time.time()
        wrapper.setdefault('pets', []).append(pet)
        wrapper['active_idx'] = len(wrapper['pets']) - 1
        await save_legend_data(user_id, wrapper)
    return {"ok": True, "name": pet.get('name', '이름없음')}


async def reorder_pets(user_id: int, from_idx: int, to_idx: int) -> dict:
    """파티 슬롯 순서 교환."""
    if from_idx == to_idx:
        return {"ok": False, "error": "같은 슬롯입니다."}
    async with get_user_lock(user_id):
        wrapper = await get_or_migrate_data(user_id)
        pets = wrapper.get('pets', [])
        if from_idx >= len(pets) or to_idx >= len(pets):
            return {"ok": False, "error": "선택한 슬롯에 전설이가 없습니다."}
        active = wrapper.get('active_idx', 0)
        active_pet = pets[active] if active < len(pets) else pets[0]
        pets[from_idx], pets[to_idx] = pets[to_idx], pets[from_idx]
        wrapper['active_idx'] = pets.index(active_pet)
        await save_legend_data(user_id, wrapper)
    return {"ok": True, "a": pets[to_idx].get('name'), "b": pets[from_idx].get('name')}


# ==========================================
# 업적 현황 (수집 진행도 — 역할 타이틀은 디스코드 전용)
# ==========================================
async def achievement_status(user_id: int) -> dict:
    wrapper = await get_or_migrate_data(user_id)
    all_pets = (wrapper.get('pets', []) or []) + (wrapper.get('box', []) or [])
    owned_types = {p.get('type') for p in all_pets}
    owned_3 = {p.get('type') for p in all_pets if p.get('level', 0) >= 3}
    synth = await get_synth_count(user_id)

    rows = []
    for rarity in RARITY_ORDER:
        pool = set(PET_POOLS.get(rarity, []))
        if not pool:
            continue
        have = len(pool & owned_3)
        rows.append({"rarity": rarity, "have": have, "total": len(pool),
                     "done": have >= len(pool)})
    all_types = set(sum([list(v) for v in PET_POOLS.values()], []))
    total_all = len(all_types)
    return {
        "collector": {"have": len(owned_types & all_types), "total": total_all,
                      "done": all_types.issubset(owned_types)},
        "all_pets_3": {"have": len(owned_3 & all_types), "total": total_all,
                       "done": all_types.issubset(owned_3)},
        "by_rarity": rows,
        "synth": {"have": min(synth, 50), "total": 50, "done": synth >= 50},
    }


# ==========================================
# 관리자 조작 (웹 관리자 패널 전용) — 대상 유저에 대해 동작
# ==========================================
async def admin_give_egg(target_id: int, name: str, rarity: str, ptype: str) -> dict:
    if rarity not in PET_POOLS:
        return {"ok": False, "error": "잘못된 등급입니다."}
    if ptype not in PET_POOLS[rarity]:
        return {"ok": False, "error": "해당 등급에 없는 전설이입니다."}
    async with get_user_lock(target_id):
        wrapper = await get_or_migrate_data(target_id)
        if len(wrapper.get('pets', [])) >= MAX_PETS:
            return {"ok": False, "error": f"대상이 이미 {MAX_PETS}마리를 보유 중입니다."}
        pet = _new_pet((name or "").strip()[:20] or f"{rarity} 전설이", ptype, rarity)
        wrapper.setdefault('pets', []).append(pet)
        if len(wrapper['pets']) == 1:
            wrapper['active_idx'] = 0
        await save_legend_data(target_id, wrapper)
    return {"ok": True, "name": pet['name'], "rarity": rarity, "type": ptype}


async def admin_take_pet(target_id: int, pet_idx: int) -> dict:
    async with get_user_lock(target_id):
        wrapper = await get_or_migrate_data(target_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "해당 전설이가 없습니다."}
        removed = pets.pop(pet_idx)
        wrapper['active_idx'] = max(0, len(pets) - 1)
        await save_legend_data(target_id, wrapper)
    return {"ok": True, "name": removed.get('name'), "rarity": removed.get('rarity'),
            "type": removed.get('type')}


async def admin_give_item(target_id: int, item: str, count: int) -> dict:
    if not item or count == 0:
        return {"ok": False, "error": "아이템/개수를 확인하세요."}
    if count > 0:
        await add_item(target_id, item, count)
        return {"ok": True, "item": item, "count": count, "op": "give"}
    ok = await consume_item(target_id, item, -count)
    return ({"ok": True, "item": item, "count": -count, "op": "take"} if ok
            else {"ok": False, "error": "회수할 수량이 부족합니다."})


async def admin_take_item(target_id: int, item: str, count: int) -> dict:
    if count <= 0:
        return {"ok": False, "error": "개수는 1 이상."}
    ok = await consume_item(target_id, item, count)
    return ({"ok": True, "item": item, "count": count} if ok
            else {"ok": False, "error": "회수할 수량이 부족합니다."})


async def admin_reset_items(target_id: int) -> dict:
    import aiosqlite
    from utils.database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM user_items WHERE user_id = ?", (target_id,))
        await db.commit()
    return {"ok": True}


async def admin_view_items(target_id: int) -> dict:
    from utils.database import get_user_items
    items = await get_user_items(target_id)
    return {"ok": True, "items": [{"name": n, "amount": a} for n, a in items]}


async def admin_view_pets(target_id: int) -> dict:
    wrapper = await get_or_migrate_data(target_id)
    def _v(p, i):
        return {"idx": i, "name": p.get('name'), "type": p.get('type'),
                "rarity": p.get('rarity'), "level": p.get('level', 0)}
    return {"ok": True,
            "pets": [_v(p, i) for i, p in enumerate(wrapper.get('pets', []))],
            "box": [_v(p, i) for i, p in enumerate(wrapper.get('box', []))]}


async def admin_force_hatch(target_id: int, pet_idx: int) -> dict:
    async with get_user_lock(target_id):
        wrapper = await get_or_migrate_data(target_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "해당 전설이가 없습니다."}
        if pets[pet_idx].get('level', 0) > 0:
            return {"ok": False, "error": "이미 부화한 전설이입니다."}
        pets[pet_idx]['level'] = 1
        pets[pet_idx]['exp'] = 0
        await save_legend_data(target_id, wrapper)
    return {"ok": True, "name": pets[pet_idx].get('name')}


async def admin_set_star(target_id: int, pet_idx: int, delta: int) -> dict:
    async with get_user_lock(target_id):
        wrapper = await get_or_migrate_data(target_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "해당 전설이가 없습니다."}
        lvl = pets[pet_idx].get('level', 0)
        new = lvl + delta
        if new < 0:
            return {"ok": False, "error": "이미 알 상태입니다."}
        if new > 3:
            return {"ok": False, "error": "이미 최대 성급(3성)입니다."}
        pets[pet_idx]['level'] = new
        pets[pet_idx]['exp'] = 0
        if new >= 3:
            await update_max_star(target_id, 3)
        await save_legend_data(target_id, wrapper)
    return {"ok": True, "name": pets[pet_idx].get('name'), "level": new}


async def admin_rename(target_id: int, pet_idx: int, new_name: str) -> dict:
    new_name = (new_name or "").strip()[:20]
    if not new_name:
        return {"ok": False, "error": "새 이름을 입력하세요."}
    async with get_user_lock(target_id):
        wrapper = await get_or_migrate_data(target_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "해당 전설이가 없습니다."}
        old = pets[pet_idx].get('name')
        pets[pet_idx]['name'] = new_name
        await save_legend_data(target_id, wrapper)
    return {"ok": True, "old": old, "new": new_name}


async def admin_give_exp(target_id: int, pet_idx: int, amount: int) -> dict:
    if amount <= 0:
        return {"ok": False, "error": "경험치는 1 이상."}
    async with get_user_lock(target_id):
        wrapper = await get_or_migrate_data(target_id)
        pets = wrapper.get('pets', [])
        if pet_idx >= len(pets):
            return {"ok": False, "error": "해당 전설이가 없습니다."}
        data = pets[pet_idx]
        if data.get('level', 0) >= 3:
            return {"ok": False, "error": "이미 최대 성급(3성)입니다."}
        before = data.get('level', 0)
        data['exp'] = data.get('exp', 0) + amount
        rarity = data.get('rarity', '서사')
        while data.get('level', 0) < 3:
            cur = data.get('level', 0)
            req = EXP_TABLE.get(rarity, {}).get(cur, 100)
            if data.get('exp', 0) >= req:
                data['level'] = cur + 1
                data['exp'] -= req
            else:
                break
        if data.get('level', 0) >= 3:
            await update_max_star(target_id, 3)
        await save_legend_data(target_id, wrapper)
    return {"ok": True, "name": data.get('name'), "amount": amount,
            "before": before, "after": data.get('level', 0)}
