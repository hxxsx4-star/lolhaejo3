import discord
from discord.ext import commands
from discord import app_commands
import random
import time
from datetime import datetime

from .data import *
from .database import *
from .ui import LegendActionView, InventoryView, create_status_embed

class PetSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        init_db()
        self.voice_sessions = {}

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
        data = get_legend_data(member.id)
        if not data or data['level'] >= 3: return

        buffs = {b[0] for b in get_active_buffs(member.id)}
        exp_multiplier = 1
        if data['intimacy'] >= 80: exp_multiplier *= 2
        if "신비한 알약" in buffs: exp_multiplier *= 2 # 예시: 신비한 알약도 경험치 2배
        
        # 부스터 적용
        # ...

        data['exp'] += int(duration_sec / 60 * exp_multiplier)
        save_legend_data(member.id, data)

    @app_commands.command(name="상태창", description="내 전설이의 상태를 확인하고 돌봅니다.")
    async def status_window(self, interaction: discord.Interaction):
        data = get_legend_data(interaction.user.id)
        if not data:
            return await interaction.response.send_message("아직 전설이가 없습니다. `/알까기`로 시작하세요!", ephemeral=True)

        data, buffs, is_annoyed, is_diseased = evaluate_pet_status(interaction.user.id, data)
        user_points = get_user(interaction.user.id)[1]
        embed = create_status_embed(interaction.user, data, user_points, buffs, is_annoyed, is_diseased)
        view = LegendActionView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)
    
    # ... 여기에 나머지 모든 명령어를 추가 ...

async def setup(bot):
    await bot.add_cog(PetSystemCog(bot))
