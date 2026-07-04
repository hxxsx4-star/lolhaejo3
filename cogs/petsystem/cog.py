import discord
from discord.ext import commands
from discord import app_commands
import random
import time
from datetime import datetime
import aiosqlite

from .data import *
from .database import *
from .ui import create_status_embed, LegendActionView, InventoryView

class PetSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_sessions = {}

    async def evaluate_pet_status(self, user_id, data):
        if not data or data['level'] == 0:
            return data, [], False, False

        now = time.time()
        active_buffs = await get_active_buffs(user_id)
        buffs = {b[0] for b in active_buffs}

        if "신비한 알약" in buffs:
            data['fullness'] = 100
            data['fatigue'] = 0
            data['intimacy'] = 100
            data['cleanliness'] = 100
        else:
            if "배부름을 부르는 약" in buffs: data['fullness'] = 100
            if "쌩쌩한약" in buffs: data['fatigue'] = 0
            if "트위치 나가라약" in buffs: data['cleanliness'] = 100
            if "아무무도 인싸로 만드는 약" in buffs: data['intimacy'] = 100

        if data['fullness'] <= 20:
            if data['low_full_since'] == 0: data['low_full_since'] = now
        else:
            data['low_full_since'] = 0

        if data.get('cleanliness', 100) <= 20:
            if data.get('low_clean_since', 0) == 0: data['low_clean_since'] = now
        else:
            data['low_clean_since'] = 0

        is_annoyed = (data['low_full_since'] > 0 and now - data['low_full_since'] >= 86400)
        is_diseased = (data.get('low_clean_since', 0) > 0 and now - data['low_clean_since'] >= 86400)

        await save_legend_data(user_id, data)
        return data, buffs, is_annoyed, is_diseased

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        if before.channel is None and after.channel is not None:
            self.voice_sessions[member.id] = time.time()
        elif before.channel is not None and after.channel is None:
            if member.id in self.voice_sessions:
                duration_sec = time.time() - self.voice_sessions.pop(member.id)
                await self.add_exp_to_pet(member, duration_sec)

    async def add_exp_to_pet(self, member, duration_sec):
        data = await get_legend_data(member.id)
        if not data or data['level'] >= 3: return

        active_buffs = await get_active_buffs(member.id)
        buffs = {b[0] for b in active_buffs}

        exp_multiplier = 1
        if data['intimacy'] >= 80: exp_multiplier *= 2

        data['exp'] += int(duration_sec / 60 * exp_multiplier)
        await save_legend_data(member.id, data)

    @app_commands.command(name="알까기", description="새로운 전설이 알을 뽑습니다.")
    async def hatch_egg(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_data = await get_user(user_id)
        current_pet = await get_legend_data(user_id)
        is_first_time = (user_data[2] == 0 and not current_pet)

        if current_pet and user_data[2] < 3:
            return await interaction.response.send_message("아직 현재 전설이를 3성으로 키우지 못했습니다! 3성 달성 후 가챠가 해금됩니다.", ephemeral=True)

        cost = 0 if is_first_time else 1000
        if not is_first_time and user_data[1] < cost:
            return await interaction.response.send_message(f"가챠 비용이 부족합니다! (필요: {cost}P)", ephemeral=True)

        if not is_first_time: await update_user_points(user_id, -cost)

        rarity = "서사" if is_first_time else random.choices(list(PET_POOLS.keys()), weights=[85, 14, 0.9, 0.1], k=1)[0]
        new_pet_name = random.choice(PET_POOLS[rarity])

        new_pet_data = {'name': new_pet_name, 'rarity': rarity, 'level': 0, 'exp': 0, 'fullness': 100, 'intimacy': 50, 'fatigue': 0, 'cleanliness': 100}
        await save_legend_data(user_id, new_pet_data)

        await interaction.response.send_message(f"🥚 신비로운 [{rarity}급] 알을 얻었습니다! `/상태창`으로 확인하세요.", ephemeral=True)

    @app_commands.command(name="상태창", description="내 전설이의 상태를 확인하고 돌봅니다.")
    async def status_window(self, interaction: discord.Interaction):
        data = await get_legend_data(interaction.user.id)
        if not data:
            return await interaction.response.send_message("아직 전설이가 없습니다. `/알까기`로 시작하세요!", ephemeral=True)

        data, buffs, is_annoyed, is_diseased = await self.evaluate_pet_status(interaction.user.id, data)
        user_info = await get_user(interaction.user.id)
        user_points = user_info[1]

        embed = create_status_embed(interaction.user, data, user_points, buffs, is_annoyed, is_diseased)
        view = LegendActionView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="보관함", description="내 아이템을 확인하고 사용합니다.")
    async def inventory(self, interaction: discord.Interaction):
        async with aiosqlite.connect('legends.db') as db:
            async with db.execute("SELECT item_name, amount FROM user_items WHERE user_id = ? AND amount > 0", (interaction.user.id,)) as cursor:
                rows = await cursor.fetchall()
        items = dict(rows)

        if not items:
            return await interaction.response.send_message("보관함이 비어있습니다.", ephemeral=True)

        view = InventoryView(interaction.user.id, items)
        await interaction.response.send_message("사용할 아이템을 선택하세요:", view=view, ephemeral=True)

    @app_commands.command(name="판매", description="보유중인 아이템을 판매하여 포인트를 얻습니다.")
    async def sell_item(self, interaction: discord.Interaction, 아이템: str):
        if 아이템 not in ITEMS_INFO:
            return await interaction.response.send_message("존재하지 않는 아이템입니다.", ephemeral=True)

        success = await consume_item(interaction.user.id, 아이템, 1)
        if success:
            price = ITEM_PRICES[ITEMS_INFO[아이템]["rarity"]]
            await update_user_points(interaction.user.id, price)
            await interaction.response.send_message(f"✅ `{아이템}` 1개를 판매하여 {price}P를 획득했습니다!", ephemeral=True)
        else:
            await interaction.response.send_message("해당 아이템을 보유하고 있지 않습니다.", ephemeral=True)

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

async def setup(bot):
    await bot.add_cog(PetSystemCog(bot))