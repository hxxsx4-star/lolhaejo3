import discord
from discord.ext import commands
import configparser
import asyncio

# --- 설정 로드 ---
config = configparser.ConfigParser()
config.read('config.ini')
TOKEN = config['discord']['token']

# --- 봇 인스턴스 생성 ---
# 모든 Intents를 활성화하여 모든 이벤트에 접근할 수 있도록 합니다.
# commands.Bot을 사용하면 명령어와 Cog 관리가 용이합니다.
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Cog 로드 목록 ---
# 앞으로 추가될 기능 파일들을 여기에 추가하면 됩니다.
extensions = [
    # 'cogs.gacha',
    'cogs.poker',
    'cogs.seotda',
    'cogs.economy',
    'cogs.help',
    'cogs.sync'  # 동기화 Cog 추가
]

# --- 봇 이벤트 ---
@bot.event
async def on_ready():
    """봇이 준비되었을 때 실행되는 이벤트입니다."""
    print(f'✅ {bot.user}으로 로그인 성공!')
    print(f'봇 ID: {bot.user.id}')
    
    # 슬래시 커맨드 동기화
    # 특정 길드에만 즉시 적용하려면 guild 인자를 사용합니다.
    # 전역으로 적용하려면 시간이 걸릴 수 있습니다.
    try:
        # 현재 봇이 속한 모든 길드에 커맨드를 동기화합니다.
        synced_count = 0
        for guild in bot.guilds:
            await bot.tree.sync(guild=guild)
            synced_count += 1
        print(f'🌀 {synced_count}개의 길드에 슬래시 커맨드를 동기화했습니다.')
    except Exception as e:
        print(f'❌ 커맨드 동기화 중 오류 발생: {e}')

    print('🚀 봇이 성공적으로 실행되었습니다.')

# --- 메인 실행 로직 ---
async def main():
    """Cog를 로드하고 봇을 실행하는 메인 함수입니다."""
    async with bot:
        # extensions 리스트에 있는 모든 Cog들을 순차적으로 로드합니다.
        for extension in extensions:
            try:
                await bot.load_extension(extension)
                print(f'▶️  {extension}.py 로드 완료')
            except Exception as e:
                print(f'🚨 {extension}.py 로드 실패: {e}')
        
        # 봇을 토큰으로 실행합니다.
        await bot.start(TOKEN)

if __name__ == '__main__':
    # 비동기 메인 함수를 실행합니다.
    asyncio.run(main())