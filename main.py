import discord
from discord.ext import commands
import configparser
import asyncio

# DB 초기화 함수 임포트
from database import init_db

# --- 설정 로드 ---
config = configparser.ConfigParser()
config.read('config.ini')
TOKEN = config['discord']['token']

# --- 봇 클래스 정의 ---
class LegendBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # 봇이 켜질 때 DB 초기화를 비동기로 실행
        await init_db()
        print("✅ 데이터베이스 초기화 완료")

        extensions = [
            'cogs.gacha',
            'cogs.help',
            'cogs.sync',
            'cogs.petsystem.cog'
        ]

        for extension in extensions:
            try:
                await self.load_extension(extension)
                print(f'▶️ {extension} 로드 완료')
            except Exception as e:
                print(f'🚨 {extension} 로드 실패: {e}')

# --- 봇 인스턴스 생성 ---
bot = LegendBot()

# --- 봇 이벤트 ---
@bot.event
async def on_ready():
    print(f'✅ {bot.user}으로 로그인 성공! (ID: {bot.user.id})')
    print('🚀 봇이 성공적으로 실행되었습니다.')

# --- 메인 실행 로직 ---
async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())