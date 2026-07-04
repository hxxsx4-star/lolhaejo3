import discord
from discord.ext import commands
from discord import app_commands

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="도움말", description="봇의 모든 명령어를 확인합니다.")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎲 꼬물이 봇 도움말 🎲",
            description="봇이 제공하는 모든 명령어 목록입니다.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)

        embed.add_field(
            name="🎉 기타 명령어",
            value="`/가챠 라인`: LOL 라인을 무작위로 뽑습니다.\n"
                  "`/가챠 챔피언`: LOL 챔피언을 무작위로 뽑습니다.\n",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
