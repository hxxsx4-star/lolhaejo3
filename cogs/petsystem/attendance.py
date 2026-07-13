import discord
from discord.ext import commands
from discord import app_commands

from utils.game import check_in, get_attendance_status, ATTENDANCE_REWARDS, ATTENDANCE_CYCLE


def _reward_line(day: int, rw: dict, marker: str) -> str:
    bonus = f" + {rw['bonus_egg']}급 알 1개" if rw.get("bonus_egg") else ""
    return f"{marker} **{day}일차** — 🥚 서사알 {rw['eggs']} · 💰 {rw['points']}P{bonus}"


def _build_embed(status: dict, title: str, color) -> discord.Embed:
    """출석 보상표 + 현재 연속/누적 현황을 담은 임베드."""
    checked = status["checked_today"]
    today_day = status["today_day"]

    lines = []
    for i, rw in enumerate(ATTENDANCE_REWARDS, start=1):
        if i == today_day:
            marker = "✅" if checked else "▶️"
        else:
            marker = "▫️"
        lines.append(_reward_line(i, rw, marker))

    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="🎁 7일 연속 출석 보상", value="\n".join(lines), inline=False)
    embed.add_field(name="🔥 연속 출석", value=f"**{status['streak']}일**", inline=True)
    embed.add_field(name="📅 누적 출석", value=f"**{status['total']}일**", inline=True)
    foot = "매일 0시(KST) 초기화 · 하루라도 빠지면 1일차부터 다시!"
    embed.set_footer(text=foot)
    return embed


class AttendanceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="출석", description="하루 1회 출석하고 연속 출석 보상을 받습니다. (KST 기준)")
    async def attendance(self, interaction: discord.Interaction):
        res = await check_in(interaction.user.id)

        if not res["ok"]:
            # 이미 출석했으면 현황만 보여줌
            status = await get_attendance_status(interaction.user.id)
            embed = _build_embed(status, "📅 오늘은 이미 출석했어요!", discord.Color.greyple())
            embed.description = f"내일 또 만나요! (연속 {res['streak']}일 유지 중)"
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        status = await get_attendance_status(interaction.user.id)
        title = "🎉 출석 완료!"
        if res["cycle_day"] == ATTENDANCE_CYCLE:
            title = "🎊 7일 연속 출석 대박 보상!"

        embed = _build_embed(status, title, discord.Color.gold())
        desc = f"🔥 **{res['streak']}일 연속 출석!**\n\n"
        if res.get("reset"):
            desc = "😢 연속 출석이 끊겨서 1일차부터 다시 시작!\n\n"
        desc += f"🥚 서사급 알 **+{res['eggs']}**\n💰 포인트 **+{res['points']}P**"
        if res.get("bonus_egg"):
            desc += f"\n✨ **{res['bonus_egg']}급 알 +1** (7일차 보너스!)"
        embed.description = desc
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AttendanceCog(bot))
