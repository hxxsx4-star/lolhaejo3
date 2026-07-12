import discord
from discord.ext import commands
from discord import app_commands

from utils.game import (quest_progress, get_quest_status, claim_daily_quests,
                        today_kst, QUESTS, ALL_CLEAR_BONUS)

# 기존 호출부(battle.py 등) 호환용 별칭 — 실제 구현은 utils/game.py
quest_hook = quest_progress


class QuestClaimView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    @discord.ui.button(label="🎁 완료 보상 받기", style=discord.ButtonStyle.success)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ 본인만 수령할 수 있습니다.", ephemeral=True)

        res = await claim_daily_quests(self.user_id)
        if not res["ok"]:
            return await interaction.response.send_message(f"❌ {res['error']}", ephemeral=True)

        embed = discord.Embed(
            title="🎉 일일 퀘스트 보상 수령!",
            description="\n".join(res["gained"]) + f"\n\n🥚 총 **서사급 알 {res['total_eggs']}개** 획득!",
            color=discord.Color.gold())
        await interaction.response.edit_message(embed=embed, view=None)


class DailyQuestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="일일퀘스트", description="오늘의 퀘스트 진행 상황을 확인하고 보상을 받습니다. (매일 0시 초기화, KST)")
    async def daily_quest(self, interaction: discord.Interaction):
        status = await get_quest_status(interaction.user.id)

        lines = []
        for q in status["quests"]:
            mark = "✅" if q["done"] else "▫️"
            got = " (수령완료)" if q["claimed"] else ""
            lines.append(f"{mark} {q['title']} — **{q['cur']}/{q['goal']}** · 보상 🥚{q['reward']}{got}")

        bonus_mark = "✅" if status["all_clear"] else "▫️"
        bonus_got = " (수령완료)" if status["all_clear_claimed"] else ""
        lines.append(f"{bonus_mark} 🌟 올클리어 보너스 — 보상 🥚{status['all_clear_bonus']}{bonus_got}")

        embed = discord.Embed(
            title=f"📋 오늘의 퀘스트 ({status['date']})",
            description="\n".join(lines) + "\n\n완료한 퀘스트는 아래 버튼으로 보상을 받으세요!",
            color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=QuestClaimView(interaction.user.id), ephemeral=True)


async def setup(bot):
    await bot.add_cog(DailyQuestCog(bot))
