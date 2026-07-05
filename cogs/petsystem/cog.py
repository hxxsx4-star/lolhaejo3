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
from utils.stats import get_points, add_points

class PetSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_sessions = {}

    # 다중 펫 데이터 마이그레이션 및 헬퍼 함수
    async def get_or_migrate_data(self, user_id):
        data = await get_legend_data(user_id)
        if not data:
            return {'pets': [], 'active_idx': 0}
        if 'pets' not in data:
            return {'pets': [data], 'active_idx': 0}
        return data

    async def evaluate_pet_status(self, user_id, wrapper):
        if not wrapper['pets']:
            return None, [], False, False

        data = wrapper['pets'][wrapper['active_idx']]
        if data['level'] == 0:
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
            if data.get('low_full_since', 0) == 0: data['low_full_since'] = now
        else:
            data['low_full_since'] = 0

        if data.get('cleanliness', 100) <= 20:
            if data.get('low_clean_since', 0) == 0: data['low_clean_since'] = now
        else:
            data['low_clean_since'] = 0

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
                duration_sec = time.time() - self.voice_sessions.pop(member.id)
                await self.add_exp_to_pet(member, duration_sec)

    async def add_exp_to_pet(self, member, duration_sec):
        wrapper = await self.get_or_migrate_data(member.id)
        if not wrapper['pets']: return

        data = wrapper['pets'][wrapper['active_idx']]
        if data['level'] >= 3 or data['level'] == 0: return # 알 상태이거나 만렙이면 패스

        active_buffs = await get_active_buffs(member.id)
        buffs = {b[0] for b in active_buffs}

        exp_multiplier = 1
        if data['intimacy'] >= 80: exp_multiplier *= 2

        data['exp'] += int(duration_sec / 60 * exp_multiplier)
        wrapper['pets'][wrapper['active_idx']] = data
        await save_legend_data(member.id, wrapper)

    @app_commands.command(name="알까기", description="새로운 전설이 알을 뽑고 이름을 지어줍니다.")
    async def hatch_egg(self, interaction: discord.Interaction, 이름: str):
        user_id = interaction.user.id
        user_data = await get_user(user_id)
        wrapper = await self.get_or_migrate_data(user_id)

        is_first_time = (len(wrapper['pets']) == 0)

        # 3마리 제한 및 해금 조건 확인
        if not is_first_time:
            if user_data[2] < 3: # 기존 코드의 첫 전설이 3성 달성 조건 (DB 연동 구조 가정)
                return await interaction.response.send_message("아직 첫 전설이를 3성으로 키우지 못했습니다! 3성 달성 후 추가 가챠가 해금됩니다.", ephemeral=True)
            if len(wrapper['pets']) >= 3:
                return await interaction.response.send_message("전설이는 최대 3마리까지만 키울 수 있습니다!", ephemeral=True)

        current_points = await get_points(user_id)
        cost = 0 if is_first_time else 1000

        if current_points < cost:
            return await interaction.response.send_message(f"가챠 비용이 부족합니다! (필요: {cost}P)", ephemeral=True)

        if not is_first_time: await add_points(user_id, -cost)

        rarity = "서사" if is_first_time else random.choices(list(PET_POOLS.keys()), weights=[85, 14, 0.9, 0.1], k=1)[0]
        # 이름은 유저가 입력한 커스텀 이름으로 지정, 종류(타입)는 랜덤 결정
        pet_type = random.choice(PET_POOLS[rarity])

        new_pet_data = {
            'name': 이름,
            'type': pet_type, # 실제 종류를 별도로 보관하는 것이 좋습니다.
            'rarity': rarity,
            'level': 0, 'exp': 0, 'fullness': 100, 'intimacy': 50, 'fatigue': 0, 'cleanliness': 100
        }

        wrapper['pets'].append(new_pet_data)
        wrapper['active_idx'] = len(wrapper['pets']) - 1 # 새로 뽑은 펫을 바로 활성화
        await save_legend_data(user_id, wrapper)

        await interaction.response.send_message(f"🥚 신비로운 [{rarity}급] 알을 얻었습니다! (이름: {이름})\n`/상태창`으로 확인하세요.", ephemeral=True)

    @app_commands.command(name="이름변경", description="전설이 이름 변경권을 사용하여 활성화된 전설이의 이름을 바꿉니다.")
    async def change_name(self, interaction: discord.Interaction, 새이름: str):
        wrapper = await self.get_or_migrate_data(interaction.user.id)
        if not wrapper['pets']:
            return await interaction.response.send_message("아직 전설이가 없습니다.", ephemeral=True)

        success = await consume_item(interaction.user.id, "전설이 이름 변경권", 1)
        if not success:
            return await interaction.response.send_message("`전설이 이름 변경권` 아이템이 필요합니다! (보관함 확인)", ephemeral=True)

        data = wrapper['pets'][wrapper['active_idx']]
        old_name = data['name']
        data['name'] = 새이름

        await save_legend_data(interaction.user.id, wrapper)
        await interaction.response.send_message(f"✨ 전설이의 이름이 `{old_name}`에서 `{새이름}`(으)로 변경되었습니다!", ephemeral=True)

    @app_commands.command(name="펫교체", description="돌볼 전설이를 교체합니다.")
    @app_commands.choices(슬롯=[
        app_commands.Choice(name="1번 펫", value=0),
        app_commands.Choice(name="2번 펫", value=1),
        app_commands.Choice(name="3번 펫", value=2)
    ])
    async def switch_pet(self, interaction: discord.Interaction, 슬롯: int):
        wrapper = await self.get_or_migrate_data(interaction.user.id)
        if 슬롯 >= len(wrapper['pets']):
            return await interaction.response.send_message(f"해당 슬롯에는 아직 전설이가 없습니다. (보유 중인 펫: {len(wrapper['pets'])}마리)", ephemeral=True)

        wrapper['active_idx'] = 슬롯
        await save_legend_data(interaction.user.id, wrapper)
        pet_name = wrapper['pets'][슬롯]['name']
        await interaction.response.send_message(f"🔄 지금부터 `{pet_name}`(을)를 돌봅니다! `/상태창`을 확인하세요.", ephemeral=True)

    @app_commands.command(name="상태창", description="내 전설이의 상태를 확인하고 돌봅니다.")
    async def status_window(self, interaction: discord.Interaction):
        wrapper = await self.get_or_migrate_data(interaction.user.id)
        if not wrapper['pets']:
            return await interaction.response.send_message("아직 전설이가 없습니다. `/알까기`로 시작하세요!", ephemeral=True)

        data, buffs, is_annoyed, is_diseased = await self.evaluate_pet_status(interaction.user.id, wrapper)
        current_points = await get_points(interaction.user.id)

        embed = create_status_embed(interaction.user, data, current_points, buffs, is_annoyed, is_diseased)
        view = LegendActionView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    # ===== 관리자 명령어 구역 =====

    @app_commands.command(name="알지급", description="[관리자] 유저에게 특정 등급의 알을 지급합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(등급=[
        app_commands.Choice(name="서사", value="서사"),
        app_commands.Choice(name="전설", value="전설"),
        app_commands.Choice(name="신화", value="신화"),
        app_commands.Choice(name="프레스티지", value="프레스티지")
    ])
    async def give_egg(self, interaction: discord.Interaction, 유저: discord.Member, 등급: app_commands.Choice[str],
                       이름: str = "관리자지급알"):
        # 1. 타임아웃 방지 (잠시만 기다려주세요 상태)
        await interaction.response.defer(ephemeral=True)

        try:
            wrapper = await self.get_or_migrate_data(유저.id)
            if len(wrapper.get('pets', [])) >= 3:
                return await interaction.followup.send("❌ 해당 유저는 이미 3마리의 전설이를 보유하고 있습니다.")

            # 혹시 모를 에러 방지 (등급.value 사용)
            pet_type = random.choice(PET_POOLS.get(등급.value, ["알 수 없음"]))
            new_pet_data = {
                'name': 이름, 'type': pet_type, 'rarity': 등급.value,
                'level': 0, 'exp': 0, 'fullness': 100, 'intimacy': 50, 'fatigue': 0, 'cleanliness': 100
            }

            if 'pets' not in wrapper:
                wrapper['pets'] = []

            wrapper['pets'].append(new_pet_data)

            # 첫 펫 지급인 경우 자동으로 0번 슬롯 활성화
            if len(wrapper['pets']) == 1:
                wrapper['active_idx'] = 0

            await save_legend_data(유저.id, wrapper)
            await interaction.followup.send(f"✅ {유저.display_name}님에게 `{등급.value}` 등급의 알을 지급했습니다.")

        except Exception as e:
            print(f"[알지급 에러] {e}")
            await interaction.followup.send("❌ 명령어를 처리하는 도중 오류가 발생했습니다. 봇 콘솔을 확인해주세요.")

    @app_commands.command(name="알회수", description="[관리자] 유저의 활성화된 전설이를 회수(삭제)합니다.")
    @app_commands.default_permissions(administrator=True)
    async def remove_egg(self, interaction: discord.Interaction, 유저: discord.Member):
        # 1. 타임아웃 방지
        await interaction.response.defer(ephemeral=True)

        try:
            wrapper = await self.get_or_migrate_data(유저.id)
            if not wrapper.get('pets'):
                return await interaction.followup.send("❌ 해당 유저는 보유한 전설이가 없습니다.")

            # 2. 인덱스 꼬임 방어 (active_idx가 pets 배열 길이보다 클 경우 강제로 0으로 조정)
            active_idx = wrapper.get('active_idx', 0)
            if active_idx >= len(wrapper['pets']):
                active_idx = 0

            # 펫 삭제 처리
            removed = wrapper['pets'].pop(active_idx)

            # 3. 삭제 후 활성화된 슬롯 재조정 (안전하게 max 사용)
            wrapper['active_idx'] = max(0, len(wrapper['pets']) - 1)

            await save_legend_data(유저.id, wrapper)
            await interaction.followup.send(
                f"✅ {유저.display_name}님의 `{removed['name']} ({removed['rarity']})`(을)를 강제 회수했습니다.")

        except Exception as e:
            print(f"[알회수 에러] {e}")
            await interaction.followup.send("❌ 명령어를 처리하는 도중 오류가 발생했습니다. 봇 콘솔을 확인해주세요.")

    @app_commands.command(name="강제부화", description="[관리자] 유저의 활성화된 알을 즉시 부화(1성)시킵니다.")
    @app_commands.default_permissions(administrator=True)
    async def force_hatch_cmd(self, interaction: discord.Interaction, 유저: discord.Member):
        # 1. 3초 이상 지연을 막기 위해 defer 호출 (관리자 명령어이므로 혼자만 보이게 ephemeral 처리)
        await interaction.response.defer(ephemeral=True)

        try:
            wrapper = await self.get_or_migrate_data(유저.id)

            if not wrapper.get('pets'):
                # defer 이후에는 response 대신 followup.send를 사용해야 합니다.
                return await interaction.followup.send("해당 유저는 보유한 전설이가 없습니다.")

            # 2. 인덱스 오류(IndexError) 방어
            active_idx = wrapper.get('active_idx', 0)
            if active_idx >= len(wrapper['pets']):
                active_idx = 0
                wrapper['active_idx'] = active_idx

            data = wrapper['pets'][active_idx]

            if data['level'] > 0:
                return await interaction.followup.send(f"해당 펫(`{data['name']}`)은 이미 부화한 상태입니다.")

            # 부화 처리
            data['level'] = 1
            data['exp'] = 0
            wrapper['pets'][active_idx] = data
            await save_legend_data(유저.id, wrapper)

            await interaction.followup.send(f"✅ {유저.display_name}님의 알(`{data['name']}`)을 강제로 부화시켰습니다!")

        except Exception as e:
            # 3. 디버깅을 위한 에러 로그 출력
            print(f"[강제부화 명령어 에러] {e}")
            await interaction.followup.send("❌ 명령어를 처리하는 도중 오류가 발생했습니다. 콘솔을 확인해주세요.")

    # (기존 보관함, 판매, 전설이목록, 아이템목록 명령어는 그대로 유지)
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
            await add_points(interaction.user.id, price)
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