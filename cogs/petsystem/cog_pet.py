import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import time
from datetime import datetime
import aiosqlite

from .data import PET_POOLS
from .database import get_or_migrate_data, get_active_buffs, save_legend_data, get_user, update_max_star
from .ui_action import create_status_embed, LegendActionView
from .logs import HATCH_LOG_CH, send_log_embed

# 💡 최상단에 utils.stats 연동
from utils.stats import get_points, add_points

class PetSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_sessions = {}
        self.bot.loop.create_task(self.init_voice_sessions())
        self.voice_exp_loop.start()

    async def init_voice_sessions(self):
        await self.bot.wait_until_ready()
        now = time.time()
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        self.voice_sessions[member.id] = now

    def cog_unload(self):
        self.voice_exp_loop.cancel()

    @tasks.loop(seconds=60)
    async def voice_exp_loop(self):
        now = time.time()
        for user_id, last_reward_time in list(self.voice_sessions.items()):
            elapsed = now - last_reward_time
            if elapsed >= 60:
                minutes_passed = int(elapsed // 60)
                self.voice_sessions[user_id] = last_reward_time + (minutes_passed * 60)
                await self.add_exp_to_pet(user_id, minutes_passed * 60)

    async def evaluate_pet_status(self, user_id, wrapper):
        if not wrapper['pets']: return None, [], False, False
        data = wrapper['pets'][wrapper['active_idx']]
        if data.get('level', 0) == 0: return data, [], False, False

        now = time.time()
        active_buffs = await get_active_buffs(user_id)
        buffs = {b[0] for b in active_buffs}
        last_calc = data.get('last_fatigue_calc', now)
        elapsed_minutes = int((now - last_calc) // 60)

        if elapsed_minutes > 0:
            fatigue_drop = elapsed_minutes * 20
            data['fatigue'] = max(0, data.get('fatigue', 0) - fatigue_drop)
            data['last_fatigue_calc'] = last_calc + (elapsed_minutes * 60)
        elif 'last_fatigue_calc' not in data:
            data['last_fatigue_calc'] = now

        if "신비한 알약" in buffs:
            data['fullness'] = 100; data['fatigue'] = 0; data['intimacy'] = 100; data['cleanliness'] = 100
        else:
            if "배부름을 부르는 약" in buffs: data['fullness'] = 100
            if "쌩쌩한약" in buffs: data['fatigue'] = 0
            if "트위치 나가라약" in buffs: data['cleanliness'] = 100
            if "아무무도 인싸로 만드는 약" in buffs: data['intimacy'] = 100

        if data.get('fullness', 100) <= 20:
            if data.get('low_full_since', 0) == 0: data['low_full_since'] = now
        else: data['low_full_since'] = 0

        if data.get('cleanliness', 100) <= 20:
            if data.get('low_clean_since', 0) == 0: data['low_clean_since'] = now
        else: data['low_clean_since'] = 0

        is_annoyed = (data.get('low_full_since', 0) > 0 and now - data['low_full_since'] >= 86400)
        is_diseased = (data.get('low_clean_since', 0) > 0 and now - data['low_clean_since'] >= 86400)

        wrapper['pets'][wrapper['active_idx']] = data
        await save_legend_data(user_id, wrapper)
        return data, buffs, is_annoyed, is_diseased

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        if before.channel is None and after.channel is not None:
            self.voice_sessions[member.id] = time.time()
        elif before.channel is not None and after.channel is None:
            if member.id in self.voice_sessions:
                last_reward_time = self.voice_sessions.pop(member.id)
                duration_sec = time.time() - last_reward_time
                if duration_sec >= 60:
                    await self.add_exp_to_pet(member.id, duration_sec)

    async def add_exp_to_pet(self, user_id, duration_sec):
        wrapper = await get_or_migrate_data(user_id)
        if not wrapper.get('pets'): return
        active_idx = wrapper.get('active_idx', 0)

        if active_idx >= len(wrapper['pets']):
            active_idx = 0; wrapper['active_idx'] = active_idx

        data = wrapper['pets'][active_idx]
        if data.get('level', 0) >= 3: return

        active_buffs = await get_active_buffs(user_id)
        buffs = {b[0]: b for b in active_buffs}

        exp_multiplier = 1
        if data.get('intimacy', 0) >= 80: exp_multiplier *= 2

        used_booster = None
        if "경험치 부스터 X10" in buffs: exp_multiplier *= 10; used_booster = "경험치 부스터 X10"
        elif "경험치 부스터 X5" in buffs: exp_multiplier *= 5; used_booster = "경험치 부스터 X5"
        elif "경험치 부스터 X2" in buffs: exp_multiplier *= 2; used_booster = "경험치 부스터 X2"

        earned_exp = int(duration_sec / 60 * exp_multiplier)
        if earned_exp <= 0: return

        data['exp'] = data.get('exp', 0) + earned_exp

        if used_booster:
            vc_seconds_left = buffs[used_booster][2]
            new_vc_seconds = vc_seconds_left - duration_sec
            async with aiosqlite.connect('legends.db') as db:
                if new_vc_seconds <= 0:
                    await db.execute("DELETE FROM active_buffs WHERE user_id = ? AND buff_name = ?", (user_id, used_booster))
                else:
                    await db.execute("UPDATE active_buffs SET vc_seconds_left = ? WHERE user_id = ? AND buff_name = ?", (new_vc_seconds, user_id, used_booster))
                await db.commit()

        rarity = data.get('rarity', '서사')
        EXP_REQUIREMENTS = {
            0: 100,
            1: {"서사": 5000, "전설": 10000, "신화": 20000, "프레스티지": 30000},
            2: {"서사": 10000, "전설": 20000, "신화": 40000, "프레스티지": 70000}
        }

        while data.get('level', 0) < 3:
            current_level = data.get('level', 0)
            if current_level == 0: required_exp = EXP_REQUIREMENTS[0]
            else: required_exp = EXP_REQUIREMENTS[current_level].get(rarity, EXP_REQUIREMENTS[current_level]["서사"])

            if data.get('exp', 0) >= required_exp:
                data['level'] = current_level + 1
                data['exp'] -= required_exp
            else: break

        if data.get('level', 0) >= 3:
            await update_max_star(user_id, 3)

        wrapper['pets'][active_idx] = data
        await save_legend_data(user_id, wrapper)

    @app_commands.command(name="알까기", description="새로운 전설이 알을 뽑고 이름을 지어줍니다.")
    async def hatch_egg(self, interaction: discord.Interaction, 이름: str):
        user_id = interaction.user.id
        user_data = await get_user(user_id)
        wrapper = await get_or_migrate_data(user_id)

        is_first_time = (len(wrapper.get('pets', [])) == 0)

        if not is_first_time:
            if user_data[2] < 3:
                return await interaction.response.send_message("아직 첫 전설이를 3성으로 키우지 못했습니다! 3성 달성 후 추가 가챠가 해금됩니다.", ephemeral=True)
            if len(wrapper['pets']) >= 3:
                return await interaction.response.send_message("전설이는 최대 3마리까지만 키울 수 있습니다!", ephemeral=True)

        current_points = await get_points(user_id) # 💡 연동
        cost = 0 if is_first_time else 1000

        if current_points < cost:
            return await interaction.response.send_message(f"가챠 비용이 부족합니다! (필요: {cost}P)", ephemeral=True)

        if not is_first_time: await add_points(user_id, -cost) # 💡 연동

        rarity = "서사" if is_first_time else random.choices(list(PET_POOLS.keys()), weights=[85, 14, 0.9, 0.1], k=1)[0]
        pet_type = random.choice(PET_POOLS[rarity])

        new_pet_data = {
            'name': 이름, 'type': pet_type, 'rarity': rarity, 'level': 0, 'exp': 0, 'fullness': 100,
            'intimacy': 50, 'fatigue': 0, 'cleanliness': 100, 'walk_count': 0, 'total_walk_count': 0,
            'last_fatigue_calc': time.time()
        }

        if 'pets' not in wrapper: wrapper['pets'] = []
        wrapper['pets'].append(new_pet_data)
        wrapper['active_idx'] = len(wrapper['pets']) - 1
        await save_legend_data(user_id, wrapper)

        await interaction.response.send_message(f"🥚 신비로운 [{rarity}급] 알을 얻었습니다! (이름: {이름})\n`/상태창`으로 확인하세요.", ephemeral=True)
        await send_log_embed(interaction.client, HATCH_LOG_CH, "🥚 알까기 로그", f"{이름} ({pet_type} - {rarity}급) 부화 완료!\n💸 소모 비용: {cost}P", interaction.user, discord.Color.purple())

    @app_commands.command(name="펫교체", description="돌볼 전설이를 교체합니다.")
    @app_commands.choices(슬롯=[app_commands.Choice(name="1번 펫", value=0), app_commands.Choice(name="2번 펫", value=1), app_commands.Choice(name="3번 펫", value=2)])
    async def switch_pet(self, interaction: discord.Interaction, 슬롯: int):
        wrapper = await get_or_migrate_data(interaction.user.id)
        if 슬롯 >= len(wrapper.get('pets', [])):
            return await interaction.response.send_message(f"해당 슬롯에는 아직 전설이가 없습니다. (보유 중인 펫: {len(wrapper.get('pets', []))}마리)", ephemeral=True)

        wrapper['active_idx'] = 슬롯
        await save_legend_data(interaction.user.id, wrapper)
        pet_name = wrapper['pets'][슬롯].get('name', '이름없음')
        await interaction.response.send_message(f"🔄 지금부터 `{pet_name}`(을)를 돌봅니다! `/상태창`을 확인하세요.", ephemeral=True)

    @app_commands.command(name="상태창", description="내 전설이의 상태를 확인하고 돌봅니다.")
    async def status_window(self, interaction: discord.Interaction):
        wrapper = await get_or_migrate_data(interaction.user.id)
        if not wrapper.get('pets'): return await interaction.response.send_message("아직 전설이가 없습니다. `/알까기`로 시작하세요!", ephemeral=True)

        data, buffs, is_annoyed, is_diseased = await self.evaluate_pet_status(interaction.user.id, wrapper)
        current_points = await get_points(interaction.user.id) # 💡 연동

        embed = create_status_embed(interaction.user, data, current_points, buffs, is_annoyed, is_diseased)

        # 💡 pet_level 파라미터를 넘겨주도록 수정! (알 상태면 버튼 잠김)
        view = LegendActionView(interaction.user.id, pet_level=data.get('level', 0))
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(PetSystemCog(bot))