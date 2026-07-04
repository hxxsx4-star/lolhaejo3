import discord
from discord.ext import commands
import sqlite3
import random

# ==========================================
# 1. 데이터베이스 초기화 및 헬퍼 함수
# ==========================================
def init_db():
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    # 유저 ID를 기본키로 하여 전설이 정보를 저장하는 테이블 생성
    c.execute('''CREATE TABLE IF NOT EXISTS user_legends
                 (user_id INTEGER PRIMARY KEY, 
                  species TEXT, 
                  level INTEGER, 
                  exp INTEGER, 
                  fullness INTEGER, 
                  intimacy INTEGER)''')
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

init_db() # 봇 실행 시 DB 초기화

# ==========================================
# 2. 임베드(상태창) 생성 함수
# ==========================================
def create_status_embed(member: discord.Member, legend_data):
    species, level, exp, fullness, intimacy = legend_data
    
    embed = discord.Embed(
        title=f"{member.display_name}님의 {species} 상태창", 
        description="전설이를 잘 보살펴 3성으로 진화시켜 보세요!",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    
    # 상태 바(막대)를 간단히 텍스트로 구현
    exp_bar = "🟩" * (exp // 10) + "⬜" * (10 - (exp // 10))
    fullness_bar = "🟧" * (fullness // 10) + "⬜" * (10 - (fullness // 10))
    
    embed.add_field(name="⭐ 등급 (레벨)", value=f"{level}성", inline=True)
    embed.add_field(name="❤️ 친밀도", value=f"{intimacy} pt", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True) # 줄바꿈용 빈 필드
    
    embed.add_field(name=f"✨ 경험치 ({exp}/100)", value=exp_bar, inline=False)
    embed.add_field(name=f"🍖 포만감 ({fullness}/100)", value=fullness_bar, inline=False)
    
    return embed

# ==========================================
# 3. 버튼 UI 클래스 (먹이주기, 놀아주기)
# ==========================================
class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    # 🍖 먹이주기 버튼
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

        # 수치 업데이트
        new_fullness = min(fullness + 20, 100)
        new_intimacy = intimacy + 5
        update_legend(self.user_id, level, exp, new_fullness, new_intimacy)
        
        # 임베드 업데이트하여 메시지 수정
        new_data = (species, level, exp, new_fullness, new_intimacy)
        embed = create_status_embed(interaction.user, new_data)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("냠냠! 포만감이 20, 친밀도가 5 올랐습니다.", ephemeral=True)

    # ⚽ 놀아주기 버튼
    @discord.ui.button(label="같이 놀아주기", style=discord.ButtonStyle.primary, emoji="⚽")
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("남의 전설이와는 놀 수 없습니다!", ephemeral=True)
            
        data = get_legend(self.user_id)
        species, level, exp, fullness, intimacy = data
        
        if fullness < 20:
            return await interaction.response.send_message("배가 고파서 놀 기운이 없어요... 간식을 먼저 주세요!", ephemeral=True)
            
        # 수치 업데이트
        new_fullness = fullness - 20
        new_exp = exp + 30
        new_level = level
        
        # 레벨업(진화) 로직
        level_up_msg = ""
        if new_exp >= 100:
            if level < 3:
                new_level += 1
                new_exp -= 100
                level_up_msg = f"🎉 앗! 전설이의 모습이...! **{new_level}성**으로 진화했습니다!"
            else:
                new_exp = 100 # 3성 만렙

        update_legend(self.user_id, new_level, new_exp, new_fullness, intimacy)
        
        # 임베드 업데이트
        new_data = (species, new_level, new_exp, new_fullness, intimacy)
        embed = create_status_embed(interaction.user, new_data)
        await interaction.response.edit_message(embed=embed, view=self)
        
        msg = "전설이와 신나게 놀았습니다! (경험치 +30, 포만감 -20)\n" + level_up_msg
        await interaction.followup.send(msg, ephemeral=True)

# ==========================================
# 4. 봇 클래스 및 슬래시 커맨드
# ==========================================
intents = discord.Intents.default()

class LegendBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
    
    async def setup_hook(self):
        await self.tree.sync()
        print("✅ 슬래시 커맨드 동기화 완료!")

bot = LegendBot()
legends_list = ["🐧 펭구", "🗡️ 깃털기사", "🦄 뿔보", "👻 말랑이", "🐢 수릉이"]

@bot.event
async def on_ready():
    print(f'봇 로그인 완료: {bot.user}')

@bot.tree.command(name="알까기", description="새로운 전설이 알을 부화시킵니다.")
async def hatch_egg(interaction: discord.Interaction):
    user_id = interaction.user.id
    if get_legend(user_id):
        return await interaction.response.send_message("이미 전설이를 키우고 계십니다! `/상태창`을 확인해보세요.", ephemeral=True)
        
    my_legend = random.choice(legends_list)
    
    # DB에 초기 데이터 저장 (레벨 1, 경험치 0, 포만감 50, 친밀도 0)
    conn = sqlite3.connect('legends.db')
    c = conn.cursor()
    c.execute("INSERT INTO user_legends VALUES (?, ?, ?, ?, ?, ?)", (user_id, my_legend, 1, 0, 50, 0))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"🎉 축하합니다! 알에서 **1성 {my_legend}**(이)가 태어났습니다!\n`/상태창` 명령어로 전설이를 돌봐주세요.")

@bot.tree.command(name="상태창", description="내 전설이의 상태를 확인하고 돌봅니다.")
async def status_window(interaction: discord.Interaction):
    data = get_legend(interaction.user.id)
    if not data:
        return await interaction.response.send_message("아직 전설이가 없습니다. `/알까기` 명령어로 알을 먼저 부화시켜주세요!", ephemeral=True)
        
    embed = create_status_embed(interaction.user, data)
    view = LegendActionView(interaction.user.id)
    
    await interaction.response.send_message(embed=embed, view=view)

# 봇 실행
# bot.run('MTUyMjU1MjY5ODYwMjUyNDc3Mg.GGuiji.xxV3EY8228d-Nk9pDDJ60qFopHJN8awziUhESk')
