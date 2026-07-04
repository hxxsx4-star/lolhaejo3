import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random
from datetime import datetime

# 기존 공유 포인트 시스템을 사용하기 위해 stats.py에서 함수들을 가져옵니다.
from utils.stats import get_points, add_points, spend_points

# ==========================================
# 데이터 정의 (등급별 전설이 및 필요 경험치)
# ==========================================
PET_POOLS = {
    "서사": ["🐧 펭구", "🗡️ 깃털기사", "🦄 뿔보", "👻 말랑이", "🐢 수릉이"],
    "전설": ["🥷 미니 아칼리", "⚔️ 미니 요네", "✨ 미니 럭스", "🎸 미니 유나라", "🦊 미니 아리"],
    "신화": ["🍌 미니 바나나 소라카", "🌹 미니 수정 장미 그웬", "🏆 미니 T1 요네", "🗡️ 미니 불멸의 영웅 이렐리아", "🐮 내가 젖소 포로"],
    "프레스티지": ["👼 프레스티지 미니 빛의 인도자 요네", "🌸 프레스티지 미니 영혼의 꽃 아리", "☕ 프레스티지 미니 귀염둥이 카페 그웬"]
}

EXP_TABLE = {
    "서사": {0: 5000, 1: 10000, 2: 15000, 3: 0},
    "전설": {0: 5000, 1: 20000, 2: 30000, 3: 0},
    "신화": {0: 5000, 1: 30000, 2: 60000, 3: 0},
    "프레스티지": {0: 5000, 1: 50000, 2: 100000, 3: 0}
}

# ==========================================
# DB 및 헬퍼 함수
# ==========================================
def init_db():
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    # users 테이블에서 'points' 컬럼을 제거하고 펫 관련 데이터만 관리합니다.
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, max_star_reached INTEGER,
                  egg_legendary INTEGER, egg_mythic INTEGER, egg_prestige INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_legends
                 (user_id INTEGER PRIMARY KEY, name TEXT, rarity TEXT,
                  level INTEGER, exp INTEGER, fullness INTEGER, intimacy INTEGER, fatigue INTEGER)''')
    conn.commit()
    conn.close()

def get_user_pet_data(user_id):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    data = c.fetchone()
    if not data:
        # 포인트는 공유 시스템에서 관리하므로, 여기서는 펫 관련 데이터만 초기화합니다.
        c.execute("INSERT INTO users VALUES (?, 0, 0, 0, 0)", (user_id,))
        conn.commit()
        data = (user_id, 0, 0, 0, 0)
    conn.close()
    return data

def update_user_egg(user_id, rarity, amount=1):
    if rarity == "서사": return
    column = {"전설": "egg_legendary", "신화": "egg_mythic", "프레스티지": "egg_prestige"}[rarity]
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute(f"UPDATE users SET {column} = MAX(0, {column} + ?) WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_legend(user_id):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("SELECT name, rarity, level, exp, fullness, intimacy, fatigue FROM user_legends WHERE user_id = ?", (user_id,))
    data = c.fetchone()
    conn.close()
    return data

def save_legend(user_id, name, rarity, level, exp, fullness, intimacy, fatigue):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO user_legends
                 (user_id, name, rarity, level, exp, fullness, intimacy, fatigue)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (user_id, name, rarity, level, exp, fullness, intimacy, fatigue))
    conn.commit()
    conn.close()

def check_and_update_max_star(user_id, level):
    user_data = get_user_pet_data(user_id)
    if level > user_data[1]: # max_star_reached 컬럼 인덱스는 1
        conn = sqlite3.connect('legends.db')
        c = conn.cursor()
        c.execute("UPDATE users SET max_star_reached = ? WHERE user_id = ?", (level, user_id))
        conn.commit()
        conn.close()

def create_status_embed(member: discord.Member, legend_data):
    name, rarity, level, exp, fullness, intimacy, fatigue = legend_data
    # 공유 포인트 시스템에서 포인트를 가져옵니다.
    points = get_points(member.id)

    is_egg = (level == 0)
    display_name = f"미확인 알 ({rarity})" if is_egg else name
    star_text = "🥚 부화 대기 중" if is_egg else f"{level}성"
    health_status = "보통 🟢" if not is_egg else "알 🥚"
    if not is_egg and fullness == 0: health_status = "질병 🔴 (포만감이 없습니다!)"
    mood_status = "행복 😊" if not is_egg else "알 🥚"
    if not is_egg and intimacy < 20: mood_status = "화남 💢 (친밀도가 너무 낮습니다!)"

    max_exp = EXP_TABLE[rarity][level]
    exp_text = "MAX" if level == 3 else f"{exp:,} / {max_exp:,}"
    exp_percent = 10 if level == 3 else int((exp / max_exp) * 10)

    color_map = {"서사": discord.Color.purple(), "전설": discord.Color.red(), "신화": discord.Color.gold(), "프레스티지": discord.Color.dark_theme()}
    embed = discord.Embed(
        title=f"{member.display_name}님의 {display_name} 상태창",
        description=f"등급: {rarity}\n보유 포인트: {points:,} P",
        color=color_map.get(rarity, discord.Color.blue())
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    exp_bar = "🟩" * exp_percent + "⬜" * (10 - exp_percent)
    embed.add_field(name="⭐ 성장", value=star_text, inline=True)
    if not is_egg:
        embed.add_field(name="❤️ 친밀도", value=f"{intimacy} pt", inline=True)
        embed.add_field(name="💤 피로도", value=f"{fatigue} pt", inline=True)
    embed.add_field(name="🩺 상태", value=f"건강: {health_status}\n기분: {mood_status}", inline=False)
    embed.add_field(name=f"✨ 경험치 ({exp_text})", value=exp_bar, inline=False)
    if not is_egg:
        fullness_bar = "🟧" * (fullness // 10) + "⬜" * (10 - (fullness // 10))
        embed.add_field(name=f"🍖 포만감 ({fullness}/100)", value=fullness_bar, inline=False)
    else:
        embed.add_field(name="안내", value="통화방 활동으로 경험치를 쌓아 알을 부화시켜보세요!", inline=False)
    return embed

# ==========================================
# UI View 클래스
# ==========================================
class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="전설이 간식 주기 (50P)", style=discord.ButtonStyle.success, emoji="🍖")
    async def feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("남의 전설이에게는 간식을 줄 수 없습니다!", ephemeral=True)

        data = get_legend(self.user_id)
        name, rarity, level, exp, fullness, intimacy, fatigue = data

        if level == 0:
            return await interaction.response.send_message("알은 아직 간식을 먹을 수 없어요! 통화방 활동으로 먼저 부화시켜주세요.", ephemeral=True)

        user_data = get_user(self.user_id)
        if user_data[1] < 50:
            return await interaction.response.send_message("포인트가 부족합니다! (필요: 50P)", ephemeral=True)

        if fullness >= 100:
            return await interaction.response.send_message("배가 불러서 더 이상 먹을 수 없어요!", ephemeral=True)

        update_user_points(self.user_id, -50)
        new_fullness = min(fullness + 20, 100)
        save_legend(self.user_id, name, rarity, level, exp, new_fullness, intimacy, fatigue)

        new_data = (name, rarity, level, exp, new_fullness, intimacy, fatigue)
        embed = create_status_embed(interaction.user, new_data, get_user(self.user_id))
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("냠냠! 50P를 사용하여 포만감을 20 채웠습니다.", ephemeral=True)

    async def handle_walk(self, interaction: discord.Interaction, count: int):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("남의 전설이와는 산책할 수 없습니다!", ephemeral=True)

        data = get_legend(self.user_id)
        name, rarity, level, exp, fullness, intimacy, fatigue = data

        if level == 0:
            return await interaction.response.send_message("알과는 산책을 할 수 없어요! 통화방 활동으로 먼저 부화시켜주세요.", ephemeral=True)

        if fullness == 0:
            return await interaction.response.send_message("전설이가 아파서(포만감 0) 산책을 갈 수 없어요. 간식을 먼저 주세요!", ephemeral=True)

        # 1. 산책 비용 계산 및 확인 (1회당 10P)
        cost = count * 10
        user_data = get_user(self.user_id)
        if user_data[1] < cost:
            return await interaction.response.send_message(f"산책 비용이 부족합니다! (필요: {cost:,}P / 현재: {user_data[1]:,}P)", ephemeral=True)

        gained_pts = 0
        lost_pts = 0
        drops = {"전설": 0, "신화": 0, "프레스티지": 0}

        for _ in range(count):
            rand = random.uniform(0, 100)
            if rand < 49.0:
                gained_pts += 50
            elif rand < 99.0:
                lost_pts += 50
            elif rand < 99.989:
                drops["전설"] += 1
            elif rand < 99.999:
                drops["신화"] += 1
            else:
                drops["프레스티지"] += 1

        # 2. 줍거나 잃은 포인트에 산책 비용(cost)을 빼서 최종 적용
        net_points = gained_pts - lost_pts - cost
        update_user_points(self.user_id, net_points)

        for drop_rarity, amount in drops.items():
            if amount > 0:
                update_user_egg(self.user_id, drop_rarity, amount)

        new_intimacy = intimacy + (1 * count)
        new_fatigue = fatigue + (1 * count)

        save_legend(self.user_id, name, rarity, level, exp, fullness, new_intimacy, new_fatigue)

        result_embed = discord.Embed(title=f"🚶 {count}회 산책 결과", color=discord.Color.green())
        # 3. 결과창에 산책 비용 명시
        result_embed.add_field(
            name="💰 포인트 변동",
            value=f"산책 비용: -{cost:,}P\n주운 포인트: +{gained_pts:,}P\n잃은 포인트: -{lost_pts:,}P\n총 합산: {net_points:,}P",
            inline=False
        )

        drop_text = ""
        if drops["전설"] > 0: drop_text += f"🟪 전설급 알 {drops['전설']}개 획득!\n"
        if drops["신화"] > 0: drop_text += f"🟨 신화급 알 {drops['신화']}개 획득!\n"
        if drops["프레스티지"] > 0: drop_text += f"⬛ 프레스티지급 알 {drops['프레스티지']}개 획득!\n"

        if drop_text:
            result_embed.add_field(name="🎁 특별 획득", value=drop_text, inline=False)
        else:
            result_embed.add_field(name="🎁 특별 획득", value="특별한 아이템을 줍지 못했습니다.", inline=False)

        new_data = (name, rarity, level, exp, fullness, new_intimacy, new_fatigue)
        embed = create_status_embed(interaction.user, new_data, get_user(self.user_id))
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(embed=result_embed, ephemeral=True)

    # 4. 버튼 라벨 및 텍스트 수정
    @discord.ui.button(label="산책 10회 (100P)", style=discord.ButtonStyle.primary, emoji="👟")
    async def walk_10_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 10)

    @discord.ui.button(label="산책 100회 (1,000P)", style=discord.ButtonStyle.primary, emoji="🏃")
    async def walk_100_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 100)

# ==========================================
# Cog 클래스 (메인 시스템)
# ==========================================
class PetSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        init_db()
        self.voice_sessions = {}

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
        data = get_legend(member.id)
        if not data: return
        name, rarity, level, exp, fullness, intimacy, fatigue = data
        if level >= 3: return

        max_exp = EXP_TABLE[rarity][level]
        new_exp = exp + gained_exp
        new_level = level
        level_ups = []
        while new_level < 3 and new_exp >= max_exp:
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

    @app_commands.command(name="알까기", description="새로운 전설이 알을 뽑습니다.")
    async def hatch_egg(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_pet_data = get_user_pet_data(user_id)
        current_pet = get_legend(user_id)
        is_first_time = user_pet_data[1] == 0 and not current_pet
        can_gacha = user_pet_data[1] == 3
        if current_pet and not can_gacha:
            return await interaction.response.send_message("아직 현재 전설이를 3성으로 키우지 못했습니다! 3성 달성 후 가챠가 해금됩니다.", ephemeral=True)
        cost = 0 if is_first_time else 1000
        if not is_first_time and get_points(user_id) < cost:
            return await interaction.response.send_message(f"가챠 비용이 부족합니다! (필요: {cost}P / 보유: {get_points(user_id)}P)", ephemeral=True)
        if not is_first_time: spend_points(user_id, cost)

        rand = random.uniform(0, 100)
        if is_first_time or rand < 85.0: rarity = "서사"
        elif rand < 99.0: rarity = "전설"
        elif rand < 99.9: rarity = "신화"
        else: rarity = "프레스티지"
        new_pet = random.choice(PET_POOLS[rarity])
        save_legend(user_id, new_pet, rarity, 0, 0, 50, 0, 0)
        rarity_map = {"서사": "🟪 [서사급] 기운이 느껴집니다...", "전설": "🟥 [전설급] 엄청난 기운이 느껴집니다...", "신화": "🟨 [신화급] 범상치 않은 기운이 뿜어져 나옵니다!", "프레스티지": "⬛ [프레스티지급] 전설적인 아우라가 느껴집니다!!"}
        msg = f"🥚 신비로운 알을 얻었습니다!\n\n{rarity_map[rarity]}\n\n통화방 활동을 통해 5,000XP를 모아 알을 부화시켜주세요!"
        await interaction.response.send_message(msg)

    @app_commands.command(name="상태창", description="내 전설이의 상태를 확인하고 돌봅니다.")
    async def status_window(self, interaction: discord.Interaction):
        data = get_legend(interaction.user.id)
        if not data:
            return await interaction.response.send_message("아직 전설이가 없습니다. `/알까기` 명령어로 알을 먼저 받아주세요!", ephemeral=True)
        embed = create_status_embed(interaction.user, data)
        view = LegendActionView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

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

async def setup(bot):
    await bot.add_cog(PetSystemCog(bot))
