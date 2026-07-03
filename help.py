import discord
from discord.ext import commands
from discord import app_commands

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="도움말", description="봇의 모든 명령어를 확인합니다.")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎲 롤 내전 봇 도움말 🎲",
            description="봇이 제공하는 모든 명령어 목록입니다.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)

        # 1. 가챠 및 간단한 명령어
        embed.add_field(
            name="🎉 가챠 & 기타",
            value="`/가챠 라인`: LOL 라인을 무작위로 뽑습니다.\n"
                  "`/가챠 챔피언`: LOL 챔피언을 무작위로 뽑습니다.\n"
                  "`/주사위`: 1부터 6까지의 주사위를 굴립니다.",
            inline=False
        )

        # 2. 경제 관련 명령어
        embed.add_field(
            name="💰 포인트 & 경제",
            value="`/지갑 [유저]`: 자신의 또는 다른 유저의 포인트를 확인합니다.\n"
                  "`/출석`: 매일 출석하여 보상을 받습니다.\n"
                  "`/순위`: 서버 내 포인트 랭킹을 확인합니다.\n"
                  "`/지급 <유저> <금액>`: (관리자) 유저에게 포인트를 지급합니다.\n"
                  "`/회수 <유저> <금액>`: (관리자) 유저의 포인트를 회수합니다.",
            inline=False
        )

        # 3. 포커 게임 명령어
        embed.add_field(
            name="🃏 텍사스 홀덤 포커",
            value="`/포커 시작`: 포커 게임 대기실을 만듭니다.\n"
                  "`/포커 참여`: 만들어진 게임에 참여합니다.\n"
                  "`/포커 진행`: (방장) 게임을 시작합니다.",
            inline=False
        )

        # 4. 섯다 게임 명령어
        embed.add_field(
            name="🎴 섯다",
            value="`/섯다 시작 [모드]`: 섯다 게임 대기실을 만듭니다. (2장/3장 모드 선택 가능)\n"
                  "`/섯다 참여`: 만들어진 게임에 참여합니다.\n"
                  "`/섯다 진행`: (방장) 게임을 시작합니다.",
            inline=False
        )
        
        embed.set_footer(text=f"요청자: {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
