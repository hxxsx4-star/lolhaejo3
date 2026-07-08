import discord
from discord.ext import commands, tasks
from discord import app_commands
import math
import time
import datetime

from utils.database import (
    consume_item, add_item, create_bet_session, get_bet_session, update_bet_status,
    add_bet_record, get_bet_totals, get_bet_winners, get_user_bet, get_item_amount, get_user_all_bets,
    set_bet_close_time, get_expired_bets,
    get_bet_session_by_message_id  # 💡 [중요] 메시지 ID로 세션을 찾는 DB 함수를 새로 추가하셔야 합니다!
)

def generate_progress_bar(total_a, total_b):
    total = total_a + total_b
    if total == 0:
        return "⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛"

    ratio_a = total_a / total
    blocks_a = round(ratio_a * 10)
    blocks_b = 10 - blocks_a

    return ("🟥" * blocks_a) + ("🟦" * blocks_b)

async def generate_bet_embed(topic, opt_a, opt_b, status="active"):
    totals = await get_bet_totals(topic)
    total_a = totals['A']
    total_b = totals['B']
    total_pool = total_a + total_b

    gauge = generate_progress_bar(total_a, total_b)

    # 📈 유동 배당률 계산 (소수점 2자리까지 표기, 5% 수수료 제외)
    dist_pool = total_pool * 0.95
    odds_a = round(dist_pool / total_a, 2) if total_a > 0 else 1.00
    odds_b = round(dist_pool / total_b, 2) if total_b > 0 else 1.00

    color = discord.Color.green() if status == "active" else discord.Color.dark_gray()
    title_prefix = "🟢 [진행중]" if status == "active" else "🔴 [마감됨]"

    # ✨ 직관적인 안내 멘트로 내용 변경
    if status == "active":
        description = "👇 아래 버튼을 누른 후 베팅할 서사급 알 개수를 입력하세요!"
    else:
        description = "🛑 이 예측은 베팅이 마감되었습니다."

    embed = discord.Embed(title=f"{title_prefix} 예측: {topic}", description=description, color=color)

    # 배당률과 누적 개수를 한눈에 보이게 배치
    embed.add_field(name=f"🟥 옵션 A: {opt_a}", value=f"📊 배당률: {odds_a}배\n(누적: {total_a}개)", inline=True)
    embed.add_field(name=f"🟦 옵션 B: {opt_b}", value=f"📊 배당률: {odds_b}배\n(누적: {total_b}개)", inline=True)

    # 현재 비율 게이지와 총상금
    embed.add_field(name="현재 베팅 비율", value=f"{gauge}\n💰 총 상금 풀: {total_pool}개 (수수료 5% 제외 후 분배)", inline=False)

    return embed

class BetInputModal(discord.ui.Modal):
    def __init__(self, topic: str, option: str, opt_name: str, view: discord.ui.View):
        super().__init__(title=f"{opt_name}에 베팅하기")
        self.topic = topic
        self.option = option # 'A' or 'B'
        self.view = view

        self.amount = discord.ui.TextInput(
            label="베팅할 서사급 알의 개수를 입력하세요",
            placeholder="숫자만 입력 (예: 10)",
            min_length=1,
            max_length=5,
            required=True
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message("❌ 올바른 숫자를 입력해주세요.", ephemeral=True)

        if bet_amount <= 0:
            return await interaction.response.send_message("❌ 1개 이상의 알을 베팅해야 합니다.", ephemeral=True)

        user_id = interaction.user.id

        # 유저가 다른 옵션에 베팅했는지 확인
        existing_bet = await get_user_bet(self.topic, user_id)
        if existing_bet and existing_bet[0] != self.option:
            return await interaction.response.send_message("❌ 이미 반대쪽 옵션에 베팅하셨습니다! 양방향 베팅은 불가능합니다.", ephemeral=True)

        # 서사급 알 차감
        success = await consume_item(user_id, "서사급 알", bet_amount)
        if not success:
            current_eggs = await get_item_amount(user_id, "서사급 알")
            return await interaction.response.send_message(f"❌ 서사급 알이 부족합니다! (현재 보유량: {current_eggs}개)", ephemeral=True)

        # 베팅 기록 추가
        await add_bet_record(self.topic, user_id, self.option, bet_amount)

        # 실시간 임베드 업데이트
        session = await get_bet_session(self.topic)
        new_embed = await generate_bet_embed(self.topic, session['option_a'], session['option_b'], session['status'])

        await interaction.message.edit(embed=new_embed, view=self.view)
        await interaction.response.send_message(f"✅ 성공적으로 `{bet_amount}`개의 서사급 알을 베팅했습니다!", ephemeral=True)

class BettingView(discord.ui.View):
    def __init__(self, topic: str, opt_a_name: str, opt_b_name: str, disabled: bool = False):
        super().__init__(timeout=None)
        self.topic = topic
        self.opt_a_name = opt_a_name
        self.opt_b_name = opt_b_name

        # disabled 파라미터를 받아 버튼 상태를 한 번에 제어할 수 있도록 수정
        self.bet_a_button.disabled = disabled
        self.bet_b_button.disabled = disabled

    @discord.ui.button(label="옵션 A 베팅", style=discord.ButtonStyle.danger, emoji="🟥", custom_id="bet_a")
    async def bet_a_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = await get_bet_session(self.topic)
        if session['status'] != 'active':
            return await interaction.response.send_message("❌ 이미 마감된 예측입니다.", ephemeral=True)
        await interaction.response.send_modal(BetInputModal(self.topic, 'A', self.opt_a_name, self))

    @discord.ui.button(label="옵션 B 베팅", style=discord.ButtonStyle.primary, emoji="🟦", custom_id="bet_b")
    async def bet_b_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = await get_bet_session(self.topic)
        if session['status'] != 'active':
            return await interaction.response.send_message("❌ 이미 마감된 예측입니다.", ephemeral=True)
        await interaction.response.send_modal(BetInputModal(self.topic, 'B', self.opt_b_name, self))

class BettingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_close_loop.start()

    def cog_unload(self):
        self.auto_close_loop.cancel()

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

                # 💡 disabled=True 플래그를 전달하여 버튼이 완전히 비활성화된 뷰 생성
                view = BettingView(topic, bet['option_a'], bet['option_b'], disabled=True)
                embed = await generate_bet_embed(topic, bet['option_a'], bet['option_b'], "closed")

                await msg.edit(embed=embed, view=view)
                await channel.send(f"⏰ 예약된 시간이 되어 [{topic}] 예측이 자동으로 마감되었습니다!")
            except Exception as e:
                print(f"🚨 [자동 마감 에러] {topic} 처리 중 문제 발생: {e}")

    @auto_close_loop.before_loop
    async def before_auto_close_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="예측생성", description="새로운 예측을 생성합니다. (관리자 전용)")
    @app_commands.checks.has_permissions(administrator=True)
    async def create_bet(self, interaction: discord.Interaction, 주제: str, 옵션a: str, 옵션b: str):
        existing = await get_bet_session(주제)
        if existing:
            return await interaction.response.send_message("❌ 이미 동일한 이름의 주제가 존재합니다.", ephemeral=True)

        embed = await generate_bet_embed(주제, 옵션a, 옵션b, "active")
        view = BettingView(주제, 옵션a, 옵션b)

        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()

        await create_bet_session(주제, 옵션a, 옵션b, msg.id, interaction.channel.id)

    @app_commands.command(name="예측마감", description="특정 예측의 베팅을 더 이상 받지 않도록 마감합니다. (버튼 비활성화)")
    @app_commands.checks.has_permissions(administrator=True)
    async def close_bet(self, interaction: discord.Interaction, 주제: str):
        session = await get_bet_session(주제)
        if not session:
            return await interaction.response.send_message("❌ 존재하지 않는 주제입니다.", ephemeral=True)
        if session['status'] != 'active':
            return await interaction.response.send_message("❌ 이미 마감되었거나 종료된 예측입니다.", ephemeral=True)

        await update_bet_status(주제, 'closed')

        try:
            channel = self.bot.get_channel(session['channel_id'])
            msg = await channel.fetch_message(session['message_id'])

            # 💡 disabled=True를 전달하여 버튼 비활성화 적용
            view = BettingView(주제, session['option_a'], session['option_b'], disabled=True)
            embed = await generate_bet_embed(주제, session['option_a'], session['option_b'], "closed")

            await msg.edit(embed=embed, view=view)
        except Exception as e:
            print(f"Message edit failed: {e}")

        await interaction.response.send_message(f"✅ `{주제}` 예측의 베팅이 성공적으로 마감(버튼 비활성화)되었습니다.")

    # 💡 주제 대신 메시지ID와 승리옵션을 받도록 변경됨
    @app_commands.command(name="예측결과", description="마감된 예측의 결과를 확정하고 상금을 분배합니다.")
    @app_commands.describe(메시지id="결과를 발표할 예측 메시지의 ID", 승리옵션="승리한 옵션을 선택하세요")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.choices(승리옵션=[
        app_commands.Choice(name="옵션 A", value="A"),
        app_commands.Choice(name="옵션 B", value="B")
    ])
    async def result_bet(self, interaction: discord.Interaction, 메시지id: str, 승리옵션: app_commands.Choice[str]):
        try:
            msg_id_int = int(메시지id)
        except ValueError:
            return await interaction.response.send_message("❌ 메시지 ID는 숫자여야 합니다.", ephemeral=True)

        # 💡 메시지 ID를 기반으로 세션을 찾습니다.
        session = await get_bet_session_by_message_id(msg_id_int)
        if not session:
            return await interaction.response.send_message("❌ 해당 메시지 ID로 등록된 예측을 찾을 수 없거나 데이터베이스에 함수가 구현되지 않았습니다.", ephemeral=True)

        주제 = session['topic'] # 세션에서 주제 추출

        if session['status'] == 'finished':
            return await interaction.response.send_message("❌ 이미 정산이 완료된 예측입니다.", ephemeral=True)
        if session['status'] == 'active':
            return await interaction.response.send_message("❌ 아직 베팅이 진행 중입니다. `/예측마감`을 먼저 사용해주세요.", ephemeral=True)

        win_opt = 승리옵션.value
        win_name = session['option_a'] if win_opt == 'A' else session['option_b']

        totals = await get_bet_totals(주제)
        total_a, total_b = totals['A'], totals['B']
        total_pool = total_a + total_b

        system_fee = int(total_pool * 0.05)
        distributable_pool = total_pool - system_fee
        win_pool = total_a if win_opt == 'A' else total_b

        await update_bet_status(주제, 'finished')

        if win_pool == 0:
            return await interaction.response.send_message(f"🏆 `{주제}`의 결과는 {win_name} 입니다!\n승리 옵션에 베팅한 유저가 없어 배당금이 시스템으로 환수되었습니다.")

        winners = await get_bet_winners(주제, win_opt)
        payout_logs = []

        for user_id, amount in winners:
            share_ratio = amount / win_pool
            reward = int(math.floor(share_ratio * distributable_pool))

            if reward > 0:
                await add_item(user_id, "서사급 알", reward)
                payout_logs.append(f"<@{user_id}>: {reward}개 (원금 {amount}개)")

        result_desc = f"총 베팅 풀 `{total_pool}개` 중 5%(`{system_fee}개`) 수수료를 제외한 `{distributable_pool}개`가 분배되었습니다.\n\n🎉 당첨자 목록\n"
        result_desc += "\n".join(payout_logs) if payout_logs else "상금을 받은 유저가 없습니다."

        embed = discord.Embed(title=f"🎊 예측 결과 발표: {주제}", description=result_desc, color=discord.Color.gold())
        embed.add_field(name="승리", value=f"👑 {win_name}", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="마감예약", description="예측 마감 시간을 예약합니다. (관리자 전용)")
    @app_commands.describe(주제="예약할 예측 주제", 날짜="형식: YYYY-MM-DD (예: 2026-07-08)", 시간="형식: HH:MM (예: 18:30)")
    @app_commands.checks.has_permissions(administrator=True)
    async def schedule_close(self, interaction: discord.Interaction, 주제: str, 날짜: str, 시간: str):
        session = await get_bet_session(주제)
        if not session:
            return await interaction.response.send_message("❌ 존재하지 않는 주제입니다.", ephemeral=True)
        if session['status'] != 'active':
            return await interaction.response.send_message("❌ 이미 마감되었거나 종료된 예측입니다.", ephemeral=True)

        try:
            dt_str = f"{날짜} {시간}"
            target_dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            target_timestamp = target_dt.timestamp()

            if target_timestamp <= time.time():
                return await interaction.response.send_message("❌ 현재 시간보다 과거의 시간으로 예약할 수 없습니다.", ephemeral=True)

        except ValueError:
            return await interaction.response.send_message("❌ 날짜나 시간 형식이 잘못되었습니다.\n👉 올바른 예시: 날짜 `2026-07-08`, 시간 `18:30`", ephemeral=True)

        await set_bet_close_time(주제, target_timestamp)
        await interaction.response.send_message(f"✅ [{주제}] 예측이 {날짜} {시간}에 자동 마감되도록 예약되었습니다!", ephemeral=False)

    @app_commands.command(name="내베팅", description="내가 참여한 예측 내역과 베팅한 알의 개수를 확인합니다.")
    async def my_bets(self, interaction: discord.Interaction):
        records = await get_user_all_bets(interaction.user.id)

        if not records:
            return await interaction.response.send_message("🎒 아직 참여하신 예측 내역이 없습니다.", ephemeral=True)

        embed = discord.Embed(title=f"📊 {interaction.user.display_name}님의 베팅 내역", color=discord.Color.blurple())

        active_bets = []
        closed_bets = []
        finished_bets = []

        for row in records:
            topic = row['topic']
            opt_letter = row['option']
            amount = row['amount']
            status = row['status']

            opt_name = row['option_a'] if opt_letter == 'A' else row['option_b']
            text = f"{topic}\n👉 `{opt_name}`에 {amount}개 베팅"

            if status == 'active': active_bets.append(text)
            elif status == 'closed': closed_bets.append(text)
            elif status == 'finished': finished_bets.append(text)

        if active_bets:
            embed.add_field(name="🟢 진행 중인 베팅", value="\n\n".join(active_bets), inline=False)
        if closed_bets:
            embed.add_field(name="🔴 결과 대기 중 (마감됨)", value="\n\n".join(closed_bets), inline=False)
        if finished_bets:
            embed.add_field(name="🏁 정산 완료", value="\n\n".join(finished_bets), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(BettingCog(bot))