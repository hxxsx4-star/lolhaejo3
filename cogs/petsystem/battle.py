import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random

from .database import get_or_migrate_data
from .ui_action import get_pet_stats
from utils.stats import add_points

class BattleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_battles = set()

    def calc_pet_power(self, pet_data):
        if pet_data.get('level', 0) == 0:
            return 0 # 알은 전투력 0
        stats = get_pet_stats(pet_data['type'], pet_data['level'])
        # 간단한 전투력 계산 공식: 스탯의 총합
        return stats['AD'] + stats['DF'] + stats['AP'] + stats['MR']

    @app_commands.command(name="배틀1vs1", description="내 전설이 한 마리를 선택해 상대방과 1vs1 배틀을 벌입니다.")
    async def battle_1v1(self, interaction: discord.Interaction, 상대: discord.Member):
        if interaction.user == 상대 or 상대.bot:
            return await interaction.response.send_message("❌ 봇이나 자기 자신과는 배틀할 수 없습니다.", ephemeral=True)

        if interaction.user.id in self.active_battles or 상대.id in self.active_battles:
            return await interaction.response.send_message("❌ 현재 다른 배틀이 진행 중입니다.", ephemeral=True)

        p1_data = await get_or_migrate_data(interaction.user.id)
        p2_data = await get_or_migrate_data(상대.id)

        p1_pets = [p for p in p1_data.get('pets', []) if p.get('level', 0) > 0]
        p2_pets = [p for p in p2_data.get('pets', []) if p.get('level', 0) > 0]

        if not p1_pets: return await interaction.response.send_message("❌ 배틀에 내보낼 부화한 펫이 없습니다.", ephemeral=True)
        if not p2_pets: return await interaction.response.send_message(f"❌ {상대.display_name}님은 부화한 펫이 없습니다.", ephemeral=True)

        options = [discord.SelectOption(label=f"{p['name']} ({p['type']})", value=str(i)) for i, p in enumerate(p1_pets)]
        select = discord.ui.Select(placeholder="출전시킬 전설이를 선택하세요.", options=options)
        view = discord.ui.View(timeout=60)
        view.add_item(select)

        await interaction.response.send_message("⚔️ 내보낼 전설이를 선택해주세요.", view=view, ephemeral=True)

        async def p1_callback(inter: discord.Interaction):
            p1_chosen_pet = p1_pets[int(select.values[0])]

            p2_options = [discord.SelectOption(label=f"{p['name']} ({p['type']})", value=str(i)) for i, p in enumerate(p2_pets)]
            p2_select = discord.ui.Select(placeholder="방어에 나설 전설이를 선택하세요.", options=p2_options)
            p2_view = discord.ui.View(timeout=60)
            p2_view.add_item(p2_select)

            await inter.response.edit_message(content=f"✅ {p1_chosen_pet['name']} 출전 대기 완료!", view=None)
            req_msg = await inter.channel.send(f"⚔️ {상대.mention}! {interaction.user.mention}님의 1vs1 배틀 신청이 도착했습니다. 방어할 펫을 고르세요!", view=p2_view)

            async def p2_callback(p2_inter: discord.Interaction):
                if p2_inter.user.id != 상대.id:
                    return await p2_inter.response.send_message("❌ 당신은 이 배틀의 대상이 아닙니다.", ephemeral=True)

                p2_chosen_pet = p2_pets[int(p2_select.values[0])]
                await p2_inter.response.edit_message(content="✅ 방어 전설이 선택 완료! 배틀을 시작합니다.", view=None)

                await self.run_battle(inter.channel, interaction.user, 상대, p1_chosen_pet, p2_chosen_pet, is_5v5=False)

            p2_select.callback = p2_callback

        select.callback = p1_callback

    @app_commands.command(name="배틀5vs5", description="보유한 모든 전설이들의 스탯을 합쳐 상대방과 총력전을 펼칩니다.")
    async def battle_5v5(self, interaction: discord.Interaction, 상대: discord.Member):
        if interaction.user == 상대 or 상대.bot:
            return await interaction.response.send_message("❌ 봇이나 자기 자신과는 배틀할 수 없습니다.", ephemeral=True)

        if interaction.user.id in self.active_battles or 상대.id in self.active_battles:
            return await interaction.response.send_message("❌ 현재 다른 배틀이 진행 중입니다.", ephemeral=True)

        class AcceptView(discord.ui.View):
            def __init__(self, cog):
                super().__init__(timeout=60)
                self.cog = cog

            @discord.ui.button(label="총력전 수락!", style=discord.ButtonStyle.danger, emoji="⚔️")
            async def accept(self, inter: discord.Interaction, button: discord.ui.Button):
                if inter.user.id != 상대.id:
                    return await inter.response.send_message("❌ 대상자만 수락할 수 있습니다.", ephemeral=True)

                await inter.response.edit_message(content="🔥 배틀이 시작됩니다!", view=None)
                await self.cog.run_battle(inter.channel, interaction.user, 상대, None, None, is_5v5=True)

        await interaction.response.send_message(f"⚔️ {상대.mention}! {interaction.user.mention}님이 5vs5 총력전을 신청했습니다!", view=AcceptView(self))

    async def run_battle(self, channel, p1, p2, p1_pet, p2_pet, is_5v5):
        self.active_battles.add(p1.id)
        self.active_battles.add(p2.id)

        try:
            if is_5v5:
                p1_data = await get_or_migrate_data(p1.id)
                p2_data = await get_or_migrate_data(p2.id)
                p1_power = sum(self.calc_pet_power(p) for p in p1_data.get('pets', []))
                p2_power = sum(self.calc_pet_power(p) for p in p2_data.get('pets', []))
                battle_title = f"⚔️ 5vs5 총력전: {p1.display_name} VS {p2.display_name} ⚔️"
                p1_desc = "보유한 모든 전설이 참전"
                p2_desc = "보유한 모든 전설이 참전"
            else:
                p1_power = self.calc_pet_power(p1_pet)
                p2_power = self.calc_pet_power(p2_pet)
                battle_title = f"⚔️ 1vs1 배틀: {p1.display_name} VS {p2.display_name} ⚔️"
                p1_desc = f"{p1_pet['name']} ({p1_pet['type']})"
                p2_desc = f"{p2_pet['name']} ({p2_pet['type']})"

            total_power = p1_power + p2_power
            if total_power == 0: total_power = 1

            p1_win_rate = p1_power / total_power
            winner = p1 if random.random() < p1_win_rate else p2

            embed = discord.Embed(title=battle_title, description="🔥 양측 전설이들이 맹렬하게 격돌합니다!\n*(결과를 계산하는 중... 15초 소요)*", color=discord.Color.orange())
            embed.add_field(name=f"🔵 {p1.display_name}", value=f"{p1_desc}\n합산 전투력: {p1_power}", inline=True)
            embed.add_field(name="VS", value="⚡", inline=True)
            embed.add_field(name=f"🔴 {p2.display_name}", value=f"{p2_desc}\n합산 전투력: {p2_power}", inline=True)

            battle_msg = await channel.send(embed=embed)

            # 15초 진행 상황 연출 대기
            await asyncio.sleep(15)

            result_embed = discord.Embed(title=battle_title, color=discord.Color.green())
            result_embed.description = f"🎉 치열한 접전 끝에 {winner.mention}님의 승리!\n\n승자에게는 전리품으로 10포인트가 지급되었습니다!"

            await add_points(winner.id, 10)
            await battle_msg.edit(embed=result_embed)

        finally:
            self.active_battles.discard(p1.id)
            self.active_battles.discard(p2.id)

async def setup(bot):
    await bot.add_cog(BattleCog(bot))