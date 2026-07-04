import discord
from discord.ext import commands
from discord import app_commands
import random
from datetime import datetime

# 분리된 파일들에서 필요한 모든 것을 가져옵니다.
from .data import PET_POOLS, EXP_TABLE
from .database import init_db, get_user_pet_data, get_legend, save_legend, check_and_update_max_star, update_user_egg
from .ui import create_status_embed, LegendActionView
from utils.stats import get_points, spend_points

# ==========================================
# Cog 클래스 (메인 시스템)
# ==========================================
class PetSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        init_db()
        self.voice_sessions = {}

    # --- 패시브 로직 ---
    async def apply_passive_changes(self, user_id):
        data = get_legend(user_id)
        if not data: return None
        name, rarity, level, exp, fullness, intimacy, fatigue, last_updated = data
        if level >= 3: return data

        now_ts = int(datetime.now().timestamp())
        elapsed_minutes = (now_ts - last_updated) // 60
        if elapsed_minutes <= 0: return data

        new_fatigue = max(0, fatigue - elapsed_minutes)
        new_exp = exp + elapsed_minutes
        new_level = level
        level_ups = []
        max_exp = EXP_TABLE[rarity].get(new_level, 0)

        while new_level < 3 and max_exp > 0 and new_exp >= max_exp:
            new_exp -= max_exp
            new_level += 1
            level_ups.append(new_level)
            max_exp = EXP_TABLE[rarity].get(new_level, 0)
            if new_level == 3: new_exp = 0; break
        
        save_legend(user_id, name, rarity, new_level, new_exp, fullness, intimacy, new_fatigue)
        
        if level_ups:
            check_and_update_max_star(user_id, new_level)
            try:
                user = await self.bot.fetch_user(user_id)
                msg = f"🎉 앗! 알에서 빛이 납니다...\n알을 깨고 1성 {name}(이)가 성공적으로 부화했습니다!" if 1 in level_ups else f"🎉 축하합니다! {name}의 모습이... {new_level}성으로 진화했습니다!"
                await user.send(msg)
            except: pass
        
        return get_legend(user_id)

    # --- 음성 채널 경험치 로직 ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        if before.channel is None and after.channel is not None:
            self.voice_sessions[member.id] = datetime.now()
        elif before.channel is not None and after.channel is None:
            if member.id in self.voice_sessions:
                duration = datetime.now() - self.voice_sessions.pop(member.id)
                minutes = int(duration.total_seconds() // 60)
                if minutes > 0: await self.add_exp_to_pet(member, minutes)

    async def add_exp_to_pet(self, member, gained_exp):
        await self.apply_passive_changes(member.id)
        data = get_legend(member.id)
        if not data: return
        name, rarity, level, exp, fullness, intimacy, fatigue, _ = data
        if level >= 3: return

        max_exp = EXP_TABLE[rarity][level]
        new_exp = exp + gained_exp
        new_level = level
        level_ups = []
        while new_level < 3 and max_exp > 0 and new_exp >= max_exp:
            new_exp -= max_exp
            new_level += 1
            level_ups.append(new_level)
            max_exp = EXP_TABLE[rarity].get(new_level, 0)
            if new_level == 3: new_exp = 0; break
        
        save_legend(member.id, name, rarity, new_level, new_exp, fullness, intimacy, fatigue)
        if level_ups:
            check_and_update_max_star(member.id, new_level)
            try:
                msg = f"🎉 앗! 알에서 빛이 납니다...\n알을 깨고 1성 {name}(이)가 성공적으로 부화했습니다!" if 1 in level_ups else f"🎉 축하합니다! 통화방 활동으로 인해 {name}의 모습이... {new_level}성으로 진화했습니다!"
                await member.send(msg)
            except: pass

    # --- 슬래시 커맨드 ---
    @app_commands.command(name="알까기", description="새로운 전설이 알을 뽑습니다.")
    async def hatch_egg(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False) # 3초 응답 제한 해제

        user_id = interaction.user.id
        user_pet_data = get_user_pet_data(user_id)
        current_pet = get_legend(user_id)
        is_first_time = user_pet_data[1] == 0 and not current_pet
        can_gacha = user_pet_data[1] == 3
        if current_pet and not can_gacha:
            await interaction.followup.send("아직 현재 전설이를 3성으로 키우지 못했습니다! 3성 달성 후 가챠가 해금됩니다.", ephemeral=True)
            return
        cost = 0 if is_first_time else 1000
        if not is_first_time and get_points(user_id) < cost:
            await interaction.followup.send(f"가챠 비용이 부족합니다! (필요: {cost}P / 보유: {get_points(user_id)}P)", ephemeral=True)
            return
        if not is_first_time: spend_points(user_id, cost)

        rand = random.uniform(0, 100)
        if is_first_time or rand < 85.0: rarity = "서사"
        elif rand < 99.0: rarity = "전설"
        elif rand < 99.9: rarity = "신화"
        else: rarity = "프레스티지"
        new_pet = random.choice(PET_POOLS[rarity])
        save_legend(user_id, new_pet, rarity, 0, 0, 50, 0, 0)
        rarity_map = {"서사": "🟪 [서사급] 기운이 느껴집니다...", "전설": "🟥 [전설급] 엄청난 기운이 느껴집니다...", "신화": "🟨 [신화급] 범상치 않은 기운이 뿜어져 나옵니다!", "프레스티지": "⬛ [프레스티지급] 전설적인 아우라가 느껴집니다!!"}
        msg = f"🥚 신비로운 알을 얻었습니다!\n\n{rarity_map[rarity]}\n\n통화방 활동을 통해 100XP를 모아 알을 부화시켜주세요!"
        await interaction.followup.send(msg)

    @app_commands.command(name="상태창", description="내 전설이의 상태를 확인하고 돌봅니다.")
    async def status_window(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False) # 3초 응답 제한 해제

        data = await self.apply_passive_changes(interaction.user.id)
        if not data:
            await interaction.followup.send("아직 전설이가 없습니다. `/알까기` 명령어로 알을 먼저 받아주세요!", ephemeral=True)
            return
        
        embed = create_status_embed(interaction.user, data)
        view = LegendActionView(interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="보관함", description="보유 중인 알과 아이템을 확인합니다.")
    async def inventory(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_pet_data = get_user_pet_data(user_id)
        
        legendary_eggs = user_pet_data[2]
        mythic_eggs = user_pet_data[3]
        prestige_eggs = user_pet_data[4]
        
        embed = discord.Embed(title=f"📦 {interaction.user.display_name}님의 보관함", color=discord.Color.dark_gold())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        egg_description = (f"🟥 전설급 알: **{legendary_eggs}**개\n"
                         f"🟨 신화급 알: **{mythic_eggs}**개\n"
                         f"⬛ 프레스티지급 알: **{prestige_eggs}**개")
        
        embed.add_field(name="🥚 보유 중인 알", value=egg_description, inline=False)
        embed.add_field(name="💎 기타 아이템", value="보유 중인 아이템이 없습니다.", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ... (관리자 명령어들은 변경 없음) ...
    @app_commands.command(name="알지급", description="[관리자 전용] 유저에게 특수 알을 지급합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(rarity=[
        app_commands.Choice(name="전설급", value="전설"),
        app_commands.Choice(name="신화급", value="신화"),
        app_commands.Choice(name="프레스티지급", value="프레스티지")
    ])
    async def admin_give_egg(self, interaction: discord.Interaction, user: discord.Member, rarity: app_commands.Choice[str], amount: int = 1):
        get_user_pet_data(user.id)
        update_user_egg(user.id, rarity.value, amount)
        await interaction.response.send_message(f"✅ 관리자 권한으로 {user.display_name}님에게 {rarity.name} 알을 {amount}개 지급했습니다.", ephemeral=True)

    @app_commands.command(name="알회수", description="[관리자 전용] 유저의 특수 알을 회수합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(rarity=[
        app_commands.Choice(name="전설급", value="전설"),
        app_commands.Choice(name="신화급", value="신화"),
        app_commands.Choice(name="프레스티지급", value="프레스티지")
    ])
    async def admin_take_egg(self, interaction: discord.Interaction, user: discord.Member, rarity: app_commands.Choice[str], amount: int = 1):
        get_user_pet_data(user.id)
        update_user_egg(user.id, rarity.value, -amount)
        await interaction.response.send_message(f"✅ 관리자 권한으로 {user.display_name}님의 {rarity.name} 알을 {amount}개 회수했습니다.", ephemeral=True)

    @app_commands.command(name="강제부화", description="[관리자 전용] 유저의 알을 즉시 부화시킵니다.")
    @app_commands.default_permissions(administrator=True)
    async def admin_force_hatch(self, interaction: discord.Interaction, user: discord.Member):
        data = get_legend(user.id)
        if not data:
            return await interaction.response.send_message(f"❌ {user.display_name}님은 알 또는 전설이를 가지고 있지 않습니다.", ephemeral=True)
        
        name, rarity, level, exp, fullness, intimacy, fatigue, _ = data
        if level != 0:
            return await interaction.response.send_message(f"❌ {user.display_name}님의 전설이는 이미 부화한 상태입니다.", ephemeral=True)
            
        save_legend(user.id, name, rarity, 1, 0, fullness, intimacy, fatigue)
        check_and_update_max_star(user.id, 1)
        
        await interaction.response.send_message(f"✅ 관리자 권한으로 {user.display_name}님의 알을 강제로 부화시켜 **1성 {name}** (으)로 만들었습니다.", ephemeral=True)
        try:
            await user.send(f"🎉 관리자에 의해 당신의 알이 강제로 부화하여 **1성 {name}**(이)가 되었습니다!")
        except:
            pass

async def setup(bot):
    await bot.add_cog(PetSystemCog(bot))
