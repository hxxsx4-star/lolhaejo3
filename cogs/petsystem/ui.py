import discord
from .data import ITEMS_INFO, EXP_TABLE
from .database import consume_item, update_user_points, add_buff

def create_status_embed(member: discord.Member, pet_data, user_points, buffs, is_annoyed, is_diseased):
    is_egg = (pet_data['level'] == 0)
    name, rarity, level = pet_data['name'], pet_data['rarity'], pet_data['level']

    display_name = f"미확인 알 ({rarity})" if is_egg else name
    star_text = "🥚 부화 대기 중" if is_egg else f"{level}성"

    health_status = "보통 🟢"
    if is_egg: health_status = "알 🥚"
    elif is_diseased: health_status = "질병 🔴 (비용 2배! 샤워 필요)"
    elif pet_data.get('cleanliness', 100) <= 20: health_status = "지저분 🟠"

    mood_status = "행복 😊"
    if is_egg: mood_status = "알 🥚"
    elif is_annoyed: mood_status = "짜증 💢 (산책 거부, 식비 2배!)"
    elif pet_data['fullness'] <= 20: mood_status = "배고픔 🟠"

    buff_text = "적용중인 버프: " + (", ".join(buffs) if buffs else "없음")

    embed = discord.Embed(
        title=f"{member.display_name}님의 {display_name} 상태창",
        description=f"등급: {rarity} | 보유 포인트: {user_points:,} P\n{buff_text}",
        color=discord.Color.purple() if rarity == "서사" else (discord.Color.red() if rarity == "전설" else discord.Color.gold())
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    if level == 3:
        exp_text, exp_percent = "MAX", 10
    else:
        max_exp = EXP_TABLE[rarity][level]
        exp_text = f"{pet_data['exp']:,} / {max_exp:,}"
        exp_percent = int((pet_data['exp'] / max_exp) * 10)

    embed.add_field(name="⭐ 성장", value=star_text, inline=True)
    if not is_egg:
        embed.add_field(name="❤️ 친밀도", value=f"{pet_data['intimacy']} pt", inline=True)
        embed.add_field(name="💤 피로도", value=f"{pet_data['fatigue']} pt", inline=True)

    embed.add_field(name="🩺 상태", value=f"건강: {health_status}\n기분: {mood_status}", inline=False)
    embed.add_field(name=f"✨ 경험치 ({exp_text})", value="🟩" * exp_percent + "⬜" * (10 - exp_percent), inline=False)

    if not is_egg:
        f_val = pet_data['fullness'] // 10
        embed.add_field(name=f"🍖 포만감 ({pet_data['fullness']}/100)", value="🟧" * f_val + "⬜" * (10 - f_val), inline=False)
        c_val = pet_data.get('cleanliness', 100) // 10
        embed.add_field(name=f"🚿 청결도 ({pet_data.get('cleanliness', 100)}/100)", value="🟦" * c_val + "⬜" * (10 - c_val), inline=False)

    return embed

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
    
    async def handle_action(self, interaction: discord.Interaction, action: str):
        pass
    async def handle_walk(self, interaction: discord.Interaction, count: int):
        pass
