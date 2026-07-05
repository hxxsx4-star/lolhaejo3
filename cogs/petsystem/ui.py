import discord
import time
import random
from .database import get_legend_data, save_legend_data
from .data import PET_IMAGES, ITEMS_INFO

class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id

    async def get_pet_data(self):
        wrapper = await get_legend_data(self.user_id)
        if not wrapper or 'pets' not in wrapper:
            return None, None
        return wrapper, wrapper['pets'][wrapper['active_idx']]

    async def update_status_message(self, interaction: discord.Interaction, data, popup_msg):
        from .database import get_user, get_active_buffs
        user_data = await get_user(self.user_id)
        current_points = user_data[1]
        active_buffs = await get_active_buffs(self.user_id)
        buffs = {b[0] for b in active_buffs}

        now = time.time()
        is_annoyed = (data.get('low_full_since', 0) > 0 and now - data['low_full_since'] >= 86400)
        is_diseased = (data.get('low_clean_since', 0) > 0 and now - data['low_clean_since'] >= 86400)

        embed = create_status_embed(interaction.user, data, current_points, buffs, is_annoyed, is_diseased)

        # ephemeral=True 로 본인에게만 산책/행동 결과가 보이게 설정!
        await interaction.response.send_message(popup_msg, ephemeral=True)
        await interaction.message.edit(embed=embed)

    # UI 윗줄 (row=0) - 밥주기, 샤워하기
    @discord.ui.button(label="밥주기 (5P)", style=discord.ButtonStyle.primary, emoji="🍚", row=0)
    async def feed(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .database import get_user, update_user_points
        user_data = await get_user(self.user_id)

        if user_data[1] < 5:
            return await interaction.response.send_message("❌ 밥값(5P)이 부족합니다!", ephemeral=True)

        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        await update_user_points(self.user_id, -5)
        data['fullness'] = min(100, data.get('fullness', 0) + 20)
        await save_legend_data(self.user_id, wrapper)

        await self.update_status_message(interaction, data, f"🍚 {data['name']}(이)가 맛있게 밥을 먹었습니다! (포만도 +20, 밥값 -5P)")

    @discord.ui.button(label="샤워하기 (10P)", style=discord.ButtonStyle.primary, emoji="🚿", row=0)
    async def shower(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .database import get_user, update_user_points
        user_data = await get_user(self.user_id)

        if user_data[1] < 10:
            return await interaction.response.send_message("❌ 수도세(10P)가 부족합니다!", ephemeral=True)

        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        await update_user_points(self.user_id, -10)
        data['cleanliness'] = min(100, data.get('cleanliness', 0) + 20)
        await save_legend_data(self.user_id, wrapper)

        await self.update_status_message(interaction, data, f"🚿 {data['name']}(이)가 깨끗해졌습니다! (청결도 +20, 수도세 -10P)")

    # 산책 처리용 핵심 함수 (1회, 10회, 100회 공통)
    async def handle_walk(self, interaction: discord.Interaction, num_walks: int):
        from .database import get_active_buffs, get_user, update_user_points, consume_item, add_item

        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        user_id = self.user_id
        user_data = await get_user(user_id)
        current_points = user_data[1]

        # 100회 산책일 경우 할인권 로직
        if num_walks == 100:
            has_ticket = await consume_item(user_id, "100회 산책 할인권", 1)
            cost = 300 if has_ticket else 1000
        else:
            has_ticket = False
            cost = num_walks * 10

        if current_points < cost:
            msg = f"❌ 산책 유지비({cost}P)가 부족합니다! (현재: {current_points}P)"
            if has_ticket: await add_item(user_id, "100회 산책 할인권", 1) # 결제 실패시 할인권 롤백
            return await interaction.response.send_message(msg, ephemeral=True)

        await update_user_points(user_id, -cost)

        active_buffs = await get_active_buffs(user_id)
        buffs = {b[0] for b in active_buffs}

        data['total_walk_count'] = data.get('total_walk_count', 0) + num_walks
        old_walk_count = data.get('walk_count', 0)
        data['walk_count'] = old_walk_count + num_walks

        stat_triggers = data['walk_count'] // 20
        data['walk_count'] = data['walk_count'] % 20

        stat_msg = ""
        if stat_triggers > 0:
            data['fullness'] = max(0, data.get('fullness', 100) - (20 * stat_triggers))
            data['cleanliness'] = max(0, data.get('cleanliness', 100) - (20 * stat_triggers))
            data['intimacy'] = min(100, data.get('intimacy', 50) + (20 * stat_triggers))

            if "쌩쌩한약" in buffs or "신비한 알약" in buffs:
                stat_msg += "\n💊 [쌩쌩한약] 효과로 피로도가 오르지 않았습니다!"
            else:
                data['fatigue'] = min(100, data.get('fatigue', 0) + (20 * stat_triggers))

            stat_msg += f"\n✨ {stat_triggers * 20}회 산책 분량 달성! 친밀도가 오르고 배고픔/더러움이 증가했습니다."

        # 🎲 가챠 및 포인트 증감 로직 (산책 횟수만큼 반복)
        gained_points = 0
        gain_count = 0
        lost_points = 0
        lose_count = 0
        found_eggs = []
        found_items = []

        epic_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '서사']
        legend_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '전설']
        mythic_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '신화']
        prestige_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '프레스티지']

        for _ in range(num_walks):
            # 1. 포인트 드랍 (각각 개별 확률)
            if random.random() < 0.60:
                gained_points += 50
                gain_count += 1
            if random.random() < 0.50:
                lost_points += 45
                lose_count += 1

            # 2. 알 드랍
            r_egg = random.random()
            if r_egg < 0.0001: found_eggs.append("프레스티지")
            elif r_egg < 0.0021: found_eggs.append("신화")
            elif r_egg < 0.0221: found_eggs.append("전설")
            elif r_egg < 0.1221: found_eggs.append("서사")

            # 3. 아이템 드랍
            r_item = random.random()
            if r_item < 0.0001 and prestige_items: found_items.append(("프레스티지", random.choice(prestige_items)))
            elif r_item < 0.0011 and mythic_items: found_items.append(("신화", random.choice(mythic_items)))
            elif r_item < 0.0111 and legend_items: found_items.append(("전설", random.choice(legend_items)))
            elif r_item < 0.2111 and epic_items: found_items.append(("서사", random.choice(epic_items)))

        # 얻거나 잃은 포인트 일괄 적용
        if gained_points > 0: await update_user_points(user_id, gained_points)
        if lost_points > 0: await update_user_points(user_id, -lost_points)

        # 얻은 알과 아이템을 유저 인벤토리에 일괄 적용
        for egg in found_eggs:
            await add_item(user_id, f"{egg}급 알", 1)
        for rarity, item_name in found_items:
            await add_item(user_id, item_name, 1)

        await save_legend_data(self.user_id, wrapper)

        # 📝 최종 결과 메시지 작성
        msg_lines = [f"🚶 {data['name']}(와)과 {num_walks}회 산책했습니다! (유지비 -{cost}P)"]
        if has_ticket: msg_lines[0] += " 🎫 100회 할인권 적용됨!"

        # 다중 산책시 줄이 너무 길어지는걸 방지하기 위해 횟수를 표기합니다.
        if num_walks == 1:
            if gain_count: msg_lines.append(f"💰 산책하다가 포인트를 주웠다! (+{gained_points}P)")
            if lose_count: msg_lines.append(f"💩 산책하다가 똥을 밟았다.. (-{lost_points}P)")
        else:
            if gain_count: msg_lines.append(f"💰 산책하다가 포인트를 주웠다! ({gain_count}번, +{gained_points}P)")
            if lose_count: msg_lines.append(f"💩 산책하다가 똥을 밟았다.. ({lose_count}번, -{lost_points}P)")

        # 멘트 요구사항 정확히 반영!
        for egg in found_eggs:
            msg_lines.append(f"🥚 {egg}급 알을 발견했다!")
        for rarity, item_name in found_items:
            msg_lines.append(f"🎁 {rarity}급 아이템 [{item_name}]을 발견했다!")

        if stat_msg:
            msg_lines.append(stat_msg)

        final_msg = "\n".join(msg_lines)
        await self.update_status_message(interaction, data, final_msg)

    # UI 아랫줄 (row=1) - 산책 버튼 3형제
    @discord.ui.button(label="1회 산책 (10P)", style=discord.ButtonStyle.success, emoji="🚶", row=1)
    async def walk_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 1)

    @discord.ui.button(label="10회 산책 (100P)", style=discord.ButtonStyle.success, emoji="🚶‍♂️", row=1)
    async def walk_10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 10)

    @discord.ui.button(label="100회 산책 (1000P)", style=discord.ButtonStyle.success, emoji="🏃", row=1)
    async def walk_100(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 100)

# ==========================================
# 기존 인벤토리 및 상태창 임베드 코드 (변경 없음)
# ==========================================
class InventoryView(discord.ui.View):
    def __init__(self, user_id, items):
        super().__init__(timeout=60)
        self.user_id = user_id
        for item_name in items:
            self.add_item(InventoryButton(item_name))

class InventoryButton(discord.ui.Button):
    def __init__(self, item_name):
        super().__init__(label=item_name, style=discord.ButtonStyle.secondary)
        self.item_name = item_name

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        item_name = self.item_name

        if item_name == "100회 산책 할인권":
            return await interaction.response.send_message("💡 이 아이템은 100회 산책 시 자동으로 사용됩니다!", ephemeral=True)
        elif item_name == "전설이 이름 변경권":
            return await interaction.response.send_message("💡 이 아이템은 `/이름변경` 명령어를 입력해서 사용할 수 있습니다!", ephemeral=True)
        elif "급 알" in item_name:
            return await interaction.response.send_message("💡 알은 인벤토리에 보관됩니다! 아직 알을 직접 까는 기능은 추가되지 않았습니다.", ephemeral=True)

        if "경험치 부스터" in item_name:
            from .database import get_legend_data
            wrapper = await get_legend_data(user_id)
            if wrapper and wrapper.get('pets'):
                pet_data = wrapper['pets'][wrapper['active_idx']]
                if pet_data.get('cleanliness', 0) == 100:
                    return await interaction.response.send_message("❌ 청결도가 100(MAX) 상태일 때는 경험치 부스터를 사용할 수 없습니다!", ephemeral=True)

        from .database import consume_item, add_buff, update_user_points
        success = await consume_item(user_id, item_name, 1)
        if not success:
            return await interaction.response.send_message("❌ 아이템을 보유하고 있지 않거나 부족합니다.", ephemeral=True)

        msg = f"✅ `{item_name}`을(를) 사용했습니다!\n"

        if item_name in ["배부름을 부르는 약", "쌩쌩한약", "트위치 나가라약", "아무무도 인싸로 만드는 약"]:
            await add_buff(user_id, buff_name=item_name, duration_sec=86400, vc_sec=0)
            msg += "✨ 효과: 24시간 동안 해당 스탯이 고정됩니다."
        elif item_name == "신비한 알약":
            await add_buff(user_id, buff_name=item_name, duration_sec=1209600, vc_sec=0)
            msg += "✨ 효과: 14일 동안 모든 스탯이 최상으로 고정됩니다."
        elif item_name in ["경험치 부스터 X2", "경험치 부스터 X5", "경험치 부스터 X10"]:
            await add_buff(user_id, buff_name=item_name, duration_sec=0, vc_sec=10800)
            msg += "📈 효과: 통화방에 있는 동안 3시간 동안 경험치 획득량이 증가합니다."
        elif item_name == "50포인트 교환권":
            await update_user_points(user_id, 50)
            msg += "💸 50P를 획득했습니다!"
        elif item_name == "100포인트 교환권":
            await update_user_points(user_id, 100)
            msg += "💸 100P를 획득했습니다!"
        elif item_name == "500포인트 교환권":
            await update_user_points(user_id, 500)
            msg += "💸 500P를 획득했습니다!"
        elif item_name == "1000포인트 교환권":
            await update_user_points(user_id, 1000)
            msg += "💸 1,000P를 획득했습니다!"
        else:
            msg += "하지만 아무 일도 일어나지 않았습니다..?"

        await interaction.response.send_message(msg, ephemeral=True)

def create_status_embed(user, data, points, buffs, is_annoyed, is_diseased):
    embed = discord.Embed(title=f"🐾 {data['name']}의 상태창", color=discord.Color.gold())

    pet_type = data.get('type')
    if pet_type in PET_IMAGES:
        embed.set_thumbnail(url=PET_IMAGES[pet_type])

    embed.add_field(name="등급", value=data.get('rarity', '서사'), inline=True)
    embed.add_field(name="레벨", value=f"{data.get('level', 0)}성", inline=True)
    embed.add_field(name="경험치", value=f"{data.get('exp', 0)}", inline=True)
    embed.add_field(name="포만도", value=f"{data.get('fullness', 0)}%", inline=True)
    embed.add_field(name="피로도", value=f"{data.get('fatigue', 0)}%", inline=True)
    embed.add_field(name="청결도", value=f"{data.get('cleanliness', 0)}%", inline=True)
    embed.add_field(name="친밀도", value=f"{data.get('intimacy', 0)}%", inline=True)

    if buffs:
        embed.add_field(name="활성화된 버프", value=", ".join(buffs), inline=False)

    if is_annoyed:
        embed.add_field(name="⚠️ 상태", value="배가 너무 고파서 심술이 났습니다!", inline=False)
    if is_diseased:
        embed.add_field(name="⚠️ 상태", value="너무 더러워서 병에 걸렸습니다!", inline=False)

    embed.set_footer(text=f"보유 포인트: {points}P | 누적 산책: {data.get('total_walk_count', 0)}회")
    return embed