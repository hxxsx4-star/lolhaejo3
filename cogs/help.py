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
            name="🎉 기타",
            value="`/가챠 라인`: LOL 라인을 무작위로 뽑습니다.\n"
                  "`/가챠 챔피언`: LOL 챔피언을 무작위로 뽑습니다.\n",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="사용법게시", description="[관리자] 지정된 채널에 펫 시스템 사용법 안내를 게시합니다.")
    @app_commands.describe(channel="안내를 게시할 텍스트 채널")
    @app_commands.default_permissions(manage_guild=True)
    async def post_guide(self, interaction: discord.Interaction, channel: discord.TextChannel):
        guide_embed = discord.Embed(
            title="🐾 꼬물이 키우기 가이드 🐾",
            description="나만의 작은 전설이를 키워 3성으로 진화시켜보세요!",
            color=discord.Color.gold()
        )
        guide_embed.set_thumbnail(url="https://i.imgur.com/lJ4A637.png")

        guide_embed.add_field(name="1️⃣ 시작하기", value="`/알까기`로 첫 전설이 알을 받으세요. 음성 채널에 접속해 경험치를 모으면 알이 부화합니다.", inline=False)
        guide_embed.add_field(name="2️⃣ 돌보기", value="`/상태창`에서 펫을 돌보세요.\n"
                                              "🚿 **샤워 (10P)**: 청결도를 회복합니다. 24시간 방치 시 `질병` 상태가 되어 비용이 2배가 됩니다.\n"
                                              "🍗 **먹이주기 (5P)**: 포만감을 회복합니다. 24시간 방치 시 `짜증` 상태가 되어 비용이 2배가 되고 산책을 거부합니다.\n"
                                              "🌲 **산책 (10P)**: 피로도와 친밀도가 오르며, 낮은 확률로 아이템이나 희귀 알을 발견합니다.", inline=False)
        guide_embed.add_field(name="3️⃣ 성장과 버프", value="음성 채널에 접속하면 시간이 지남에 따라 경험치가 오릅니다. 친밀도가 높으면 경험치 획득량이 **2배**가 됩니다. 3성을 달성하면 새로운 알을 뽑을 수 있습니다.", inline=False)
        guide_embed.add_field(name="4️⃣ 아이템", value="`/보관함`에서 아이템을 확인하고 사용할 수 있습니다. `/판매` 명령어로 아이템을 팔아 포인트를 얻을 수도 있습니다.", inline=False)

        try:
            await channel.send(embed=guide_embed)
            await interaction.response.send_message(f"✅ {channel.mention} 채널에 사용법 안내를 성공적으로 게시했습니다.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ {channel.mention} 채널에 메시지를 보낼 권한이 없습니다.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 알 수 없는 오류가 발생했습니다: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
