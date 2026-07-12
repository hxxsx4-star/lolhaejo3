import discord
from discord.ext import commands, tasks
from discord import app_commands

from utils.database import get_or_migrate_data, get_synth_count, get_top_epic_egg_owners
from utils.data import PET_POOLS

# 서사급 알 상위 N명에게 순위 역할을 부여합니다. (원하는 인원수로 이 값만 바꾸면 됨)
TOP_EGG_RANK = 3

ROLE_IDS = {
    "ALL_PETS": 1523077720404398131,
    "FIRST_MYTHIC_3": 1523080290203992124,
    "FIRST_PRESTIGE_3": 1523080331413028945,
    "ALL_EPIC_3": 1523080402309484614,
    "ALL_LEGEND_3": 1523080441974751352,
    "ALL_MYTHIC_3": 1523080471960092722,
    "ALL_PRESTIGE_3": 1523080498715300092,
    "ALL_NOBLE_3": 1523269218215399474,
    "ALL_TRANS_3": 1523269417537114172,
    "ALL_PETS_3": 1523080369585524786,
    "TOP5_EPIC_EGG": 1523080677187260587,
    "SYNTH_50": 1523080635831423157
}

class AchievementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.top_egg_role_loop.start()

    def cog_unload(self):
        self.top_egg_role_loop.cancel()

    # ==========================================
    # 💡 서사급 알 순위 역할 실시간 동기화
    # ==========================================
    @tasks.loop(seconds=60)
    async def top_egg_role_loop(self):
        # 60초마다 순위를 확인해 이탈자 회수 + 신규 진입자 부여를 자동 처리
        for guild in self.bot.guilds:
            if guild.get_role(ROLE_IDS["TOP5_EPIC_EGG"]):
                try:
                    await self.reconcile_top_egg_role(guild)
                except Exception as e:
                    print(f"⚠️ 서사급 알 순위 역할 동기화 실패({guild.id}): {e}")

    @top_egg_role_loop.before_loop
    async def before_top_egg_role_loop(self):
        await self.bot.wait_until_ready()

    async def reconcile_top_egg_role(self, guild: discord.Guild):
        """현재 서사급 알 상위 TOP_EGG_RANK 명에게만 역할이 유지되도록 동기화합니다.

        - 순위 밖으로 밀려난 기존 보유자에게서는 역할을 회수
        - 새로 순위권에 든 유저에게는 역할을 부여
        변화가 없으면 Discord API 호출도 하지 않습니다(가드 조건).
        """
        role = guild.get_role(ROLE_IDS["TOP5_EPIC_EGG"])
        if not role:
            return

        top_owners = await get_top_epic_egg_owners()  # 보유량 내림차순 (최대 5명)
        top_ids = {uid for uid, amt in top_owners[:TOP_EGG_RANK] if amt and amt > 0}

        # 1) 순위에서 이탈한 보유자에게서 역할 회수
        for member in list(role.members):
            if member.id not in top_ids:
                try:
                    await member.remove_roles(role, reason="서사급 알 순위 이탈")
                except discord.HTTPException:
                    pass

        # 2) 새로 순위권에 든 유저에게 역할 부여
        for uid in top_ids:
            member = guild.get_member(uid)
            if member and role not in member.roles:
                try:
                    await member.add_roles(role, reason="서사급 알 순위 진입")
                except discord.HTTPException:
                    pass

    async def check_and_grant_roles(self, member: discord.Member):
        if not member.guild: return
        wrapper = await get_or_migrate_data(member.id)
        pets = wrapper.get('pets', [])
        box_pets = wrapper.get('box', []) # 박스에 보관된 펫 리스트 가져오기

        # 파티에 있는 펫과 박스에 있는 펫 데이터를 병합
        all_owned_pets = pets + box_pets

        owned_types = {p['type'] for p in all_owned_pets}
        owned_3stars = {p['type']: p for p in all_owned_pets if p.get('level', 0) >= 3}

        roles_to_add = []
        all_pet_types = set(sum(PET_POOLS.values(), []))

        if all_pet_types.issubset(owned_types): roles_to_add.append(ROLE_IDS["ALL_PETS"])
        if any(p['rarity'] == '신화' for p in owned_3stars.values()): roles_to_add.append(ROLE_IDS["FIRST_MYTHIC_3"])
        if any(p['rarity'] == '프레스티지' for p in owned_3stars.values()): roles_to_add.append(ROLE_IDS["FIRST_PRESTIGE_3"])

        if set(PET_POOLS["서사"]).issubset(set(owned_3stars.keys())): roles_to_add.append(ROLE_IDS["ALL_EPIC_3"])
        if set(PET_POOLS["전설"]).issubset(set(owned_3stars.keys())): roles_to_add.append(ROLE_IDS["ALL_LEGEND_3"])
        if set(PET_POOLS["신화"]).issubset(set(owned_3stars.keys())): roles_to_add.append(ROLE_IDS["ALL_MYTHIC_3"])
        if set(PET_POOLS["프레스티지"]).issubset(set(owned_3stars.keys())): roles_to_add.append(ROLE_IDS["ALL_PRESTIGE_3"])
        # 고귀/초월은 풀이 비어 있으면 issubset(빈집합)이 항상 참이 되므로, 풀이 존재할 때만 판정
        if PET_POOLS.get("고귀") and set(PET_POOLS["고귀"]).issubset(set(owned_3stars.keys())): roles_to_add.append(ROLE_IDS["ALL_NOBLE_3"])
        if PET_POOLS.get("초월") and set(PET_POOLS["초월"]).issubset(set(owned_3stars.keys())): roles_to_add.append(ROLE_IDS["ALL_TRANS_3"])
        if all_pet_types.issubset(set(owned_3stars.keys())): roles_to_add.append(ROLE_IDS["ALL_PETS_3"])

        synth_count = await get_synth_count(member.id)
        if synth_count >= 50: roles_to_add.append(ROLE_IDS["SYNTH_50"])

        guild_roles = {r.id: r for r in member.guild.roles}
        for role_id in roles_to_add:
            role = guild_roles.get(role_id)
            if role and role not in member.roles:
                try: await member.add_roles(role)
                except discord.Forbidden: pass

    # 💡 들여쓰기 정상화 완료!
    @app_commands.command(name="업적", description="나의 업적 달성 현황을 확인합니다.")
    async def view_achievements(self, interaction: discord.Interaction):
        await self.check_and_grant_roles(interaction.user)

        wrapper = await get_or_migrate_data(interaction.user.id)
        pets = wrapper.get('pets', [])
        box_pets = wrapper.get('box', []) # 박스에 보관된 펫 리스트 가져오기

        # 파티와 박스 전설이 병합하여 수집 현황 체크
        all_owned_pets = pets + box_pets

        owned_types = {p['type'] for p in all_owned_pets}
        owned_3stars_types = {p['type'] for p in all_owned_pets if p.get('level', 0) >= 3}
        synth_count = await get_synth_count(interaction.user.id)

        all_epic = len(PET_POOLS["서사"])
        all_leg = len(PET_POOLS["전설"])
        all_myth = len(PET_POOLS["신화"])
        all_pres = len(PET_POOLS["프레스티지"])
        all_noble = len(PET_POOLS.get("고귀", []))
        all_trans = len(PET_POOLS.get("초월", []))

        total_pets_count = all_epic + all_leg + all_myth + all_pres + all_noble + all_trans

        embed = discord.Embed(title=f"🏆 {interaction.user.display_name}님의 업적 현황", color=discord.Color.gold())
        embed.add_field(name="🐾 전설이 수집가", value=f"{len(owned_types)} / {total_pets_count} 마리", inline=True)
        embed.add_field(name="✨ 모든 서사 3성", value=f"{len(set(PET_POOLS['서사']) & owned_3stars_types)} / {all_epic} 마리", inline=True)
        embed.add_field(name="⚔️ 모든 전설 3성", value=f"{len(set(PET_POOLS['전설']) & owned_3stars_types)} / {all_leg} 마리", inline=True)
        embed.add_field(name="🌟 모든 신화 3성", value=f"{len(set(PET_POOLS['신화']) & owned_3stars_types)} / {all_myth} 마리", inline=True)
        embed.add_field(name="👑 모든 프레스티지 3성", value=f"{len(set(PET_POOLS['프레스티지']) & owned_3stars_types)} / {all_pres} 마리", inline=True)
        embed.add_field(name="💠 모든 고귀 3성", value=f"{len(set(PET_POOLS.get('고귀', [])) & owned_3stars_types)} / {all_noble} 마리", inline=True)
        embed.add_field(name="🌌 모든 초월 3성", value=f"{len(set(PET_POOLS.get('초월', [])) & owned_3stars_types)} / {all_trans} 마리", inline=True)
        embed.add_field(name="🏅 모든 전설이 3성", value=f"{len(owned_3stars_types)} / {total_pets_count} 마리", inline=True)
        embed.add_field(name="🔮 합성 장인", value=f"{synth_count} / 50 회", inline=True)

        member_roles = [r.id for r in interaction.user.roles]
        achieved_list = []
        if ROLE_IDS["FIRST_MYTHIC_3"] in member_roles: achieved_list.append("🥇 신화 3성 최초 달성")
        if ROLE_IDS["FIRST_PRESTIGE_3"] in member_roles: achieved_list.append("💎 프레스티지 3성 최초 달성")
        if ROLE_IDS["ALL_EPIC_3"] in member_roles: achieved_list.append("✨ 모든 서사 3성 정복")
        if ROLE_IDS["ALL_LEGEND_3"] in member_roles: achieved_list.append("⚔️ 모든 전설 3성 정복")
        if ROLE_IDS["ALL_MYTHIC_3"] in member_roles: achieved_list.append("🌟 모든 신화 3성 정복")
        if ROLE_IDS["ALL_PRESTIGE_3"] in member_roles: achieved_list.append("👑 모든 프레스티지 3성 정복")
        if ROLE_IDS["ALL_NOBLE_3"] in member_roles: achieved_list.append("💠 모든 고귀 3성 정복")
        if ROLE_IDS["ALL_TRANS_3"] in member_roles: achieved_list.append("🌌 모든 초월 3성 정복")
        if ROLE_IDS["ALL_PETS_3"] in member_roles: achieved_list.append("🏅 모든 전설이 3성 정복")
        if ROLE_IDS["ALL_PETS"] in member_roles: achieved_list.append("🐾 전설이 도감 완성")
        if ROLE_IDS["TOP5_EPIC_EGG"] in member_roles: achieved_list.append(f"🥚 서사급 알 만수르 (TOP {TOP_EGG_RANK})")

        if achieved_list:
            embed.add_field(name="🎉 특별 타이틀 달성", value="\n".join(achieved_list), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="알개수", description="서사급 알 보유량 순위 TOP 5를 확인합니다.")
    async def egg_ranking(self, interaction: discord.Interaction):
        top_users = await get_top_epic_egg_owners()
        embed = discord.Embed(title="🏆 서사급 알 부자 TOP 5", color=discord.Color.gold())

        if not top_users:
            embed.description = "아직 랭킹에 등록된 유저가 없습니다."
        else:
            desc = ""
            for idx, (uid, amt) in enumerate(top_users, 1):
                member = interaction.guild.get_member(uid)
                name = member.display_name if member else f"알수없는유저({uid})"
                crown = " 👑" if idx <= TOP_EGG_RANK else ""
                desc += f"{idx}위: {name} - {amt}개{crown}\n"
            embed.description = desc
            embed.set_footer(text=f"👑 상위 {TOP_EGG_RANK}위에게 순위 역할이 자동 부여/회수됩니다.")

        await interaction.response.send_message(embed=embed)

        # 순위 역할을 즉시 동기화(이탈자 회수 + 신규 진입자 부여)
        if interaction.guild:
            try:
                await self.reconcile_top_egg_role(interaction.guild)
            except discord.HTTPException:
                pass

async def setup(bot):
    await bot.add_cog(AchievementCog(bot))