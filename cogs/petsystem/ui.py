import discord
from .database import get_legend_data, save_legend_data

class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id

    async def get_pet_data(self):
        wrapper = await get_legend_data(self.user_id)
        if not wrapper or 'pets' not in wrapper:
            return None, None
        return wrapper, wrapper['pets'][wrapper['active_idx']]

    @discord.ui.button(label="밥주기", style=discord.ButtonStyle.primary, emoji="🍚")
    async def feed(self, interaction: discord.Interaction, button: discord.ui.Button):
        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        # 포만도 20 증가
        data['fullness'] = min(100, data.get('fullness', 0) + 20)

        await save_legend_data(self.user_id, wrapper)
        await interaction.response.send_message(f"🍚 {data['name']}(이)가 맛있게 밥을 먹었습니다! (포만도 +20)", ephemeral=True)

    @discord.ui.button(label="산책하기", style=discord.ButtonStyle.primary, emoji="🚶")
    async def walk(self, interaction: discord.Interaction, button: discord.ui.Button):
        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        # 산책 횟수 증가 (기존 데이터가 없으면 0부터 시작)
        data['walk_count'] = data.get('walk_count', 0) + 1
        msg = f"🚶 {data['name']}(와)과 즐겁게 산책했습니다! ({data['walk_count']}/20)"

        # 20회마다 스탯 변화
        if data['walk_count'] >= 20:
            data['fullness'] = max(0, data.get('fullness', 100) - 20)
            data['fatigue'] = min(100, data.get('fatigue', 0) + 20)
            data['cleanliness'] = max(0, data.get('cleanliness', 100) - 20)
            data['intimacy'] = min(100, data.get('intimacy', 50) + 20)
            data['walk_count'] = 0 # 카운트 초기화
            msg += "\n✨ 20회 산책 달성! 친밀도가 오르고 일부 스탯이 변했습니다."

        await save_legend_data(self.user_id, wrapper)
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="샤워하기", style=discord.ButtonStyle.primary, emoji="🚿")
    async def shower(self, interaction: discord.Interaction, button: discord.ui.Button):
        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        # 청결도 20 증가
        data['cleanliness'] = min(100, data.get('cleanliness', 0) + 20)

        await save_legend_data(self.user_id, wrapper)
        await interaction.response.send_message(f"🚿 {data['name']}(이)가 깨끗해졌습니다! (청결도 +20)", ephemeral=True)

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
        # 아이템 사용 로직은 기존 구현 방식에 따름 (여기선 예시)
        await interaction.response.send_message(f"{self.item_name} 아이템을 사용했습니다! (기능 구현 필요)", ephemeral=True)

def create_status_embed(user, data, points, buffs, is_annoyed, is_diseased):
    embed = discord.Embed(title=f"🐾 {data['name']}의 상태창", color=discord.Color.gold())
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

    embed.set_footer(text=f"보유 포인트: {points}P | 산책 횟수: {data.get('walk_count', 0)}/20")
    return embed