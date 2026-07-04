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
        if not data: return await interaction.followup.send("펫이 없습니다.", ephemeral=True)

        name, rarity, level, exp, fullness, intimacy, fatigue, cleanliness, _, _, _ = data

        if level == 0:
            return await interaction.followup.send("알 상태에서는 할 수 없는 행동입니다!", ephemeral=True)

        try:
            if action_type == "shower":
                cost = 20 if "질병" in debuffs else 10
                if get_points(user_id) < cost: return await interaction.followup.send(f"비용 부족! (필요: {cost}P)", ephemeral=True)
                spend_points(user_id, cost)
                update_legend_specific(user_id, cleanliness=100, last_cleaned=int(datetime.now().timestamp()))
                await interaction.message.edit(embed=create_status_embed(interaction.user, get_legend(user_id), [], get_points(user_id)))
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
                
                drops = {}
                for _ in range(count):
                    rand = random.uniform(0, 100)
                    if rand < 0.01: r, i = "프레스티지", random.choice([k for k,v in SHOP_ITEMS.items() if v['rarity']=='프레스티지'])
                    elif rand < 0.1: r, i = "신화", random.choice([k for k,v in SHOP_ITEMS.items() if v['rarity']=='신화'])
                    elif rand < 1: r, i = "전설", random.choice([k for k,v in SHOP_ITEMS.items() if v['rarity']=='전설'])
                    elif rand < 10: r, i = "서사", random.choice([k for k,v in SHOP_ITEMS.items() if v['rarity']=='서사'])
                    else: continue
                    drops[i] = drops.get(i, 0) + 1
                    add_user_item(user_id, i)

                update_legend_specific(user_id, fatigue=min(fatigue + count, 100), intimacy=min(intimacy + count, 100))
                
                drop_text = "\n".join([f"- {item} {qty}개" for item, qty in drops.items()]) or "아무것도 줍지 못했습니다."
                result_embed = discord.Embed(title=f"🚶 {count}회 산책 완료", color=discord.Color.green())
                result_embed.add_field(name="🎁 획득한 아이템", value=drop_text, inline=False)
                await interaction.followup.send(embed=result_embed, ephemeral=True)
                await interaction.message.edit(embed=create_status_embed(interaction.user, get_legend(user_id), await self.process_state_and_get_debuffs(user_id)[1], get_points(user_id)))

        except Exception:
            await interaction.followup.send(f"오류 발생!\n```py\n{traceback.format_exc()}\n```", ephemeral=True)

    @app_commands.command(name="상태창", description="내 전설이의 상태를 확인하고 돌봅니다.")
    async def status_window(self, interaction: discord.Interaction):
        await interaction.response.defer()
        data, debuffs = await self.process_state_and_get_debuffs(interaction.user.id)
        if not data:
            return await interaction.followup.send("아직 전설이가 없습니다. `/알까기`로 시작해주세요.", ephemeral=True)
        
        embed = create_status_embed(interaction.user, data, debuffs, get_points(interaction.user.id))
        view = LegendActionView(self.bot, interaction.user.id, debuffs)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="보관함", description="보유 중인 알과 아이템을 확인합니다.")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        user_pet_data = get_user_pet_data(user_id)
        items = get_user_items(user_id)
        
        embed = discord.Embed(title=f"📦 {interaction.user.display_name}님의 보관함")
        
        egg_desc = f"🟥 전설급 알: **{user_pet_data[2]}**개\n🟨 신화급 알: **{user_pet_data[3]}**개\n⬛ 프레스티지급 알: **{user_pet_data[4]}**개"
        embed.add_field(name="🥚 보유 알", value=egg_desc, inline=False)
        
        item_desc = "\n".join([f"- {name} ({qty}개)" for name, qty in items]) or "보유 아이템 없음"
        embed.add_field(name="💎 보유 아이템", value=item_desc, inline=False)
        
        view = ItemUseView(self.bot, user_id, items)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="판매", description="보유한 아이템을 판매하여 포인트를 얻습니다.")
    @app_commands.autocomplete(아이템=[app_commands.Choice(name=i, value=i) for i in SHOP_ITEMS.keys()])
    async def sell_item(self, interaction: discord.Interaction, 아이템: str):
        user_id = interaction.user.id
        user_items = dict(get_user_items(user_id))
        
        if 아이템 not in user_items or user_items[아이템] <= 0:
            return await interaction.response.send_message("해당 아이템을 보유하고 있지 않습니다.", ephemeral=True)
            
        item_rarity = SHOP_ITEMS.get(아이템, {}).get("rarity")
        if not item_rarity: return await interaction.response.send_message("알 수 없는 아이템입니다.", ephemeral=True)
            
        sell_price = SELL_PRICES[item_rarity]
        remove_user_item(user_id, 아이템, 1)
        add_points(user_id, sell_price)
        
        await interaction.response.send_message(f"`{아이템}` 1개를 판매하여 {sell_price}P를 얻었습니다!", ephemeral=True)

    # ... (다른 모든 명령어들) ...

async def setup(bot):
    await bot.add_cog(PetSystemCog(bot))
