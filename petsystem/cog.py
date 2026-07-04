import discord
from discord.ext import commands
from discord import app_commands
import random
from datetime import datetime, timedelta
import traceback

from .data import *
from .database import *
from .ui import create_status_embed, LegendActionView, ItemUseView
from utils.stats import get_points, spend_points, add_points

class PetSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        init_db()
        self.voice_sessions = {}

    async def get_debuffs(self, user_id, data):
        debuffs = []
        now_ts = int(datetime.now().timestamp())
        if data and data[2] > 0: # level > 0
            if (now_ts - data[10]) > 86400: debuffs.append("짜증") # last_fed
            if (now_ts - data[11]) > 86400: debuffs.append("질병") # last_cleaned
        return debuffs

    # --- Listeners for UI events ---
    @commands.Cog.listener()
    async def on_legend_action(self, interaction: discord.Interaction, action_type: str):
        user_id = interaction.user.id
        data = get_legend(user_id)
        debuffs = await self.get_debuffs(user_id, data)

        if action_type == "shower":
            cost = 20 if "질병" in debuffs else 10
            if get_points(user_id) < cost:
                return await interaction.response.send_message(f"비용이 부족합니다! (필요: {cost}P)", ephemeral=True)
            spend_points(user_id, cost)
            update_legend_specific(user_id, cleanliness=100, last_cleaned=int(datetime.now().timestamp()))
            await interaction.response.edit_message(embed=create_status_embed(interaction.user, get_legend(user_id), debuffs))
            await interaction.followup.send(f"뽀득뽀득! {cost}P를 사용하여 전설이를 씻겼습니다.", ephemeral=True)
        
        elif action_type == "feed":
            cost = 10 if "짜증" in debuffs else 5
            if get_points(user_id) < cost:
                return await interaction.response.send_message(f"비용이 부족합니다! (필요: {cost}P)", ephemeral=True)
            if data[5] >= 100: # fullness
                return await interaction.response.send_message("배가 불러서 더 이상 먹을 수 없어요!", ephemeral=True)
            spend_points(user_id, cost)
            update_legend_specific(user_id, fullness=min(data[5] + 20, 100), last_fed=int(datetime.now().timestamp()))
            await interaction.response.edit_message(embed=create_status_embed(interaction.user, get_legend(user_id), debuffs))
            await interaction.followup.send(f"냠냠! {cost}P를 사용하여 포만감을 20 채웠습니다.", ephemeral=True)

        elif action_type == "walk":
            if "짜증" in debuffs:
                return await interaction.followup.send("전설이가 짜증이 나서 산책에 응하지 않습니다...", ephemeral=True)
            # ... (산책 로직) ...
            gained_pts, lost_pts, drops = 0, 0, {rarity: 0 for rarity in SELL_PRICES.keys()}
            # ... (산책 결과 계산) ...
            add_user_item(user_id, "서사급 아이템", 1) # 예시
            await interaction.followup.send("산책 결과...", ephemeral=True)


    @commands.Cog.listener()
    async def on_legend_item_use(self, interaction: discord.Interaction, item_name: str):
        user_id = interaction.user.id
        # ... (아이템 사용 로직) ...
        remove_user_item(user_id, item_name, 1)
        await interaction.followup.send(f"{item_name}을(를) 사용했습니다!", ephemeral=True)

    # ... (기존 나머지 코드) ...

    @app_commands.command(name="전설이목록", description="게임에 등장하는 모든 전설이의 종류를 확인합니다.")
    async def pet_list(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🐾 전설이 도감", color=0x7289da)
        for rarity, pets in PET_POOLS.items():
            embed.add_field(name=f"**{rarity}**", value="- " + "\n- ".join(pets), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="아이템목록", description="게임에 등장하는 모든 아이템의 정보를 확인합니다.")
    async def item_list(self, interaction: discord.Interaction):
        embed = discord.Embed(title="💎 아이템 도감", color=0x7289da)
        for name, data in SHOP_ITEMS.items():
            embed.add_field(name=f"**{name}** ({data['rarity']})", value=data['description'], inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="판매", description="보유한 아이템을 판매하여 포인트를 얻습니다.")
    async def sell_item(self, interaction: discord.Interaction, 아이템: str):
        user_id = interaction.user.id
        user_items = dict(get_user_items(user_id))
        
        if 아이템 not in user_items or user_items[아이템] <= 0:
            return await interaction.response.send_message("해당 아이템을 보유하고 있지 않습니다.", ephemeral=True)
            
        item_rarity = SHOP_ITEMS.get(아이템, {}).get("rarity")
        if not item_rarity:
            return await interaction.response.send_message("알 수 없는 아이템입니다.", ephemeral=True)
            
        sell_price = SELL_PRICES[item_rarity]
        
        remove_user_item(user_id, 아이템, 1)
        add_points(user_id, sell_price)
        
        await interaction.response.send_message(f"`{아이템}` 1개를 판매하여 {sell_price}P를 얻었습니다!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PetSystemCog(bot))
