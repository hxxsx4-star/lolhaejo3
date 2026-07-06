import discord
from discord.ext import commands
from discord import app_commands
import time
import traceback
import aiosqlite

from .data import PET_POOLS
from .database import get_or_migrate_data, save_legend_data, add_item, consume_item

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ 이 명령어를 사용할 수 있는 관리자 권한이 없습니다.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ 명령어를 처리하는 중 오류가 발생했습니다: {error}", ephemeral=True)

    @app_commands.command(name="알지급", description="[관리자] 유저에게 특정 종류의 알을 지급합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def give_egg(self, interaction: discord.Interaction, 유저: discord.Member, 알이름: str, 종류: str):
        await interaction.response.defer(ephemeral=True)
        try:
            wrapper = await get_or_migrate_data(유저.id)
            if 'pets' not in wrapper: wrapper['pets'] = []
            if len(wrapper['pets']) >= 5:
                return await interaction.followup.send(f"❌ {유저.display_name}님은 이미 5마리의 전설이를 보유하고 있습니다.")

            # 입력된 '종류'를 바탕으로 등급 탐색
            등급 = "서사"
            for r, pools in PET_POOLS.items():
                if 종류 in pools:
                    등급 = r
                    break

            new_pet_data = {
                'name': 알이름, 'type': 종류, 'rarity': 등급, 'level': 0, 'exp': 0, 'fullness': 100,
                'intimacy': 50, 'fatigue': 0, 'cleanliness': 100, 'walk_count': 0, 'total_walk_count': 0,
                'last_fatigue_calc': time.time()
            }
            wrapper['pets'].append(new_pet_data)
            if len(wrapper['pets']) == 1: wrapper['active_idx'] = 0

            await save_legend_data(유저.id, wrapper)
            await interaction.followup.send(f"✅ {유저.display_name}님에게 `{알이름}` ({등급} - {종류}) 알을 성공적으로 지급했습니다!")
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ 명령어를 처리하는 도중 오류가 발생했습니다.")

    @app_commands.command(name="알회수", description="[관리자] 특정 이름과 종류를 가진 유저의 전설이를 회수합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_egg(self, interaction: discord.Interaction, 유저: discord.Member, 알이름: str, 종류: str):
        await interaction.response.defer(ephemeral=True)
        try:
            wrapper = await get_or_migrate_data(유저.id)
            if not wrapper.get('pets'): return await interaction.followup.send("❌ 해당 유저는 보유한 전설이가 없습니다.")

            target_idx = -1
            for i, pet in enumerate(wrapper['pets']):
                if pet.get('name') == 알이름 and pet.get('type') == 종류:
                    target_idx = i
                    break

            if target_idx == -1:
                return await interaction.followup.send(f"❌ {유저.display_name}님의 전설이 중 이름이 `{알이름}`이고 종류가 `{종류}`인 펫을 찾을 수 없습니다.")

            removed = wrapper['pets'].pop(target_idx)
            wrapper['active_idx'] = max(0, len(wrapper['pets']) - 1)

            await save_legend_data(유저.id, wrapper)
            await interaction.followup.send(f"✅ {유저.display_name}님의 `{removed['name']} ({removed['type']})`(을)를 강제 회수했습니다.")
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ 오류가 발생했습니다.")

    @app_commands.command(name="아이템지급", description="[관리자] 유저에게 특정 아이템을 지급합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_add_item(self, interaction: discord.Interaction, 유저: discord.Member, 종류: str, 개수: int):
        if 개수 <= 0: return await interaction.response.send_message("개수는 1개 이상이어야 합니다.", ephemeral=True)
        await add_item(유저.id, 종류, 개수)
        await interaction.response.send_message(f"✅ {유저.display_name}님에게 `{종류}` {개수}개를 지급했습니다.", ephemeral=True)

    @app_commands.command(name="아이템회수", description="[관리자] 유저의 아이템을 회수합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_remove_item(self, interaction: discord.Interaction, 유저: discord.Member, 종류: str, 개수: int):
        if 개수 <= 0: return await interaction.response.send_message("개수는 1개 이상이어야 합니다.", ephemeral=True)
        success = await consume_item(유저.id, 종류, 개수)
        if success:
            await interaction.response.send_message(f"✅ {유저.display_name}님의 `{종류}` {개수}개를 회수했습니다.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {유저.display_name}님이 해당 아이템을 {개수}개만큼 보유하고 있지 않습니다.", ephemeral=True)

    @app_commands.command(name="아이템확인", description="[관리자] 유저의 보관함을 확인합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_check_item(self, interaction: discord.Interaction, 유저: discord.Member):
        async with aiosqlite.connect('legends.db') as db:
            async with db.execute("SELECT item_name, amount FROM user_items WHERE user_id = ? AND amount > 0", (유저.id,)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message(f"🎒 {유저.display_name}님의 보관함이 비어있습니다.", ephemeral=True)

        embed = discord.Embed(title=f"🎒 {유저.display_name}님의 보관함", color=discord.Color.purple())
        for item_name, amount in rows:
            embed.add_field(name=item_name, value=f"{amount}개", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="아이템초기화", description="[관리자] 유저의 모든 아이템을 영구 삭제합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_reset_item(self, interaction: discord.Interaction, 유저: discord.Member):
        async with aiosqlite.connect('legends.db') as db:
            await db.execute("DELETE FROM user_items WHERE user_id = ?", (유저.id,))
            await db.commit()
        await interaction.response.send_message(f"💥 {유저.display_name}님의 모든 아이템을 초기화했습니다.", ephemeral=True)

    @app_commands.command(name="강제부화", description="[관리자] 유저의 활성화된 알을 즉시 부화(1성)시킵니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
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

    @app_commands.command(name="성급상승", description="[관리자] 유저의 특정 전설이 성급을 1단계 올립니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def level_up_pet(self, interaction: discord.Interaction, 유저: discord.Member, 알이름: str):
        await interaction.response.defer(ephemeral=True)
        try:
            wrapper = await get_or_migrate_data(유저.id)
            if not wrapper.get('pets'): return await interaction.followup.send("❌ 해당 유저는 보유한 전설이가 없습니다.")

            target_idx = -1
            for i, pet in enumerate(wrapper['pets']):
                if pet.get('name') == 알이름:
                    target_idx = i
                    break

            if target_idx == -1:
                return await interaction.followup.send(f"❌ {유저.display_name}님의 전설이 중 이름이 `{알이름}`인 펫을 찾을 수 없습니다.")

            pet_data = wrapper['pets'][target_idx]
            if pet_data.get('level', 0) >= 3:
                return await interaction.followup.send(f"❌ `{알이름}`은(는) 이미 최대 성급(3성)입니다.")

            pet_data['level'] += 1
            pet_data['exp'] = 0
            wrapper['pets'][target_idx] = pet_data

            await save_legend_data(유저.id, wrapper)
            await interaction.followup.send(f"✅ {유저.display_name}님의 `{알이름}` 성급을 {pet_data['level']}성으로 상승시켰습니다!")
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ 오류가 발생했습니다.")

    @app_commands.command(name="성급하락", description="[관리자] 유저의 특정 전설이 성급을 1단계 내립니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def level_down_pet(self, interaction: discord.Interaction, 유저: discord.Member, 알이름: str):
        await interaction.response.defer(ephemeral=True)
        try:
            wrapper = await get_or_migrate_data(유저.id)
            if not wrapper.get('pets'): return await interaction.followup.send("❌ 해당 유저는 보유한 전설이가 없습니다.")

            target_idx = -1
            for i, pet in enumerate(wrapper['pets']):
                if pet.get('name') == 알이름:
                    target_idx = i
                    break

            if target_idx == -1:
                return await interaction.followup.send(f"❌ {유저.display_name}님의 전설이 중 이름이 `{알이름}`인 펫을 찾을 수 없습니다.")

            pet_data = wrapper['pets'][target_idx]
            if pet_data.get('level', 0) <= 0:
                return await interaction.followup.send(f"❌ `{알이름}`은(는) 이미 최하 성급(알, 0성)입니다.")

            pet_data['level'] -= 1
            pet_data['exp'] = 0
            wrapper['pets'][target_idx] = pet_data

            await save_legend_data(유저.id, wrapper)
            await interaction.followup.send(f"✅ {유저.display_name}님의 `{알이름}` 성급을 {pet_data['level']}성으로 하락시켰습니다!")
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ 오류가 발생했습니다.")

    @app_commands.command(name="이름변경", description="[관리자] 유저의 특정 전설이 이름을 변경합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_rename_pet(self, interaction: discord.Interaction, 유저: discord.Member, 알이름: str, 변경할이름: str):
        await interaction.response.defer(ephemeral=True)
        try:
            wrapper = await get_or_migrate_data(유저.id)
            if not wrapper.get('pets'): return await interaction.followup.send("❌ 해당 유저는 보유한 전설이가 없습니다.")

            target_idx = -1
            for i, pet in enumerate(wrapper['pets']):
                if pet.get('name') == 알이름:
                    target_idx = i
                    break

            if target_idx == -1:
                return await interaction.followup.send(f"❌ {유저.display_name}님의 전설이 중 이름이 `{알이름}`인 펫을 찾을 수 없습니다.")

            wrapper['pets'][target_idx]['name'] = 변경할이름

            await save_legend_data(유저.id, wrapper)
            await interaction.followup.send(f"✅ {유저.display_name}님의 전설이 이름을 `{알이름}`에서 `{변경할이름}`(으)로 변경했습니다!")
        except Exception:
            traceback.print_exc()
            await interaction.followup.send("❌ 오류가 발생했습니다.")

async def setup(bot):
    await bot.add_cog(AdminCog(bot))