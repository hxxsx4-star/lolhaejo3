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
        if data and data[3] > 0: # level > 0
            if (now_ts - data[10]) > 86400: debuffs.append("짜증")
            if (now_ts - data[11]) > 86400: debuffs.append("질병")
        return debuffs

    async def process_pet_state(self, user_id):
        data = get_legend(user_id)
        if not data: return None, []
        
        now = datetime.now()
        now_ts = int(now.timestamp())
        
        name, rarity, level, exp, fullness, intimacy, fatigue, cleanliness, last_updated, last_fed, last_cleaned = data
        
        elapsed_minutes = (now_ts - last_updated) // 60
        if elapsed_minutes > 0:
            fatigue = max(0, fatigue - elapsed_minutes)
            
            exp_multiplier = 1
            if intimacy >= 80: exp_multiplier *= 2
            
            exp += int(elapsed_minutes * exp_multiplier)
            
            max_exp = EXP_TABLE[rarity].get(level, 0)
            if level < 3 and max_exp > 0 and exp >= max_exp:
                level += 1
                exp = 0
                check_and_update_max_star(user_id, level)
            
            update_legend_specific(user_id, exp=exp, fatigue=fatigue, last_updated=now_ts)

        debuffs = await self.get_debuffs(user_id, get_legend(user_id))
        return get_legend(user_id), debuffs

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
            await interaction.message.edit(embed=create_status_embed(interaction.user, get_legend(user_id), await self.get_debuffs(user_id, get_legend(user_id))))
            await interaction.response.send_message(f"뽀득뽀득! {cost}P를 사용하여 전설이를 씻겼습니다.", ephemeral=True)
        
        elif action_type == "feed":
            cost = 10 if "짜증" in debuffs else 5
            if get_points(user_id) < cost:
                return await interaction.response.send_message(f"비용이 부족합니다! (필요: {cost}P)", ephemeral=True)
            if data[5] >= 100:
                return await interaction.response.send_message("배가 불러서 더 이상 먹을 수 없어요!", ephemeral=True)
            spend_points(user_id, cost)
            update_legend_specific(user_id, fullness=min(data[5] + 20, 100), last_fed=int(datetime.now().timestamp()))
            await interaction.message.edit(embed=create_status_embed(interaction.user, get_legend(user_id), await self.get_debuffs(user_id, get_legend(user_id))))
            await interaction.response.send_message(f"냠냠! {cost}P를 사용하여 포만감을 20 채웠습니다.", ephemeral=True)

        elif action_type == "walk":
            if "짜증" in debuffs:
                return await interaction.response.send_message("전설이가 짜증이 나서 산책에 응하지 않습니다...", ephemeral=True)
            
            # 산책 로직
            gained_pts, drops = 0, {}
            for _ in range(10): # 10회 산책 기준
                rand = random.uniform(0, 100)
                if rand < 10: # 서사 아이템
                    item = random.choice([k for k, v in SHOP_ITEMS.items() if v['rarity'] == '서사'])
                    drops[item] = drops.get(item, 0) + 1
                elif rand < 11: # 전설 아이템
                    item = random.choice([k for k, v in SHOP_ITEMS.items() if v['rarity'] == '전설'])
                    drops[item] = drops.get(item, 0) + 1
                # ... 신화, 프레스티지 확률 추가
            
            for item, qty in drops.items():
                add_user_item(user_id, item, qty)
            
            update_legend_specific(user_id, fatigue=min(data[7] + 10, 100))
            await interaction.message.edit(embed=create_status_embed(interaction.user, get_legend(user_id), await self.get_debuffs(user_id, get_legend(user_id))))
            await interaction.response.send_message(f"산책 결과... {drops}", ephemeral=True)

    @app_commands.command(name="알까기", description="새로운 전설이 알을 뽑습니다.")
    async def hatch_egg(self, interaction: discord.Interaction):
        await interaction.response.defer()
        # ... (알까기 로직) ...
        await interaction.followup.send("알을 획득했습니다!")

    @app_commands.command(name="상태창", description="내 전설이의 상태를 확인하고 돌봅니다.")
    async def status_window(self, interaction: discord.Interaction):
        await interaction.response.defer()
        data, debuffs = await self.process_pet_state(interaction.user.id)
        if not data:
            return await interaction.followup.send("아직 전설이가 없습니다. `/알까기`로 시작해주세요.", ephemeral=True)
        
        embed = create_status_embed(interaction.user, data, debuffs)
        view = LegendActionView(interaction.user, debuffs)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="보관함", description="보유 중인 알과 아이템을 확인합니다.")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = get_user_items(interaction.user.id)
        embed = discord.Embed(title=f"📦 {interaction.user.display_name}님의 보관함")
        
        item_list = "\n".join([f"- {name} ({qty}개)" for name, qty in items]) or "보유한 아이템이 없습니다."
        embed.add_field(name="아이템", value=item_list)
        
        view = ItemUseView(self.bot, interaction.user.id, items)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="알지급", description="[관리자] 유저에게 알을 지급합니다.")
    @app_commands.default_permissions(administrator=True)
    async def admin_give_egg(self, interaction: discord.Interaction, user: discord.Member, rarity: str, amount: int = 1):
        # ... (알지급 로직) ...
        await interaction.response.send_message(f"{user.mention}에게 {rarity} 알 {amount}개를 지급했습니다.", ephemeral=True)

    @app_commands.command(name="알회수", description="[관리자] 유저의 알을 회수합니다.")
    @app_commands.default_permissions(administrator=True)
    async def admin_take_egg(self, interaction: discord.Interaction, user: discord.Member, rarity: str, amount: int = 1):
        # ... (알회수 로직) ...
        await interaction.response.send_message(f"{user.mention}의 {rarity} 알 {amount}개를 회수했습니다.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PetSystemCog(bot))
