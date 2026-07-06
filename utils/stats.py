import discord
from datetime import datetime

# 💡 분리된 로그 채널 ID 모음
WALK_LOG_CH = 1523244061505359942
HATCH_LOG_CH = 1523245573308809226
ITEM_USE_LOG_CH = 1523245707601907712
ITEM_GIVE_TAKE_LOG_CH = 1523244132724899952 # 아이템 지급/회수
EGG_GIVE_TAKE_LOG_CH = 1523394183207977130  # 알 지급/회수

async def send_log_embed(bot, channel_id, title, description, user: discord.Member, color, extra_footer=""):
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        if not channel: return

        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now())
        footer_text = f"유저: {user.display_name} ({user.id})"
        if extra_footer: footer_text += f" | {extra_footer}"

        embed.set_footer(text=footer_text, icon_url=user.display_avatar.url if user.display_avatar else None)
        await channel.send(embed=embed)
    except Exception as e:
        print(f"🚨 [로그 전송 실패] 채널 ID: {channel_id} | 에러: {e}")