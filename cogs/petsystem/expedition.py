import discord
from discord.ext import commands
from discord import app_commands

from utils.database import get_or_migrate_data
from utils.game import (EXPEDITION_DURATIONS, get_expedition_status,
                        start_expedition_for, claim_expedition)
from .combat import calc_pet_power


class ExpeditionStartView(discord.ui.View):
    def __init__(self, user_id: int, pets: list):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.pet_idx = None

        self.pet_select = discord.ui.Select(
            placeholder="① 원정 보낼 전설이를 선택하세요",
            options=[discord.SelectOption(
                label=f"{p.get('name','이름없음')} ({p.get('level',0)}성 {p.get('type','?')})",
                description=f"전투력 {calc_pet_power(p)}", value=str(i))
                for i, p in pets[:25]],
        )
        self.pet_select.callback = self.on_pet
        self.add_item(self.pet_select)

        self.dur_select = discord.ui.Select(
            placeholder="② 원정 시간을 선택하세요",
            options=[discord.SelectOption(label=f"{h}시간", value=str(h)) for h in EXPEDITION_DURATIONS],
        )
        self.dur_select.callback = self.on_duration
        self.add_item(self.dur_select)

    async def on_pet(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ 본인만 선택할 수 있습니다.", ephemeral=True)
        self.pet_idx = int(self.pet_select.values[0])
        await interaction.response.defer()

    async def on_duration(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ 본인만 선택할 수 있습니다.", ephemeral=True)
        if self.pet_idx is None:
            return await interaction.response.send_message("❌ 먼저 전설이를 선택해주세요!", ephemeral=True)

        hours = int(self.dur_select.values[0])
        res = await start_expedition_for(self.user_id, self.pet_idx, hours, calc_pet_power)
        if not res["ok"]:
            return await interaction.response.send_message(f"❌ {res['error']}", ephemeral=True)

        embed = discord.Embed(title="🏕️ 원정 출발!", color=discord.Color.green())
        embed.description = (
            f"**{res['name']}** ({res['level']}성 {res['type']})가 "
            f"**{res['hours']}시간** 원정을 떠났습니다!\n\n"
            f"⚔️ 원정 전투력: **{res['power']}**\n"
            f"🥚 예상 기본 보상: 서사급 알 약 **{res['est_eggs']}개** + 시간당 상위 알 확률\n\n"
            f"⏰ {res['hours']}시간 후 `/원정`으로 보상을 수령하세요!"
        )
        await interaction.response.edit_message(embed=embed, view=None)


class ExpeditionClaimView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    @discord.ui.button(label="🎁 보상 받기", style=discord.ButtonStyle.success)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ 본인만 수령할 수 있습니다.", ephemeral=True)

        res = await claim_expedition(self.user_id)
        if not res["ok"]:
            return await interaction.response.send_message(res["error"], ephemeral=True)

        desc = (
            f"**{res['pet_name']}**(이)가 {res['hours']}시간의 원정에서 돌아왔습니다!\n\n"
            f"🥚 서사급 알 **+{res['epic_eggs']}개**\n"
        )
        for rarity in res["bonus_eggs"]:
            desc += f"✨ **{rarity}급 알 +1개** (희귀 발견!)\n"
        desc += f"💰 포인트 **+{res['points']}P**"

        embed = discord.Embed(title="🎉 원정 완료!", description=desc, color=discord.Color.gold())
        await interaction.response.edit_message(embed=embed, view=None)


class ExpeditionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="원정", description="전설이를 원정 보내 알과 포인트를 획득합니다. (유저당 1회 진행)")
    async def expedition(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        status = await get_expedition_status(user_id)

        if status:
            if status["done"]:
                embed = discord.Embed(
                    title="🏕️ 원정 완료 대기 중!",
                    description=f"**{status['pet_name']}**(이)가 원정에서 돌아왔습니다!\n아래 버튼으로 보상을 수령하세요.",
                    color=discord.Color.gold())
                return await interaction.response.send_message(embed=embed, view=ExpeditionClaimView(user_id), ephemeral=True)
            remain_min = status["remain_sec"] // 60 + 1
            embed = discord.Embed(
                title="🏕️ 원정 진행 중",
                description=(f"**{status['pet_name']}** ({status['pet_level']}성 {status['pet_type']}) 원정 중...\n"
                             f"⏰ 남은 시간: 약 **{remain_min // 60}시간 {remain_min % 60}분**"),
                color=discord.Color.blue())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        wrapper = await get_or_migrate_data(user_id)
        eligible = [(i, p) for i, p in enumerate(wrapper.get('pets', [])) if p.get('level', 0) > 0]
        if not eligible:
            return await interaction.response.send_message("❌ 원정 보낼 부화한 전설이가 없습니다!", ephemeral=True)

        embed = discord.Embed(
            title="🏕️ 원정 보내기",
            description=("전설이를 원정 보내면 시간에 비례해 보상을 받습니다!\n\n"
                         "🥚 기본: 시간당 서사급 알 (전투력 비례 증가)\n"
                         "✨ 시간당 확률: 전설 5% · 신화 1.2% · 프레스티지 0.25% · 고귀 0.03%\n"
                         "💰 시간당 20P\n\n"
                         "👇 전설이와 시간을 선택하세요."),
            color=discord.Color.green())
        await interaction.response.send_message(embed=embed, view=ExpeditionStartView(user_id, eligible), ephemeral=True)


async def setup(bot):
    await bot.add_cog(ExpeditionCog(bot))
