import discord
from .database import get_legend_data, get_or_migrate_data, save_legend_data, consume_item, add_buff
from .data import ITEMS_INFO
from .logs import ITEM_USE_LOG_CH, send_log_embed

from utils.stats import add_points

class NameChangeModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="전설이 이름 변경")
        self.new_name = discord.ui.TextInput(
            label="새로운 전설이의 이름을 입력하세요",
            placeholder="예: 멍멍이",
            min_length=1,
            max_length=20,
            required=True
        )
        self.add_item(self.new_name)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        wrapper = await get_or_migrate_data(user_id)
        if not wrapper.get('pets'):
            return await interaction.response.send_message("❌ 아직 돌보고 있는 전설이가 없습니다.", ephemeral=True)

        success = await consume_item(user_id, "전설이 이름 변경권", 1)
        if not success:
            return await interaction.response.send_message("❌ '전설이 이름 변경권' 아이템이 부족합니다.", ephemeral=True)

        data = wrapper['pets'][wrapper['active_idx']]
        old_name = data.get('name', '이름없음')
        data['name'] = self.new_name.value

        await save_legend_data(user_id, wrapper)
        await interaction.response.send_message(f"✨ 뾰로롱! 전설이의 이름이 `{old_name}`에서 `{self.new_name.value}`(으)로 변경되었습니다!", ephemeral=True)

# 💡 [수정됨] 판매 관련 로직 제거, 순수하게 사용량만 입력받는 모달
class ItemQuantityModal(discord.ui.Modal):
    def __init__(self, item_name: str, max_amount: int):
        self.item_name = item_name
        self.max_amount = max_amount
        super().__init__(title=f"{item_name} 사용")

        self.amount_input = discord.ui.TextInput(
            label=f"수량을 입력하세요 (보유량: {max_amount}개)",
            placeholder=f"1 ~ {max_amount} 사이의 숫자를 입력",
            min_length=1,
            max_length=5,
            required=True
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
        except ValueError:
            return await interaction.response.send_message("❌ 올바른 숫자를 입력해주세요.", ephemeral=True)

        if amount <= 0 or amount > self.max_amount:
            return await interaction.response.send_message(f"❌ 보유하신 수량(1~{self.max_amount}개) 내에서 입력해주세요.", ephemeral=True)

        user_id = interaction.user.id
        await self.handle_use(interaction, user_id, amount)

    async def handle_use(self, interaction: discord.Interaction, user_id: int, amount: int):
        item_name = self.item_name

        if "경험치 부스터" in item_name:
            wrapper = await get_legend_data(user_id)
            if wrapper and wrapper.get('pets'):
                pet_data = wrapper['pets'][wrapper['active_idx']]
                if pet_data.get('cleanliness', 0) == 100:
                    return await interaction.response.send_message("❌ 청결도가 100(MAX) 상태일 때는 경험치 부스터를 사용할 수 없습니다!", ephemeral=True)

        success = await consume_item(user_id, item_name, amount)
        if not success: return await interaction.response.send_message("❌ 아이템을 보유하고 있지 않거나 부족합니다.", ephemeral=True)

        msg = f"✅ `{item_name}` {amount}개를 사용했습니다!\n"

        if item_name in ["배부름을 부르는 약", "쌩쌩한약", "트위치 나가라약", "아무무도 인싸로 만드는 약"]:
            await add_buff(user_id, buff_name=item_name, duration_sec=86400 * amount, vc_sec=0)
            msg += f"✨ 효과: {24 * amount}시간 동안 해당 스탯이 고정됩니다."
        elif item_name == "신비한 알약":
            await add_buff(user_id, buff_name=item_name, duration_sec=1209600 * amount, vc_sec=0)
            msg += f"✨ 효과: {14 * amount}일 동안 모든 스탯이 최상으로 고정됩니다."
        elif item_name in ["경험치 부스터 X2", "경험치 부스터 X5", "경험치 부스터 X10"]:
            await add_buff(user_id, buff_name=item_name, duration_sec=0, vc_sec=10800 * amount)
            msg += f"📈 효과: 통화방에 있는 동안 {3 * amount}시간 동안 경험치 획득량이 증가합니다."
        elif item_name == "50포인트 교환권":
            await add_points(user_id, 50 * amount)
            msg += f"💸 {50 * amount}P를 획득했습니다!"
        elif item_name == "100포인트 교환권":
            await add_points(user_id, 100 * amount)
            msg += f"💸 {100 * amount}P를 획득했습니다!"
        elif item_name == "500포인트 교환권":
            await add_points(user_id, 500 * amount)
            msg += f"💸 {500 * amount}P를 획득했습니다!"
        elif item_name == "1000포인트 교환권":
            await add_points(user_id, 1000 * amount)
            msg += f"💸 {1000 * amount}P를 획득했습니다!"

        await interaction.response.send_message(msg, ephemeral=True)
        await send_log_embed(interaction.client, ITEM_USE_LOG_CH, "🎒 아이템 다중 사용 로그", f"사용 아이템: {item_name} x {amount}개", interaction.user, discord.Color.blue())

class InventoryView(discord.ui.View):
    def __init__(self, user_id, items):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.items = items
        self.selected_item = None

        options = [discord.SelectOption(label=name, description=f"보유량: {amt}개") for name, amt in list(items.items())[:25]]
        self.select_menu = discord.ui.Select(placeholder="여기를 눌러 조작할 아이템/알을 선택하세요", options=options)
        self.select_menu.callback = self.on_select
        self.add_item(self.select_menu)

        self.use_btn = discord.ui.Button(label="사용하기", style=discord.ButtonStyle.success, emoji="✨", disabled=True)
        self.use_btn.callback = self.on_use_click
        self.add_item(self.use_btn)

    async def on_select(self, interaction: discord.Interaction):
        self.selected_item = self.select_menu.values[0]
        self.use_btn.disabled = False
        await interaction.response.edit_message(view=self)

    async def on_use_click(self, interaction: discord.Interaction):
        if self.selected_item == "100회 산책 할인권":
            return await interaction.response.send_message("💡 이 아이템은 100회 산책 시 자동으로 사용됩니다!", ephemeral=True)
        elif self.selected_item == "전설이 이름 변경권":
            modal = NameChangeModal()
            return await interaction.response.send_modal(modal)
        elif "급 알" in self.selected_item:
            return await interaction.response.send_message("💡 알은 인벤토리에 보관되며, 인벤토리에서 직접 깔 수 없습니다. 알까기를 이용해 주세요.", ephemeral=True)

        modal = ItemQuantityModal(self.selected_item, self.items[self.selected_item])
        await interaction.response.send_modal(modal)