import discord
import io
import time
import random
from datetime import datetime

from utils.database import get_legend_data, get_or_migrate_data, save_legend_data, get_active_buffs
from utils.logs import WALK_LOG_CH, send_log_embed
from utils.stats import get_points
from utils.image_generator import generate_status_image
from utils.game import feed_pet, shower_pet, do_walk

# 전투/스탯 계산 로직은 combat.py 로 분리되었습니다.
# 기존 `from .ui_action import get_pet_stats` 호출부 호환을 위해 여기서 재노출합니다.
from .combat import get_pet_stats

class LegendActionView(discord.ui.View):
    def __init__(self, user_id, current_idx=0, total_pets=1, pet_level=1):
        super().__init__(timeout=300)  # 상태창 버튼 유효시간(초). 짧으면 잠깐 뒤에 눌러도 먹통이라 넉넉히
        self.user_id = user_id
        self.current_idx = current_idx
        self.total_pets = total_pets

        if pet_level == 0:
            self.feed.disabled = True
            self.shower.disabled = True
            self.walk_1.disabled = True
            self.walk_10.disabled = True
            self.walk_100.disabled = True

        if self.total_pets <= 1:
            self.prev_btn.disabled = True
            self.next_btn.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 남의 전설이 상태창은 조작할 수 없습니다!", ephemeral=True)
            return False
        return True

    async def get_pet_data(self):
        wrapper = await get_legend_data(self.user_id)
        if not wrapper or 'pets' not in wrapper: return None, None
        if self.current_idx >= len(wrapper['pets']): self.current_idx = 0
        return wrapper, wrapper['pets'][self.current_idx]

    async def update_status_message(self, interaction: discord.Interaction, data, popup_msg=None, popup_embed=None):
        current_points = await get_points(self.user_id)
        active_buffs = await get_active_buffs(self.user_id)
        buffs = {b[0] for b in active_buffs}

        now = time.time()
        is_annoyed = (data.get('low_full_since', 0) > 0 and now - data['low_full_since'] >= 86400)
        is_diseased = (data.get('low_clean_since', 0) > 0 and now - data['low_clean_since'] >= 86400)

        pet_level = data.get('level', 0)
        self.feed.disabled = (pet_level == 0)
        self.shower.disabled = (pet_level == 0)
        self.walk_1.disabled = (pet_level == 0)
        self.walk_10.disabled = (pet_level == 0)
        self.walk_100.disabled = (pet_level == 0)

        status_image_file = await generate_status_image(
            data, current_points, buffs, is_annoyed, is_diseased, self.current_idx, self.total_pets
        )

        # defer된 상태이므로 followup을 사용해 팝업 전송
        if popup_embed:
            await interaction.followup.send(embed=popup_embed, ephemeral=True)
        elif popup_msg:
            await interaction.followup.send(popup_msg, ephemeral=True)

        # 원본 메시지의 첨부파일과 뷰 업데이트
        await interaction.message.edit(attachments=[status_image_file], embed=None, view=self)

    @discord.ui.button(label="밥주기 (알 1개)", style=discord.ButtonStyle.primary, emoji="🍚", row=0)
    async def feed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer() # 🌟 3초 타임아웃 방지
        # 게임 로직은 utils/game.py 공용 함수에 위임 (내부에서 유저 락 처리)
        res = await feed_pet(self.user_id, self.current_idx)
        if not res["ok"]: return await interaction.followup.send(res["error"], ephemeral=True)
        await self.update_status_message(interaction, res["data"], popup_msg=f"🍚 {res['name']}(이)가 맛있게 밥을 먹었습니다! (포만도 +20, 서사급 알 -1)")

    @discord.ui.button(label="샤워하기 (알 1개)", style=discord.ButtonStyle.primary, emoji="🚿", row=0)
    async def shower(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer() # 🌟 3초 타임아웃 방지
        res = await shower_pet(self.user_id, self.current_idx)
        if not res["ok"]: return await interaction.followup.send(res["error"], ephemeral=True)
        await self.update_status_message(interaction, res["data"], popup_msg=f"🚿 {res['name']}(이)가 깨끗해졌습니다! (청결도 +20, 서사급 알 -1)")

    async def handle_walk(self, interaction: discord.Interaction, num_walks: int):
        await interaction.response.defer() # 🌟 3초 타임아웃 방지
        # 산책 로직은 utils/game.py 공용 함수에 위임 (내부에서 유저 락 처리)
        res = await do_walk(self.user_id, self.current_idx, num_walks)
        if not res["ok"]: return await interaction.followup.send(res["error"], ephemeral=True)

        data = res["data"]
        result_embed = discord.Embed(title="🐾 산책 결과", color=discord.Color.green())
        desc = f"{res['name']}(와)과 {num_walks}회 산책했습니다!\n"
        if res["has_ticket"]: desc += "🎫 `100회 산책 할인권`이 적용되어 서사급 알 30개만 소모되었습니다.\n"
        else: desc += f"🥚 소모된 서사급 알: -{res['cost']}개\n"
        desc += "━━━━━━━━━━━━━━━━━━━━\n"
        if res["gained_exp"] > 0: desc += f"📈 산책을 하며 경험치를 얻었다! (+{res['gained_exp']} XP)\n"
        for egg in res["found_eggs"]: desc += f"🥚 {egg}급 알을 발견했다!\n"
        for rarity, item_name in res["found_items"]: desc += f"🎁 {rarity}급 아이템 [{item_name}]을 발견했다!\n"
        if res["stat_msgs"]: desc += "\n" + "\n".join(res["stat_msgs"])

        result_embed.description = desc
        result_embed.set_footer(text=f"사용자 ID: {self.user_id} | 실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await self.update_status_message(interaction, data, popup_embed=result_embed)

        log_desc = f"🐾 {res['name']} 산책\n🥚 소모 서사급 알: -{res['cost']}개\n"
        if res["gained_exp"] > 0: log_desc += f"📈 획득 경험치: +{res['gained_exp']} XP\n"
        if res["found_eggs"]: log_desc += f"🥚 획득한 알: {', '.join(res['found_eggs'])}급 알\n"
        if res["found_items"]: log_desc += f"🎁 획득한 아이템: {', '.join([i[1] for i in res['found_items']])}\n"
        await send_log_embed(interaction.client, WALK_LOG_CH, "👟 산책 로그", log_desc.strip(), interaction.user, discord.Color.green(), f"구분: {num_walks}회 산책")

    @discord.ui.button(label="1회 산책 (알 1개)", style=discord.ButtonStyle.success, emoji="🚶", row=1)
    async def walk_1(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_walk(interaction, 1)

    @discord.ui.button(label="10회 산책 (알 10개)", style=discord.ButtonStyle.success, emoji="🚶‍♂️", row=1)
    async def walk_10(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_walk(interaction, 10)

    @discord.ui.button(label="100회 산책 (알 100개)", style=discord.ButtonStyle.success, emoji="🏃", row=1)
    async def walk_100(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_walk(interaction, 100)

    @discord.ui.button(label="이전 펫", style=discord.ButtonStyle.secondary, emoji="◀️", row=2)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._navigate(interaction, -1)

    @discord.ui.button(label="다음 펫", style=discord.ButtonStyle.secondary, emoji="▶️", row=2)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._navigate(interaction, +1)

    async def _navigate(self, interaction: discord.Interaction, delta: int):
        await interaction.response.defer() # 🌟 3초 타임아웃 방지
        wrapper = await get_or_migrate_data(self.user_id)
        pets = wrapper.get('pets', [])
        if len(pets) <= 1:
            return await interaction.followup.send("전환할 다른 전설이가 없습니다.", ephemeral=True)
        # 뷰 생성 이후 펫 수가 바뀌었어도 안전하도록 매번 최신값으로 갱신
        self.total_pets = len(pets)
        self.current_idx = (self.current_idx + delta) % self.total_pets
        await self._change_pet(interaction, wrapper)

    async def _change_pet(self, interaction: discord.Interaction, wrapper=None):
        if wrapper is None:  # 직접 호출 대비(하위 호환)
            await interaction.response.defer()
            wrapper = await get_or_migrate_data(self.user_id)
        pets = wrapper.get('pets', [])
        if not pets:
            return await interaction.followup.send("전설이 데이터가 없습니다.", ephemeral=True)
        if self.current_idx >= len(pets):
            self.current_idx = 0
        self.total_pets = len(pets)
        wrapper['active_idx'] = self.current_idx
        data = wrapper['pets'][self.current_idx]

        now = time.time()
        active_buffs = await get_active_buffs(self.user_id)
        buffs = {b[0] for b in active_buffs}

        last_calc = data.get('last_fatigue_calc', now)
        elapsed_minutes = int((now - last_calc) // 60)
        if elapsed_minutes > 0 and data.get('level', 0) > 0:
            fatigue_drop = elapsed_minutes * 20
            data['fatigue'] = max(0, data.get('fatigue', 0) - fatigue_drop)
            data['last_fatigue_calc'] = last_calc + (elapsed_minutes * 60)
        elif 'last_fatigue_calc' not in data: data['last_fatigue_calc'] = now

        if "신비한 알약" in buffs:
            data['fullness'] = 100; data['fatigue'] = 0; data['intimacy'] = 100; data['cleanliness'] = 100
        else:
            if "배부름을 부르는 약" in buffs: data['fullness'] = 100
            if "쌩쌩한약" in buffs: data['fatigue'] = 0
            if "트위치 나가라약" in buffs: data['cleanliness'] = 100
            if "아무무도 인싸로 만드는 약" in buffs: data['intimacy'] = 100

        if data.get('fullness', 100) <= 20:
            if data.get('low_full_since', 0) == 0: data['low_full_since'] = now
        else: data['low_full_since'] = 0

        if data.get('cleanliness', 100) <= 20:
            if data.get('low_clean_since', 0) == 0: data['low_clean_since'] = now
        else: data['low_clean_since'] = 0

        wrapper['pets'][self.current_idx] = data
        await save_legend_data(self.user_id, wrapper)
        await self.update_status_message(interaction, data)