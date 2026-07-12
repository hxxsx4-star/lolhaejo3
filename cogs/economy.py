# cogs/economy.py
# ✨ 이 봇 전용(자체) 포인트 지갑 명령어: /지갑 /지급 /회수
#    utils.stats(로컬 legends.db 기반)를 사용하므로 포인트가 다른 봇과 공유되지 않습니다.
import configparser

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from utils.stats import get_points, add_points, spend_points, format_num

CURRENCY = "P"

# --- 로그 채널 설정 로드 (config.ini [Economy]) ---
_config = configparser.ConfigParser()
_config.read("config.ini", encoding="utf-8")


def _get_channel_id(key: str) -> int:
    try:
        return int(_config.get("Economy", key, fallback="0").strip())
    except (ValueError, configparser.Error):
        return 0


GRANT_LOG_CHANNEL_ID = _get_channel_id("grant_log_channel_id")
REVOKE_LOG_CHANNEL_ID = _get_channel_id("revoke_log_channel_id")


@app_commands.guild_only()
class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_log(self, guild: Optional[discord.Guild], channel_id: int, embed: discord.Embed):
        if not guild or not channel_id:
            return
        ch = guild.get_channel(channel_id)
        if isinstance(ch, discord.TextChannel) and ch.permissions_for(guild.me).send_messages:
            try:
                await ch.send(embed=embed)
            except Exception as e:
                print(f"[ERROR] 로그 전송 실패 #{ch.name}: {e}")
        else:
            print(f"[ERROR] 로그 채널을 찾을 수 없거나 권한이 없습니다. (ID: {channel_id})")

    @app_commands.command(name="지갑", description="포인트 보유량을 확인합니다.")
    @app_commands.describe(유저="확인할 유저 (선택하지 않으면 본인)")
    async def wallet(self, interaction: discord.Interaction, 유저: Optional[discord.Member] = None):
        target = 유저 or interaction.user
        points = await get_points(target.id)
        await interaction.response.send_message(
            f"{target.mention} 님은 {format_num(points)} {CURRENCY}를 보유하고 있어요!"
        )

    @app_commands.command(name="지급", description="[관리자] 특정 유저에게 포인트를 지급합니다.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(유저="포인트를 받을 유저", 금액="지급할 포인트 양")
    async def grant_points(self, interaction: discord.Interaction, 유저: discord.Member, 금액: int):
        if 금액 <= 0:
            await interaction.response.send_message("금액은 1 이상이어야 합니다.", ephemeral=True)
            return

        await add_points(유저.id, 금액)
        await interaction.response.send_message(
            f"{유저.mention}님에게 {format_num(금액)} {CURRENCY}를 지급했습니다.", ephemeral=True
        )

        log_embed = discord.Embed(title="💰 포인트 지급 로그", color=discord.Color.gold())
        log_embed.add_field(name="실행자", value=interaction.user.mention, inline=False)
        log_embed.add_field(name="대상", value=유저.mention, inline=False)
        log_embed.add_field(name="금액", value=f"{format_num(금액)} {CURRENCY}", inline=False)
        await self._send_log(interaction.guild, GRANT_LOG_CHANNEL_ID, log_embed)

    @app_commands.command(name="회수", description="[관리자] 특정 유저의 포인트를 회수합니다.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(유저="포인트를 회수할 유저", 금액="회수할 포인트 양")
    async def revoke_points(self, interaction: discord.Interaction, 유저: discord.Member, 금액: int):
        if 금액 <= 0:
            await interaction.response.send_message("금액은 1 이상이어야 합니다.", ephemeral=True)
            return

        success = await spend_points(유저.id, 금액)
        if not success:
            await interaction.response.send_message("대상의 포인트가 부족합니다.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"{유저.mention}님에게서 {format_num(금액)} {CURRENCY}를 회수했습니다.", ephemeral=True
        )

        log_embed = discord.Embed(title="💸 포인트 회수 로그", color=discord.Color.dark_red())
        log_embed.add_field(name="실행자", value=interaction.user.mention, inline=False)
        log_embed.add_field(name="대상", value=유저.mention, inline=False)
        log_embed.add_field(name="금액", value=f"{format_num(금액)} {CURRENCY}", inline=False)
        await self._send_log(interaction.guild, REVOKE_LOG_CHANNEL_ID, log_embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
