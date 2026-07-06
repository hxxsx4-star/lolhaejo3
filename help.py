import discord
from discord.ext import commands
from discord import app_commands

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    help_group = app_commands.Group(name="도움말", description="봇의 명령어 목록을 확인합니다.")

    @help_group.command(name="일반", description="일반 사용자를 위한 명령어 목록을 확인합니다.")
    async def help_general(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎲 전설이 키우기 봇 도움말 🎲",
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

        # 3. 펫 시스템 명령어
        embed.add_field(
            name="🐾 전설이 시스템",
            value="`/알까기 <이름>`: 새로운 전설이를 얻고 이름을 지어줍니다.\n"
                  "`/상태창`: 전설이의 현재 상태를 확인하고 돌봅니다.\n"
                  "`/펫교체 <슬롯>`: 돌볼 전설이를 다른 전설이로 교체합니다.\n"
                  "`/스탯 [유저]`: 나와 다른 유저의 전설이 스탯을 확인합니다.\n"
                  "`/보관함`: 보유 중인 아이템을 확인하고 사용합니다.\n"
                  "`/전설이목록`: 획득 가능한 모든 전설이의 종류를 봅니다.\n"
                  "`/아이템목록`: 게임 내 모든 아이템의 효과를 봅니다.\n"
                  "`/알환전`: 하위 등급 알을 상위 등급 알로 교환합니다.\n"
                  "`/알분해`: 상위 등급 알을 하위 등급 알로 분해합니다.",
            inline=False
        )
        
        embed.set_footer(text=f"요청자: {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.response.send_message(embed=embed)

    @help_group.command(name="관리자", description="[관리자] 관리자를 위한 명령어 목록을 확인합니다.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def help_admin(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛠️ 전설이 키우기 봇 관리자 도움말 🛠️",
            description="관리자 전용 명령어 목록입니다.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)

        embed.add_field(
            name="📦 아이템 관리",
            value="`/아이템지급 <유저> <종류> <개수>`: 유저에게 특정 아이템을 지급합니다.\n"
                  "`/아이템회수 <유저> <종류> <개수>`: 유저의 특정 아이템을 회수합니다.\n"
                  "`/아이템확인 <유저>`: 유저의 보관함을 확인합니다.\n"
                  "`/아이템초기화 <유저>`: 유저의 모든 아이템을 삭제합니다.",
            inline=False
        )
        embed.add_field(
            name="🐾 전설이 관리",
            value="`/알지급 <유저> <등급> <알이름> <종류>`: 유저에게 특정 전설이 알을 지급합니다.\n"
                  "`/알회수 <유저> <등급> <알이름> <종류>`: 유저의 특정 전설이를 회수합니다.\n"
                  "`/강제부화 <유저>`: 유저의 활성화된 알을 즉시 부화시킵니다.\n"
                  "`/성급상승 <유저> <알이름>`: 전설이의 성급을 1 올립니다.\n"
                  "`/성급하락 <유저> <알이름>`: 전설이의 성급을 1 내립니다.\n"
                  "`/이름변경 <유저> <알이름> <변경할이름>`: 전설이의 이름을 변경합니다.",
            inline=False
        )
        embed.add_field(
            name="⚙️ 기타 관리",
            value="`/사용법게시 <채널>`: 지정된 채널에 사용법 안내를 게시합니다.",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))