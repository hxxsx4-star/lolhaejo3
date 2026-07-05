import discord
from discord.ext import commands
from discord import app_commands
import random
import time
import traceback

from .data import PET_POOLS
from .database import get_or_migrate_data, save_legend_data

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 💡 [추가됨] 권한 부족 시 오류를 잡아내서 깔끔하게 안내하는 핸들러
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ 이 명령어를 사용할 수 있는 관리자 권한이 없습니다.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ 명령어를 처리하는 중 오류가 발생했습니다: {error}", ephemeral=True)

    @app_commands.command(name="알지급", description="[관리자] 유저에게 특정 등급의 알을 지급합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True) # 💡 [추가됨] 강력한 권한 검사
    @app_commands.choices(등급=[
        app_commands.Choice(name="서사", value="서사"), app_commands.Choice(name="전설", value="전설"),
        app_commands.Choice(name="신화", value="신화"), app_commands.Choice(name="프레스티지", value="프레스티지")
    ])
    async def give_egg(self, interaction: discord.Interaction, 유저: discord.Member, 등급: str, 이름: str = "관리자지급알"):
        await interaction.response.defer(ephemeral=True)
        try:
            wrapper = await get_or_migrate_data(유저.id)
            if 'pets' not in wrapper: wrapper['pets'] = []
            if len(wrapper['pets']) >= 3:
                return await interaction.followup.send(f"❌ {유저.display_name}님은 이미 3마리의 전설이를 보유하고 있습니다.")

            pet_type = random.choice(PET_POOLS.get(등급, ["알 수 없음"]))
            new_pet_data = {
                'name': 이름, 'type': pet_type, 'rarity': 등급, 'level': 0, 'exp': 0, 'fullness': 100,
                'intimacy': 50, 'fatigue': 0, 'cleanliness': 100, 'walk_count': 0, 'total_walk_count': 0,
                'last_fatigue_calc': time.time()
            }
            wrapper['pets'].append(new_pet_data)
            if len(wrapper['pets']) == 1: wrapper['active_idx'] = 0

            await save_legend_data(유저.id, wrapper)
            await interaction.followup.send(f"✅ {유저.display_name}님에게 `{이름}` ({등급}) 알을 성공적으로 지급했습니다!")
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ 명령어를 처리하는 도중 오류가 발생했습니다.")

    @app_commands.command(name="알회수", description="[관리자] 유저의 활성화된 전설이를 회수(삭제)합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True) # 💡 [추가됨] 강력한 권한 검사
    async def remove_egg(self, interaction: discord.Interaction, 유저: discord.Member):
        await interaction.response.defer(ephemeral=True)
        try:
            wrapper = await get_or_migrate_data(유저.id)
            if not wrapper.get('pets'): return await interaction.followup.send("❌ 해당 유저는 보유한 전설이가 없습니다.")

            active_idx = wrapper.get('active_idx', 0)
            if active_idx >= len(wrapper['pets']): active_idx = 0

            removed = wrapper['pets'].pop(active_idx)
            removed_name = removed.get('name', '이름없음')
            removed_rarity = removed.get('rarity', '알수없음')
            wrapper['active_idx'] = max(0, len(wrapper['pets']) - 1)

            await save_legend_data(유저.id, wrapper)
            await interaction.followup.send(f"✅ {유저.display_name}님의 `{removed_name} ({removed_rarity})`(을)를 강제 회수했습니다.")
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ 오류가 발생했습니다.")

    @app_commands.command(name="강제부화", description="[관리자] 유저의 활성화된 알을 즉시 부화(1성)시킵니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True) # 💡 [추가됨] 강력한 권한 검사
    async def force_hatch_cmd(self, interaction: discord.Interaction, 유저: discord.Member):
        await interaction.response.defer(ephemeral=True)
        try:
            wrapper = await get_or_migrate_data(유저.id)
            if not wrapper.get('pets'): return await interaction.followup.send("❌ 해당 유저는 보유한 전설이가 없습니다.")

            active_idx = wrapper.get('active_idx', 0)
            if active_idx >= len(wrapper['pets']): active_idx = 0

            data = wrapper['pets'][active_idx]
            pet_name = data.get('name', '이름없음')
            if data.get('level', 0) > 0:
                return await interaction.followup.send(f"해당 펫(`{pet_name}`)은 이미 부화한 상태입니다.")

            data['level'] = 1; data['exp'] = 0
            wrapper['pets'][active_idx] = data
            await save_legend_data(유저.id, wrapper)
            await interaction.followup.send(f"✅ {유저.display_name}님의 알(`{pet_name}`)을 강제로 부화시켰습니다!")
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ 오류가 발생했습니다.")

async def setup(bot):
    await bot.add_cog(AdminCog(bot))