import discord
from discord.ext import commands
import configparser
import asyncio

# utils 폴더에서 데이터베이스 초기화 함수를 가져옵니다.
from utils.database import init_db

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
            # 'cogs.gacha',                   # 에러 방지를 위해 주석 처리 (파일이 있다면 주석 해제)
            'cogs.help',                      # 개편된 도움말
            'cogs.sync',                      # 기존 동기화 (유지)
            'cogs.petsystem.core',            # 펫 시스템 코어 (알까기, 상태창)
            'cogs.petsystem.inventory',       # 보관함, 도감, 상점(알환전/분해) 통합
            'cogs.petsystem.admin',           # 관리자 명령어 (UI 방식 적용)
            'cogs.petsystem.battle',          # 배틀 및 베팅 시스템
            'cogs.petsystem.achievement',     # ✨ 신규 업적 시스템
            'cogs.petsystem.cog_synthetis',   # 50회 업적 연동 합성
            'cogs.petsystem.cog_box',          # 기존 박스 (유지)
            'cogs.predict',
            'cogs.ui_predict.py'
        ]

        for extension in extensions:
            try:
                await self.load_extension(extension)
                print(f'▶️ {extension} 로드 완료')
            except Exception as e:
                print(f'🚨 {extension} 로드 실패 : {e}')

        synced = await self.tree.sync()
        print(f"🌀 디스코드에 총 {len(synced)}개의 커맨드를 강제 동기화했습니다!")

# --- 봇 인스턴스 생성 ---
bot = LegendBot()

# --- 봇 이벤트 ---
@bot.event
async def on_ready():
    print(f'✅ {bot.user.name}으로 로그인 성공! (ID: {bot.user.id})')
    print('🚀 봇이 성공적으로 실행되었습니다.')

# --- 메인 실행 로직 ---
async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
