import discord
from discord.ext import commands
from discord import app_commands
import random
import itertools
from typing import List, Dict, Tuple, Optional

from utils.stats import get_points, spend_points, add_points, format_num

# ───────── 카드 및 덱 정의 ─────────
class SeotdaCard:
    def __init__(self, month: int, is_gwang: bool):
        self.month = month
        self.is_gwang = is_gwang
    def __str__(self):
        label = "광" if self.is_gwang else ""
        return f"{self.month}{label}"
    def get_ascii(self) -> List[str]:
        m_str = str(self.month).ljust(2)
        lbl = "광(光)" if self.is_gwang else "일 반"
        return ["┌───────┐", f"│ 🎴 {m_str}│", f"│ {lbl} │", f"│       │", "└───────┘"]

def render_seotda_cards(cards: List[SeotdaCard]) -> str:
    if not cards: return ""
    lines = ["", "", "", "", ""]
    for card in cards:
        ascii_art = card.get_ascii()
        for i in range(5): lines[i] += ascii_art[i] + "  "
    return "```text\n" + "\n".join(lines) + "\n```"

class SeotdaDeck:
    def __init__(self):
        self.cards = []
        for month in range(1, 11):
            if month in [1, 3, 8]:
                self.cards.extend([SeotdaCard(month, True), SeotdaCard(month, False)])
            else:
                self.cards.extend([SeotdaCard(month, False), SeotdaCard(month, False)])
        self.shuffle()
    def shuffle(self): random.shuffle(self.cards)
    def deal(self, num_cards: int) -> List[SeotdaCard]:
        return [self.cards.pop() for _ in range(num_cards)]

# ───────── 섯다 족보 판별 로직 ─────────
def evaluate_seotda_hand(cards: List[SeotdaCard]) -> Tuple[int, str]:
    m1, m2 = cards[0].month, cards[1].month
    g1, g2 = cards[0].is_gwang, cards[1].is_gwang
    if m1 > m2:
        m1, m2 = m2, m1
        g1, g2 = g2, g1

    if m1 == 3 and m2 == 8 and g1 and g2: return 10000, "🌟 38광땡"
    if m1 == 1 and m2 == 8 and g1 and g2: return 9000, "✨ 18광땡"
    if m1 == 1 and m2 == 3 and g1 and g2: return 9000, "✨ 13광땡"
    if m1 == m2: return 8000 + m1, f"💥 {m1}땡" if m1 != 10 else "💥 장땡"

    if m1 == 1 and m2 == 2: return 7000, "알리"
    if m1 == 1 and m2 == 4: return 6000, "독사"
    if m1 == 1 and m2 == 9: return 5000, "구삥"
    if m1 == 1 and m2 == 10: return 4000, "장삥"
    if m1 == 4 and m2 == 10: return 3000, "장사"
    if m1 == 4 and m2 == 6: return 2000, "세륙"

    total = (m1 + m2) % 10
    if total == 9: return 1009, "갑오"
    if total == 0: return 1000, "망통"
    return 1000 + total, f"{total}끗"

def evaluate_best_seotda_hand(cards: List[SeotdaCard]) -> Tuple[int, str, List[SeotdaCard]]:
    """세장 섯다: 3장 중 2장을 뽑아 가장 높은 족보 반환"""
    best_score = -1
    best_name = ""
    best_combo = []

    for combo in itertools.combinations(cards, 2):
        score, name = evaluate_seotda_hand(list(combo))
        if score > best_score:
            best_score = score
            best_name = name
            best_combo = list(combo)

    return best_score, best_name, best_combo

# ───────── 섯다 게임 상태 관리 ─────────
class SeotdaGame:
    def __init__(self, host_id: int, channel_id: int, mode: int):
        self.host_id = host_id
        self.channel_id = channel_id
        self.mode = mode # 2(기본 섯다) 또는 3(세장 섯다)

        self.players: List[int] = []
        self.active_players: List[int] = []
        self.hands: Dict[int, List[SeotdaCard]] = {}

        self.deck = SeotdaDeck()
        self.pot = 0
        self.current_bet = 0
        self.round_bets: Dict[int, int] = {}

        self.state = "waiting" # waiting, betting_1, betting_2, finished
        self.turn_index = 0
        self.last_raiser: int = 0
        self.message: Optional[discord.Message] = None

    def add_player(self, user_id: int):
        if user_id not in self.players:
            self.players.append(user_id)
            return True
        return False

    def start_game(self) -> bool:
        if len(self.players) < 2: return False
        self.deck = SeotdaDeck()
        self.active_players = self.players.copy()

        for p in self.players:
            self.hands[p] = self.deck.deal(2) # 처음엔 모두 2장씩
            self.round_bets[p] = 0

        self.state = "betting_1"
        self.turn_index = 0
        self.current_bet = 0
        self.last_raiser = self.active_players[0]
        return True

    def get_current_player(self) -> int: return self.active_players[self.turn_index]

    def next_turn(self) -> str:
        """턴을 넘기고, 라운드/게임의 상태(진행, 3장분배, 종료)를 반환합니다."""
        self.turn_index = (self.turn_index + 1) % len(self.active_players)

        if len(self.active_players) == 1:
            self.state = "finished"
            return "finished"

        if self.active_players[self.turn_index] == self.last_raiser:
            if self.mode == 3 and self.state == "betting_1":
                self.state = "betting_2"
                return "next_round" # 세장 섯다: 세 번째 카드 분배 단계
            else:
                self.state = "finished"
                return "finished"
        return "next_turn"

    def handle_bet(self, player_id: int, amount: int):
        spend_points(player_id, amount)
        self.round_bets[player_id] += amount
        self.pot += amount
        if self.round_bets[player_id] > self.current_bet:
            self.current_bet = self.round_bets[player_id]
            self.last_raiser = player_id

    def handle_fold(self, player_id: int):
        self.active_players.remove(player_id)
        if player_id == self.last_raiser and len(self.active_players) > 0:
            self.last_raiser = self.active_players[self.turn_index % len(self.active_players)]
        if self.turn_index >= len(self.active_players): self.turn_index = 0

# ───────── UI View ─────────
class SeotdaBetModal(discord.ui.Modal, title="레이즈 (베팅 금액 입력)"):
    amount = discord.ui.TextInput(label="금액", placeholder="베팅할 포인트를 숫자로 입력하세요", style=discord.TextStyle.short, required=True)
    def __init__(self, cog, game: SeotdaGame):
        super().__init__()
        self.cog = cog
        self.game = game

    async def on_submit(self, interaction: discord.Interaction):
        if not self.amount.value.isdigit():
            await interaction.response.send_message("❌ 숫자만 입력해주세요.", ephemeral=True)
            return
        bet_amount = int(self.amount.value)
        player_id = interaction.user.id
        call_amount = self.game.current_bet - self.game.round_bets.get(player_id, 0)
        total_required = call_amount + bet_amount

        if get_points(player_id) < total_required:
            await interaction.response.send_message(f"❌ 포인트가 부족합니다. (필요: {total_required} P)", ephemeral=True)
            return
        if bet_amount <= 0:
            await interaction.response.send_message("❌ 레이즈 금액은 1 이상이어야 합니다.", ephemeral=True)
            return

        self.game.handle_bet(player_id, total_required)
        await self.cog.process_next_turn(interaction, self.game)

class SeotdaBetView(discord.ui.View):
    def __init__(self, cog, game: SeotdaGame):
        super().__init__(timeout=None)
        self.cog = cog
        self.game = game

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.game.get_current_player():
            await interaction.response.send_message("❌ 당신의 차례가 아닙니다.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="체크 / 콜", style=discord.ButtonStyle.primary)
    async def call_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player_id = interaction.user.id
        call_amount = self.game.current_bet - self.game.round_bets.get(player_id, 0)

        if get_points(player_id) < call_amount:
            await interaction.response.send_message(f"❌ 포인트가 부족하여 콜을 받을 수 없습니다. (필요: {call_amount} P).", ephemeral=True)
            return

        if call_amount > 0: self.game.handle_bet(player_id, call_amount)
        await self.cog.process_next_turn(interaction, self.game)

    @discord.ui.button(label="레이즈", style=discord.ButtonStyle.success)
    async def raise_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SeotdaBetModal(self.cog, self.game))

    @discord.ui.button(label="다이 (폴드)", style=discord.ButtonStyle.danger)
    async def fold_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.handle_fold(interaction.user.id)
        await self.cog.process_next_turn(interaction, self.game)

    @discord.ui.button(label="올인", style=discord.ButtonStyle.secondary)
    async def allin_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player_id = interaction.user.id
        all_in_amount = get_points(player_id)
        if all_in_amount <= 0:
            await interaction.response.send_message("❌ 올인할 포인트가 없습니다.", ephemeral=True)
            return

        self.game.handle_bet(player_id, all_in_amount)
        await self.cog.process_next_turn(interaction, self.game)

# ✨ 다음 판(연전)을 위한 결과 뷰
class SeotdaResultView(discord.ui.View):
    def __init__(self, cog, old_game: SeotdaGame):
        super().__init__(timeout=None)
        self.cog = cog
        self.old_game = old_game

    @discord.ui.button(label="다음 판 (같은 인원)", style=discord.ButtonStyle.secondary)
    async def next_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.old_game.host_id and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ 방장이나 관리자만 다음 판을 생성할 수 있습니다.", ephemeral=True)
            return

        button.disabled = True
        await interaction.response.edit_message(view=self)

        new_game = SeotdaGame(interaction.user.id, interaction.channel_id, self.old_game.mode)
        new_game.players = self.old_game.players.copy()
        self.cog.active_games[interaction.channel_id] = new_game

        mode_text = "세장 섯다" if new_game.mode == 3 else "일반 섯다(2장)"
        embed = discord.Embed(
            title=f"🎴 {mode_text} 대기실 (연전)",
            description=f"{interaction.user.mention}님이 다음 판을 생성했습니다.\n\n멤버가 그대로 유지되었습니다. 방장이 `/섯다 진행`을 누르면 바로 시작합니다.",
            color=discord.Color.dark_red()
        )
        await interaction.channel.send(embed=embed)

# ───────── Cog 구현 ─────────
class SeotdaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_games: Dict[int, SeotdaGame] = {}

    seotda_group = app_commands.Group(name="섯다", description="화투 섯다 게임 명령어입니다.")

    async def process_next_turn(self, interaction: discord.Interaction, game: SeotdaGame):
        """턴을 넘기고 상태에 따라 3번째 카드 분배 및 UI 갱신을 처리합니다."""
        status = game.next_turn()
        await interaction.response.defer()

        if status == "next_round":
            # 세장 섯다: 액티브 플레이어에게 카드 1장씩 더 주고 라운드 초기화
            for p in game.active_players:
                game.hands[p].extend(game.deck.deal(1))
                game.round_bets[p] = 0
            game.current_bet = 0
            game.turn_index = 0
            game.last_raiser = game.active_players[0]

            await interaction.channel.send("🎴 세장 섯다: 살아남은 플레이어들에게 마지막 3번째 카드를 분배했습니다!")
            for p in game.active_players:
                member = interaction.guild.get_member(p)
                if member:
                    try: await member.send(f"🎴 추가된 당신의 패 (총 3장):\n{render_seotda_cards(game.hands[p])}")
                    except: pass

            await self.update_game_message(interaction.channel, game)
        else:
            # next_turn 이거나 finished 일 때
            await self.update_game_message(interaction.channel, game)

    async def update_game_message(self, channel, game: SeotdaGame):
        if game.state == "finished":
            await self.handle_showdown(channel, game)
            return

        round_name = "최종 베팅 라운드 (3장)" if game.state == "betting_2" else "첫 번째 베팅 라운드"
        embed = discord.Embed(title=f"🎴 섯다 진행 중 - {round_name}", color=discord.Color.dark_red())

        current_p = channel.guild.get_member(game.get_current_player())
        p_name = current_p.mention if current_p else "알 수 없는 유저"

        embed.add_field(name="💰 누적 판돈", value=f"{format_num(game.pot)} P", inline=False)
        embed.add_field(name="👉 현재 턴", value=f"{p_name} 님의 차례입니다.\n현재 콜 비용: {game.current_bet - game.round_bets.get(game.get_current_player(), 0)} P", inline=False)

        if game.message: await game.message.edit(embed=embed, view=SeotdaBetView(self, game))
        else: game.message = await channel.send(embed=embed, view=SeotdaBetView(self, game))

    async def handle_showdown(self, channel, game: SeotdaGame):
        embed = discord.Embed(title="🏆 섯다 게임 결과 (패 공개)", color=discord.Color.gold())

        if len(game.active_players) == 1:
            winner_id = game.active_players[0]
            w_member = channel.guild.get_member(winner_id)
            w_name = w_member.mention if w_member else "유저"
            add_points(winner_id, game.pot)
            embed.description = f"다른 플레이어들이 모두 다이(기권)하여 {w_name} 님이 승리했습니다!\n상금: {format_num(game.pot)} P"
        else:
            hand_scores = {}
            for p in game.active_players:
                if game.mode == 3:
                    # 세장 섯다: 3장 중 가장 높은 2장 선택
                    score, name, best_combo = evaluate_best_seotda_hand(game.hands[p])
                    hand_scores[p] = (score, name, best_combo)
                else:
                    score, name = evaluate_seotda_hand(game.hands[p])
                    hand_scores[p] = (score, name, game.hands[p])

            has_gwang_ddaeng = any(s == 9000 for s, _, _ in hand_scores.values())
            has_ddaeng = any(8001 <= s <= 8009 for s, _, _ in hand_scores.values())

            # 특수 족보 처리
            for p_id in game.active_players:
                score, name, active_cards = hand_scores[p_id]
                m1, m2 = sorted([c.month for c in active_cards])
                if m1 == 4 and m2 == 7 and has_gwang_ddaeng:
                    hand_scores[p_id] = (9500, "🕵️ 암행어사 출두!", active_cards)
                elif m1 == 3 and m2 == 7 and has_ddaeng:
                    hand_scores[p_id] = (8500, "🔪 땡잡이!", active_cards)

            best_score = -1
            winners = []
            results = []

            for p_id in game.active_players:
                score, name, active_cards = hand_scores[p_id]
                m = channel.guild.get_member(p_id)
                card_str = ", ".join(str(c) for c in game.hands[p_id])

                # 3장 섯다일 경우, 버린 카드도 함께 표기
                if game.mode == 3:
                    unused = [c for c in game.hands[p_id] if c not in active_cards]
                    discard_str = f" (버린 패: {unused[0]})" if unused else ""
                else: discard_str = ""

                results.append(f"{m.display_name if m else p_id}: {name} [{card_str}]{discard_str}")

                if score > best_score:
                    best_score = score
                    winners = [p_id]
                elif score == best_score:
                    winners.append(p_id)

            embed.add_field(name="📊 플레이어 족보", value="\n".join(results), inline=False)

            prize = game.pot // len(winners)
            w_mentions = []
            for w in winners:
                add_points(w, prize)
                wm = channel.guild.get_member(w)
                w_mentions.append(wm.mention if wm else str(w))
            embed.description = f"승자: {', '.join(w_mentions)}\n획득 상금: 각 {format_num(prize)} P (총 {format_num(game.pot)} P)"

        await channel.send(embed=embed, view=SeotdaResultView(self, game))
        del self.active_games[channel.id]

    @seotda_group.command(name="시작", description="새로운 섯다 게임 로비를 생성합니다.")
    @app_commands.describe(mode="게임 모드를 선택하세요 (기본 2장)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="일반 섯다 (2장)", value=2),
        app_commands.Choice(name="세장 섯다 (3장)", value=3)
    ])
    async def start_seotda(self, interaction: discord.Interaction, mode: app_commands.Choice[int] = None):
        if interaction.channel_id in self.active_games:
            await interaction.response.send_message("❌ 이 채널에서 이미 섯다 게임이 진행 중입니다.", ephemeral=True)
            return

        game_mode = mode.value if mode else 2
        game = SeotdaGame(interaction.user.id, interaction.channel_id, game_mode)
        game.add_player(interaction.user.id)
        self.active_games[interaction.channel_id] = game

        mode_str = "세장 섯다 (3장)" if game_mode == 3 else "일반 섯다 (2장)"
        embed = discord.Embed(
            title=f"🎴 {mode_str} 대기실",
            description=f"{interaction.user.mention}님이 게임을 생성했습니다.\n\n참여를 원하시면 `/섯다 참여`를 입력하세요.\n시작하려면 방장이 `/섯다 진행`을 눌러주세요.",
            color=discord.Color.dark_red()
        )
        await interaction.response.send_message(embed=embed)

    @seotda_group.command(name="참여", description="진행 중인 섯다 게임 로비에 참여합니다.")
    async def join_seotda(self, interaction: discord.Interaction):
        game = self.active_games.get(interaction.channel_id)
        if not game:
            await interaction.response.send_message("❌ 진행 중인 섯다 게임이 없습니다.", ephemeral=True)
            return
        if game.state != "waiting":
            await interaction.response.send_message("❌ 이미 게임이 시작되었습니다.", ephemeral=True)
            return

        if game.add_player(interaction.user.id):
            await interaction.response.send_message(f"✅ {interaction.user.mention}님이 섯다판에 앉았습니다! (현재 {len(game.players)}명)")
        else:
            await interaction.response.send_message("❌ 이미 참여 중입니다.", ephemeral=True)

    @seotda_group.command(name="진행", description="방장 전용: 게임을 시작하고 패를 돌립니다.")
    async def proceed_seotda(self, interaction: discord.Interaction):
        game = self.active_games.get(interaction.channel_id)
        if not game or game.host_id != interaction.user.id:
            await interaction.response.send_message("❌ 방장만 게임을 시작할 수 있습니다.", ephemeral=True)
            return
        if game.state != "waiting":
            await interaction.response.send_message("❌ 게임이 이미 시작되었습니다.", ephemeral=True)
            return

        if not game.start_game():
            await interaction.response.send_message("❌ 최소 2명의 플레이어가 필요합니다.", ephemeral=True)
            return

        await interaction.response.send_message(f"🔥 {'세장 섯다' if game.mode == 3 else '일반 섯다'}를 시작합니다! 개인 DM으로 화투패를 발송했습니다.")

        for p_id in game.players:
            member = interaction.guild.get_member(p_id)
            if member:
                try: await member.send(f"🎴 당신의 패:\n{render_seotda_cards(game.hands[p_id])}")
                except discord.Forbidden: await interaction.channel.send(f"⚠️ {member.mention}님에게 DM을 보낼 수 없습니다. 서버 설정에서 다이렉트 메시지를 허용해주세요.")

        await self.update_game_message(interaction.channel, game)

async def setup(bot: commands.Bot):
    await bot.add_cog(SeotdaCog(bot))