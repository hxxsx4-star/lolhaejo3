import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from datetime import datetime, timezone, timedelta
import configparser
import os
from utils.stats import load_stats, save_stats, ensure_user, format_num, get_points, add_points, spend_points

# --- 설정 로더 ---
_cfg = configparser.ConfigParser()
try:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.')) # 경로 수정
    config_path = os.path.join(project_root, 'config.ini')
    _cfg.read(config_path, encoding="utf-8")
except Exception as e:
    print(f"[ERROR] economy.py: config.ini 로딩 오류: {e}")

def _get_id(section: str, key: str) -> int:
    try: return int(_cfg.get(section, key, fallback="0"))
    except: return 0

GRANT_LOG_CHANNEL_ID = _get_id("Economy", "grant_log_channel_id")
REVOKE_LOG_CHANNEL_ID = _get_id("Economy", "revoke_log_channel_id")
CURRENCY, DAILY_REWARD, ATTEND_KEY = "Point", 50, "출석_최근"
try: KST = timezone(timedelta(hours=9), 'KST')
except: KST = timezone(timedelta(hours=9))

@app_commands.guild_only()
class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_log(self, guild: discord.Guild, channel_id: int, embed: discord.Embed):
        if not guild or not channel_id:
            print(f"[DEBUG] 로그 전송 건너뜀: Guild 또는 Channel ID 없음.")
            return
            
        ch = guild.get_channel(channel_id)
        if isinstance(ch, discord.TextChannel):
            if ch.permissions_for(guild.me).send_messages:
                try:
                    await ch.send(embed=embed)
                except Exception as e:
                    print(f"[ERROR] 로그 전송 실패 #{ch.name}: {e}")
            else:
                print(f"[ERROR] 권한 부족: #{ch.name} 채널에 메시지를 보낼 수 없습니다.")
        else:
            print(f"[ERROR] 채널을 찾을 수 없음: ID {channel_id} 에 해당하는 텍스트 채널이 없습니다.")

    @app_commands.command(name="지갑", description="포인트 보유량을 확인합니다.")
    @app_commands.describe(유저="확인할 유저 (선택)")
    async def wallet(self, interaction: discord.Interaction, 유저: Optional[discord.Member] = None):
        target = 유저 or interaction.user
        await interaction.response.send_message(f"{target.mention} 님은 **{format_num(get_points(target.id))} {CURRENCY}**를 보유하고 있어요!")

    @app_commands.command(name="출석", description="하루에 한 번 출석하여 포인트를 받습니다.")
    async def attendance(self, interaction: discord.Interaction):
        user_id, now_kst, today_str = str(interaction.user.id), datetime.now(tz=KST), datetime.now(tz=KST).date().isoformat()
        stats = load_stats()
        rec = ensure_user(stats, user_id)
        if rec.get(ATTEND_KEY) == today_str:
            await interaction.response.send_message("이미 오늘 출석했습니다.", ephemeral=True)
            return
        rec["포인트"] = int(rec.get("포인트", 0)) + DAILY_REWARD
        rec[ATTEND_KEY] = today_str
        save_stats(stats)
        await interaction.response.send_message(f"출석 보상 **{format_num(DAILY_REWARD)} {CURRENCY}**가 지급되었습니다!", ephemeral=True)

    @app_commands.command(name="순위", description="서버 내 포인트 순위를 확인합니다.")
    async def ranking(self, interaction: discord.Interaction):
        if not interaction.guild: return
        stats = load_stats()
        ranking_list = sorted([(int(uid), rec.get("포인트", 0)) for uid, rec in stats.items() if str(uid).isdigit() and isinstance(rec, dict) and interaction.guild.get_member(int(uid))], key=lambda x: x[1], reverse=True)
        if not ranking_list:
            await interaction.response.send_message("순위 정보가 없습니다.")
            return
        lines = [f"{i}. {interaction.guild.get_member(uid).display_name} — **{format_num(point)} {CURRENCY}**" for i, (uid, point) in enumerate(ranking_list[:10], 1)]
        embed = discord.Embed(title="🏆 서버 포인트 랭킹 (상위 10명)", description="\n".join(lines), color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="지급", description="관리자 전용: 특정 유저에게 포인트를 지급합니다.")
    @app_commands.describe(유저="포인트를 받을 유저", 금액="지급할 포인트 양")
    @app_commands.default_permissions(manage_guild=True)
    async def grant_points(self, interaction: discord.Interaction, 유저: discord.Member, 금액: int):
        if 금액 <= 0: await interaction.response.send_message("금액은 1 이상이어야 합니다.", ephemeral=True); return
        add_points(유저.id, 금액)
        await interaction.response.send_message(f"{유저.mention}님에게 **{format_num(금액)} {CURRENCY}**를 지급했습니다.", ephemeral=True)
        log_embed = discord.Embed(title="💰 포인트 지급 로그", color=discord.Color.gold()).add_field(name="실행자", value=interaction.user.mention, inline=False).add_field(name="대상", value=유저.mention, inline=False).add_field(name="금액", value=f"{format_num(금액)} {CURRENCY}", inline=False)
        await self._send_log(interaction.guild, GRANT_LOG_CHANNEL_ID, log_embed)

    @app_commands.command(name="회수", description="관리자 전용: 특정 유저의 포인트를 회수합니다.")
    @app_commands.describe(유저="포인트를 회수할 유저", 금액="회수할 포인트 양")
    @app_commands.default_permissions(manage_guild=True)
    async def revoke_points(self, interaction: discord.Interaction, 유저: discord.Member, 금액: int):
        if 금액 <= 0: await interaction.response.send_message("금액은 1 이상이어야 합니다.", ephemeral=True); return
        if get_points(유저.id) < 금액: await interaction.response.send_message("대상의 포인트가 부족합니다.", ephemeral=True); return
        spend_points(유저.id, 금액)
        await interaction.response.send_message(f"{유저.mention}님에게서 **{format_num(금액)} {CURRENCY}**를 회수했습니다.", ephemeral=True)
        log_embed = discord.Embed(title="💸 포인트 회수 로그", color=discord.Color.dark_red()).add_field(name="실행자", value=interaction.user.mention, inline=False).add_field(name="대상", value=유저.mention, inline=False).add_field(name="금액", value=f"{format_num(금액)} {CURRENCY}", inline=False)
        await self._send_log(interaction.guild, REVOKE_LOG_CHANNEL_ID, log_embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))