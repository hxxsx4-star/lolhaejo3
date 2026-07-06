import discord
from discord.ext import commands
from discord import app_commands

from .database import consume_item, add_item

class ShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="알환전", description="하위 등급의 알 여러 개를 소모하여 상위 등급의 알을 얻습니다.")
    @app_commands.choices(목표등급=[
        app_commands.Choice(name="전설급 알 (비용: 서사급 알 50개)", value="전설급 알"),
        app_commands.Choice(name="신화급 알 (비용: 전설급 알 20개)", value="신화급 알"),
        app_commands.Choice(name="프레스티지급 알 (비용: 신화급 알 10개)", value="프레스티지급 알")
    ])
    async def exchange_egg(self, interaction: discord.Interaction, 목표등급: str, 개수: int = 1):
        if 개수 <= 0:
            return await interaction.response.send_message("❌ 환전할 개수는 1개 이상이어야 합니다.", ephemeral=True)

        required_item = ""
        cost_per_item = 0

        if 목표등급 == "전설급 알":
            required_item = "서사급 알"
            cost_per_item = 50
        elif 목표등급 == "신화급 알":
            required_item = "전설급 알"
            cost_per_item = 20
        elif 목표등급 == "프레스티지급 알":
            required_item = "신화급 알"
            cost_per_item = 10

        total_cost = cost_per_item * 개수

        success = await consume_item(interaction.user.id, required_item, total_cost)
        if not success:
            return await interaction.response.send_message(f"❌ `{required_item}`이(가) 부족합니다. (필요량: {total_cost}개)", ephemeral=True)

        await add_item(interaction.user.id, 목표등급, 개수)

        embed = discord.Embed(title="♻️ 알 환전 성공!", color=discord.Color.gold())
        embed.description = f"`{required_item}` {total_cost}개를 소모하여\n`{목표등급}` {개수}개를 획득했습니다!"
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(ShopCog(bot))