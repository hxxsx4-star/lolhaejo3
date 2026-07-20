import discord
from datetime import datetime

WALK_LOG_CH = 1523244061505359942
HATCH_LOG_CH = 1523245573308809226
ITEM_USE_LOG_CH = 1523245707601907712
ITEM_GIVE_TAKE_LOG_CH = 1523244132724899952 # 아이템 지급 및 회수
EGG_GIVE_TAKE_LOG_CH = 1523394183207977130  # 알 지급 및 회수

# 로그를 남길 "특정 서버"의 ID. 0이면 각 로그 채널이 속한 서버를 자동으로 사용합니다.
# (봇이 여러 서버에 있어도, 이 서버에서 일어난 일만 로그 채널에 기록됩니다)
MAIN_GUILD_ID = 0

async def send_log_embed(bot, channel_id, title, description, user: discord.Member, color, extra_footer=""):
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        if not channel: return

        # 지정된 서버(또는 로그 채널이 속한 서버)에서 발생한 일만 기록하고,
        # 다른 서버에서 일어난 활동은 로그에 남기지 않는다.
        target_gid = MAIN_GUILD_ID or getattr(getattr(channel, "guild", None), "id", None)
        action_guild = getattr(user, "guild", None)
        if target_gid is not None and (action_guild is None or action_guild.id != target_gid):
            return

        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now())
        footer_text = f"유저: {user.display_name} ({user.id})"
        if extra_footer: footer_text += f" | {extra_footer}"

        embed.set_footer(text=footer_text, icon_url=user.display_avatar.url if user.display_avatar else None)
        await channel.send(embed=embed)
    except Exception as e:
        print(f"🚨 [로그 전송 실패] 채널 ID: {channel_id} | 에러: {e}")