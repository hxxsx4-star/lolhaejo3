from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands
from discord import app_commands

from utils.database import add_quest_progress, get_quest_row, set_quest_claimed, add_item
from .locks import get_user_lock

KST = timezone(timedelta(hours=9))

# 일일 퀘스트 정의: (필드, 제목, 목표치, 보상 서사급 알, 비트)
QUESTS = [
    ("walk",   "🚶 산책 30회",        30, 30, 1),
    ("care",   "🍚 돌보기 3회 (밥/샤워)", 3,  20, 2),
    ("battle", "⚔️ 배틀 1회 참여",      1,  50, 4),
]
ALL_CLEAR_BONUS = 100   # 3개 전부 달성 시 추가 서사급 알
ALL_CLEAR_BIT = 8


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


async def quest_hook(user_id: int, field: str, amount: int = 1):
    """산책/돌보기/배틀 코드에서 호출하는 진행도 훅."""
    try:
        await add_quest_progress(user_id, today_kst(), field, amount)
    except Exception as e:
        print(f"⚠️ 일일 퀘스트 진행도 기록 실패({field}): {e}")


class QuestClaimView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    @discord.ui.button(label="🎁 완료 보상 받기", style=discord.ButtonStyle.success)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ 본인만 수령할 수 있습니다.", ephemeral=True)

        qdate = today_kst()
        async with get_user_lock(self.user_id):
            row = await get_quest_row(self.user_id, qdate)
            if not row:
                return await interaction.response.send_message("❌ 오늘 진행한 퀘스트가 없습니다.", ephemeral=True)

            claimed = row['claimed'] or 0
            total_eggs = 0
            gained = []
            done_count = 0

            for field, title, goal, reward, bit in QUESTS:
                if (row[field] or 0) >= goal:
                    done_count += 1
                    if not claimed & bit:
                        total_eggs += reward
                        claimed |= bit
                        gained.append(f"{title} → 서사급 알 +{reward}")

            if done_count == len(QUESTS) and not claimed & ALL_CLEAR_BIT:
                total_eggs += ALL_CLEAR_BONUS
                claimed |= ALL_CLEAR_BIT
                gained.append(f"🌟 올클리어 보너스 → 서사급 알 +{ALL_CLEAR_BONUS}")

            if not gained:
                return await interaction.response.send_message("❌ 수령할 완료 보상이 없습니다. (미완료거나 이미 수령함)", ephemeral=True)

            await add_item(self.user_id, "서사급 알", total_eggs)
            await set_quest_claimed(self.user_id, qdate, claimed)

        embed = discord.Embed(
            title="🎉 일일 퀘스트 보상 수령!",
            description="\n".join(gained) + f"\n\n🥚 총 **서사급 알 {total_eggs}개** 획득!",
            color=discord.Color.gold())
        await interaction.response.edit_message(embed=embed, view=None)


class DailyQuestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="일일퀘스트", description="오늘의 퀘스트 진행 상황을 확인하고 보상을 받습니다. (매일 0시 초기화, KST)")
    async def daily_quest(self, interaction: discord.Interaction):
        row = await get_quest_row(interaction.user.id, today_kst())
        claimed = (row['claimed'] if row else 0) or 0

        lines = []
        done_count = 0
        for field, title, goal, reward, bit in QUESTS:
            cur = min((row[field] if row else 0) or 0, goal)
            done = cur >= goal
            if done:
                done_count += 1
            mark = "✅" if done else "▫️"
            got = " (수령완료)" if claimed & bit else ""
            lines.append(f"{mark} {title} — **{cur}/{goal}** · 보상 🥚{reward}{got}")

        bonus_mark = "✅" if done_count == len(QUESTS) else "▫️"
        bonus_got = " (수령완료)" if claimed & ALL_CLEAR_BIT else ""
        lines.append(f"{bonus_mark} 🌟 올클리어 보너스 — 보상 🥚{ALL_CLEAR_BONUS}{bonus_got}")

        embed = discord.Embed(
            title=f"📋 오늘의 퀘스트 ({today_kst()})",
            description="\n".join(lines) + "\n\n완료한 퀘스트는 아래 버튼으로 보상을 받으세요!",
            color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=QuestClaimView(interaction.user.id), ephemeral=True)


async def setup(bot):
    await bot.add_cog(DailyQuestCog(bot))
