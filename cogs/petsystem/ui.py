import discord
import time
from .data import ITEMS_INFO, EXP_TABLE
from .database import (
    consume_item, add_buff,
    get_legend_data, save_legend_data, get_user,
    get_active_buffs, add_item
)
# 기존 .database의 update_user_points 대신 메인 봇의 stats 모듈을 불러옵니다.
# (경로는 실제 폴더 구조에 맞게 수정해야 할 수 있습니다.)
from utils.stats import get_points, add_points


def create_status_embed(member: discord.Member, pet_data, user_points, buffs, is_annoyed, is_diseased):
    is_egg = (pet_data['level'] == 0)
    name, rarity, level = pet_data['name'], pet_data['rarity'], pet_data['level']

    display_name = f"미확인 알 ({rarity})" if is_egg else name
    star_text = "🥚 부화 대기 중" if is_egg else f"{level}성"

    health_status = "보통 🟢"
    if is_egg:
        health_status = "알 🥚"
    elif is_diseased:
        health_status = "질병 🔴 (비용 2배! 샤워 필요)"
    elif pet_data.get('cleanliness', 100) <= 20:
        health_status = "지저분 🟠"

    mood_status = "행복 😊"
    if is_egg:
        mood_status = "알 🥚"
    elif is_annoyed:
        mood_status = "짜증 💢 (산책 거부, 식비 2배!)"
    elif pet_data['fullness'] <= 20:
        mood_status = "배고픔 🟠"

    buff_text = "적용중인 버프: " + (", ".join(buffs) if buffs else "없음")

    embed = discord.Embed(
        title=f"{member.display_name}님의 {display_name} 상태창",
        description=f"등급: {rarity} | 보유 포인트: {user_points:,} P\n{buff_text}",
        color=discord.Color.purple() if rarity == "서사" else (
            discord.Color.red() if rarity == "전설" else discord.Color.gold())
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    if level == 3:
        exp_text, exp_percent = "MAX", 10
    else:
        max_exp = EXP_TABLE[rarity][level]
        exp_text = f"{pet_data['exp']:,} / {max_exp:,}"
        exp_percent = int((pet_data['exp'] / max_exp) * 10)

    embed.add_field(name="⭐ 성장", value=star_text, inline=True)
    if not is_egg:
        embed.add_field(name="❤️ 친밀도", value=f"{pet_data['intimacy']} pt", inline=True)
        embed.add_field(name="💤 피로도", value=f"{pet_data['fatigue']} pt", inline=True)

    embed.add_field(name="🩺 상태", value=f"건강: {health_status}\n기분: {mood_status}", inline=False)
    embed.add_field(name=f"✨ 경험치 ({exp_text})", value="🟩" * exp_percent + "⬜" * (10 - exp_percent), inline=False)

    if not is_egg:
        f_val = pet_data['fullness'] // 10
        embed.add_field(name=f"🍖 포만감 ({pet_data['fullness']}/100)", value="🟧" * f_val + "⬜" * (10 - f_val),
                        inline=False)
        c_val = pet_data.get('cleanliness', 100) // 10
        embed.add_field(name=f"🚿 청결도 ({pet_data.get('cleanliness', 100)}/100)", value="🟦" * c_val + "⬜" * (10 - c_val),
                        inline=False)

    return embed


class InventoryView(discord.ui.View):
    def __init__(self, user_id, items_dict):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.items = items_dict
        self.selected_item = None

        options = [
            discord.SelectOption(label=f"{name} (보유: {amount}개)", value=name, description=ITEMS_INFO[name]["desc"][:50])
            for name, amount in items_dict.items()]
        if not options:
            options.append(discord.SelectOption(label="사용할 아이템이 없습니다.", value="no_item"))

        self.select_menu = discord.ui.Select(placeholder="사용할 아이템을 선택하세요", options=options)
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("자신의 보관함만 조작할 수 있습니다.", ephemeral=True)

        self.selected_item = self.select_menu.values[0]
        if self.selected_item == "no_item":
            return await interaction.response.defer()

        btn = discord.ui.Button(label=f"[{self.selected_item}] 사용하기", style=discord.ButtonStyle.success)
        btn.callback = self.use_callback

        view = discord.ui.View()
        view.add_item(btn)
        await interaction.response.edit_message(
            content=f"선택됨: {self.selected_item}\n{ITEMS_INFO[self.selected_item]['desc']}", view=view)

    async def use_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return

        success = await consume_item(self.user_id, self.selected_item, 1)
        if success:
            msg = f"✅ `{self.selected_item}` 아이템을 사용했습니다!"
            if "포인트 교환권" in self.selected_item:
                pts = int(self.selected_item.split("포인트")[0])
                # 메인 봇의 포인트 추가 함수 사용
                await add_points(self.user_id, pts)
                msg += f"\n포인트 {pts}P를 얻었습니다."
            elif "부스터" in self.selected_item:
                await add_buff(self.user_id, self.selected_item, vc_sec=10800)
                msg += "\n통화방 활동 3시간 동안 경험치 부스터가 적용됩니다."
            elif "신비한 알약" in self.selected_item:
                await add_buff(self.user_id, "신비한 알약", duration_sec=1209600)
                msg += "\n2주 동안 전설이의 모든 능력치가 MAX로 유지됩니다."
            elif "할인권" not in self.selected_item:
                await add_buff(self.user_id, self.selected_item, duration_sec=86400)
                msg += "\n24시간 동안 버프 효과가 적용됩니다."
            await interaction.response.edit_message(content=msg, view=None, embed=None)
        else:
            await interaction.response.send_message("아이템이 부족합니다.", ephemeral=True)


class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="밥 주기", style=discord.ButtonStyle.success, emoji="🍖")
    async def feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "feed")

    @discord.ui.button(label="샤워", style=discord.ButtonStyle.secondary, emoji="🚿")
    async def shower_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "shower")

    @discord.ui.button(label="산책 1회", style=discord.ButtonStyle.primary, emoji="👟")
    async def walk_1_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 1)

    @discord.ui.button(label="산책 100회", style=discord.ButtonStyle.primary, emoji="🏃")
    async def walk_100_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 100)

    async def handle_action(self, interaction: discord.Interaction, action: str):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("자신의 전설이만 돌볼 수 있습니다!", ephemeral=True)

        data = await get_legend_data(self.user_id)
        if not data or data['level'] == 0:
            return await interaction.response.send_message("전설이가 알 상태이거나 존재하지 않습니다.", ephemeral=True)

        # 메인 봇의 포인트를 불러옵니다.
        current_points = await get_points(self.user_id)

        now = time.time()
        is_annoyed = (data.get('low_full_since', 0) > 0 and now - data.get('low_full_since', 0) >= 86400)
        is_diseased = (data.get('low_clean_since', 0) > 0 and now - data.get('low_clean_since', 0) >= 86400)

        msg = ""

        if action == "feed":
            if data['fullness'] >= 100:
                return await interaction.response.send_message("전설이가 이미 배가 부릅니다!", ephemeral=True)

            cost = 100 if is_annoyed else 50  # 짜증 상태면 식비 2배
            if current_points < cost:
                return await interaction.response.send_message(f"포인트가 부족합니다! (필요: {cost}P)", ephemeral=True)

            # 포인트 차감 (add_points에 음수 값을 전달)
            await add_points(self.user_id, -cost)
            data['fullness'] = min(100, data['fullness'] + 30)
            data['low_full_since'] = 0  # 배고픔 시간 초기화
            msg = f"🍖 밥을 먹였습니다! (포만감 +30, -{cost}P)"
            if is_annoyed: msg += "\n💢 전설이의 짜증이 풀렸습니다!"

        elif action == "shower":
            if data.get('cleanliness', 100) >= 100:
                return await interaction.response.send_message("전설이가 이미 깨끗합니다!", ephemeral=True)

            cost = 100 if is_diseased else 50  # 질병 상태면 비용 2배
            if current_points < cost:
                return await interaction.response.send_message(f"포인트가 부족합니다! (필요: {cost}P)", ephemeral=True)

            # 포인트 차감
            await add_points(self.user_id, -cost)
            data['cleanliness'] = 100
            data['low_clean_since'] = 0  # 지저분함 시간 초기화
            msg = f"🚿 깨끗하게 씻겼습니다! (청결도 MAX, -{cost}P)"
            if is_diseased: msg += "\n🔴 전설이의 질병이 치료되었습니다!"

        # 데이터 저장
        await save_legend_data(self.user_id, data)

        # 엠베드 갱신
        active_buffs = await get_active_buffs(self.user_id)
        buffs = {b[0] for b in active_buffs}

        # 갱신된 메인 봇 포인트 불러오기
        new_points = await get_points(self.user_id)

        is_annoyed_now = (data.get('low_full_since', 0) > 0 and now - data.get('low_full_since', 0) >= 86400)
        is_diseased_now = (data.get('low_clean_since', 0) > 0 and now - data.get('low_clean_since', 0) >= 86400)

        embed = create_status_embed(interaction.user, data, new_points, buffs, is_annoyed_now, is_diseased_now)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(msg, ephemeral=True)

    async def handle_walk(self, interaction: discord.Interaction, count: int):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("자신의 전설이만 돌볼 수 있습니다!", ephemeral=True)

        data = await get_legend_data(self.user_id)
        if not data or data['level'] == 0:
            return await interaction.response.send_message("전설이가 알 상태이거나 존재하지 않습니다.", ephemeral=True)

        if data['level'] >= 3:
            return await interaction.response.send_message("전설이가 이미 최대 레벨(3성)에 도달했습니다!", ephemeral=True)

        # 짜증 상태(is_annoyed) 체크 - 산책 거부
        now = time.time()
        is_annoyed = (data.get('low_full_since', 0) > 0 and now - data.get('low_full_since', 0) >= 86400)
        if is_annoyed:
            return await interaction.response.send_message("전설이가 짜증이 나서 산책을 거부합니다! (밥을 먼저 주세요)", ephemeral=True)

        # 메인 봇의 포인트를 불러옵니다.
        current_points = await get_points(self.user_id)
        active_buffs = await get_active_buffs(self.user_id)
        buffs = {b[0] for b in active_buffs}

        # 산책 비용 계산 (1회당 5P)
        cost = 5 * count
        used_discount = False

        if count >= 100:
            success = await consume_item(self.user_id, "100회 산책 할인권", 1)
            if success:
                cost = 300
                used_discount = True

        if current_points < cost:
            if used_discount: await add_item(self.user_id, "100회 산책 할인권", 1)  # 아이템 환불
            return await interaction.response.send_message(f"포인트가 부족합니다! (필요: {cost}P)", ephemeral=True)

        # --- 신규 산책 로직 (20회당 1칸(10 포인트)) ---
        # 1회 산책 시 꼼수 방지를 위해 최소 1은 깎이도록 설계 (100회면 50 포인트 깎임)
        stat_change = max(1, int(count * 0.5))

        # 버프가 없을 경우에만 페널티(감소량) 적용
        full_decrease = 0 if ("배부름을 부르는 약" in buffs or "신비한 알약" in buffs) else stat_change
        clean_decrease = 0 if ("트위치 나가라약" in buffs or "신비한 알약" in buffs) else stat_change
        fatigue_increase = 0 if ("쌩쌩한약" in buffs or "신비한 알약" in buffs) else stat_change

        # 친밀도는 버프 중이면 이미 MAX일 것이므로 자연 증가만 계산
        intimacy_increase = stat_change

        if data['fatigue'] + fatigue_increase > 100 and fatigue_increase > 0:
            if used_discount: await add_item(self.user_id, "100회 산책 할인권", 1)
            return await interaction.response.send_message("전설이가 너무 피곤해합니다! 휴식이 필요합니다. (피로도 한도 초과 예정)", ephemeral=True)

        # 경험치 계산 (1회당 100 예시)
        exp_gain = 100 * count
        exp_multiplier = 1
        if data['intimacy'] >= 80: exp_multiplier *= 2  # 친밀도 높으면 2배
        total_exp = int(exp_gain * exp_multiplier)

        # 메인 봇 포인트 차감
        await add_points(self.user_id, -cost)
        data['exp'] += total_exp

        data['fullness'] = max(0, data['fullness'] - full_decrease)
        data['cleanliness'] = max(0, data.get('cleanliness', 100) - clean_decrease)
        data['intimacy'] = min(100, data['intimacy'] + intimacy_increase)
        data['fatigue'] = min(100, data['fatigue'] + fatigue_increase)

        # 레벨업 체크
        max_exp = EXP_TABLE[data['rarity']][data['level']]
        leveled_up = False
        while data['level'] < 3 and data['exp'] >= max_exp:
            data['exp'] -= max_exp
            data['level'] += 1
            leveled_up = True
            if data['level'] < 3:
                max_exp = EXP_TABLE[data['rarity']][data['level']]

        if data['level'] >= 3:
            data['exp'] = 0

        await save_legend_data(self.user_id, data)

        # 결과 메시지
        msg = f"🏃 산책 {count}회를 완료했습니다! (경험치 +{total_exp}, 비용 -{cost}P)\n"
        msg += f"📉 포만감 -{full_decrease}, 청결도 -{clean_decrease} | 📈 친밀도 +{intimacy_increase}, 피로도 +{fatigue_increase}"

        if used_discount:
            msg += "\n🎫 `100회 산책 할인권`을 사용했습니다!"
        if leveled_up:
            msg += f"\n🎉 축하합니다! 전설이가 {data['level']}성으로 레벨업했습니다!"

        # 엠베드 갱신 시 갱신된 메인 봇 포인트 불러오기
        new_points = await get_points(self.user_id)
        is_diseased = (data.get('low_clean_since', 0) > 0 and now - data.get('low_clean_since', 0) >= 86400)

        embed = create_status_embed(interaction.user, data, new_points, buffs, is_annoyed, is_diseased)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(msg, ephemeral=True)