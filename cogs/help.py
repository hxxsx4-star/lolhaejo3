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
            name="🐾 전설이 키우기",
            value="`/알까기`: 새로운 전설이 알을 받습니다.\n"
                  "`/상태창`: 내 전설이의 상태를 확인하고 돌봅니다.\n"
                  "`/보관함`: 보유 중인 알과 아이템을 확인/사용합니다.\n"
                  "`/판매`: 아이템을 판매하여 포인트를 얻습니다.",
            inline=False
        )
        embed.add_field(
            name="📚 도감",
            value="`/전설이목록`: 게임에 등장하는 모든 전설이를 봅니다.\n"
                  "`/아이템목록`: 게임에 등장하는 모든 아이템을 봅니다.",
            inline=False
        )
        embed.add_field(
            name="🎉 기타 명령어",
            value="`/가챠 라인`: LOL 라인을 무작위로 뽑습니다.\n"
                  "`/가챠 챔피언`: LOL 챔피언을 무작위로 뽑습니다.\n",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="사용법게시", description="[관리자 전용] 채널에 펫 시스템 사용법 안내를 게시합니다.")
    @app_commands.default_permissions(manage_guild=True)
    async def post_guide(self, interaction: discord.Interaction):
        guide_embed = discord.Embed(
            title="🐾 꼬물이 키우기 가이드 🐾",
            description="나만의 작은 전설이를 키워 3성으로 진화시켜보세요!",
            color=discord.Color.gold()
        )
        guide_embed.add_field(
            name="3️⃣ 전설이 돌보기: `/상태창`",
            value="`/상태창` 명령어로 내 전설이의 상태를 확인하고, 버튼을 눌러 돌봐줄 수 있습니다.\n"
                  "🚿 **샤워하기**: 10P를 사용하여 청결도를 채웁니다. (질병 시 20P)\n"
                  "🍖 **간식 주기**: 5P를 사용하여 포만감을 채웁니다. (짜증 시 10P)\n"
                  "🌲 **산책하기**: 포인트를 얻거나 잃으며, 낮은 확률로 **아이템**이나 **상위 등급의 알**을 줍습니다!",
            inline=False
        )
        # ... (기존 다른 필드들) ...
        await interaction.channel.send(embed=guide_embed)
        await interaction.response.send_message("✅ 사용법 안내를 현재 채널에 게시했습니다.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
