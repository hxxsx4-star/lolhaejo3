import discord
import math
import time
import aiosqlite
from utils.database import consume_item, add_item, get_item_amount

# 💡 predictions.db 전용 독립 비동기 로컬 데이터 전송 함수군
async def local_get_bet_session(topic):
    async with aiosqlite.connect('predictions.db') as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM betting_sessions WHERE topic = ?", (topic,)) as cursor:
            return await cursor.fetchone()

async def local_get_bet_session_by_message_id(message_id):
    async with aiosqlite.connect('predictions.db') as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM betting_sessions WHERE message_id = ?", (message_id,)) as cursor:
            return await cursor.fetchone()

async def local_update_bet_status(topic, status):
    async with aiosqlite.connect('predictions.db') as db:
        await db.execute("UPDATE betting_sessions SET status = ? WHERE topic = ?", (status, topic))
        await db.commit()

async def local_create_bet_session(topic, opt_a, opt_b, msg_id, ch_id):
    async with aiosqlite.connect('predictions.db') as db:
        await db.execute("INSERT INTO betting_sessions (topic, option_a, option_b, status, message_id, channel_id) VALUES (?, ?, ?, 'active', ?, ?)",
                         (topic, opt_a, opt_b, msg_id, ch_id))
        await db.commit()

async def local_add_bet_record(topic, user_id, option, amount):
    async with aiosqlite.connect('predictions.db') as db:
        # 동시 베팅 시 잠금 충돌로 실패하지 않도록 잠깐 대기합니다.
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute('''INSERT INTO betting_records (topic, user_id, option, amount)
                          VALUES (?, ?, ?, ?)
                          ON CONFLICT(topic, user_id) DO UPDATE SET amount = amount + ?''',
                       (topic, user_id, option, amount, amount))
        await db.commit()

async def local_get_bet_totals(topic):
    async with aiosqlite.connect('predictions.db') as db:
        async with db.execute("SELECT option, SUM(amount) FROM betting_records WHERE topic = ? GROUP BY option", (topic,)) as cursor:
            rows = await cursor.fetchall()
        totals = {'A': 0, 'B': 0}
        for row in rows:
            totals[row[0]] = row[1]
        return totals

async def local_get_bet_winners(topic, win_option):
    async with aiosqlite.connect('predictions.db') as db:
        async with db.execute("SELECT user_id, amount FROM betting_records WHERE topic = ? AND option = ?", (topic, win_option)) as cursor:
            return await cursor.fetchall()

async def local_get_user_bet(topic, user_id):
    async with aiosqlite.connect('predictions.db') as db:
        async with db.execute("SELECT option, amount FROM betting_records WHERE topic = ? AND user_id = ?", (topic, user_id)) as cursor:
            return await cursor.fetchone()

async def local_get_user_all_bets(user_id):
    async with aiosqlite.connect('predictions.db') as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT r.topic, r.option, r.amount, s.status, s.option_a, s.option_b
            FROM betting_records r
            JOIN betting_sessions s ON r.topic = s.topic
            WHERE r.user_id = ?
        ''', (user_id,)) as cursor:
            return await cursor.fetchall()

async def local_set_bet_close_time(topic, close_at):
    async with aiosqlite.connect('predictions.db') as db:
        await db.execute("UPDATE betting_sessions SET close_at = ? WHERE topic = ?", (close_at, topic))
        await db.commit()

async def local_get_expired_bets():
    now = time.time()
    async with aiosqlite.connect('predictions.db') as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM betting_sessions WHERE status = 'active' AND close_at IS NOT NULL AND close_at <= ?", (now,)) as cursor:
            return await cursor.fetchall()

def generate_progress_bar(total_a, total_b):
    total = total_a + total_b
    if total == 0:
        return "⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛"

    ratio_a = total_a / total
    blocks_a = round(ratio_a * 10)
    blocks_b = 10 - blocks_a

    return ("🟥" * blocks_a) + ("🟦" * blocks_b)

async def generate_bet_embed(topic, opt_a, opt_b, status="active"):
    totals = await local_get_bet_totals(topic)
    total_a = totals['A']
    total_b = totals['B']
    total_pool = total_a + total_b

    gauge = generate_progress_bar(total_a, total_b)

    dist_pool = total_pool * 0.95
    odds_a = round(dist_pool / total_a, 2) if total_a > 0 else 1.00
    odds_b = round(dist_pool / total_b, 2) if total_b > 0 else 1.00

    color = discord.Color.green() if status == "active" else discord.Color.dark_gray()
    title_prefix = "🟢 [진행중]" if status == "active" else "🔴 [마감됨]"

    if status == "active":
        description = "👇 아래 버튼을 누른 후 베팅할 서사급 알 개수를 직접 입력하세요!"
    else:
        description = "🛑 이 예측은 베팅이 마감되었습니다."

    embed = discord.Embed(title=f"{title_prefix} 예측: {topic}", description=description, color=color)

    embed.add_field(name=f"🟥 옵션 A: {opt_a}", value=f"📊 배당률: {odds_a}배\n(누적: {total_a}개)", inline=True)
    embed.add_field(name=f"🟦 옵션 B: {opt_b}", value=f"📊 배당률: {odds_b}배\n(누적: {total_b}개)", inline=True)

    embed.add_field(name="현재 베팅 비율", value=f"{gauge}\n💰 총 상금 풀: {total_pool}개 (수수료 5% 제외 후 분배)", inline=False)

    return embed

class BetInputModal(discord.ui.Modal):
    def __init__(self, topic: str, option: str, opt_name: str):
        super().__init__(title=f"{opt_name}에 베팅하기")
        self.topic = topic
        self.option = option # 'A' or 'B'

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

        # 🌟 DB/메시지 수정 작업 전에 먼저 상호작용을 확정(ack)합니다.
        # 사람이 몰려 DB나 메시지 편집이 3초 이상 걸려도 '상호작용 실패'가 뜨지 않습니다.
        await interaction.response.defer(ephemeral=True, thinking=True)

        user_id = interaction.user.id

        # 베팅 도중 마감됐을 수 있으므로 상태를 다시 확인합니다.
        session = await local_get_bet_session(self.topic)
        if not session:
            return await interaction.followup.send("❌ 예측 정보를 찾을 수 없습니다.", ephemeral=True)
        if session['status'] != 'active':
            return await interaction.followup.send("❌ 이미 마감된 예측입니다.", ephemeral=True)

        existing_bet = await local_get_user_bet(self.topic, user_id)
        if existing_bet and existing_bet[0] != self.option:
            return await interaction.followup.send("❌ 이미 반대쪽 옵션에 베팅하셨습니다! 양방향 베팅은 불가능합니다.", ephemeral=True)

        success = await consume_item(user_id, "서사급 알", bet_amount)
        if not success:
            current_eggs = await get_item_amount(user_id, "서사급 알")
            return await interaction.followup.send(f"❌ 서사급 알이 부족합니다! (현재 보유량: {current_eggs}개)", ephemeral=True)

        await local_add_bet_record(self.topic, user_id, self.option, bet_amount)

        new_embed = await generate_bet_embed(self.topic, session['option_a'], session['option_b'], session['status'])
        try:
            view = BettingView(self.topic, session['option_a'], session['option_b'])
            await interaction.message.edit(embed=new_embed, view=view)
        except Exception as e:
            # 임베드 갱신이 실패(레이트리밋 등)해도 베팅 자체는 이미 성공 처리됨
            print(f"[예측 임베드 갱신 실패] topic={self.topic}: {e}")

        await interaction.followup.send(f"✅ 성공적으로 `{bet_amount}`개의 서사급 알을 베팅했습니다!", ephemeral=True)

class BettingView(discord.ui.View):
    # topic/옵션명을 넘기지 않으면(=봇 재시작 후 등록되는 영구 뷰) 버튼 클릭 시
    # 메시지 ID로 세션을 역추적합니다.
    def __init__(self, topic: str = None, opt_a_name: str = None, opt_b_name: str = None, disabled: bool = False):
        super().__init__(timeout=None)
        self.topic = topic
        self.opt_a_name = opt_a_name
        self.opt_b_name = opt_b_name

        self.bet_a_button.disabled = disabled
        self.bet_b_button.disabled = disabled

    async def _resolve_session(self, interaction: discord.Interaction):
        if self.topic:
            return await local_get_bet_session(self.topic)
        if interaction.message:
            return await local_get_bet_session_by_message_id(interaction.message.id)
        return None

    async def _open_bet_modal(self, interaction: discord.Interaction, option: str):
        try:
            session = await self._resolve_session(interaction)
            if not session:
                return await interaction.response.send_message("❌ 예측 정보를 찾을 수 없습니다.", ephemeral=True)
            if session['status'] != 'active':
                return await interaction.response.send_message("❌ 이미 마감된 예측입니다.", ephemeral=True)

            opt_name = session['option_a'] if option == 'A' else session['option_b']
            await interaction.response.send_modal(BetInputModal(session['topic'], option, opt_name))
        except Exception as e:
            print(f"[예측 버튼 오류] option={option}: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "⚠️ 잠시 처리가 지연되고 있어요. 다시 한 번 눌러주세요.", ephemeral=True
                )

    @discord.ui.button(label="옵션 A 베팅", style=discord.ButtonStyle.danger, emoji="🟥", custom_id="bet_a")
    async def bet_a_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_bet_modal(interaction, 'A')

    @discord.ui.button(label="옵션 B 베팅", style=discord.ButtonStyle.primary, emoji="🟦", custom_id="bet_b")
    async def bet_b_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_bet_modal(interaction, 'B')