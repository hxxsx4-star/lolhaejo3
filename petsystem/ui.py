import discord
import random

# 다른 파일에서 필요한 데이터와 함수를 가져옵니다.
from .database import get_legend, save_legend, get_user_pet_data, update_user_egg
from .data import EXP_TABLE
from utils.stats import get_points, spend_points, add_points

# ==========================================
# 임베드(상태창) 생성 함수
# ==========================================
def create_status_embed(member: discord.Member, legend_data):
    name, rarity, level, exp, fullness, intimacy, fatigue = legend_data
    points = get_points(member.id)

    is_egg = (level == 0)
    display_name = f"미확인 알 ({rarity})" if is_egg else name
    star_text = "🥚 부화 대기 중" if is_egg else f"{level}성"
    health_status = "보통 🟢" if not is_egg else "알 🥚"
    if not is_egg and fullness == 0: health_status = "질병 🔴 (포만감이 없습니다!)"
    mood_status = "행복 😊" if not is_egg else "알 🥚"
    if not is_egg and intimacy < 20: mood_status = "화남 💢 (친밀도가 너무 낮습니다!)"

    max_exp = EXP_TABLE[rarity][level]
    exp_text = "MAX" if level == 3 else f"{exp:,} / {max_exp:,}"
    exp_percent = 10 if level == 3 else int((exp / max_exp) * 10)

    color_map = {"서사": discord.Color.purple(), "전설": discord.Color.red(), "신화": discord.Color.gold(), "프레스티지": discord.Color.dark_theme()}
    embed = discord.Embed(
        title=f"{member.display_name}님의 {display_name} 상태창",
        description=f"등급: {rarity}\n보유 포인트: {points:,} P",
        color=color_map.get(rarity, discord.Color.blue())
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    
    exp_bar = "█" * exp_percent + "─" * (10 - exp_percent)
    
    embed.add_field(name="⭐ 성장", value=star_text, inline=True)
    if not is_egg:
        embed.add_field(name="❤️ 친밀도", value=f"{intimacy} pt", inline=True)
        embed.add_field(name="💤 피로도", value=f"{fatigue} pt", inline=True)
    embed.add_field(name="🩺 상태", value=f"건강: {health_status}\n기분: {mood_status}", inline=False)
    embed.add_field(name=f"✨ 경험치 ({exp_text})", value=exp_bar, inline=False)
    if not is_egg:
        fullness_bar = "█" * (fullness // 10) + "─" * (10 - (fullness // 10))
        embed.add_field(name=f"🍖 포만감 ({fullness}/100)", value=fullness_bar, inline=False)
    else:
        embed.add_field(name="안내", value="통화방 활동으로 경험치를 쌓아 알을 부화시켜보세요!", inline=False)
    return embed

# ==========================================
# 버튼 UI 클래스
# ==========================================
class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="전설이 간식 주기 (50P)", style=discord.ButtonStyle.success, emoji="🍖")
    async def feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("남의 전설이에게는 간식을 줄 수 없습니다!", ephemeral=True)
        data = get_legend(self.user_id)
        name, rarity, level, exp, fullness, intimacy, fatigue = data
        if level == 0:
            return await interaction.response.send_message("알은 아직 간식을 먹을 수 없어요! 통화방 활동으로 먼저 부화시켜주세요.", ephemeral=True)
        if get_points(self.user_id) < 50:
            return await interaction.response.send_message("포인트가 부족합니다! (필요: 50P)", ephemeral=True)
        if fullness >= 100:
            return await interaction.response.send_message("배가 불러서 더 이상 먹을 수 없어요!", ephemeral=True)

        spend_points(self.user_id, 50)
        new_fullness = min(fullness + 20, 100)
        save_legend(self.user_id, name, rarity, level, exp, new_fullness, intimacy, fatigue)

        new_data = (name, rarity, level, exp, new_fullness, intimacy, fatigue)
        embed = create_status_embed(interaction.user, new_data)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("냠냠! 50P를 사용하여 포만감을 20 채웠습니다.", ephemeral=True)

    async def handle_walk(self, interaction: discord.Interaction, count: int):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("남의 전설이와는 산책할 수 없습니다!", ephemeral=True)
        data = get_legend(self.user_id)
        name, rarity, level, exp, fullness, intimacy, fatigue = data
        if level == 0:
            return await interaction.response.send_message("알과는 산책을 할 수 없어요! 통화방 활동으로 먼저 부화시켜주세요.", ephemeral=True)
        if fullness == 0:
            return await interaction.response.send_message("전설이가 아파서(포만감 0) 산책을 갈 수 없어요. 간식을 먼저 주세요!", ephemeral=True)

        gained_pts, lost_pts = 0, 0
        drops = {"전설": 0, "신화": 0, "프레스티지": 0}
        for _ in range(count):
            rand = random.uniform(0, 100)
            if rand < 49.0: gained_pts += 50
            elif rand < 99.0: lost_pts += 50
            elif rand < 99.989: drops["전설"] += 1
            elif rand < 99.999: drops["신화"] += 1
            else: drops["프레스티지"] += 1

        net_points = gained_pts - lost_pts
        add_points(self.user_id, net_points)

        for drop_rarity, amount in drops.items():
            if amount > 0: update_user_egg(self.user_id, drop_rarity, amount)

        new_intimacy = intimacy + (1 * count)
        new_fatigue = fatigue + (1 * count)
        save_legend(self.user_id, name, rarity, level, exp, fullness, new_intimacy, new_fatigue)

        result_embed = discord.Embed(title=f"🚶 {count}회 산책 결과", color=discord.Color.green())
        result_embed.add_field(name="💰 포인트 변동", value=f"주운 포인트: +{gained_pts}P\n잃은 포인트: -{lost_pts}P\n총 합산: {net_points}P", inline=False)
        drop_text = "".join([f"{'🟪 전설' if r=='전설' else '🟨 신화' if r=='신화' else '⬛ 프레스티지'}급 알 {a}개 획득!\n" for r, a in drops.items() if a > 0])
        result_embed.add_field(name="🎁 특별 획득", value=drop_text if drop_text else "특별한 아이템을 줍지 못했습니다.", inline=False)

        new_data = (name, rarity, level, exp, fullness, new_intimacy, new_fatigue)
        embed = create_status_embed(interaction.user, new_data)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(embed=result_embed, ephemeral=True)

    @discord.ui.button(label="산책 10회", style=discord.ButtonStyle.primary, emoji="👟")
    async def walk_10_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 10)

    @discord.ui.button(label="산책 100회", style=discord.ButtonStyle.primary, emoji="🏃")
    async def walk_100_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 100)
