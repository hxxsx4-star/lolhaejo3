import discord
from discord.ext import commands, tasks # tasks 추가
from discord import app_commands
import math
import time
import datetime # 날짜/시간 계산용 추가

from utils.database import (
    consume_item, add_item, create_bet_session, get_bet_session, update_bet_status,
    add_bet_record, get_bet_totals, get_bet_winners, get_user_bet, get_item_amount, get_user_all_bets,
    set_bet_close_time, get_expired_bets # 새로 만든 DB 함수들 추가
)

# ... (기존 generate_progress_bar 등 상단 함수와 UI 클래스들은 그대로 둡니다) ...

class BettingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_close_loop.start() # 봇 시작 시 자동 마감 루프 실행

    def cog_unload(self):
        self.auto_close_loop.cancel() # Cog가 언로드될 때 루프 정지

    # 💡 30초마다 자동으로 예약된 마감 시간이 지났는지 확인하는 백그라운드 루프
    @tasks.loop(seconds=30)
    async def auto_close_loop(self):
        expired_bets = await get_expired_bets()
        for bet in expired_bets:
            topic = bet['topic']
            await update_bet_status(topic, 'closed')

            try:
                channel = self.bot.get_channel(bet['channel_id'])
                if not channel:
                    channel = await self.bot.fetch_channel(bet['channel_id'])

                msg = await channel.fetch_message(bet['message_id'])

                # 버튼 비활성화
                view = BettingView(topic, bet['option_a'], bet['option_b'])
                for child in view.children:
                    child.disabled = True

                embed = await generate_bet_embed(topic, bet['option_a'], bet['option_b'], "closed")
                await msg.edit(embed=embed, view=view)

                # 알림 메시지 전송
                await channel.send(f"⏰ 예약된 시간이 되어 [{topic}] 승부예측이 자동으로 마감되었습니다!")
            except Exception as e:
                print(f"🚨 [자동 마감 에러] {topic} 처리 중 문제 발생: {e}")

    @auto_close_loop.before_loop
    async def before_auto_close_loop(self):
        await self.bot.wait_until_ready() # 봇이 완전히 켜진 후 루프 시작

    # ... (기존 승부예측_생성, 승부예측_마감 등의 명령어는 그대로 둡니다) ...

    # 💡 신규 예약 명령어 추가
    @app_commands.command(name="마감예약", description="승부예측 마감 시간을 예약합니다. (관리자 전용)")
    @app_commands.describe(주제="예약할 승부예측 주제", 날짜="형식: YYYY-MM-DD (예: 2026-07-08)", 시간="형식: HH:MM (예: 18:30)")
    @app_commands.checks.has_permissions(administrator=True)
    async def schedule_close(self, interaction: discord.Interaction, 주제: str, 날짜: str, 시간: str):
        session = await get_bet_session(주제)
        if not session:
            return await interaction.response.send_message("❌ 존재하지 않는 주제입니다.", ephemeral=True)
        if session['status'] != 'active':
            return await interaction.response.send_message("❌ 이미 마감되었거나 종료된 승부예측입니다.", ephemeral=True)

        try:
            # 입력받은 문자열(예: 2026-07-08 18:30)을 datetime 객체로 변환
            dt_str = f"{날짜} {시간}"
            target_dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            target_timestamp = target_dt.timestamp() # Unix 타임스탬프로 변환

            if target_timestamp <= time.time():
                return await interaction.response.send_message("❌ 현재 시간보다 과거의 시간으로 예약할 수 없습니다.", ephemeral=True)

        except ValueError:
            return await interaction.response.send_message("❌ 날짜나 시간 형식이 잘못되었습니다.\n👉 올바른 예시: 날짜 `2026-07-08`, 시간 `18:30`", ephemeral=True)

        await set_bet_close_time(주제, target_timestamp)
        await interaction.response.send_message(f"✅ [{주제}] 승부예측이 {날짜} {시간}에 자동 마감되도록 예약되었습니다!", ephemeral=False)