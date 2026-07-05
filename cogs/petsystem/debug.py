import discord
from discord.ext import commands
from discord import app_commands
from utils.stats import get_points

class DebugCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="펫봇지갑", description="펫 봇이 실시간으로 읽고 있는 포인트를 확인합니다.")
    async def check_pet_wallet(self, interaction: discord.Interaction):
        # 펫 봇이 utils/stats.py를 통해 직접 파일을 열어 포인트를 가져옵니다.
        pts = await get_points(interaction.user.id)
        await interaction.response.send_message(f"🔍 펫 봇이 인식한 현재 포인트: {pts}P", ephemeral=True)

async def setup(bot):
    await bot.add_cog(DebugCog(bot))