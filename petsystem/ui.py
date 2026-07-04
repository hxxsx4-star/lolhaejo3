import discord
from .data import EXP_TABLE

def create_status_embed(member: discord.Member, legend_data, debuffs, points):
    name, rarity, level, exp, fullness, intimacy, fatigue, cleanliness, _, _, _ = legend_data
    is_egg = (level == 0)

    color_map = {"서사": 0x9b59b6, "전설": 0xe74c3c, "신화": 0xf1c40f, "프레스티지": 0x95a5a6}
    embed = discord.Embed(color=color_map.get(rarity, 0x3498db))
    embed.set_author(name=f"{member.display_name}님의 전설이", icon_url=member.display_avatar.url)

    desc = ""
    if is_egg:
        embed.title = f"🥚 미확인 알 ({rarity})"
        max_exp = EXP_TABLE[rarity][0]
        exp_percent = min(int((exp / max_exp) * 100), 100)
        desc += f"🌻 **부화 대기 중**\n`[{'█' * (exp_percent//10)}{'─' * (10-exp_percent//10)}]` ({exp_percent}%)\n\n"
        desc += "안내: 통화방 활동으로 경험치를 쌓아 알을 부화시켜보세요!\n"
    else:
        embed.title = f"🐾 {name} ({level}성)"
        max_exp = EXP_TABLE[rarity].get(level, 1)
        exp_percent = 100 if level >= 3 else min(int((exp / max_exp) * 100), 100)
        exp_bar = f"`[{'█' * (exp_percent//10)}{'─' * (10-exp_percent//10)}]`"
        exp_text = "MAX" if level >= 3 else f"{exp_percent}%"

        desc += f"**경험치** {exp_bar} ({exp_text})\n\n"
        
        fullness_icon = "🤢" if "짜증" in debuffs else ("😊" if fullness > 50 else "😐")
        intimacy_icon = "💖" if intimacy > 50 else "🙂"
        fatigue_icon = "😴" if fatigue > 50 else "😐"
        cleanliness_icon = "💩" if "질병" in debuffs else ("✨" if cleanliness > 50 else "🧼")

        desc += f"**포만감**: {fullness_icon} | **친밀도**: {intimacy_icon} | **피로도**: {fatigue_icon} | **청결도**: {cleanliness_icon}\n"
        if debuffs:
            desc += f"**상태이상**: {' '.join([f'`{d}`' for d in debuffs])}"

    embed.description = desc
    embed.set_footer(text=f"💰 보유 포인트: {points:,} P")
    return embed

class LegendActionView(discord.ui.View):
    def __init__(self, bot, user_id, debuffs):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        
        shower_cost = 20 if "질병" in debuffs else 10
        feed_cost = 10 if "짜증" in debuffs else 5

        # 버튼 라벨을 동적으로 변경
        self.children[0].label = f"샤워 ({shower_cost}P)"
        self.children[1].label = f"먹이주기 ({feed_cost}P)"
        # 산책 버튼들은 고정 비용이므로 그대로 둠

    async def dispatch_action(self, interaction, action_type, count=None):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("다른 사람의 전설이를 돌볼 수 없습니다!", ephemeral=True)
        # Cog에 이벤트 전달
        self.bot.dispatch("legend_action", interaction, action_type, count)
        await interaction.response.defer()

    @discord.ui.button(label="샤워 (10P)", style=discord.ButtonStyle.primary, emoji="🚿")
    async def shower_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.dispatch_action(interaction, "shower")

    @discord.ui.button(label="먹이주기 (5P)", style=discord.ButtonStyle.secondary, emoji="🍗")
    async def feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.dispatch_action(interaction, "feed")

    @discord.ui.button(label="산책 (10P)", style=discord.ButtonStyle.success, emoji="🌲")
    async def walk_1_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.dispatch_action(interaction, "walk", 1)

    @discord.ui.button(label="10회 산책 (100P)", style=discord.ButtonStyle.success, emoji="🌳")
    async def walk_10_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.dispatch_action(interaction, "walk", 10)

    @discord.ui.button(label="100회 산책 (1000P)", style=discord.ButtonStyle.success, emoji="🌴")
    async def walk_100_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.dispatch_action(interaction, "walk", 100)

class ItemSelect(discord.ui.Select):
    def __init__(self, items):
        options = [discord.SelectOption(label=f"{name} ({qty}개)", value=name) for name, qty in items] or \
                  [discord.SelectOption(label="사용할 아이템이 없습니다.", value="no_item")]
        super().__init__(placeholder="사용할 아이템을 선택하세요...", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_item = self.values[0]
        if selected_item == "no_item":
            return await interaction.response.send_message("사용할 아이템이 없습니다.", ephemeral=True)
        
        self.view.stop()
        await interaction.response.defer()
        self.view.bot.dispatch("legend_item_use", interaction, selected_item)

class ItemUseView(discord.ui.View):
    def __init__(self, bot, user_id, items):
        super().__init__(timeout=180)
        self.bot = bot
        self.user_id = user_id
        self.add_item(ItemSelect(items))
