import discord
import random
from datetime import datetime

# 다른 파일에서 필요한 데이터와 함수를 가져옵니다.
from .database import get_legend, update_legend_specific, get_user_items, add_user_item
from .data import EXP_TABLE, SHOP_ITEMS
from utils.stats import get_points, spend_points, add_points

def get_status_icon(value, thresholds, icons):
    for i, threshold in enumerate(thresholds):
        if value >= threshold:
            return icons[i]
    return icons[-1]

def create_status_embed(member: discord.Member, legend_data, debuffs):
    name, rarity, level, exp, fullness, intimacy, fatigue, cleanliness, _, _, _ = legend_data
    points = get_points(member.id)
    is_egg = (level == 0)

    color_map = {"서사": 0x9b59b6, "전설": 0xe74c3c, "신화": 0xf1c40f, "프레스티지": 0x95a5a6}
    embed = discord.Embed(color=color_map.get(rarity, 0x3498db))
    embed.set_author(name=f"{member.display_name}님의 전설이", icon_url=member.display_avatar.url)

    if is_egg:
        embed.title = f"🥚 미확인 알 ({rarity})"
        max_exp = EXP_TABLE[rarity][0]
        exp_percent = min(int((exp / max_exp) * 100), 100)
        embed.description = f"부화를 위해 온기가 더 필요합니다...\n`[{'█' * (exp_percent//10)}{'─' * (10-exp_percent//10)}]` ({exp_percent}%)"
    else:
        embed.title = f"🐾 {name} ({level}성)"
        
        fullness_icon = "🤢" if "짜증" in debuffs else get_status_icon(fullness, [80, 40, 1], ["😊", "😐", "😕"])
        cleanliness_icon = "💩" if "질병" in debuffs else get_status_icon(cleanliness, [80, 40, 1], ["✨", "🧼", "😕"])
        intimacy_icon = get_status_icon(intimacy, [80, 40, 1], ["💖", "🙂", "😠"])
        fatigue_icon = get_status_icon(fatigue, [80, 40, 1], ["😴", "😐", "😵"])

        max_exp = EXP_TABLE[rarity].get(level, 0)
        exp_bar = f"`[{'─'*10}]` (MAX)"
        if level < 3:
            exp_percent = min(int((exp / max_exp) * 100), 100)
            exp_bar = f"`[{'█' * (exp_percent//10)}{'─' * (10-exp_percent//10)}]` ({exp_percent}%)"

        embed.add_field(name="경험치", value=exp_bar, inline=False)
        embed.add_field(name="포만감", value=fullness_icon, inline=True)
        embed.add_field(name="친밀도", value=intimacy_icon, inline=True)
        embed.add_field(name="피로도", value=fatigue_icon, inline=True)
        embed.add_field(name="청결도", value=cleanliness_icon, inline=True)
        
        if debuffs:
            embed.add_field(name="디버프", value=" ".join([f"`{d}`" for d in debuffs]), inline=False)

    embed.set_footer(text=f"💰 보유 포인트: {points:,} P")
    return embed

class LegendActionView(discord.ui.View):
    def __init__(self, user_id, debuffs):
        super().__init__(timeout=None)
        self.user_id = user_id
        
        shower_cost = 20 if "질병" in debuffs else 10
        feed_cost = 10 if "짜증" in debuffs else 5

        # 버튼 라벨을 동적으로 변경
        self.children[0].label = f"샤워 ({shower_cost}P)"
        self.children[1].label = f"먹이주기 ({feed_cost}P)"

    @discord.ui.button(label="샤워 (10P)", style=discord.ButtonStyle.primary, emoji="🚿")
    async def shower_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 이 로직은 Cog로 이동
        self.bot.dispatch("legend_action", interaction, "shower")

    @discord.ui.button(label="먹이주기 (5P)", style=discord.ButtonStyle.secondary, emoji="🍗")
    async def feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.bot.dispatch("legend_action", interaction, "feed")

    @discord.ui.button(label="산책", style=discord.ButtonStyle.secondary, emoji="🌲")
    async def walk_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.bot.dispatch("legend_action", interaction, "walk")

class ItemSelect(discord.ui.Select):
    def __init__(self, items):
        options = [discord.SelectOption(label=f"{name} ({qty}개)", value=name) for name, qty in items] or \
                  [discord.SelectOption(label="사용할 아이템이 없습니다.", value="no_item")]
        super().__init__(placeholder="사용할 아이템을 선택하세요...", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_item = self.values[0]
        if selected_item == "no_item":
            return await interaction.response.send_message("사용할 아이템이 없습니다.", ephemeral=True)
        
        # 아이템 사용 로직은 Cog에서 처리
        self.view.stop()
        await interaction.response.defer()
        self.view.bot.dispatch("legend_item_use", interaction, selected_item)

class ItemUseView(discord.ui.View):
    def __init__(self, bot, user_id, items):
        super().__init__(timeout=180)
        self.bot = bot
        self.user_id = user_id
        self.add_item(ItemSelect(items))
