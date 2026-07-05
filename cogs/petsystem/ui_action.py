import discord
import time
import random
from datetime import datetime

# 💡 update_max_star 추가
from .database import get_legend_data, save_legend_data, get_active_buffs, consume_item, add_item, update_max_star
from .data import PET_IMAGES, ITEMS_INFO, RARITY_IMAGES, EXP_TABLE
from .logs import WALK_LOG_CH, send_log_embed

from utils.stats import get_points, add_points, spend_points

def get_progress_bar(value, fill_emoji, empty_emoji="⬛"):
    val = max(0, min(100, value))
    fill_count = int(val // 20)
    empty_count = 5 - fill_count
    return (fill_emoji * fill_count) + (empty_emoji * empty_count) + f" ({val}%)"

def create_status_embed(user, data, points, buffs, is_annoyed, is_diseased):
    embed = discord.Embed(title=f"🐾 {data['name']}의 상태창", color=discord.Color.gold())

    pet_type = data.get('type')
    if pet_type in PET_IMAGES: embed.set_thumbnail(url=PET_IMAGES[pet_type])

    rarity = data.get('rarity', '서사')
    level = data.get('level', 0)

    if rarity in RARITY_IMAGES:
        embed.set_author(name=f"[{rarity}급 전설이]", icon_url=RARITY_IMAGES[rarity])
    else:
        embed.add_field(name="등급", value=rarity, inline=True)

    current_exp = data.get('exp', 0)
    max_exp = EXP_TABLE.get(rarity, {}).get(level, 0)

    if level >= 3:
        exp_display = "MAX"
    elif level == 0:
        exp_display = f"{current_exp} / 100 (부화 대기)"
    else:
        exp_display = f"{current_exp} / {max_exp}"

    embed.add_field(name="레벨", value=f"{level}성" if level > 0 else "🥚 알", inline=True)
    embed.add_field(name="경험치", value=exp_display, inline=True)

    embed.add_field(name="포만도", value=get_progress_bar(data.get('fullness', 0), "🍗"), inline=True)
    embed.add_field(name="피로도", value=get_progress_bar(data.get('fatigue', 0), "😴"), inline=True)
    embed.add_field(name="청결도", value=get_progress_bar(data.get('cleanliness', 0), "🚿"), inline=True)
    embed.add_field(name="친밀도", value=get_progress_bar(data.get('intimacy', 0), "💖", "🖤"), inline=True)

    if buffs: embed.add_field(name="활성화된 버프", value=", ".join(buffs), inline=False)
    if is_annoyed: embed.add_field(name="⚠️ 상태", value="배가 너무 고파서 심술이 났습니다!", inline=False)
    if is_diseased: embed.add_field(name="⚠️ 상태", value="너무 더러워서 병에 걸렸습니다!", inline=False)

    embed.set_footer(text=f"보유 포인트: {points}P | 누적 산책: {data.get('total_walk_count', 0)}회")
    return embed

class LegendActionView(discord.ui.View):
    def __init__(self, user_id, pet_level=1):
        super().__init__(timeout=60)
        self.user_id = user_id

        if pet_level == 0:
            self.feed.disabled = True
            self.shower.disabled = True
            self.walk_1.disabled = True
            self.walk_10.disabled = True
            self.walk_100.disabled = True

    # 💡 [중요] 타인 조작 방지 보안 코드
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 남의 전설이 상태창은 조작할 수 없습니다!", ephemeral=True)
            return False
        return True

    async def get_pet_data(self):
        wrapper = await get_legend_data(self.user_id)
        if not wrapper or 'pets' not in wrapper:
            return None, None
        return wrapper, wrapper['pets'][wrapper['active_idx']]

    async def update_status_message(self, interaction: discord.Interaction, data, popup_msg=None, popup_embed=None):
        current_points = await get_points(self.user_id)
        active_buffs = await get_active_buffs(self.user_id)
        buffs = {b[0] for b in active_buffs}

        now = time.time()
        is_annoyed = (data.get('low_full_since', 0) > 0 and now - data['low_full_since'] >= 86400)
        is_diseased = (data.get('low_clean_since', 0) > 0 and now - data['low_clean_since'] >= 86400)

        status_embed = create_status_embed(interaction.user, data, current_points, buffs, is_annoyed, is_diseased)

        if popup_embed:
            await interaction.response.send_message(embed=popup_embed, ephemeral=True)
        elif popup_msg:
            await interaction.response.send_message(popup_msg, ephemeral=True)

        if data.get('level', 0) == 0:
            self.feed.disabled = True
            self.shower.disabled = True
            self.walk_1.disabled = True
            self.walk_10.disabled = True
            self.walk_100.disabled = True

        await interaction.message.edit(embed=status_embed, view=self)

    @discord.ui.button(label="밥주기 (5P)", style=discord.ButtonStyle.primary, emoji="🍚", row=0)
    async def feed(self, interaction: discord.Interaction, button: discord.ui.Button):
        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        success = await spend_points(self.user_id, 5)
        if not success: return await interaction.response.send_message("❌ 밥값(5P)이 부족합니다!", ephemeral=True)

        data['fullness'] = min(100, data.get('fullness', 0) + 20)
        await save_legend_data(self.user_id, wrapper)
        await self.update_status_message(interaction, data, popup_msg=f"🍚 {data['name']}(이)가 맛있게 밥을 먹었습니다! (포만도 +20, 밥값 -5P)")

    @discord.ui.button(label="샤워하기 (10P)", style=discord.ButtonStyle.primary, emoji="🚿", row=0)
    async def shower(self, interaction: discord.Interaction, button: discord.ui.Button):
        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        success = await spend_points(self.user_id, 10)
        if not success: return await interaction.response.send_message("❌ 수도세(10P)가 부족합니다!", ephemeral=True)

        data['cleanliness'] = min(100, data.get('cleanliness', 0) + 20)
        await save_legend_data(self.user_id, wrapper)
        await self.update_status_message(interaction, data, popup_msg=f"🚿 {data['name']}(이)가 깨끗해졌습니다! (청결도 +20, 수도세 -10P)")

    async def handle_walk(self, interaction: discord.Interaction, num_walks: int):
        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        user_id = self.user_id

        if num_walks == 100:
            has_ticket = await consume_item(user_id, "100회 산책 할인권", 1)
            cost = 300 if has_ticket else 1000
        else:
            has_ticket = False
            cost = num_walks * 10

        success = await spend_points(user_id, cost)
        if not success:
            if has_ticket: await add_item(user_id, "100회 산책 할인권", 1)
            return await interaction.response.send_message(f"❌ 산책 유지비({cost}P)가 부족합니다!", ephemeral=True)

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

            # 💡 1. 포만도 체크
            if "신비한 알약" in buffs or "배부름을 부르는 약" in buffs:
                data['fullness'] = 100
                stat_msg += "💊 [배부름 약] 효과로 포만도가 100으로 유지되었습니다!\n"
            else:
                data['fullness'] = max(0, data.get('fullness', 100) - (20 * stat_triggers))

            # 💡 2. 청결도 체크
            if "신비한 알약" in buffs or "트위치 나가라약" in buffs:
                data['cleanliness'] = 100
                stat_msg += "💊 [나가라 약] 효과로 청결도가 100으로 유지되었습니다!\n"
            else:
                data['cleanliness'] = max(0, data.get('cleanliness', 100) - (20 * stat_triggers))

            # 💡 3. 친밀도 체크
            if "신비한 알약" in buffs or "아무무도 인싸로 만드는 약" in buffs:
                data['intimacy'] = 100
                stat_msg += "💊 [인싸 약] 효과로 친밀도가 100으로 유지되었습니다!\n"
            else:
                data['intimacy'] = min(100, data.get('intimacy', 50) + (20 * stat_triggers))

            # 💡 4. 피로도 체크
            if "신비한 알약" in buffs or "쌩쌩한약" in buffs:
                data['fatigue'] = 0
                stat_msg += "💊 [쌩쌩한약] 효과로 피로도가 0으로 유지되었습니다!\n"
            else:
                data['fatigue'] = min(100, data.get('fatigue', 0) + (20 * stat_triggers))

        lost_points = 0
        lose_count = 0
        found_eggs = []
        found_items = []

        epic_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '서사']
        legend_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '전설']
        mythic_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '신화']
        prestige_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '프레스티지']

        for _ in range(num_walks):
            if random.random() < 0.50:
                lost_points += 45
                lose_count += 1

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

        # 💡 산책으로 인한 경험치 획득 (1회당 1XP) 및 레벨업 로직
        gained_exp = 0
        if data.get('level', 0) > 0 and data.get('level', 0) < 3:
            gained_exp = num_walks
            data['exp'] = data.get('exp', 0) + gained_exp

            rarity = data.get('rarity', '서사')
            EXP_REQUIREMENTS = {
                0: 100,
                1: {"서사": 5000, "전설": 10000, "신화": 20000, "프레스티지": 30000},
                2: {"서사": 10000, "전설": 20000, "신화": 40000, "프레스티지": 70000}
            }

            while data.get('level', 0) < 3:
                current_level = data.get('level', 0)
                required_exp = EXP_REQUIREMENTS[current_level].get(rarity, EXP_REQUIREMENTS[current_level]["서사"])

                if data.get('exp', 0) >= required_exp:
                    data['level'] = current_level + 1
                    data['exp'] -= required_exp
                else: break

            if data.get('level', 0) >= 3:
                await update_max_star(user_id, 3)

        # 💡 포인트 차감 로직 (획득이 없으므로 항상 마이너스)
        net_points = -lost_points
        if net_points < 0:
            deduct_amount = abs(net_points)
            current_user_points = await get_points(user_id)
            if current_user_points < deduct_amount:
                await spend_points(user_id, current_user_points) # 가진 돈 전부 차감 (마이너스 방지)
            else:
                await spend_points(user_id, deduct_amount)

        for egg in found_eggs: await add_item(user_id, f"{egg}급 알", 1)
        for rarity, item_name in found_items: await add_item(user_id, item_name, 1)

        await save_legend_data(self.user_id, wrapper)

        result_embed = discord.Embed(title="🐾 산책 결과", color=discord.Color.green())
        desc = f"{data['name']}(와)과 {num_walks}회 산책했습니다!\n"
        if has_ticket: desc += "🎫 `100회 산책 할인권`이 적용되어 300P만 소모되었습니다.\n"
        else: desc += f"💸 소모된 유지비: -{cost}P\n"
        desc += "━━━━━━━━━━━━━━━━━━━━\n"

        if gained_exp > 0:
            desc += f"📈 산책을 하며 경험치를 얻었다! (+{gained_exp} XP)\n"

        if num_walks == 1:
            if lose_count: desc += f"💩 산책하다가 똥을 밟았다.. (-{lost_points}P)\n"
        else:
            if lose_count: desc += f"💩 산책하다가 똥을 밟았다.. ({lose_count}번, -{lost_points}P)\n"

        if lost_points > 0:
            desc += f"*(정산 결과: -{lost_points}P)*\n"
        else:
            desc += f"*(정산 결과: 추가 포인트 소모 없음)*\n"

        for egg in found_eggs: desc += f"🥚 {egg}급 알을 발견했다!\n"
        for rarity, item_name in found_items: desc += f"🎁 {rarity}급 아이템 [{item_name}]을 발견했다!\n"
        if stat_msg: desc += f"\n{stat_msg}"

        result_embed.description = desc
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_embed.set_footer(text=f"사용자 ID: {user_id} | 실행 시각: {current_time}")

        await self.update_status_message(interaction, data, popup_embed=result_embed)

        log_desc = f"🐾 {data['name']} 산책\n💸 소모 유지비: -{cost}P\n"
        if gained_exp > 0: log_desc += f"📈 획득 경험치: +{gained_exp} XP\n"
        if lost_points > 0: log_desc += f"💩 잃은 포인트: -{lost_points}P\n"
        if found_eggs: log_desc += f"🥚 획득한 알: {', '.join(found_eggs)}급 알\n"
        if found_items: log_desc += f"🎁 획득한 아이템: {', '.join([i[1] for i in found_items])}\n"

        await send_log_embed(
            interaction.client, WALK_LOG_CH, "👟 산책 로그", log_desc.strip(),
            interaction.user, discord.Color.green(), f"구분: {num_walks}회 산책"
        )

    @discord.ui.button(label="1회 산책 (10P)", style=discord.ButtonStyle.success, emoji="🚶", row=1)
    async def walk_1(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_walk(interaction, 1)

    @discord.ui.button(label="10회 산책 (100P)", style=discord.ButtonStyle.success, emoji="🚶‍♂️", row=1)
    async def walk_10(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_walk(interaction, 10)

    @discord.ui.button(label="100회 산책 (1000P)", style=discord.ButtonStyle.success, emoji="🏃", row=1)
    async def walk_100(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_walk(interaction, 100)