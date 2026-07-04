import discord
from discord.ext import commands
import configparser
import asyncio

# --- 설정 로드 ---
config = configparser.ConfigParser()
config.read('config.ini')
TOKEN = config['discord']['token']

# --- 봇 인스턴스 생성 ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Cog 로드 목록 ---
extensions = [
    'cogs.gacha',
    'cogs.help',
    'cogs.sync',
    'cogs.petsystem.cog'  # 새로운 경로
]

# --- 봇 이벤트 ---
@bot.event
async def on_ready():
    print(f'✅ {bot.user}으로 로그인 성공!')
    print(f'봇 ID: {bot.user.id}')
    try:
        synced = await bot.tree.sync()
        print(f'🌀 {len(synced)}개의 전역 슬래시 커맨드를 동기화했습니다.')
    except Exception as e:
        print(f'❌ 커맨드 동기화 중 오류 발생: {e}')
    print('🚀 봇이 성공적으로 실행되었습니다.')

# --- 메인 실행 로직 ---
async def main():
    async with bot:
        for extension in extensions:
            try:
                await bot.load_extension(extension)
                print(f'▶️ {extension}.py 로드 완료')
            except Exception as e:
                print(f'🚨 {extension}.py 로드 실패: {e}')
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
