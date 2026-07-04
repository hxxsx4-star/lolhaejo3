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
    name, rarity, level, exp, fullness, intimacy, fatigue, _ = legend_data
    points = get_points(member.id)
    is_egg = (level == 0)

    # 1. 기본 정보 설정
    display_name = f"알 ({rarity})" if is_egg else name
    gender_icon = "🥚" if is_egg else "🐾"

    color_map = {
        "서사": discord.Color.purple(),
        "전설": discord.Color.red(),
        "신화": discord.Color.gold(),
        "프레스티지": discord.Color.dark_theme()
    }

    embed = discord.Embed(
        title=f"| {gender_icon} {display_name} ({rarity})",
        color=color_map.get(rarity, discord.Color.dark_embed())
    )

    embed.set_thumbnail(url=member.display_avatar.url)

    # 2. 본문(Description) 조립 시작
    desc = ""

    if is_egg:
        # --- [ 알 상태 UI ] ---
        desc += "🌻 **부화 대기 중**\n\n"
        desc += "안내: 통화방 활동으로 경험치를 쌓아\n알을 부화시켜보세요!\n\n"
        desc += "**상태**\n"
        desc += "• **상태**: 🥚 무럭무럭 자라는 중\n"
    else:
        # --- [ 펫 상태 UI (사진 스타일) ] ---
        max_exp = EXP_TABLE[rarity][level]
        exp_percent = min(int((exp / max_exp) * 10), 10) if level < 3 else 10

        # 디스코드 기본 이모지를 활용한 경험치 바
        exp_bar_fill = "🟩" * exp_percent
        exp_bar_empty = "⬛" * (10 - exp_percent)

        exp_text = f"MAX XP" if level == 3 else f"{exp:,}/{max_exp:,} XP"

        desc += f"🌻 **성장 {level}단계**\n"
        desc += f"{exp_bar_fill}{exp_bar_empty}\n"
        desc += f"({exp_text})\n\n"

        # 스탯을 5칸짜리 이모지로 변환 (100 기준 20당 1칸)
        full_icons = fullness // 20
        int_icons = intimacy // 20 if intimacy < 100 else 5
        fat_icons = fatigue // 20 if fatigue < 100 else 5

        fullness_str = ("🍗" * full_icons) + ("🦴" * (5 - full_icons))
        intimacy_str = ("🎀" * int_icons) + ("🖤" * (5 - int_icons))
        fatigue_str = ("💧" * fat_icons) + ("💤" * (5 - fat_icons))

        desc += "**상태**\n"
        desc += f"• **친밀도**: {intimacy_str}\n"
        desc += f"• **포만도**: {fullness_str}\n"
        desc += f"• **피로도**: {fatigue_str}\n\n"

    # 3. 하단 안내문 (Footer 대체용)
    embed.description = desc
    embed.set_footer(text=f"💰 보유 포인트: {points:,} P")

    return embed


# ==========================================
# 버튼 UI 클래스
# ==========================================
class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="먹이주기 (50P)", style=discord.ButtonStyle.secondary, emoji="🍗")
    async def feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("남의 전설이에게는 간식을 줄 수 없습니다!", ephemeral=True)

        data = get_legend(self.user_id)
        name, rarity, level, exp, fullness, intimacy, fatigue, last_updated = data

        if level == 0:
            return await interaction.response.send_message("알은 아직 간식을 먹을 수 없어요!", ephemeral=True)
        if get_points(self.user_id) < 50:
            return await interaction.response.send_message("포인트가 부족합니다! (필요: 50P)", ephemeral=True)
        if fullness >= 100:
            return await interaction.response.send_message("배가 불러서 더 이상 먹을 수 없어요!", ephemeral=True)

        spend_points(self.user_id, 50)
        new_fullness = min(fullness + 20, 100)
        save_legend(self.user_id, name, rarity, level, exp, new_fullness, intimacy, fatigue)

        new_data = (name, rarity, level, exp, new_fullness, intimacy, fatigue, last_updated)
        embed = create_status_embed(interaction.user, new_data)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("냠냠! 50P를 사용하여 포만감을 20 채웠습니다.", ephemeral=True)

    # 산책 처리용 통합 로직
    async def handle_walk(self, interaction: discord.Interaction, count: int):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("남의 전설이와는 산책할 수 없습니다!", ephemeral=True)

        # 1. 비용 계산 및 잔액 확인
        cost = count * 10
        if get_points(self.user_id) < cost:
            return await interaction.response.send_message(f"산책 비용이 부족합니다! (필요: {cost}P)", ephemeral=True)

        # 2. 펫 상태 확인
        data = get_legend(self.user_id)
        name, rarity, level, exp, fullness, intimacy, fatigue, last_updated = data

        if level == 0:
            return await interaction.response.send_message("알과는 산책을 할 수 없어요!", ephemeral=True)
        if fullness == 0:
            return await interaction.response.send_message("전설이가 배고파서(포만감 0) 산책을 갈 수 없어요. 먹이를 먼저 주세요!", ephemeral=True)

        # 3. 검증이 끝났으므로 산책 비용 차감
        spend_points(self.user_id, cost)

        # 4. 산책 결과 확률 돌리기
        gained_pts, lost_pts = 0, 0
        drops = {"전설": 0, "신화": 0, "프레스티지": 0}

        for _ in range(count):
            rand = random.uniform(0, 100)
            if rand < 49.0:
                gained_pts += 50
            elif rand < 99.0:
                lost_pts += 50
            elif rand < 99.989:
                drops["전설"] += 1
            elif rand < 99.999:
                drops["신화"] += 1
            else:
                drops["프레스티지"] += 1

        net_points = gained_pts - lost_pts

        # 잃은 돈이 딴 돈보다 많아서 마이너스가 되면 spend_points, 아니면 add_points
        if net_points > 0:
            add_points(self.user_id, net_points)
        elif net_points < 0:
            # 혹시 모를 잔액 부족(음수) 방지를 위해 현재 잔액만큼만 차감되게 안전장치
            spend_points(self.user_id, min(abs(net_points), get_points(self.user_id)))

        for drop_rarity, amount in drops.items():
            if amount > 0: update_user_egg(self.user_id, drop_rarity, amount)

        # 스탯 업데이트
        new_intimacy = min(intimacy + (1 * count), 100)
        new_fatigue = min(fatigue + (1 * count), 100)

        save_legend(self.user_id, name, rarity, level, exp, fullness, new_intimacy, new_fatigue)

        # 5. 결과 임베드 생성
        final_balance_change = net_points - cost
        result_embed = discord.Embed(title=f"🚶 {count}회 산책 완료", color=discord.Color.green())
        result_embed.add_field(
            name="💰 포인트 정산",
            value=f"입장료: -{cost}P\n길에서 주운 돈: +{gained_pts}P\n길에서 흘린 돈: -{lost_pts}P\n**최종 수익: {final_balance_change}P**",
            inline=False
        )

        drop_text = "".join(
            [f"{'🟪 전설' if r == '전설' else '🟨 신화' if r == '신화' else '⬛ 프레스티지'}급 알 {a}개 획득!\n" for r, a in drops.items() if
             a > 0])
        result_embed.add_field(name="🎁 특별 획득", value=drop_text if drop_text else "특별한 아이템을 줍지 못했습니다.", inline=False)

        new_data = (name, rarity, level, exp, fullness, new_intimacy, new_fatigue, last_updated)
        embed = create_status_embed(interaction.user, new_data)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(embed=result_embed, ephemeral=True)

    @discord.ui.button(label="산책 (10P)", style=discord.ButtonStyle.success, emoji="🌲")
    async def walk_1_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 1)

    @discord.ui.button(label="10회 산책 (100P)", style=discord.ButtonStyle.success, emoji="🌳")
    async def walk_10_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 10)

    @discord.ui.button(label="100회 산책 (1000P)", style=discord.ButtonStyle.success, emoji="🌴")
    async def walk_100_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_walk(interaction, 100)