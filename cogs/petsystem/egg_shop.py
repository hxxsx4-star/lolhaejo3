import discord
from discord.ext import commands
from discord import app_commands

from utils.database import get_item_amount, consume_item, add_item

# 🛒 알 상점 판매 목록 (단일 소스)
# 항목 추가 시 이 딕셔너리에만 넣으면 /알상점 버튼이 자동으로 생성됩니다.
SHOP_CATALOG = {
    "합성 방어권": {
        "price_item": "서사급 알",
        "price": 100000,
        "emoji": "🛡️",
        "desc": "합성에 실패해도 재료 전설이가 소멸하지 않습니다. (합성 실패 시 1개 자동 소모)",
    },
}


class EggShopView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        for item_name, info in SHOP_CATALOG.items():
            btn = discord.ui.Button(
                label=f"{item_name} 구매 ({info['price_item']} {info['price']:,}개)",
                style=discord.ButtonStyle.success,
                emoji=info["emoji"],
            )
            btn.callback = self._make_callback(item_name, info)
            self.add_item(btn)

    def _make_callback(self, item_name: str, info: dict):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ 본인의 상점만 이용할 수 있습니다.", ephemeral=True)

            price_item, price = info["price_item"], info["price"]
            owned = await get_item_amount(self.user_id, price_item)
            if owned < price:
                return await interaction.response.send_message(
                    f"❌ `{price_item}`이(가) 부족합니다!\n필요: {price:,}개 / 보유: {owned:,}개",
                    ephemeral=True,
                )

            # 결제(consume_item 내부에서 잔량을 한 번 더 검증하므로 동시성에도 안전)
            success = await consume_item(self.user_id, price_item, price)
            if not success:
                return await interaction.response.send_message("❌ 결제에 실패했습니다. 잔여 수량을 다시 확인해주세요.", ephemeral=True)

            await add_item(self.user_id, item_name, 1)
            await interaction.response.send_message(
                f"✅ `{item_name}` 1개를 구매했습니다!\n💸 `{price_item}` {price:,}개가 소모되었습니다.",
                ephemeral=True,
            )
        return callback


class EggShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="알상점", description="모아둔 서사급 알로 특별한 아이템을 구매합니다.")
    async def egg_shop(self, interaction: discord.Interaction):
        owned_epic = await get_item_amount(interaction.user.id, "서사급 알")
        embed = discord.Embed(
            title="🥚 알 상점",
            description=f"보유 중인 서사급 알: **{owned_epic:,}개**\n아래 버튼을 눌러 아이템을 구매하세요!",
            color=discord.Color.gold(),
        )
        for item_name, info in SHOP_CATALOG.items():
            embed.add_field(
                name=f"{info['emoji']} {item_name} — {info['price_item']} {info['price']:,}개",
                value=info["desc"],
                inline=False,
            )
        view = EggShopView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(EggShopCog(bot))
