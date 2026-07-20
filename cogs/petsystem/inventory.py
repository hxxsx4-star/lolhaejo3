import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite

from utils.data import ITEMS_INFO, PET_POOLS, PET_IMAGES, RARITY_ORDER, EGG_EXCHANGE_RATE, egg_item_name, prev_rarity
from utils.database import consume_item, add_item, get_user_items
from .ui_inventory import InventoryView

# 알 환전/분해 선택지는 data.py의 EGG_EXCHANGE_RATE(단일 소스)에서 자동 생성됩니다.
# 등급을 추가/수정하려면 data.py만 고치면 여기 명령어는 자동 반영됩니다.
_EGG_TIERS = [r for r in RARITY_ORDER if r in EGG_EXCHANGE_RATE]
EXCHANGE_CHOICES = [
    app_commands.Choice(name=f"{r}급 알 (비용: {prev_rarity(r)}급 알 {EGG_EXCHANGE_RATE[r]}개)", value=egg_item_name(r))
    for r in _EGG_TIERS
]
DECOMPOSE_CHOICES = [
    app_commands.Choice(name=f"{r}급 알 ({prev_rarity(r)}급 알 {EGG_EXCHANGE_RATE[r]}개 획득)", value=egg_item_name(r))
    for r in _EGG_TIERS
]

class InventoryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="보관함", description="내 아이템을 확인하고 사용합니다.")
    async def inventory(self, interaction: discord.Interaction):
        items = await get_user_items(interaction.user.id)
        if not items: return await interaction.response.send_message("보관함이 비어있습니다.", ephemeral=True)

        embed = discord.Embed(title="🎒 내 보관함", description="아래 메뉴에서 아이템을 선택한 후 사용 버튼을 눌러주세요.", color=discord.Color.blurple())
        for item_name, amount in items:
            embed.add_field(name=f"▪️ {item_name}", value=f"{amount}개 보유", inline=False)

        view = InventoryView(interaction.user.id, dict(items))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="전설이목록", description="등급별 획득 가능한 전설이 목록을 확인합니다.")
    async def legend_list(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📜 전설이 목록", color=discord.Color.blue())
        for rarity, pets in PET_POOLS.items():
            embed.add_field(name=f"[{rarity}급]", value=", ".join(pets), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="아이템목록", description="모든 아이템의 효과와 등급을 확인합니다.")
    async def item_list(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🎒 아이템 도감", color=discord.Color.green())
        for name, info in ITEMS_INFO.items():
            embed.add_field(name=f"[{info['rarity']}] {name}", value=info['desc'], inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="알환전", description="하위 등급의 알 여러 개를 소모하여 상위 등급의 알을 얻습니다.")
    @app_commands.choices(목표등급=EXCHANGE_CHOICES)
    async def exchange_egg(self, interaction: discord.Interaction, 목표등급: str, 개수: int = 1):
        if 개수 <= 0: return await interaction.response.send_message("❌ 환전할 개수는 1개 이상이어야 합니다.", ephemeral=True)

        target_rarity = 목표등급.replace("급 알", "")
        cost_per_item = EGG_EXCHANGE_RATE[target_rarity]
        required_item = egg_item_name(prev_rarity(target_rarity))

        total_cost = cost_per_item * 개수
        success = await consume_item(interaction.user.id, required_item, total_cost)
        if not success: return await interaction.response.send_message(f"❌ `{required_item}`이(가) 부족합니다. (필요량: {total_cost}개)", ephemeral=True)

        await add_item(interaction.user.id, 목표등급, 개수)
        embed = discord.Embed(title="♻️ 알 환전 성공!", description=f"`{required_item}` {total_cost}개를 소모하여\n`{목표등급}` {개수}개를 획득했습니다!", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="알분해", description="상위 등급의 알을 분해하여 하위 등급의 알 여러 개를 얻습니다.")
    @app_commands.choices(분해할알=DECOMPOSE_CHOICES)
    async def reverse_exchange_egg(self, interaction: discord.Interaction, 분해할알: str, 개수: int = 1):
        if 개수 <= 0: return await interaction.response.send_message("❌ 분해할 개수는 1개 이상이어야 합니다.", ephemeral=True)

        src_rarity = 분해할알.replace("급 알", "")
        result_per_item = EGG_EXCHANGE_RATE[src_rarity]
        result_item = egg_item_name(prev_rarity(src_rarity))

        total_result = result_per_item * 개수
        success = await consume_item(interaction.user.id, 분해할알, 개수)
        if not success: return await interaction.response.send_message(f"❌ `{분해할알}`이(가) 부족합니다. (보유량이 {개수}개 미만입니다)", ephemeral=True)

        await add_item(interaction.user.id, result_item, total_result)
        embed = discord.Embed(title="🔨 알 분해(역환전) 성공!", description=f"`{분해할알}` {개수}개를 분해하여\n`{result_item}` {total_result}개를 획득했습니다!", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(InventoryCog(bot))
