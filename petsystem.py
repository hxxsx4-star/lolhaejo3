import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random

# ==========================================
# DB 및 헬퍼 함수, View 클래스는 기존과 동일하게 유지합니다.
# ==========================================
def init_db():
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_legends
                 (user_id INTEGER PRIMARY KEY,
                  species TEXT, level INTEGER, exp INTEGER,
                  fullness INTEGER, intimacy INTEGER)''')
    conn.commit()
    conn.close()

def get_legend(user_id):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("SELECT species, level, exp, fullness, intimacy FROM user_legends WHERE user_id = ?", (user_id,))
    data = c.fetchone()
    conn.close()
    return data

def update_legend(user_id, level, exp, fullness, intimacy):
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute('''UPDATE user_legends
                 SET level = ?, exp = ?, fullness = ?, intimacy = ?
                 WHERE user_id = ?''', (level, exp, fullness, intimacy, user_id))
    conn.commit()
    conn.close()

def create_status_embed(member: discord.Member, legend_data):
    species, level, exp, fullness, intimacy = legend_data

    embed = discord.Embed(
        title=f"{member.display_name}님의 {species} 상태창",
        description="전설이를 잘 보살펴 3성으로 진화시켜 보세요!",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    exp_bar = "🟩" * (exp // 10) + "⬜" * (10 - (exp // 10))
    fullness_bar = "🟧" * (fullness // 10) + "⬜" * (10 - (fullness // 10))

    embed.add_field(name="⭐ 등급 (레벨)", value=f"{level}성", inline=True)
    embed.add_field(name="❤️ 친밀도", value=f"{intimacy} pt", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(name=f"✨ 경험치 ({exp}/100)", value=exp_bar, inline=False)
    embed.add_field(name=f"🍖 포만감 ({fullness}/100)", value=fullness_bar, inline=False)

    return embed

class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="포로 간식 주기", style=discord.ButtonStyle.success, emoji="🍖")
    async def feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("남의 전설이에게는 간식을 줄 수 없습니다!", ephemeral=True)

        data = get_legend(self.user_id)
        if not data:
            return await interaction.response.send_message("전설이가 없습니다!", ephemeral=True)

        species, level, exp, fullness, intimacy = data
        if fullness >= 100:
            return await interaction.response.send_message("배가 불러서 더 이상 먹을 수 없어요!", ephemeral=True)

        new_fullness = min(fullness + 20, 100)
        new_intimacy = intimacy + 5
        update_legend(self.user_id, level, exp, new_fullness, new_intimacy)

        new_data = (species, level, exp, new_fullness, new_intimacy)
        embed = create_status_embed(interaction.user, new_data)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("냠냠! 포만감이 20, 친밀도가 5 올랐습니다.", ephemeral=True)

    @discord.ui.button(label="같이 놀아주기", style=discord.ButtonStyle.primary, emoji="⚽")
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("남의 전설이와는 놀 수 없습니다!", ephemeral=True)

        data = get_legend(self.user_id)
        species, level, exp, fullness, intimacy = data

        if fullness < 20:
            return await interaction.response.send_message("배가 고파서 놀 기운이 없어요... 간식을 먼저 주세요!", ephemeral=True)

        new_fullness = fullness - 20
        new_exp = exp + 30
        new_level = level

        level_up_msg = ""
        if new_exp >= 100:
            if level < 3:
                new_level += 1
                new_exp -= 100
                level_up_msg = f"🎉 앗! 전설이의 모습이...! {new_level}성으로 진화했습니다!"
            else:
                new_exp = 100

        update_legend(self.user_id, new_level, new_exp, new_fullness, intimacy)

        new_data = (species, new_level, new_exp, new_fullness, intimacy)
        embed = create_status_embed(interaction.user, new_data)
        await interaction.response.edit_message(embed=embed, view=self)

        msg = "전설이와 신나게 놀았습니다! (경험치 +30, 포만감 -20)\n" + level_up_msg
        await interaction.followup.send(msg, ephemeral=True)

# ==========================================
# 봇 클래스 대신 Cog 클래스로 변경
# ==========================================
class PetSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.legends_list = ["🐧 펭구", "🗡️ 깃털기사", "🦄 뿔보", "👻 말랑이", "🐢 수릉이"]
        init_db() # 코그가 로드될 때 DB 초기화

    # @bot.tree.command 대신 @app_commands.command 사용, self 매개변수 추가
    @app_commands.command(name="알까기", description="새로운 전설이 알을 부화시킵니다.")
    async def hatch_egg(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if get_legend(user_id):
            return await interaction.response.send_message("이미 전설이를 키우고 계십니다! `/상태창`을 확인해보세요.", ephemeral=True)

        my_legend = random.choice(self.legends_list)

        conn = sqlite3.connect('legends.db')
        c = conn.cursor()
        c.execute("INSERT INTO user_legends VALUES (?, ?, ?, ?, ?, ?)", (user_id, my_legend, 1, 0, 50, 0))
        conn.commit()
        conn.close()

        await interaction.response.send_message(f"🎉 축하합니다! 알에서 1성 {my_legend}(이)가 태어났습니다!\n`/상태창` 명령어로 전설이를 돌봐주세요.")

    @app_commands.command(name="상태창", description="내 전설이의 상태를 확인하고 돌봅니다.")
    async def status_window(self, interaction: discord.Interaction):
        data = get_legend(interaction.user.id)
        if not data:
            return await interaction.response.send_message("아직 전설이가 없습니다. `/알까기` 명령어로 알을 먼저 부화시켜주세요!", ephemeral=True)

        embed = create_status_embed(interaction.user, data)
        view = LegendActionView(interaction.user.id)

        await interaction.response.send_message(embed=embed, view=view)

# 메인 봇이 이 파일을 로드할 수 있도록 setup 함수 추가
async def setup(bot):
    await bot.add_cog(PetSystemCog(bot))
