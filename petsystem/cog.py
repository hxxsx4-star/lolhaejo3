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

    async def process_state_and_get_debuffs(self, user_id):
        data = get_legend(user_id)
        if not data: return None, []
        
        now_ts = int(datetime.now().timestamp())
        name, rarity, level, exp, fullness, intimacy, fatigue, cleanliness, last_updated, last_fed, last_cleaned = data
        
        elapsed_minutes = (now_ts - last_updated) // 60
        if elapsed_minutes > 0:
            fatigue = max(0, fatigue - elapsed_minutes)
            exp_multiplier = 2 if intimacy >= 80 else 1
            exp += int(elapsed_minutes * exp_multiplier)
            
            max_exp = EXP_TABLE[rarity].get(level, 1)
            if level < 3 and exp >= max_exp:
                level += 1
                exp = 0
                check_and_update_max_star(user_id, level)
            
            update_legend_specific(user_id, exp=exp, fatigue=fatigue)

        debuffs = []
        if level > 0:
            if (now_ts - last_fed) > 86400: debuffs.append("짜증")
            if (now_ts - last_cleaned) > 86400: debuffs.append("질병")
            
        return get_legend(user_id), debuffs

    @commands.Cog.listener()
    async def on_legend_action(self, interaction: discord.Interaction, action_type: str, count: int = None):
        user_id = interaction.user.id
        data, debuffs = await self.process_state_and_get_debuffs(user_id)
        if not data: return

        name, rarity, level, exp, fullness, intimacy, fatigue, cleanliness, _, _, _ = data

        if level == 0 and action_type != "hatch":
            return await interaction.followup.send("알 상태에서는 할 수 없는 행동입니다!", ephemeral=True)

        if action_type == "shower":
            cost = 20 if "질병" in debuffs else 10
            if get_points(user_id) < cost: return await interaction.followup.send(f"비용 부족! (필요: {cost}P)", ephemeral=True)
            spend_points(user_id, cost)
            update_legend_specific(user_id, cleanliness=100, last_cleaned=int(datetime.now().timestamp()))
            await interaction.message.edit(embed=create_status_embed(interaction.user, get_legend(user_id), await self.process_state_and_get_debuffs(user_id)[1], get_points(user_id)))
            await interaction.followup.send(f"뽀득뽀득! {cost}P로 전설이를 씻겼습니다.", ephemeral=True)

        elif action_type == "feed":
            cost = 10 if "짜증" in debuffs else 5
            if get_points(user_id) < cost: return await interaction.followup.send(f"비용 부족! (필요: {cost}P)", ephemeral=True)
            if fullness >= 100: return await interaction.followup.send("배가 너무 불러요!", ephemeral=True)
            spend_points(user_id, cost)
            update_legend_specific(user_id, fullness=min(fullness + 20, 100), last_fed=int(datetime.now().timestamp()))
            await interaction.message.edit(embed=create_status_embed(interaction.user, get_legend(user_id), await self.process_state_and_get_debuffs(user_id)[1], get_points(user_id)))
            await interaction.followup.send(f"냠냠! {cost}P로 포만감을 채웠습니다.", ephemeral=True)

        elif action_type == "walk":
            cost = count * 10
            if get_points(user_id) < cost: return await interaction.followup.send(f"산책 비용 부족! (필요: {cost}P)", ephemeral=True)
            if "짜증" in debuffs: return await interaction.followup.send("전설이가 짜증내서 산책을 거부합니다.", ephemeral=True)
            if fullness == 0: return await interaction.followup.send("배고파서 산책 갈 힘이 없어요.", ephemeral=True)
            
            spend_points(user_id, cost)
            
            gained_pts, lost_pts, drops = 0, 0, {}
            for _ in range(count):
                # 포인트 획득/손실
                # 아이템 드랍
                rand = random.uniform(0, 100)
                if rand < 0.01: r, i = "프레스티지", random.choice([k for k,v in SHOP_ITEMS.items() if v['rarity']=='프레스티지'])
                elif rand < 0.1: r, i = "신화", random.choice([k for k,v in SHOP_ITEMS.items() if v['rarity']=='신화'])
                elif rand < 1: r, i = "전설", random.choice([k for k,v in SHOP_ITEMS.items() if v['rarity']=='전설'])
                elif rand < 10: r, i = "서사", random.choice([k for k,v in SHOP_ITEMS.items() if v['rarity']=='서사'])
                else: continue
                drops[i] = drops.get(i, 0) + 1
                add_user_item(user_id, i)

            update_legend_specific(user_id, fatigue=min(fatigue + count, 100), intimacy=min(intimacy + count, 100))
            
            # 결과 전송
            # ...

    @app_commands.command(name="상태창", description="내 전설이의 상태를 확인하고 돌봅니다.")
    async def status_window(self, interaction: discord.Interaction):
        await interaction.response.defer()
        data, debuffs = await self.process_state_and_get_debuffs(interaction.user.id)
        if not data:
            return await interaction.followup.send("아직 전설이가 없습니다. `/알까기`로 시작해주세요.", ephemeral=True)
        
        embed = create_status_embed(interaction.user, data, debuffs, get_points(interaction.user.id))
        view = LegendActionView(self.bot, interaction.user.id, debuffs)
        await interaction.followup.send(embed=embed, view=view)

    # ... (나머지 모든 명령어들) ...

async def setup(bot):
    await bot.add_cog(PetSystemCog(bot))
