import discord
import time
import random
from datetime import datetime
from .database import get_legend_data, save_legend_data
from .data import PET_IMAGES, ITEMS_INFO
from .logs import WALK_LOG_CH, ITEM_USE_LOG_CH, send_log_embed # 💡 로그 모듈 추가

def get_progress_bar(value, fill_emoji, empty_emoji="⬛"):
    val = max(0, min(100, value))
    fill_count = int(val // 20)
    empty_count = 5 - fill_count
    return (fill_emoji * fill_count) + (empty_emoji * empty_count) + f" ({val}%)"

class LegendActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id

    async def get_pet_data(self):
        wrapper = await get_legend_data(self.user_id)
        if not wrapper or 'pets' not in wrapper:
            return None, None
        return wrapper, wrapper['pets'][wrapper['active_idx']]

    async def update_status_message(self, interaction: discord.Interaction, data, popup_msg=None, popup_embed=None):
        from .database import get_user, get_active_buffs
        user_data = await get_user(self.user_id)
        current_points = user_data[1]
        active_buffs = await get_active_buffs(self.user_id)
        buffs = {b[0] for b in active_buffs}

        now = time.time()
        is_annoyed = (data.get('low_full_since', 0) > 0 and now - data['low_full_since'] >= 86400)
        is_diseased = (data.get('low_clean_since', 0) > 0 and now - data['low_clean_since'] >= 86400)

        status_embed = create_status_embed(interaction.user, data, current_points, buffs, is_annoyed, is_diseased)

        if popup_embed:
            await interaction.response.send_message(embed=popup_embed, ephemeral=True)
        elif popup_msg:
            await interaction.response.send_message(popup_msg, ephemeral=True)

        await interaction.message.edit(embed=status_embed)

    @discord.ui.button(label="밥주기 (5P)", style=discord.ButtonStyle.primary, emoji="🍚", row=0)
    async def feed(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .database import get_user, update_user_points
        user_data = await get_user(self.user_id)

        if user_data[1] < 5: return await interaction.response.send_message("❌ 밥값(5P)이 부족합니다!", ephemeral=True)

        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        await update_user_points(self.user_id, -5)
        data['fullness'] = min(100, data.get('fullness', 0) + 20)
        await save_legend_data(self.user_id, wrapper)
        await self.update_status_message(interaction, data, popup_msg=f"🍚 {data['name']}(이)가 맛있게 밥을 먹었습니다! (포만도 +20, 밥값 -5P)")

    @discord.ui.button(label="샤워하기 (10P)", style=discord.ButtonStyle.primary, emoji="🚿", row=0)
    async def shower(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .database import get_user, update_user_points
        user_data = await get_user(self.user_id)

        if user_data[1] < 10: return await interaction.response.send_message("❌ 수도세(10P)가 부족합니다!", ephemeral=True)

        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        await update_user_points(self.user_id, -10)
        data['cleanliness'] = min(100, data.get('cleanliness', 0) + 20)
        await save_legend_data(self.user_id, wrapper)
        await self.update_status_message(interaction, data, popup_msg=f"🚿 {data['name']}(이)가 깨끗해졌습니다! (청결도 +20, 수도세 -10P)")

    async def handle_walk(self, interaction: discord.Interaction, num_walks: int):
        from .database import get_active_buffs, get_user, update_user_points, consume_item, add_item

        wrapper, data = await self.get_pet_data()
        if not data: return await interaction.response.send_message("펫 데이터가 없습니다.", ephemeral=True)

        user_id = self.user_id
        user_data = await get_user(user_id)
        current_points = user_data[1]

        if num_walks == 100:
            has_ticket = await consume_item(user_id, "100회 산책 할인권", 1)
            cost = 300 if has_ticket else 1000
        else:
            has_ticket = False
            cost = num_walks * 10

        if current_points < cost:
            msg = f"❌ 산책 유지비({cost}P)가 부족합니다! (현재: {current_points}P)"
            if has_ticket: await add_item(user_id, "100회 산책 할인권", 1)
            return await interaction.response.send_message(msg, ephemeral=True)

        await update_user_points(user_id, -cost)

        active_buffs = await get_active_buffs(user_id)
        buffs = {b[0] for b in active_buffs}

        data['total_walk_count'] = data.get('total_walk_count', 0) + num_walks
        old_walk_count = data.get('walk_count', 0)
        data['walk_count'] = old_walk_count + num_walks

        stat_triggers = data['walk_count'] // 20
        data['walk_count'] = data['walk_count'] % 20

        stat_msg = ""
        if stat_triggers > 0:
            data['fullness'] = max(0, data.get('fullness', 100) - (20 * stat_triggers))
            data['cleanliness'] = max(0, data.get('cleanliness', 100) - (20 * stat_triggers))
            data['intimacy'] = min(100, data.get('intimacy', 50) + (20 * stat_triggers))
            if "쌩쌩한약" in buffs or "신비한 알약" in buffs:
                stat_msg += "💊 [쌩쌩한약] 효과로 피로도가 오르지 않았습니다!\n"
            else:
                data['fatigue'] = min(100, data.get('fatigue', 0) + (20 * stat_triggers))
            stat_msg += f"✨ {stat_triggers * 20}회 산책 분량 달성! 친밀도가 오르고 배고픔/더러움이 증가했습니다.\n"

        gained_points = 0
        gain_count = 0
        lost_points = 0
        lose_count = 0
        found_eggs = []
        found_items = []

        epic_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '서사']
        legend_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '전설']
        mythic_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '신화']
        prestige_items = [k for k, v in ITEMS_INFO.items() if v['rarity'] == '프레스티지']

        for _ in range(num_walks):
            if random.random() < 0.60:
                gained_points += 50
                gain_count += 1
            if random.random() < 0.50:
                lost_points += 45
                lose_count += 1

            r_egg = random.random()
            if r_egg < 0.0001: found_eggs.append("프레스티지")
            elif r_egg < 0.0021: found_eggs.append("신화")
            elif r_egg < 0.0221: found_eggs.append("전설")
            elif r_egg < 0.1221: found_eggs.append("서사")

            r_item = random.random()
            if r_item < 0.0001 and prestige_items: found_items.append(("프레스티지", random.choice(prestige_items)))
            elif r_item < 0.0011 and mythic_items: found_items.append(("신화", random.choice(mythic_items)))
            elif r_item < 0.0111 and legend_items: found_items.append(("전설", random.choice(legend_items)))
            elif r_item < 0.2111 and epic_items: found_items.append(("서사", random.choice(epic_items)))

        if gained_points > 0: await update_user_points(user_id, gained_points)
        if lost_points > 0: await update_user_points(user_id, -lost_points)

        for egg in found_eggs: await add_item(user_id, f"{egg}급 알", 1)
        for rarity, item_name in found_items: await add_item(user_id, item_name, 1)

        await save_legend_data(self.user_id, wrapper)

        # UI 출력용 임베드 구성
        result_embed = discord.Embed(title="🐾 산책 결과", color=discord.Color.green())
        desc = f"{data['name']}(와)과 {num_walks}회 산책했습니다!\n"
        if has_ticket: desc += "🎫 `100회 산책 할인권`이 적용되어 300P만 소모되었습니다.\n"
        else: desc += f"💸 소모된 유지비: -{cost}P\n"
        desc += "━━━━━━━━━━━━━━━━━━━━\n"

        if num_walks == 1:
            if gain_count: desc += f"💰 산책하다가 포인트를 주웠다! (+{gained_points}P)\n"
            if lose_count: desc += f"💩 산책하다가 똥을 밟았다.. (-{lost_points}P)\n"
        else:
            if gain_count: desc += f"💰 산책하다가 포인트를 주웠다! ({gain_count}번, +{gained_points}P)\n"
            if lose_count: desc += f"💩 산책하다가 똥을 밟았다.. ({lose_count}번, -{lost_points}P)\n"

        for egg in found_eggs: desc += f"🥚 {egg}급 알을 발견했다!\n"
        for rarity, item_name in found_items: desc += f"🎁 {rarity}급 아이템 [{item_name}]을 발견했다!\n"
        if stat_msg: desc += f"\n{stat_msg}"

        result_embed.description = desc
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_embed.set_footer(text=f"사용자 ID: {user_id} | 실행 시각: {current_time}")

        # 사용자에게 결과 전송
        await self.update_status_message(interaction, data, popup_embed=result_embed)

        # 💡 [로그] 산책 로그 발송 (1회/10회/100회 구분)
        log_desc = f"🐾 {data['name']} 산책\n💸 소모 유지비: -{cost}P\n"
        if gained_points > 0: log_desc += f"💰 획득 포인트: +{gained_points}P\n"
        if lost_points > 0: log_desc += f"💩 잃은 포인트: -{lost_points}P\n"
        if found_eggs: log_desc += f"🥚 획득한 알: {', '.join(found_eggs)}급 알\n"
        if found_items: log_desc += f"🎁 획득한 아이템: {', '.join([i[1] for i in found_items])}\n"

        await send_log_embed(
            interaction.client, WALK_LOG_CH, "👟 산책 로그", log_desc.strip(),
            interaction.user, discord.Color.green(), f"구분: {num_walks}회 산책"
        )

    @discord.ui.button(label="1회 산책 (10P)", style=discord.ButtonStyle.success, emoji="🚶", row=1)
    async def walk_1(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_walk(interaction, 1)

    @discord.ui.button(label="10회 산책 (100P)", style=discord.ButtonStyle.success, emoji="🚶‍♂️", row=1)
    async def walk_10(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_walk(interaction, 10)

    @discord.ui.button(label="100회 산책 (1000P)", style=discord.ButtonStyle.success, emoji="🏃", row=1)
    async def walk_100(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_walk(interaction, 100)

class InventoryView(discord.ui.View):
    def __init__(self, user_id, items):
        super().__init__(timeout=60)
        self.user_id = user_id
        for item_name in items:
            self.add_item(InventoryButton(item_name))

class InventoryButton(discord.ui.Button):
    def __init__(self, item_name):
        super().__init__(label=item_name, style=discord.ButtonStyle.secondary)
        self.item_name = item_name

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        item_name = self.item_name

        if item_name == "100회 산책 할인권": return await interaction.response.send_message("💡 이 아이템은 100회 산책 시 자동으로 사용됩니다!", ephemeral=True)
        elif item_name == "전설이 이름 변경권": return await interaction.response.send_message("💡 이 아이템은 `/이름변경` 명령어를 입력해서 사용할 수 있습니다!", ephemeral=True)
        elif "급 알" in item_name: return await interaction.response.send_message("💡 알은 인벤토리에 보관됩니다! 아직 알을 직접 까는 기능은 추가되지 않았습니다.", ephemeral=True)

        if "경험치 부스터" in item_name:
            from .database import get_legend_data
            wrapper = await get_legend_data(user_id)
            if wrapper and wrapper.get('pets'):
                pet_data = wrapper['pets'][wrapper['active_idx']]
                if pet_data.get('cleanliness', 0) == 100:
                    return await interaction.response.send_message("❌ 청결도가 100(MAX) 상태일 때는 경험치 부스터를 사용할 수 없습니다!", ephemeral=True)

        from .database import consume_item, add_buff, update_user_points
        success = await consume_item(user_id, item_name, 1)
        if not success: return await interaction.response.send_message("❌ 아이템을 보유하고 있지 않거나 부족합니다.", ephemeral=True)

        msg = f"✅ `{item_name}`을(를) 사용했습니다!\n"

        if item_name in ["배부름을 부르는 약", "쌩쌩한약", "트위치 나가라약", "아무무도 인싸로 만드는 약"]:
            await add_buff(user_id, buff_name=item_name, duration_sec=86400, vc_sec=0)
            msg += "✨ 효과: 24시간 동안 해당 스탯이 고정됩니다."
        elif item_name == "신비한 알약":
            await add_buff(user_id, buff_name=item_name, duration_sec=1209600, vc_sec=0)
            msg += "✨ 효과: 14일 동안 모든 스탯이 최상으로 고정됩니다."
        elif item_name in ["경험치 부스터 X2", "경험치 부스터 X5", "경험치 부스터 X10"]:
            await add_buff(user_id, buff_name=item_name, duration_sec=0, vc_sec=10800)
            msg += "📈 효과: 통화방에 있는 동안 3시간 동안 경험치 획득량이 증가합니다."
        elif item_name == "50포인트 교환권":
            await update_user_points(user_id, 50)
            msg += "💸 50P를 획득했습니다!"
        elif item_name == "100포인트 교환권":
            await update_user_points(user_id, 100)
            msg += "💸 100P를 획득했습니다!"
        elif item_name == "500포인트 교환권":
            await update_user_points(user_id, 500)
            msg += "💸 500P를 획득했습니다!"
        elif item_name == "1000포인트 교환권":
            await update_user_points(user_id, 1000)
            msg += "💸 1,000P를 획득했습니다!"

        await interaction.response.send_message(msg, ephemeral=True)

        # 💡 [로그] 아이템 사용 로그 발송
        await send_log_embed(
            interaction.client, ITEM_USE_LOG_CH, "🎒 아이템 사용 로그",
            f"사용 아이템: {item_name}\n효과가 성공적으로 적용되었습니다.",
            interaction.user, discord.Color.blue()
        )

def create_status_embed(user, data, points, buffs, is_annoyed, is_diseased):
    embed = discord.Embed(title=f"🐾 {data['name']}의 상태창", color=discord.Color.gold())

    pet_type = data.get('type')
    if pet_type in PET_IMAGES: embed.set_thumbnail(url=PET_IMAGES[pet_type])

    embed.add_field(name="등급", value=data.get('rarity', '서사'), inline=True)
    embed.add_field(name="레벨", value=f"{data.get('level', 0)}성", inline=True)
    embed.add_field(name="경험치", value=f"{data.get('exp', 0)}", inline=True)

    embed.add_field(name="포만도", value=get_progress_bar(data.get('fullness', 0), "🍗"), inline=True)
    embed.add_field(name="피로도", value=get_progress_bar(data.get('fatigue', 0), "😴"), inline=True)
    embed.add_field(name="청결도", value=get_progress_bar(data.get('cleanliness', 0), "🚿"), inline=True)
    embed.add_field(name="친밀도", value=get_progress_bar(data.get('intimacy', 0), "💖", "🖤"), inline=True)

    if buffs: embed.add_field(name="활성화된 버프", value=", ".join(buffs), inline=False)
    if is_annoyed: embed.add_field(name="⚠️ 상태", value="배가 너무 고파서 심술이 났습니다!", inline=False)
    if is_diseased: embed.add_field(name="⚠️ 상태", value="너무 더러워서 병에 걸렸습니다!", inline=False)

    embed.set_footer(text=f"보유 포인트: {points}P | 누적 산책: {data.get('total_walk_count', 0)}회")
    return embed