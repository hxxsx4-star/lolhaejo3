import discord
from discord.ext import commands
from discord import app_commands

# ==========================================
# 상점 UI 및 아이템 데이터 (추후 확장용)
# ==========================================

# 예시 아이템 데이터
SHOP_ITEMS = {
    "피로회복제": {"price": 100, "description": "전설이의 피로도를 50 낮춰줍니다."},
    "친밀도사탕": {"price": 200, "description": "전설이와의 친밀도를 30 올려줍니다."},
}

# ==========================================
# 상점 Cog 클래스
# ==========================================
class PetShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="상점", description="전설이 관련 아이템을 구매할 수 있는 상점입니다.")
    async def shop(self, interaction: discord.Interaction):
        # 현재는 비활성화 상태이므로 준비 중 메시지만 표시
        embed = discord.Embed(
            title="🏪 전설이 상점",
            description="🚧 현재 준비 중입니다. 곧 멋진 아이템들과 함께 찾아올게요!",
            color=discord.Color.light_grey()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# 메인 봇이 이 파일을 로드할 수 있도록 setup 함수 추가
async def setup(bot):
    await bot.add_cog(PetShopCog(bot))
