import discord
import io
import time
import random
from datetime import datetime

from utils.database import get_legend_data, save_legend_data, get_active_buffs, consume_item, add_item, update_max_star
from utils.data import ITEMS_INFO, EXP_TABLE, PET_STATS
from utils.logs import WALK_LOG_CH, send_log_embed
from utils.stats import get_points, add_points, spend_points
from utils.image_generator import generate_status_image

def get_pet_stats(pet_type, level):
    base_stats = PET_STATS.get(pet_type, {"AD": 5, "DF": 5, "AP": 5, "MR": 5})
    multiplier = (1.5+max(0, level - 1)) if level > 0 else 1
    return {
        "AD": int(base_stats["AD"] * multiplier),
        "DF": int(base_stats["DF"] * multiplier),
        "AP": int(base_stats["AP"] * multiplier),
        "MR": int(base_stats["MR"] * multiplier)
    }

# --- 버튼 정의(외형) ---------------------------------------------------------
# 각 버튼은 custom_id 안에 "소유자 ID"를 심어두기 때문에 봇이 재시작되거나
# 시간이 오래 지나도(타임아웃 없음) 상호작용이 죽지 않습니다.
BUTTON_SPECS = {
    "feed":    dict(label="밥주기 (5P)",     style=discord.ButtonStyle.primary,   emoji="🍚",     row=0),
    "shower":  dict(label="샤워하기 (10P)",  style=discord.ButtonStyle.primary,   emoji="🚿",     row=0),
    "walk1":   dict(label="1회 산책 (1P)",   style=discord.ButtonStyle.success,   emoji="🚶",     row=1),
    "walk10":  dict(label="10회 산책 (10P)", style=discord.ButtonStyle.success,   emoji="🚶‍♂️",  row=1),
    "walk100": dict(label="100회 산책 (100P)", style=discord.ButtonStyle.success, emoji="🏃",     row=1),
    "prev":    dict(label="이전 펫",         style=discord.ButtonStyle.secondary, emoji="◀️",     row=2),
    "next":    dict(label="다음 펫",         style=discord.ButtonStyle.secondary, emoji="▶️",     row=2),
}

CARE_ACTIONS = {"feed", "shower", "walk1", "walk10", "walk100"}
WALK_COUNTS = {"walk1": 1, "walk10": 10, "walk100": 100}


async def _load_active(owner_id):
    """소유자의 현재 활성 펫과 인덱스를 DB에서 읽어옵니다. (in-memory 상태 의존 X)"""
    wrapper = await get_legend_data(owner_id)
    if not wrapper or "pets" not in wrapper or not wrapper["pets"]:
        return None, None, 0, 0
    pets = wrapper["pets"]
    idx = wrapper.get("active_idx", 0)
    if idx >= len(pets):
        idx = 0
        wrapper["active_idx"] = 0
    return wrapper, pets[idx], idx, len(pets)


def build_status_view(owner_id: int, pet_level: int, total_pets: int) -> discord.ui.View:
    """상태창에 붙일 영구(persistent) 버튼 뷰를 생성합니다."""
    view = discord.ui.View(timeout=None)
    for action, spec in BUTTON_SPECS.items():
        disabled = False
        if pet_level == 0 and action in CARE_ACTIONS:
            disabled = True
        if action in ("prev", "next") and total_pets <= 1:
            disabled = True
        view.add_item(LegendButton(action, owner_id, disabled=disabled, **spec))
    return view


async def _render(interaction, owner_id, data, idx, total_pets, popup_msg=None, popup_embed=None):
    """defer 이후 상태창 이미지를 다시 그리고 뷰를 갱신합니다."""
    current_points = await get_points(owner_id)
    active_buffs = await get_active_buffs(owner_id)
    buffs = {b[0] for b in active_buffs}

    now = time.time()
    is_annoyed = (data.get('low_full_since', 0) > 0 and now - data['low_full_since'] >= 86400)
    is_diseased = (data.get('low_clean_since', 0) > 0 and now - data['low_clean_since'] >= 86400)

    pet_level = data.get('level', 0)

    status_image_file = await generate_status_image(
        data, current_points, buffs, is_annoyed, is_diseased, idx, total_pets
    )

    if popup_embed:
        await interaction.followup.send(embed=popup_embed, ephemeral=True)
    elif popup_msg:
        await interaction.followup.send(popup_msg, ephemeral=True)

    view = build_status_view(owner_id, pet_level, total_pets)
    await interaction.message.edit(attachments=[status_image_file], embed=None, view=view)


# --- 실제 동작 핸들러 --------------------------------------------------------
async def handle_feed(interaction, owner_id):
    await interaction.response.defer()  # 🌟 3초 타임아웃 방지
    wrapper, data, idx, total = await _load_active(owner_id)
    if not data:
        return await interaction.followup.send("펫 데이터가 없습니다.", ephemeral=True)
    if data.get('level', 0) == 0:
        return await interaction.followup.send("아직 부화하지 않은 알이에요!", ephemeral=True)
    success = await spend_points(owner_id, 5)
    if not success:
        return await interaction.followup.send("❌ 밥값(5P)이 부족합니다!", ephemeral=True)
    data['fullness'] = min(100, data.get('fullness', 0) + 20)
    await save_legend_data(owner_id, wrapper)
    await _render(interaction, owner_id, data, idx, total,
                  popup_msg=f"🍚 {data['name']}(이)가 맛있게 밥을 먹었습니다! (포만도 +20, 밥값 -5P)")


async def handle_shower(interaction, owner_id):
    await interaction.response.defer()  # 🌟 3초 타임아웃 방지
    wrapper, data, idx, total = await _load_active(owner_id)
    if not data:
        return await interaction.followup.send("펫 데이터가 없습니다.", ephemeral=True)
    if data.get('level', 0) == 0:
        return await interaction.followup.send("아직 부화하지 않은 알이에요!", ephemeral=True)
    success = await spend_points(owner_id, 10)
    if not success:
        return await interaction.followup.send("❌ 수도세(10P)가 부족합니다!", ephemeral=True)
    data['cleanliness'] = min(100, data.get('cleanliness', 0) + 20)
    await save_legend_data(owner_id, wrapper)
    await _render(interaction, owner_id, data, idx, total,
                  popup_msg=f"🚿 {data['name']}(이)가 깨끗해졌습니다! (청결도 +20, 수도세 -10P)")


async def handle_walk(interaction, owner_id, num_walks: int):
    await interaction.response.defer()  # 🌟 3초 타임아웃 방지
    wrapper, data, idx, total = await _load_active(owner_id)
    if not data:
        return await interaction.followup.send("펫 데이터가 없습니다.", ephemeral=True)
    if data.get('level', 0) == 0:
        return await interaction.followup.send("아직 부화하지 않은 알이에요!", ephemeral=True)
    user_id = owner_id

    if num_walks == 100:
        has_ticket = await consume_item(user_id, "100회 산책 할인권", 1)
        cost = 30 if has_ticket else 100
    else:
        has_ticket = False; cost = num_walks * 1

    success = await spend_points(user_id, cost)
    if not success:
        if has_ticket: await add_item(user_id, "100회 산책 할인권", 1)
        return await interaction.followup.send(f"❌ 산책 유지비({cost}P)가 부족합니다!", ephemeral=True)

    active_buffs = await get_active_buffs(user_id)
    buffs = {b[0] for b in active_buffs}

    data['total_walk_count'] = data.get('total_walk_count', 0) + num_walks
    old_walk_count = data.get('walk_count', 0)
    data['walk_count'] = old_walk_count + num_walks
    stat_triggers = data['walk_count'] // 20
    data['walk_count'] = data['walk_count'] % 20
    stat_msg = ""

    if stat_triggers > 0:
        stat_msg += f"✨ {stat_triggers * 20}회 산책 분량 달성!\n"
        if "신비한 알약" in buffs or "배부름을 부르는 약" in buffs:
            data['fullness'] = 100; stat_msg += "💊 [배부름 약] 효과로 포만도가 100으로 유지되었습니다!\n"
        else: data['fullness'] = max(0, data.get('fullness', 100) - (20 * stat_triggers))

        if "신비한 알약" in buffs or "트위치 나가라약" in buffs:
            data['cleanliness'] = 100; stat_msg += "💊 [나가라 약] 효과로 청결도가 100으로 유지되었습니다!\n"
        else: data['cleanliness'] = max(0, data.get('cleanliness', 100) - (20 * stat_triggers))

        if "신비한 알약" in buffs or "아무무도 인싸로 만드는 약" in buffs:
            data['intimacy'] = 100; stat_msg += "💊 [인싸 약] 효과로 친밀도가 100으로 유지되었습니다!\n"
        else: data['intimacy'] = min(100, data.get('intimacy', 50) + (20 * stat_triggers))

        if "신비한 알약" in buffs or "쌩쌩한약" in buffs:
            data['fatigue'] = 0; stat_msg += "💊 [쌩쌩한약] 효과로 피로도가 0으로 유지되었습니다!\n"
        else: data['fatigue'] = min(100, data.get('fatigue', 0) + (20 * stat_triggers))

    found_eggs = []; found_items = []
    epic_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '서사']
    legend_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '전설']
    mythic_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '신화']
    prestige_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '프레스티지']

    for _ in range(num_walks):
        r_egg = random.random()
        if r_egg < 0.0001: found_eggs.append("프레스티지")
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
        EXP_REQ = {0: 100, 1: {"서사": 5000, "전설": 10000, "신화": 20000, "프레스티지": 30000}, 2: {"서사": 10000, "전설": 20000, "신화": 40000, "프레스티지": 70000}}

        while data.get('level', 0) < 3:
            curr_level = data.get('level', 0)
            req_exp = EXP_REQ[curr_level].get(rarity, EXP_REQ[curr_level]["서사"])
            if data.get('exp', 0) >= req_exp:
                data['level'] = curr_level + 1
                data['exp'] -= req_exp
            else: break

        if data.get('level', 0) >= 3:
            await update_max_star(user_id, 3)

    for egg in found_eggs: await add_item(user_id, f"{egg}급 알", 1)
    for rarity, item_name in found_items: await add_item(user_id, item_name, 1)

    await save_legend_data(owner_id, wrapper)

    result_embed = discord.Embed(title="🐾 산책 결과", color=discord.Color.green())
    desc = f"{data['name']}(와)과 {num_walks}회 산책했습니다!\n"
    if has_ticket: desc += "🎫 `100회 산책 할인권`이 적용되어 30P만 소모되었습니다.\n"
    else: desc += f"💸 소모된 유지비: -{cost}P\n"
    desc += "━━━━━━━━━━━━━━━━━━━━\n"
    if gained_exp > 0: desc += f"📈 산책을 하며 경험치를 얻었다! (+{gained_exp} XP)\n"
    for egg in found_eggs: desc += f"🥚 {egg}급 알을 발견했다!\n"
    for rarity, item_name in found_items: desc += f"🎁 {rarity}급 아이템 [{item_name}]을 발견했다!\n"
    if stat_msg: desc += f"\n{stat_msg}"

    result_embed.description = desc
    result_embed.set_footer(text=f"사용자 ID: {user_id} | 실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    await _render(interaction, owner_id, data, idx, total, popup_embed=result_embed)

    log_desc = f"🐾 {data['name']} 산책\n💸 소모 유지비: -{cost}P\n"
    if gained_exp > 0: log_desc += f"📈 획득 경험치: +{gained_exp} XP\n"
    if found_eggs: log_desc += f"🥚 획득한 알: {', '.join(found_eggs)}급 알\n"
    if found_items: log_desc += f"🎁 획득한 아이템: {', '.join([i[1] for i in found_items])}\n"
    await send_log_embed(interaction.client, WALK_LOG_CH, "👟 산책 로그", log_desc.strip(), interaction.user, discord.Color.green(), f"구분: {num_walks}회 산책")


async def handle_nav(interaction, owner_id, delta: int):
    """이전/다음 펫으로 이동. 현재 인덱스는 DB(active_idx)를 기준으로 계산합니다."""
    await interaction.response.defer()  # 🌟 3초 타임아웃 방지
    wrapper = await get_legend_data(owner_id)
    if not wrapper or not wrapper.get('pets'):
        return
    total = len(wrapper['pets'])
    cur = wrapper.get('active_idx', 0)
    if cur >= total: cur = 0
    new_idx = (cur + delta) % total
    wrapper['active_idx'] = new_idx
    data = wrapper['pets'][new_idx]

    now = time.time()
    active_buffs = await get_active_buffs(owner_id)
    buffs = {b[0] for b in active_buffs}

    last_calc = data.get('last_fatigue_calc', now)
    elapsed_minutes = int((now - last_calc) // 60)
    if elapsed_minutes > 0 and data.get('level', 0) > 0:
        fatigue_drop = elapsed_minutes * 20
        data['fatigue'] = max(0, data.get('fatigue', 0) - fatigue_drop)
        data['last_fatigue_calc'] = last_calc + (elapsed_minutes * 60)
    elif 'last_fatigue_calc' not in data: data['last_fatigue_calc'] = now

    if "신비한 알약" in buffs:
        data['fullness'] = 100; data['fatigue'] = 0; data['intimacy'] = 100; data['cleanliness'] = 100
    else:
        if "배부름을 부르는 약" in buffs: data['fullness'] = 100
        if "쌩쌩한약" in buffs: data['fatigue'] = 0
        if "트위치 나가라약" in buffs: data['cleanliness'] = 100
        if "아무무도 인싸로 만드는 약" in buffs: data['intimacy'] = 100

    if data.get('fullness', 100) <= 20:
        if data.get('low_full_since', 0) == 0: data['low_full_since'] = now
    else: data['low_full_since'] = 0

    if data.get('cleanliness', 100) <= 20:
        if data.get('low_clean_since', 0) == 0: data['low_clean_since'] = now
    else: data['low_clean_since'] = 0

    wrapper['pets'][new_idx] = data
    await save_legend_data(owner_id, wrapper)
    await _render(interaction, owner_id, data, new_idx, total)


ACTION_HANDLERS = {
    "feed":    lambda i, o: handle_feed(i, o),
    "shower":  lambda i, o: handle_shower(i, o),
    "walk1":   lambda i, o: handle_walk(i, o, 1),
    "walk10":  lambda i, o: handle_walk(i, o, 10),
    "walk100": lambda i, o: handle_walk(i, o, 100),
    "prev":    lambda i, o: handle_nav(i, o, -1),
    "next":    lambda i, o: handle_nav(i, o, +1),
}


# --- 영구(persistent) 버튼 --------------------------------------------------
class LegendButton(discord.ui.DynamicItem[discord.ui.Button], template=r"legend:(?P<action>[a-z0-9]+):(?P<owner>\d+)"):
    """custom_id 에 소유자 ID를 담아 재시작/타임아웃에도 살아있는 상태창 버튼."""

    def __init__(self, action: str, owner_id: int, *, label, style, emoji, row, disabled=False):
        self.action = action
        self.owner_id = owner_id
        super().__init__(
            discord.ui.Button(
                label=label, style=style, emoji=emoji, row=row, disabled=disabled,
                custom_id=f"legend:{action}:{owner_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        action = match["action"]
        owner_id = int(match["owner"])
        spec = BUTTON_SPECS.get(action)
        if spec is None:
            # 알 수 없는 액션이면 안전하게 feed 스펙으로 복원(실제 콜백은 아래에서 걸러짐)
            spec = BUTTON_SPECS["feed"]
        return cls(action, owner_id, **spec)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ 남의 전설이 상태창은 조작할 수 없습니다!", ephemeral=True)
            return False
        return True

    async def callback(self, interaction: discord.Interaction):
        handler = ACTION_HANDLERS.get(self.action)
        if handler is None:
            return await interaction.response.send_message("알 수 없는 버튼입니다.", ephemeral=True)
        try:
            await handler(interaction, self.owner_id)
        except Exception as e:
            # 예외를 그대로 두면 디스코드에 '상호작용 실패'가 뜨므로, 반드시 응답을 마무리합니다.
            print(f"[상태창 버튼 오류] action={self.action} owner={self.owner_id}: {e}")
            msg = "⚠️ 처리 중 오류가 발생했어요. 잠시 후 다시 시도하거나 `/상태창`을 다시 입력해주세요."
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            except Exception:
                pass
