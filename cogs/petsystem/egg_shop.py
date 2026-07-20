import discord
from discord.ext import commands
from discord import app_commands

from utils.database import get_item_amount, consume_item, add_item
from utils.data import EQUIPMENTS, EQUIP_PRICE, format_equip_effect

# 합성 방어권 가격 (서사급 알)
PROTECT_TICKET = "합성 방어권"
PROTECT_TICKET_PRICE = 100000

# 카테고리 (라벨, 값). 값이 '합성 방어권'이면 특수 아이템, 나머지는 장비 등급명.
CATEGORY_OPTIONS = [
    ("🛡️ 합성 방어권", PROTECT_TICKET),
    ("⚔️ 서사 장비", "서사"),
    ("⚔️ 전설 장비", "전설"),
    ("🌟 신화 장비", "신화"),
    ("👑 프레스티지 장비", "프레스티지"),
    ("💎 고귀 장비", "고귀"),
    ("✨ 초월 장비", "초월"),
]


def _equip_names(rarity):
    return [n for n, i in EQUIPMENTS.items() if i["rarity"] == rarity]


def _price_of(item_name):
    if item_name == PROTECT_TICKET:
        return PROTECT_TICKET_PRICE
    info = EQUIPMENTS.get(item_name)
    return EQUIP_PRICE[info["rarity"]] if info else None


class EggShopView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.selected_item = None

        self.category_select = discord.ui.Select(
            placeholder="① 구매할 종류를 선택하세요",
            options=[discord.SelectOption(label=lb, value=v) for lb, v in CATEGORY_OPTIONS],
        )
        self.category_select.callback = self.on_category
        self.add_item(self.category_select)

        self.item_select = None
        self.buy_button = discord.ui.Button(label="구매하기", style=discord.ButtonStyle.success, emoji="💰", disabled=True)
        self.buy_button.callback = self.on_buy
        self.add_item(self.buy_button)

    def _guard(self, interaction):
        return interaction.user.id == self.user_id

    async def on_category(self, interaction: discord.Interaction):
        if not self._guard(interaction):
            return await interaction.response.send_message("❌ 본인의 상점만 이용할 수 있습니다.", ephemeral=True)

        category = self.category_select.values[0]
        self.selected_item = None
        self.buy_button.disabled = True

        if self.item_select:
            self.remove_item(self.item_select)

        if category == PROTECT_TICKET:
            options = [discord.SelectOption(label=f"{PROTECT_TICKET} (서사급 알 {PROTECT_TICKET_PRICE:,})",
                                            value=PROTECT_TICKET, description="합성 실패 시 재료 전설이 보존")]
        else:
            price = EQUIP_PRICE[category]
            options = [discord.SelectOption(label=f"{n} (서사급 알 {price:,})", value=n,
                                            description=format_equip_effect(n)[:100])
                       for n in _equip_names(category)][:25]

        self.item_select = discord.ui.Select(placeholder="② 구매할 아이템을 선택하세요", options=options)
        self.item_select.callback = self.on_item
        self.add_item(self.item_select)

        owned = await get_item_amount(self.user_id, "서사급 알")
        await interaction.response.edit_message(embed=self._embed(category, owned), view=self)

    async def on_item(self, interaction: discord.Interaction):
        if not self._guard(interaction):
            return await interaction.response.send_message("❌ 본인의 상점만 이용할 수 있습니다.", ephemeral=True)
        self.selected_item = self.item_select.values[0]
        self.buy_button.disabled = False
        price = _price_of(self.selected_item)
        owned = await get_item_amount(self.user_id, "서사급 알")
        embed = self._embed(None, owned)
        embed.add_field(name="🛒 선택한 아이템", value=f"**{self.selected_item}** — 서사급 알 {price:,}개", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_buy(self, interaction: discord.Interaction):
        if not self._guard(interaction):
            return await interaction.response.send_message("❌ 본인의 상점만 이용할 수 있습니다.", ephemeral=True)
        if not self.selected_item:
            return await interaction.response.send_message("❌ 먼저 구매할 아이템을 선택하세요.", ephemeral=True)

        item_name = self.selected_item
        price = _price_of(item_name)
        if price is None:
            return await interaction.response.send_message("❌ 알 수 없는 아이템입니다.", ephemeral=True)

        owned = await get_item_amount(self.user_id, "서사급 알")
        if owned < price:
            return await interaction.response.send_message(
                f"❌ 서사급 알이 부족합니다!\n필요: {price:,}개 / 보유: {owned:,}개", ephemeral=True)

        # 원자적 차감(동시 클릭 시 초과 결제 방지)
        if not await consume_item(self.user_id, "서사급 알", price):
            return await interaction.response.send_message("❌ 결제에 실패했습니다. 잔여 수량을 확인해주세요.", ephemeral=True)

        await add_item(self.user_id, item_name, 1)
        suffix = "\n🎽 장비는 `/장비` 명령으로 전설이에게 장착하세요." if item_name in EQUIPMENTS else ""
        await interaction.response.send_message(
            f"✅ `{item_name}` 1개를 구매했습니다! (서사급 알 -{price:,}){suffix}", ephemeral=True)

    def _embed(self, category, owned):
        embed = discord.Embed(title="🛒 알 상점", description=f"보유 서사급 알: **{owned:,}개**", color=discord.Color.gold())
        if category == PROTECT_TICKET:
            embed.add_field(name=f"🛡️ {PROTECT_TICKET} — {PROTECT_TICKET_PRICE:,}개",
                            value="합성 실패 시 재료 전설이가 소멸하지 않습니다.", inline=False)
        elif category in EQUIP_PRICE:
            price = EQUIP_PRICE[category]
            lines = [f"• **{n}** — {format_equip_effect(n)}" for n in _equip_names(category)]
            embed.add_field(name=f"⚔️ {category} 장비 (각 {price:,}개)", value="\n".join(lines) or "-", inline=False)
        else:
            embed.add_field(name="판매 목록", value="🛡️ 합성 방어권 / ⚔️ 등급별 장비 (서사~초월)", inline=False)
        embed.set_footer(text="① 종류 선택 → ② 아이템 선택 → 💰 구매하기")
        return embed


class EggShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="알상점", description="모아둔 서사급 알로 장비와 아이템을 구매합니다.")
    async def egg_shop(self, interaction: discord.Interaction):
        owned = await get_item_amount(interaction.user.id, "서사급 알")
        view = EggShopView(interaction.user.id)
        await interaction.response.send_message(embed=view._embed(None, owned), view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(EggShopCog(bot))
