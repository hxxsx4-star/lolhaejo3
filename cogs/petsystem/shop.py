import discord
from discord.ext import commands
from discord import app_commands
from utils.stats import get_points, spend_points
from cogs.petsystem.database import add_item


class PetShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="상점", description="포인트를 사용하여 아이템을 구매합니다.")
    async def shop(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏪 전설이 상점",
            description="현재 임시 오픈 중입니다! 아래 메뉴에서 구매할 아이템을 선택하세요.\n보유 포인트에 맞춰 구매가 진행됩니다.",
            color=discord.Color.gold()
        )

        current_points = await get_points(interaction.user.id)
        embed.set_footer(text=f"내 포인트: {current_points}P")

        # 💡 향후 판매할 아이템 목록 (가격을 자유롭게 수정/추가 가능)
        view = ShopView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ShopView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id

        # value에는 "아이템이름_가격" 형태로 넣습니다.
        options = [
            discord.SelectOption(label="배부름을 부르는 약", description="1,000P", value="배부름을 부르는 약_1000", emoji="💊"),
            discord.SelectOption(label="트위치 나가라약", description="2,000P", value="트위치 나가라약_2000", emoji="🚿"),
            discord.SelectOption(label="100회 산책 할인권", description="1,500P", value="100회 산책 할인권_1500", emoji="🎫")
        ]

        self.select_menu = discord.ui.Select(placeholder="구매할 아이템을 선택하세요", options=options)
        self.select_menu.callback = self.on_select
        self.add_item(self.select_menu)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("본인의 상점만 이용 가능합니다.", ephemeral=True)

        selected = self.select_menu.values[0]
        item_name, price_str = selected.split("_")
        price = int(price_str)

        success = await spend_points(self.user_id, price)
        if not success:
            return await interaction.response.send_message(f"❌ 포인트가 부족합니다! (필요: {price}P)", ephemeral=True)

        await add_item(self.user_id, item_name, 1)
        await interaction.response.send_message(f"✅ `{item_name}`을(를) 구매했습니다! (-{price}P)\n`/보관함`에서 확인하세요.",
                                                ephemeral=True)


async def setup(bot):
    await bot.add_cog(PetShopCog(bot))