import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
from cogs.petsystem.database import get_or_migrate_data
from utils.stats import get_points, add_points, spend_points # 💡 포인트 함수 연동

active_battles = {}

class BattleView(discord.ui.View):
    def __init__(self, challenger: discord.Member, target: discord.Member, c_pet, t_pet):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.target = target
        self.c_pet = c_pet
        self.t_pet = t_pet
        self.accepted = False

    @discord.ui.button(label="수락하기", style=discord.ButtonStyle.success, emoji="⚔️")
    async def btn_accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id: return
        self.accepted = True

        for child in self.children: child.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(f"⚔️ {self.challenger.display_name}님의 배틀을 수락했습니다! 배틀이 곧 시작됩니다.")

        active_battles[self.challenger.id] = f"{self.target.display_name}의 {self.t_pet['name']}"
        active_battles[self.target.id] = f"{self.challenger.display_name}의 {self.c_pet['name']}"
        self.stop()

    @discord.ui.button(label="거절하기", style=discord.ButtonStyle.danger, emoji="❌")
    async def btn_decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id: return

        for child in self.children: child.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message("배틀을 거절했습니다.")

        try:
            await self.challenger.send(f"❌ {self.target.display_name}님이 배틀 신청을 거절하셨습니다.")
        except discord.Forbidden: pass
        self.stop()

class BattleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="배틀신청", description="다른 유저의 활성화된 전설이에게 배틀을 신청합니다.")
    async def request_battle(self, interaction: discord.Interaction, 상대: discord.Member):
        if 상대.bot or 상대.id == interaction.user.id:
            return await interaction.response.send_message("❌ 올바른 상대를 선택해주세요.", ephemeral=True)

        if interaction.user.id in active_battles:
            return await interaction.response.send_message("❌ 이미 배틀을 진행 중입니다!", ephemeral=True)

        c_wrapper = await get_or_migrate_data(interaction.user.id)
        t_wrapper = await get_or_migrate_data(상대.id)

        if not c_wrapper.get('pets'): return await interaction.response.send_message("❌ 먼저 `/알까기`로 전설이를 뽑아주세요.", ephemeral=True)
        if not t_wrapper.get('pets'): return await interaction.response.send_message("❌ 상대방이 아직 전설이를 보유하고 있지 않습니다.", ephemeral=True)

        c_pet = c_wrapper['pets'][c_wrapper['active_idx']]
        t_pet = t_wrapper['pets'][t_wrapper['active_idx']]

        if c_pet.get('level', 0) == 0: return await interaction.response.send_message("❌ 내 전설이가 알 상태일 때는 배틀을 할 수 없습니다!", ephemeral=True)
        if t_pet.get('level', 0) == 0: return await interaction.response.send_message("❌ 상대방의 전설이가 아직 알 상태입니다!", ephemeral=True)

        view = BattleView(interaction.user, 상대, c_pet, t_pet)

        try:
            dm_channel = await 상대.create_dm()
            embed = discord.Embed(
                title="⚔️ 전설이 배틀 신청이 도착했습니다!",
                description=f"도전자: {interaction.user.display_name}의 `{c_pet['name']}`\n나의 전설이: `{t_pet['name']}`\n\n수락하시겠습니까? (1분 내 미응답 시 자동 거절)",
                color=discord.Color.red()
            )
            await dm_channel.send(embed=embed, view=view)
            await interaction.response.send_message(f"✅ {상대.display_name}님에게 배틀 신청을 보냈습니다. 응답을 기다립니다...", ephemeral=True)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ 상대방의 DM이 막혀있어 배틀을 신청할 수 없습니다.", ephemeral=True)

        await view.wait()

        if view.accepted:
            await asyncio.sleep(10)

            rarity_idx = {"서사": 0, "전설": 1, "신화": 2, "프레스티지": 3}
            c_score = rarity_idx.get(c_pet.get('rarity', '서사'), 0)
            t_score = rarity_idx.get(t_pet.get('rarity', '서사'), 0)

            c_lvl = c_pet.get('level', 1)
            t_lvl = t_pet.get('level', 1)

            win_prob = 50 + ((c_lvl - t_lvl) * 5) + ((c_score - t_score) * 5)
            win_prob = max(5, min(95, win_prob))

            is_challenger_win = random.randint(1, 100) <= win_prob

            winner = interaction.user if is_challenger_win else 상대
            loser = 상대 if is_challenger_win else interaction.user
            w_pet = c_pet['name'] if is_challenger_win else t_pet['name']

            # 💡 [중요] 포인트 변동 적용 (100 ~ 1000 사이)
            bet_points = random.randint(100, 1000)

            # 승자 보상
            await add_points(winner.id, bet_points)

            # 패자 차감 (마이너스 방지)
            loser_current_points = await get_points(loser.id)
            if loser_current_points < bet_points:
                await spend_points(loser.id, loser_current_points)
                actual_lost = loser_current_points
            else:
                await spend_points(loser.id, bet_points)
                actual_lost = bet_points

            result_embed = discord.Embed(
                title="🏆 배틀 결과 발표!",
                description=f"{winner.display_name}의 `{w_pet}`(이)가 치열한 접전 끝에 승리했습니다!\n*(도전자 승률: {win_prob}%)*\n\n"
                            f"💰 {winner.display_name}님은 {bet_points}P를 획득했습니다!\n"
                            f"💸 {loser.display_name}님은 {actual_lost}P를 잃었습니다...",
                color=discord.Color.gold()
            )

            active_battles.pop(interaction.user.id, None)
            active_battles.pop(상대.id, None)

            try:
                await interaction.user.send(embed=result_embed)
                await 상대.send(embed=result_embed)
            except discord.Forbidden: pass

        elif not view.accepted and view.is_finished():
            try:
                await interaction.user.send(f"🕒 {상대.display_name}님이 1분 내에 응답하지 않아 배틀이 자동 취소되었습니다.")
            except discord.Forbidden: pass

    @app_commands.command(name="배틀상황", description="현재 진행 중인 배틀을 텍스트 중계로 구경합니다.")
    async def battle_status(self, interaction: discord.Interaction):
        if interaction.user.id not in active_battles:
            return await interaction.response.send_message("❌ 현재 진행 중인 배틀이 없습니다.", ephemeral=True)

        target_name = active_battles[interaction.user.id]
        await interaction.response.send_message(f"⚔️ 상대: {target_name}")

        msg = await interaction.original_response()

        texts = [
            "치고박고 싸우는 중입니다... 💥",
            "치고박고 싸우는 중입니다... 💥",
            "상대의 공격을 아슬아슬하게 피했습니다! 💨",
            "강력한 한 방이 들어갔습니다! ⚡",
            "결과를 판정 중입니다... ⚖️"
        ]

        for text in texts:
            await asyncio.sleep(1)
            await msg.edit(content=f"⚔️ 상대: {target_name}\n> {text}")

async def setup(bot):
    await bot.add_cog(BattleCog(bot))