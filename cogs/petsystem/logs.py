import discord
from datetime import datetime

# 💡 지정해주신 채널 ID
ITEM_SELL_LOG_CH = 1523244132724899952
WALK_LOG_CH = 1523244061505359942
HATCH_LOG_CH = 1523245573308809226
ITEM_USE_LOG_CH = 1523245707601907712

async def send_log_embed(bot, channel_id, title, description, user: discord.Member, color, extra_footer=""):
    """채널에 로그 임베드를 전송하는 통합 함수"""
    try:
        # 채널 캐시 확인 후 없으면 API로 직접 가져옵니다.
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        if not channel:
            return

        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now())
        
        # 꼬리말에 유저 닉네임과 고유 ID 표시
        footer_text = f"유저: {user.display_name} ({user.id})"
        
        # 산책 1회/10회/100회 등 추가 정보가 있을 경우 결합
        if extra_footer:
            footer_text += f" | {extra_footer}"
            
        embed.set_footer(text=footer_text, icon_url=user.display_avatar.url if user.display_avatar else None)
        await channel.send(embed=embed)
        
    except Exception as e:
        print(f"🚨 [로그 전송 실패] 채널 ID: {channel_id} | 에러: {e}")
