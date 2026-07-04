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

        # 1. 펫 시스템 명령어
        embed.add_field(
            name="🐾 전설이 키우기",
            value="`/알까기`: 새로운 전설이 알을 받습니다.\n"
                  "`/상태창`: 내 전설이의 상태를 확인하고 돌봅니다.",
            inline=False
        )

        # 2. 가챠 및 간단한 명령어
        embed.add_field(
            name="🎉 기타 명령어",
            value="`/가챠 라인`: LOL 라인을 무작위로 뽑습니다.\n"
                  "`/가챠 챔피언`: LOL 챔피언을 무작위로 뽑습니다.\n",
            inline=False
        )
        
        embed.set_footer(text=f"요청자: {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="사용법게시", description="[관리자 전용] 채널에 펫 시스템 사용법 안내를 게시합니다.")
    @app_commands.default_permissions(manage_guild=True)
    async def post_guide(self, interaction: discord.Interaction):
        guide_embed = discord.Embed(
            title="🐾 꼬물이 키우기 가이드 🐾",
            description="나만의 작은 전설이를 키워 3성으로 진화시켜보세요!",
            color=discord.Color.gold()
        )
        guide_embed.set_thumbnail(url="https://i.imgur.com/lJ4A637.png") # 예시 썸네일

        guide_embed.add_field(
            name="1️⃣ 시작하기: `/알까기`",
            value="가장 먼저 `/알까기` 명령어로 당신의 첫 전설이 알을 받아야 합니다. 처음에는 **서사급** 알을 받게 됩니다.",
            inline=False
        )
        guide_embed.add_field(
            name="2️⃣ 알 부화시키기: `음성 채널 활동`",
            value="알을 받은 후, 서버의 **음성 채널에 접속**해 있으면 자동으로 경험치(XP)가 오릅니다. **100XP**를 모으면 알이 부화하여 1성 전설이가 태어납니다!",
            inline=False
        )
        guide_embed.add_field(
            name="3️⃣ 전설이 돌보기: `/상태창`",
            value="`/상태창` 명령어로 내 전설이의 상태를 확인하고, 버튼을 눌러 돌봐줄 수 있습니다.\n"
                  "🍖 **간식 주기**: 50P를 사용하여 포만감을 채웁니다.\n"
                  "👟 **산책하기**: 포인트를 얻거나 잃을 수 있으며, 낮은 확률로 **상위 등급의 알**을 주워올 수 있습니다!",
            inline=False
        )
        guide_embed.add_field(
            name="4️⃣ 진화시키기: `음성 채널 활동`",
            value="1성, 2성 전설이도 알과 마찬가지로 **음성 채널에 접속**해 있으면 경험치가 오릅니다. 경험치를 모두 채우면 다음 등급으로 진화하며, **최종 목표는 3성**입니다!",
            inline=False
        )
        guide_embed.add_field(
            name="5️⃣ 새로운 알 얻기: `3성 달성 후 /알까기`",
            value="현재 키우는 전설이를 **3성으로 만들면, 그 이후부터 `/알까기`가 가챠(뽑기) 기능으로 변경**됩니다. 1,000P를 사용하여 더 높은 등급의 알을 뽑을 수 있는 기회를 얻게 됩니다!",
            inline=False
        )
        guide_embed.set_footer(text="궁금한 점이 있다면 관리자에게 문의해주세요!")

        await interaction.response.send_message("✅ 사용법 안내를 현재 채널에 게시했습니다.", ephemeral=True)
        await interaction.channel.send(embed=guide_embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
