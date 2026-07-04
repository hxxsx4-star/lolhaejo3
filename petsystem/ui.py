import discord
from .data import ITEMS_INFO, EXP_TABLE
from .database import consume_item, update_user_points, add_buff

class InventoryView(discord.ui.View):
    def __init__(self, user_id, items_dict):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.items = items_dict
        self.selected_item = None

        options = [discord.SelectOption(label=f"{name} (보유: {amount}개)", value=name, description=ITEMS_INFO[name]["desc"][:50])
                   for name, amount in items_dict.items()]
        if not options:
            options.append(discord.SelectOption(label="사용할 아이템이 없습니다.", value="no_item"))

        self.select_menu = discord.ui.Select(placeholder="사용할 아이템을 선택하세요", options=options)
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("자신의 보관함만 조작할 수 있습니다.", ephemeral=True)

        self.selected_item = self.select_menu.values[0]
        btn = discord.ui.Button(label=f"[{self.selected_item}] 사용하기", style=discord.ButtonStyle.success)
        btn.callback = self.use_callback
        
        view = discord.ui.View()
        view.add_item(btn)
        await interaction.response.edit_message(content=f"**선택됨: {self.selected_item}**\n{ITEMS_INFO[self.selected_item]['desc']}", view=view)

    async def use_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return

        if consume_item(self.user_id, self.selected_item, 1):
            msg = f"✅ `{self.selected_item}` 아이템을 사용했습니다!"
            if "포인트 교환권" in self.selected_item:
                pts = int(self.selected_item.split("포인트")[0])
                update_user_points(self.user_id, pts)
                msg += f"\n포인트 {pts}P를 얻었습니다."
            elif "부스터" in self.selected_item:
                add_buff(self.user_id, self.selected_item, vc_sec=10800)
                msg += "\n통화방 활동 3시간 동안 경험치 부스터가 적용됩니다."
            elif "신비한 알약" in self.selected_item:
                add_buff(self.user_id, "신비한 알약", duration_sec=1209600)
                msg += "\n2주 동안 전설이의 모든 능력치가 MAX로 유지됩니다."
            elif "할인권" not in self.selected_item:
                add_buff(self.user_id, self.selected_item, duration_sec=86400)
                msg += "\n24시간 동안 버프 효과가 적용됩니다."
            await interaction.response.edit_message(content=msg, view=None, embed=None)
        else:
            await interaction.response.send_message("아이템이 부족합니다.", ephemeral=True)

class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="밥 주기", style=discord.ButtonStyle.success, emoji="🍖")
    async def feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "feed")

    @discord.ui.button(label="샤워", style=discord.ButtonStyle.secondary, emoji="🚿")
    async def shower_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "shower")

    @discord.ui.button(label="산책 1회", style=discord.ButtonStyle.primary, emoji="👟")
    async def walk_1_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 1)

    @discord.ui.button(label="산책 100회", style=discord.ButtonStyle.primary, emoji="🏃")
    async def walk_100_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 100)
    
    # 이 아래는 Cog에서 호출할 실제 로직이므로, 이 파일에 있을 필요가 없습니다.
    # Cog로 옮겨서 이벤트 기반으로 처리하는 것이 더 좋습니다.
    async def handle_action(self, interaction: discord.Interaction, action: str):
        pass
    async def handle_walk(self, interaction: discord.Interaction, count: int):
        pass
