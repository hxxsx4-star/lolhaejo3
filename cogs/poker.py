import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from itertools import combinations

# 카드 문양 및 숫자 정의
SUITS = ['♠️', '♥️', '♦️', '♣️']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANK_VALUES = {r: i for i, r in enumerate(RANKS, 2)}

# 🎨 시각 효과용 이미지 URL (원하는 이미지 링크로 교체 가능)
LOBBY_IMAGE_URL = "https://images.unsplash.com/photo-1541278107931-e006523892df?q=80&w=1000&auto=format&fit=crop"
BOARD_THUMBNAIL_URL = "https://cdn-icons-png.flaticon.com/512/1053/1053386.png" # 포커 칩 아이콘
WINNER_IMAGE_URL = "https://images.unsplash.com/photo-1601053916960-91a13e2dfb9a?q=80&w=1000&auto=format&fit=crop"

class Card:
    def __init__(self, suit, rank):
        self.suit = suit
        self.rank = rank
        self.value = RANK_VALUES[rank]

    def __str__(self):
        return f"{self.suit}{self.rank}"

# 5장 족보 판별 함수 (기존 로직 유지)
def evaluate_hand(cards):
    best_score = (-1,)
    best_name = "하이카드"

    for comb in combinations(cards, 5):
        sorted_cards = sorted(comb, key=lambda c: c.value, reverse=True)
        values = [c.value for c in sorted_cards]
        suits = [c.suit for c in sorted_cards]

        is_flush = len(set(suits)) == 1

        # 스트레이트 체크
        unique_vals = sorted(list(set(values)), reverse=True)
        is_straight = False
        straight_high = 0
        if len(unique_vals) >= 5:
            for i in range(len(unique_vals) - 4):
                if unique_vals[i] - unique_vals[i+4] == 4:
                    is_straight = True
                    straight_high = unique_vals[i]
                    break
            # 백스트레이트 (A, 5, 4, 3, 2)
            if not is_straight and set([14, 5, 4, 3, 2]).issubset(set(values)):
                is_straight = True
                straight_high = 5

        val_counts = {v: values.count(v) for v in set(values)}
        counts = sorted(val_counts.values(), reverse=True)
        sorted_by_count = sorted(val_counts.keys(), key=lambda v: (val_counts[v], v), reverse=True)

        score = (-1,)
        name = "하이카드"

        if is_flush and is_straight:
            score = (8, straight_high)
            name = "스트레이트 플러시"
        elif counts == [4, 1]:
            score = (7, sorted_by_count[0], sorted_by_count[1])
            name = "포카드"
        elif counts == [3, 2]:
            score = (6, sorted_by_count[0], sorted_by_count[1])
            name = "풀하우스"
        elif is_flush:
            score = (5, values)
            name = "플러시"
        elif is_straight:
            score = (4, straight_high)
            name = "스트레이트"
        elif counts == [3, 1, 1]:
            score = (3, sorted_by_count[0], values)
            name = "트리플"
        elif counts == [2, 2, 1]:
            score = (2, sorted_by_count[0], sorted_by_count[1], sorted_by_count[2])
            name = "투페어"
        elif counts == [2, 1, 1, 1]:
            score = (1, sorted_by_count[0], values)
            name = "원페어"
        else:
            score = (0, values)
            name = "하이카드"

        if score > best_score:
            best_score = score
            best_name = name

    return best_score, best_name

# 오마하 홀덤 전용 족보 판별 함수
def evaluate_omaha_hand(hand_cards, community_cards):
    """오마하는 무조건 손패 2장 + 공용카드 3장을 조합해야 함"""
    best_score = (-1,)
    best_name = "하이카드"

    # 내 패 4장 중 2장을 뽑는 모든 경우의 수
    for h_comb in combinations(hand_cards, 2):
        # 공용 카드 최대 5장 중 3장을 뽑는 모든 경우의 수
        for c_comb in combinations(community_cards, 3):
            # 정확히 5장을 만들어 평가
            score, name = evaluate_hand(list(h_comb) + list(c_comb))
            if score > best_score:
                best_score = score
                best_name = name

    return best_score, best_name

class PokerGame:
    def __init__(self, host: discord.Member, ante: int, mode: str):
        self.host = host
        self.ante = ante
        self.mode = mode  # "holdem" 또는 "omaha"
        self.players = {}
        self.active_players = []
        self.deck = []
        self.community_cards = []
        self.hands = {}
        self.folded = set()
        self.pot = 0
        self.current_bet = 0
        self.player_bets = {}
        self.turn_index = 0
        self.stage = "LOBBY"

    def reset_for_next_round(self):
        self.deck = [Card(s, r) for s in SUITS for r in RANKS]
        random.shuffle(self.deck)
        self.community_cards = []
        self.hands = {}
        self.folded = set()
        self.pot = 0
        self.current_bet = self.ante
        self.active_players = [p for p, chips in self.players.items() if chips >= self.ante]
        self.player_bets = {p: self.ante for p in self.active_players}

        for p in self.active_players:
            self.players[p] -= self.ante
            self.pot += self.ante

        # 모드에 따른 카드 분배 (홀덤: 2장, 오마하: 4장)
        cards_to_deal = 4 if self.mode == "omaha" else 2
        for p in self.active_players:
            self.hands[p] = [self.deck.pop() for _ in range(cards_to_deal)]

        self.turn_index = 0
        self.stage = "PREFLOP"

class PokerTurnView(discord.ui.View):
    def __init__(self, game: PokerGame, message: discord.Message):
        super().__init__(timeout=120)
        self.game = game
        self.message = message

    async def update_game_state(self, interaction: discord.Interaction):
        active_unfolded = [p for p in self.game.active_players if p not in self.game.folded]

        if len(active_unfolded) <= 1:
            await self.end_game(interaction, active_unfolded[0] if active_unfolded else None)
            return

        all_matched = all(self.game.player_bets[p] == self.game.current_bet for p in active_unfolded)

        self.game.turn_index = (self.game.turn_index + 1) % len(self.game.active_players)
        while self.game.active_players[self.game.turn_index] in self.game.folded:
            self.game.turn_index = (self.game.turn_index + 1) % len(self.game.active_players)

        if all_matched and self.game.turn_index == 0:
            if self.game.stage == "PREFLOP":
                self.game.stage = "FLOP"
                self.game.community_cards.extend([self.game.deck.pop() for _ in range(3)])
            elif self.game.stage == "FLOP":
                self.game.stage = "TURN"
                self.game.community_cards.append(self.game.deck.pop())
            elif self.game.stage == "TURN":
                self.game.stage = "RIVER"
                self.game.community_cards.append(self.game.deck.pop())
            elif self.game.stage == "RIVER":
                await self.end_game(interaction)
                return

            self.game.current_bet = 0
            self.game.player_bets = {p: 0 for p in active_unfolded}
            self.game.turn_index = 0

        await self.render_board(interaction)

    async def render_board(self, interaction: discord.Interaction):
        mode_name = "텍사스 홀덤" if self.game.mode == "holdem" else "오마하 홀덤"
        embed = discord.Embed(title=f"🃏 {mode_name} 진행 중 - {self.game.stage}", color=discord.Color.dark_green())

        # 썸네일 이미지 추가
        embed.set_thumbnail(url=BOARD_THUMBNAIL_URL)

        comm_str = " ".join(str(c) for c in self.game.community_cards) if self.game.community_cards else "🎴 🎴 🎴 (아직 공개되지 않음)"
        embed.add_field(name="공용 카드 (Community Cards)", value=f"### {comm_str}", inline=False)
        embed.add_field(name="💰 총 판돈 (Pot)", value=f"{self.game.pot} 칩", inline=True)

        current_turn_player = self.game.active_players[self.game.turn_index]
        embed.add_field(name="👉 현재 턴", value=f"{current_turn_player.mention}", inline=True)

        player_status = ""
        for p in self.game.active_players:
            status = "❌ 폴드" if p in self.game.folded else f"베팅: {self.game.player_bets[p]}칩 (보유: {self.game.players[p]})"
            prefix = "▶️ " if p == current_turn_player and p not in self.game.folded else ""
            player_status += f"{prefix}{p.display_name}: {status}\n"

        embed.add_field(name="참가자 현황", value=player_status, inline=False)

        if interaction.response.is_done():
            await self.message.edit(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def end_game(self, interaction: discord.Interaction, winner=None):
        self.stop()
        active_unfolded = [p for p in self.game.active_players if p not in self.game.folded]

        embed = discord.Embed(title="🏁 게임 종료! 결과 발표", color=discord.Color.gold())
        embed.set_image(url=WINNER_IMAGE_URL) # 우승 축하 이미지 추가

        comm_str = " ".join(str(c) for c in self.game.community_cards)
        embed.add_field(name="최종 공용 카드", value=f"### {comm_str}", inline=False)

        if winner:
            self.game.players[winner] += self.game.pot
            embed.description = f"다른 플레이어들이 모두 기권하여 {winner.mention}님이 판돈 {self.game.pot}칩을 독식합니다!"
        else:
            best_player = None
            best_hand_score = (-1,)
            best_hand_name = ""
            results = ""

            for p in active_unfolded:
                if self.game.mode == "omaha":
                    # 오마하 족보 판별 (내 패 2장, 공용 3장 강제 조합)
                    score, name = evaluate_omaha_hand(self.game.hands[p], self.game.community_cards)
                else:
                    # 텍사스 홀덤 족보 판별
                    full_hand = self.game.hands[p] + self.game.community_cards
                    score, name = evaluate_hand(full_hand)

                hand_str = " ".join(str(c) for c in self.game.hands[p])
                results += f"{p.display_name} [{hand_str}] 👉 {name}\n"

                if score > best_hand_score:
                    best_hand_score = score
                    best_player = p
                    best_hand_name = name

            self.game.players[best_player] += self.game.pot
            embed.description = f"🎉 우승: {best_player.mention} ({best_hand_name})!\n판돈 {self.game.pot}칩을 획득했습니다!"
            embed.add_field(name="플레이어 패 공개", value=results, inline=False)

        chips_str = "\n".join(f"{p.display_name}: {chips}칩" for p, chips in self.game.players.items())
        embed.add_field(name="💳 현재 칩 현황", value=chips_str, inline=False)

        rematch_view = PokerRematchView(self.game)
        if interaction.response.is_done():
            await self.message.edit(embed=embed, view=rematch_view)
        else:
            await interaction.response.edit_message(embed=embed, view=rematch_view)

    @discord.ui.button(label="🃏 내 패 확인", style=discord.ButtonStyle.secondary)
    async def check_hand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in self.game.hands:
            await interaction.response.send_message("이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
        cards = self.game.hands[interaction.user]
        card_str = " ".join(str(c) for c in cards)
        await interaction.response.send_message(f"🤫 {interaction.user.mention}님의 손패: {card_str}", ephemeral=True)

    @discord.ui.button(label="콜 / 체크", style=discord.ButtonStyle.success)
    async def call_check(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.game.active_players[self.game.turn_index]:
            await interaction.response.send_message("지금은 당신의 턴이 아닙니다!", ephemeral=True)
            return

        diff = self.game.current_bet - self.game.player_bets[interaction.user]
        if diff > self.game.players[interaction.user]:
            diff = self.game.players[interaction.user] # 올인

        self.game.players[interaction.user] -= diff
        self.game.player_bets[interaction.user] += diff
        self.game.pot += diff

        await interaction.response.defer()
        await self.update_game_state(interaction)

    @discord.ui.button(label="레이즈 (+50)", style=discord.ButtonStyle.primary)
    async def raise_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.game.active_players[self.game.turn_index]:
            await interaction.response.send_message("지금은 당신의 턴이 아닙니다!", ephemeral=True)
            return

        raise_amount = (self.game.current_bet - self.game.player_bets[interaction.user]) + 50
        if raise_amount > self.game.players[interaction.user]:
            await interaction.response.send_message("칩이 부족하여 레이즈할 수 없습니다!", ephemeral=True)
            return

        self.game.players[interaction.user] -= raise_amount
        self.game.player_bets[interaction.user] += raise_amount
        self.game.current_bet += 50
        self.game.pot += raise_amount

        await interaction.response.defer()
        await self.update_game_state(interaction)

    @discord.ui.button(label="폴드 (기권)", style=discord.ButtonStyle.danger)
    async def fold_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.game.active_players[self.game.turn_index]:
            await interaction.response.send_message("지금은 당신의 턴이 아닙니다!", ephemeral=True)
            return

        self.game.folded.add(interaction.user)
        await interaction.response.defer()
        await self.update_game_state(interaction)

class PokerRematchView(discord.ui.View):
    def __init__(self, game: PokerGame):
        super().__init__(timeout=60)
        self.game = game

    @discord.ui.button(label="🔄 다음 판 시작 (연전)", style=discord.ButtonStyle.success)
    async def next_round(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.game.host:
            await interaction.response.send_message("방장만 다음 판을 시작할 수 있습니다!", ephemeral=True)
            return

        survivors = {p: c for p, c in self.game.players.items() if c >= self.game.ante}
        if len(survivors) < 2:
            await interaction.response.send_message("남은 플레이어 중 칩이 충분한 사람이 2명 미만이라 연전할 수 없습니다.", ephemeral=True)
            return

        self.game.players = survivors
        self.game.reset_for_next_round()

        turn_view = PokerTurnView(self.game, interaction.message)
        await turn_view.render_board(interaction)

class PokerLobbyView(discord.ui.View):
    def __init__(self, game: PokerGame):
        super().__init__(timeout=180)
        self.game = game
        self.message = None

    @discord.ui.button(label="참가하기 (기본 1000칩)", style=discord.ButtonStyle.primary)
    async def join_poker(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.game.players:
            await interaction.response.send_message("이미 참가하셨습니다!", ephemeral=True)
            return

        self.game.players[interaction.user] = 1000
        await interaction.response.send_message(f"✅ {interaction.user.mention}님이 포커 게임에 참가했습니다!", ephemeral=False)

    @discord.ui.button(label="▶️ 게임 시작", style=discord.ButtonStyle.success)
    async def start_poker(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.game.host:
            await interaction.response.send_message("방장만 게임을 시작할 수 있습니다.", ephemeral=True)
            return
        if len(self.game.players) < 2:
            await interaction.response.send_message("최소 2명 이상 참가해야 시작할 수 있습니다.", ephemeral=True)
            return

        self.game.reset_for_next_round()
        turn_view = PokerTurnView(self.game, self.message)
        await turn_view.render_board(interaction)

class PokerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="포커", description="포커 게임을 시작합니다.")
    @app_commands.describe(
        ante="판마다 기본으로 내야 하는 칩 (기본값: 50)",
        mode="플레이할 포커 모드 (기본: 텍사스 홀덤)"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="텍사스 홀덤 (기본)", value="holdem"),
        app_commands.Choice(name="오마하 홀덤 (손패 4장)", value="omaha")
    ])
    async def poker(self, interaction: discord.Interaction, ante: int = 50, mode: app_commands.Choice[str] = None):
        selected_mode = mode.value if mode else "holdem"
        mode_name = "텍사스 홀덤" if selected_mode == "holdem" else "오마하 홀덤"

        game = PokerGame(host=interaction.user, ante=ante, mode=selected_mode)
        game.players[interaction.user] = 1000

        view = PokerLobbyView(game)
        embed = discord.Embed(
            title=f"🃏 {mode_name} 로비",
            description=f"{interaction.user.display_name}님이 포커 게임을 개설했습니다!\n아래의 `참가하기` 버튼을 눌러 자리에 앉아주세요.\n*(기본 제공: 1,000칩 / 참가비: 매 판 {ante}칩)*",
            color=discord.Color.blue()
        )

        # 로비에 대기방용 배너 이미지 추가
        embed.set_image(url=LOBBY_IMAGE_URL)

        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

async def setup(bot: commands.Bot):
    await bot.add_cog(PokerCog(bot))