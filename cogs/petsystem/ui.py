import discord
import time
from .database import get_legend_data, save_legend_data
from .data import PET_IMAGES

class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id

    async def get_pet_data(self):
        wrapper = await get_legend_data(self.user_id)
        if not wrapper or 'pets' not in wrapper:
            return None, None
        return wrapper, wrapper['pets'][wrapper['active_idx']]

    # 💡 [추가됨] 버튼 클릭 시 상태창 UI를 즉시 업데이트 해주는 도우미 함수
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

        await interaction.response.send_message(popup_msg, ephemeral=True)
        await interaction.message.edit(embed=embed)

    @discord.ui.button(label="밥주기", style=discord.ButtonStyle.primary, emoji="🍚")
    async def feed(self, interaction: discord.Interaction, button: discord.ui.Button):
        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        data['fullness'] = min(100, data.get('fullness', 0) + 20)
        await save_legend_data(self.user_id, wrapper)

        await self.update_status_message(interaction, data, f"🍚 {data['name']}(이)가 맛있게 밥을 먹었습니다! (포만도 +20)")

    @discord.ui.button(label="산책하기", style=discord.ButtonStyle.primary, emoji="🚶")
    async def walk(self, interaction: discord.Interaction, button: discord.ui.Button):
        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        from .database import get_active_buffs, get_user, update_user_points, consume_item, add_item
        active_buffs = await get_active_buffs(self.user_id)
        buffs = {b[0] for b in active_buffs}

        data['walk_count'] = data.get('walk_count', 0) + 1
        data['total_walk_count'] = data.get('total_walk_count', 0) + 1

        msg = f"🚶 {data['name']}(와)과 즐겁게 산책했습니다! (현재: {data['walk_count']}/20, 누적: {data['total_walk_count']}회)"

        if data['walk_count'] >= 20:
            data['fullness'] = max(0, data.get('fullness', 100) - 20)
            data['cleanliness'] = max(0, data.get('cleanliness', 100) - 20)
            data['intimacy'] = min(100, data.get('intimacy', 50) + 20)

            # 피로도 방어
            if "쌩쌩한약" in buffs or "신비한 알약" in buffs:
                msg += "\n💊 [쌩쌩한약] 효과로 피로도가 오르지 않았습니다!"
            else:
                data['fatigue'] = min(100, data.get('fatigue', 0) + 20)

            data['walk_count'] = 0
            msg += "\n✨ 20회 산책 달성! 친밀도가 오르고 배고픔/더러움이 증가했습니다."

        # 누적 100회 결제 로직
        if data['total_walk_count'] > 0 and data['total_walk_count'] % 100 == 0:
            user_data = await get_user(self.user_id)
            current_points = user_data[1]

            has_ticket = await consume_item(self.user_id, "100회 산책 할인권", 1)
            cost = 300 if has_ticket else 500

            if current_points < cost:
                msg += f"\n❌ 산책 유지비({cost}P)가 부족합니다! (포인트를 모아오세요)"
                data['total_walk_count'] -= 1
                if has_ticket:
                    await add_item(self.user_id, "100회 산책 할인권", 1)
            else:
                await update_user_points(self.user_id, -cost)
                ticket_msg = "(🎫 할인권 적용됨!)" if has_ticket else ""
                msg += f"\n🎉 누적 100회 산책! 산책 유지비 {cost}P가 소모되었습니다. {ticket_msg}"

        await save_legend_data(self.user_id, wrapper)
        await self.update_status_message(interaction, data, msg)

    @discord.ui.button(label="샤워하기", style=discord.ButtonStyle.primary, emoji="🚿")
    async def shower(self, interaction: discord.Interaction, button: discord.ui.Button):
        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        data['cleanliness'] = min(100, data.get('cleanliness', 0) + 20)
        await save_legend_data(self.user_id, wrapper)

        await self.update_status_message(interaction, data, f"🚿 {data['name']}(이)가 깨끗해졌습니다! (청결도 +20)")

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

    # 💡 [추가됨] 펫 썸네일 이미지 표시 기능
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