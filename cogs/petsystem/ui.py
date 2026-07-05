import discord
import time
# data.py에서 필요한 데이터들을 불러옵니다.
from .data import ITEMS_INFO, EXP_TABLE, PET_IMAGES, PET_POOLS
from .database import (
    consume_item, add_buff,
    get_legend_data, save_legend_data, get_user,
    get_active_buffs, add_item
)
from utils.stats import get_points, add_points, spend_points

def create_status_embed(member: discord.Member, pet_data, user_points, buffs, is_annoyed, is_diseased):
    is_egg = (pet_data['level'] == 0)

    # 💡 데이터에서 이름, 등급, 레벨과 함께 'type'(종류, PET_POOLS의 항목)을 가져옵니다.
    name = pet_data['name']
    rarity = pet_data['rarity']
    level = pet_data['level']
    pet_type = pet_data.get('type', '알 수 없음')

    display_name = f"미확인 알" if is_egg else name
    star_text = "🥚 부화 대기 중" if is_egg else f"{level}성"

    # UI 디자인 개편: 펫 이름(# 큰 글씨), 등급, 종류 텍스트 배치
    embed = discord.Embed(
        description=f"# {display_name}\n\n⭐ 성장: {star_text}\n💎 등급: {rarity}\n🧬 종류: {pet_type}",
        color=discord.Color.purple() if rarity == "서사" else (
            discord.Color.red() if rarity == "전설" else discord.Color.gold())
    )

    # 💡 [핵심 수정 부분] 썸네일 이미지를 이름(name)이 아닌 종류(type)로 찾습니다.
    thumbnail_url = PET_IMAGES.get(pet_type)

    if thumbnail_url and not is_egg:
        embed.set_thumbnail(url=thumbnail_url)
    else:
        # 알 상태이거나 이미지가 없을 때는 기본 유저 프사 유지
        embed.set_thumbnail(url=member.display_avatar.url)

    # 적용중인 버프
    if buffs:
        embed.add_field(name="", value=f"💊 적용중인 버프: {', '.join(buffs)}", inline=False)

    # 경험치 바 (알은 100으로 고정)
    if level == 3:
        exp_text, exp_percent = "MAX", 10
        bar = "🟩" * 10
    else:
        max_exp = 100 if is_egg else EXP_TABLE[rarity][level]
        exp_text = f"{pet_data['exp']:,} / {max_exp:,}"
        exp_percent = int((pet_data['exp'] / max_exp) * 10)
        bar = "🟩" * exp_percent + "⬜" * (10 - exp_percent)

    embed.add_field(name="", value=f"{bar}\n({exp_text} XP)", inline=False)

    # 상태 및 이모지 출력
    if not is_egg:
        h_val = max(1, pet_data['intimacy'] // 20)
        f_val = max(1, pet_data['fullness'] // 20)
        c_val = max(1, pet_data.get('cleanliness', 100) // 20)
        s_val = max(1, pet_data['fatigue'] // 20)

        status_text = (
            f"친밀도: {'❤️' * h_val}\n"
            f"포만도: {'🍗' * f_val}\n"
            f"청결도: {'🚿' * c_val}\n"
            f"피로도: {'😴' * s_val}"
        )

        # 짜증이나 질병 상태일 경우 경고 메시지 추가
        warning = ""
        if is_annoyed: warning += "\n💢 짜증남! (밥 부족, 산책 거부)"
        if is_diseased: warning += "\n🔴 질병 발생! (청결 부족, 비용 2배)"

        embed.add_field(name="상태", value=status_text + warning, inline=False)
    else:
        embed.add_field(name="상태", value="건강: 알 🥚\n기분: 평온 😌", inline=False)

    # 보유 포인트 맨 아래 배치
    embed.set_footer(text=f"💰 보유 포인트: {user_points:,} P")

    return embed

class InventoryView(discord.ui.View):
    def __init__(self, user_id, items):
        super().__init__(timeout=60.0)
        self.user_id = user_id

        options = []
        for item_name, amount in items.items():
            if item_name in ITEMS_INFO:
                rarity = ITEMS_INFO[item_name]['rarity']
                desc = ITEMS_INFO[item_name]['desc'][:50]
                options.append(discord.SelectOption(
                    label=f"{item_name} (보유: {amount}개)",
                    description=desc,
                    value=item_name
                ))

        if options:
            self.select = discord.ui.Select(placeholder="사용할 아이템을 선택하세요", min_values=1, max_values=1, options=options)
            self.select.callback = self.select_callback
            self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("자신의 보관함만 사용할 수 있습니다!", ephemeral=True)

        selected_item = self.select.values[0]

        if selected_item == "전설이 이름 변경권" or "할인권" in selected_item:
            return await interaction.response.send_message(f"`{selected_item}`은(는) 여기서 직접 사용할 수 없습니다. 알맞은 상황에 자동으로 사용되거나 전용 명령어를 이용해주세요.", ephemeral=True)

        success = await consume_item(self.user_id, selected_item, 1)
        if not success:
            return await interaction.response.send_message("아이템 사용에 실패했습니다. (수량 부족)", ephemeral=True)

        if "포인트 교환권" in selected_item:
            points_to_add = int(selected_item.replace("포인트 교환권", ""))
            await add_points(self.user_id, points_to_add)
            return await interaction.response.send_message(f"✅ `{selected_item}`을(를) 사용하여 {points_to_add}P를 획득했습니다!", ephemeral=True)

        await add_buff(self.user_id, selected_item)
        await interaction.response.send_message(f"✅ `{selected_item}`을(를) 사용했습니다! (버프가 적용됩니다)", ephemeral=True)

class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    async def get_active_pet(self):
        wrapper = await get_legend_data(self.user_id)
        if not wrapper or 'pets' not in wrapper or not wrapper['pets']:
            return None, wrapper
        active_idx = wrapper.get('active_idx', 0)
        return wrapper['pets'][active_idx], wrapper

    # 포인트 명시 및 색상 적용 완료
    @discord.ui.button(label="밥 주기 (5P)", style=discord.ButtonStyle.secondary, emoji="🍖")
    async def feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "feed")

    @discord.ui.button(label="샤워 (10P)", style=discord.ButtonStyle.primary, emoji="🚿")
    async def shower_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "shower")

    @discord.ui.button(label="산책 1회 (10P)", style=discord.ButtonStyle.success, emoji="👟")
    async def walk_1_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 1)

    @discord.ui.button(label="산책 10회 (100P)", style=discord.ButtonStyle.success, emoji="🚶")
    async def walk_10_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 10)

    @discord.ui.button(label="산책 100회 (할인권)", style=discord.ButtonStyle.success, emoji="🏃")
    async def walk_100_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 100)

    async def handle_action(self, interaction: discord.Interaction, action: str):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("자신의 전설이만 돌볼 수 있습니다!", ephemeral=True)

        data, wrapper = await self.get_active_pet()
        if not data or data['level'] == 0:
            return await interaction.response.send_message("전설이가 알 상태이거나 존재하지 않습니다.", ephemeral=True)

        now = time.time()
        is_annoyed = (data.get('low_full_since', 0) > 0 and now - data.get('low_full_since', 0) >= 86400)
        is_diseased = (data.get('low_clean_since', 0) > 0 and now - data.get('low_clean_since', 0) >= 86400)
        msg = ""

        if action == "feed":
            if data['fullness'] >= 100:
                return await interaction.response.send_message("전설이가 이미 배가 부릅니다!", ephemeral=True)
            cost = 10 if is_annoyed else 5

            if not await spend_points(self.user_id, cost):
                return await interaction.response.send_message(f"포인트가 부족합니다! (필요: {cost}P)", ephemeral=True)

            data['fullness'] = min(100, data['fullness'] + 30)
            data['low_full_since'] = 0
            msg = f"🍖 밥을 먹였습니다! (포만감 +30, -{cost}P)"
            if is_annoyed: msg += "\n💢 전설이의 짜증이 풀렸습니다!"

        elif action == "shower":
            if data.get('cleanliness', 100) >= 100:
                return await interaction.response.send_message("전설이가 이미 깨끗합니다!", ephemeral=True)
            cost = 20 if is_diseased else 10

            if not await spend_points(self.user_id, cost):
                return await interaction.response.send_message(f"포인트가 부족합니다! (필요: {cost}P)", ephemeral=True)

            data['cleanliness'] = 100
            data['low_clean_since'] = 0
            msg = f"🚿 깨끗하게 씻겼습니다! (청결도 MAX, -{cost}P)"
            if is_diseased: msg += "\n🔴 전설이의 질병이 치료되었습니다!"

        wrapper['pets'][wrapper['active_idx']] = data
        await save_legend_data(self.user_id, wrapper)

        active_buffs = await get_active_buffs(self.user_id)
        buffs = {b[0] for b in active_buffs}
        new_points = await get_points(self.user_id)
        is_annoyed_now = (data.get('low_full_since', 0) > 0 and now - data.get('low_full_since', 0) >= 86400)
        is_diseased_now = (data.get('low_clean_since', 0) > 0 and now - data.get('low_clean_since', 0) >= 86400)

        embed = create_status_embed(interaction.user, data, new_points, buffs, is_annoyed_now, is_diseased_now)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(msg, ephemeral=True)

    async def handle_walk(self, interaction: discord.Interaction, count: int):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("자신의 전설이만 돌볼 수 있습니다!", ephemeral=True)

        data, wrapper = await self.get_active_pet()
        if not data or data['level'] == 0:
            return await interaction.response.send_message("전설이가 알 상태이거나 존재하지 않습니다.", ephemeral=True)

        if data['level'] >= 3:
            return await interaction.response.send_message("전설이가 이미 최대 레벨(3성)에 도달했습니다!", ephemeral=True)

        now = time.time()
        is_annoyed = (data.get('low_full_since', 0) > 0 and now - data.get('low_full_since', 0) >= 86400)
        if is_annoyed:
            return await interaction.response.send_message("전설이가 짜증이 나서 산책을 거부합니다! (밥을 먼저 주세요)", ephemeral=True)

        active_buffs = await get_active_buffs(self.user_id)
        buffs = {b[0] for b in active_buffs}

        stat_change = max(1, int(count * 0.5))
        fatigue_increase = 0 if ("쌩쌩한약" in buffs or "신비한 알약" in buffs) else stat_change

        if data['fatigue'] + fatigue_increase > 100 and fatigue_increase > 0:
            return await interaction.response.send_message("전설이가 너무 피곤해합니다! 휴식이 필요합니다.", ephemeral=True)

        cost = 10 * count
        used_discount = False

        if count >= 100:
            success = await consume_item(self.user_id, "100회 산책 할인권", 1)
            if success:
                cost = 300
                used_discount = True

        if not await spend_points(self.user_id, cost):
            if used_discount: await add_item(self.user_id, "100회 산책 할인권", 1)
            return await interaction.response.send_message(f"포인트가 부족합니다! (필요: {cost}P)", ephemeral=True)

        full_decrease = 0 if ("배부름을 부르는 약" in buffs or "신비한 알약" in buffs) else stat_change
        clean_decrease = 0 if ("트위치 나가라약" in buffs or "신비한 알약" in buffs) else stat_change
        intimacy_increase = stat_change
        exp_gain = 100 * count
        exp_multiplier = 1
        if data['intimacy'] >= 80: exp_multiplier *= 2
        total_exp = int(exp_gain * exp_multiplier)

        data['exp'] += total_exp
        data['fullness'] = max(0, data['fullness'] - full_decrease)
        data['cleanliness'] = max(0, data.get('cleanliness', 100) - clean_decrease)
        data['intimacy'] = min(100, data['intimacy'] + intimacy_increase)
        data['fatigue'] = min(100, data['fatigue'] + fatigue_increase)

        max_exp = 100 if data['level'] == 0 else EXP_TABLE[data['rarity']][data['level']]
        leveled_up = False
        while data['level'] < 3 and data['exp'] >= max_exp:
            data['exp'] -= max_exp
            data['level'] += 1
            leveled_up = True
            if data['level'] < 3:
                max_exp = EXP_TABLE[data['rarity']][data['level']]

        if data['level'] >= 3:
            data['exp'] = 0

        wrapper['pets'][wrapper['active_idx']] = data
        await save_legend_data(self.user_id, wrapper)

        msg = f"🏃 산책 {count}회를 완료했습니다! (경험치 +{total_exp}, 비용 -{cost}P)\n"
        msg += f"📉 포만감 -{full_decrease}, 청결도 -{clean_decrease} | 📈 친밀도 +{intimacy_increase}, 피로도 +{fatigue_increase}"

        if used_discount: msg += "\n🎫 `100회 산책 할인권`을 사용했습니다!"
        if leveled_up: msg += f"\n🎉 축하합니다! 전설이가 {data['level']}성으로 레벨업했습니다!"

        new_points = await get_points(self.user_id)
        is_diseased = (data.get('low_clean_since', 0) > 0 and now - data.get('low_clean_since', 0) >= 86400)

        embed = create_status_embed(interaction.user, data, new_points, buffs, is_annoyed, is_diseased)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(msg, ephemeral=True)