import discord
from utils.database import get_legend_data, get_or_migrate_data, save_legend_data, consume_item, add_buff, get_active_buffs
from utils.data import ITEMS_INFO, PET_POOLS
from utils.logs import ITEM_USE_LOG_CH, HATCH_LOG_CH, send_log_embed
from utils.stats import add_points
from utils.game import egg_rarity, hatch_egg_item


class EggTypeView(discord.ui.View):
    """알 사용 2단계: 이름 입력 후, 해당 등급 안에서 원하는 종류를 골라 부화합니다."""
    def __init__(self, user_id: int, egg_name: str, pet_name: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.egg_name = egg_name
        self.pet_name = pet_name
        self.done = False

        rarity = egg_rarity(egg_name)
        pool = PET_POOLS.get(rarity, [])[:25]
        options = [discord.SelectOption(label=t, value=t) for t in pool]
        self.select = discord.ui.Select(placeholder=f"부화할 {rarity}급 전설이를 선택하세요", options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ 본인만 선택할 수 있습니다.", ephemeral=True)
        # 연타로 인한 중복 부화 방지
        if self.done:
            return await interaction.response.send_message("⏳ 이미 부화 처리된 알입니다.", ephemeral=True)
        self.done = True
        pet_type = self.select.values[0]

        res = await hatch_egg_item(self.user_id, self.egg_name, pet_type, self.pet_name)
        if not res["ok"]:
            self.done = False  # 실패 시 다시 시도 가능하도록
            return await interaction.response.send_message(f"❌ {res['error']}", ephemeral=True)

        embed = discord.Embed(
            title="🥚 알 부화 성공!",
            description=f"[{res['rarity']}급] {res['type']} 알을 얻었습니다!\n이름: `{res['name']}`\n`/상태창`으로 돌봐주세요.",
            color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=None)
        await send_log_embed(interaction.client, HATCH_LOG_CH, "🥚 알 사용 부화 로그",
                             f"{res['name']} ({res['type']} - {res['rarity']}급) 부화! (보관함 알 사용)",
                             interaction.user, discord.Color.purple())


class EggNameModal(discord.ui.Modal):
    """알 사용 1단계: 전설이 이름 입력."""
    def __init__(self, user_id: int, egg_name: str):
        super().__init__(title=f"{egg_name} 부화")
        self.user_id = user_id
        self.egg_name = egg_name
        self.pet_name = discord.ui.TextInput(label="새로 태어날 전설이의 이름", placeholder="예: 멍멍이",
                                             min_length=1, max_length=20, required=True)
        self.add_item(self.pet_name)

    async def on_submit(self, interaction: discord.Interaction):
        rarity = egg_rarity(self.egg_name)
        view = EggTypeView(self.user_id, self.egg_name, self.pet_name.value)
        embed = discord.Embed(
            title=f"🥚 {self.egg_name} 부화",
            description=f"이름: `{self.pet_name.value}`\n아래에서 원하는 **{rarity}급** 전설이 종류를 선택하세요!",
            color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class NameChangeModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="전설이 이름 변경")
        self.new_name = discord.ui.TextInput(label="새로운 전설이의 이름을 입력하세요", placeholder="예: 멍멍이", min_length=1, max_length=20, required=True)
        self.add_item(self.new_name)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        wrapper = await get_or_migrate_data(user_id)
        if not wrapper.get('pets'): return await interaction.response.send_message("❌ 아직 돌보고 있는 전설이가 없습니다.", ephemeral=True)
        success = await consume_item(user_id, "전설이 이름 변경권", 1)
        if not success: return await interaction.response.send_message("❌ '전설이 이름 변경권' 아이템이 부족합니다.", ephemeral=True)
        data = wrapper['pets'][wrapper['active_idx']]
        old_name = data.get('name', '이름없음')
        data['name'] = self.new_name.value
        await save_legend_data(user_id, wrapper)
        await interaction.response.send_message(f"✨ 뾰로롱! 전설이의 이름이 `{old_name}`에서 `{self.new_name.value}`(으)로 변경되었습니다!", ephemeral=True)

class ItemQuantityModal(discord.ui.Modal):
    def __init__(self, item_name: str, max_amount: int):
        self.item_name = item_name
        self.max_amount = max_amount
        super().__init__(title=f"{item_name} 사용")
        self.amount_input = discord.ui.TextInput(label=f"수량을 입력하세요 (보유량: {max_amount}개)", placeholder=f"1 ~ {max_amount} 사이의 숫자를 입력", min_length=1, max_length=5, required=True)
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try: amount = int(self.amount_input.value)
        except ValueError: return await interaction.response.send_message("❌ 올바른 숫자를 입력해주세요.", ephemeral=True)
        if amount <= 0 or amount > self.max_amount:
            return await interaction.response.send_message(f"❌ 보유하신 수량(1~{self.max_amount}개) 내에서 입력해주세요.", ephemeral=True)
        user_id = interaction.user.id
        await self.handle_use(interaction, user_id, amount)

    async def handle_use(self, interaction: discord.Interaction, user_id: int, amount: int):
        item_name = self.item_name

        # 청결도 100% 조건문 전면 삭제 처리
        if "경험치 부스터" in item_name:
            active_buffs = await get_active_buffs(user_id)
            buffs = {b[0] for b in active_buffs}

            # 경험치 부스터 종류가 버프 목록에 하나라도 존재하면 중복 실행 방지
            if any("경험치 부스터" in b for b in buffs):
                return await interaction.response.send_message("❌ 이미 적용 중인 경험치 부스터가 있습니다! 기존 부스터 효과가 끝난 후 사용해주세요.", ephemeral=True)

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
        elif egg_rarity(self.selected_item):
            # 알을 사용하면 유저가 직접 이름을 짓고 종류를 골라 부화합니다.
            # (알 소모는 종류 선택 완료 시점에 원자적으로 처리)
            modal = EggNameModal(self.user_id, self.selected_item)
            return await interaction.response.send_modal(modal)

        modal = ItemQuantityModal(self.selected_item, self.items[self.selected_item])
        await interaction.response.send_modal(modal)