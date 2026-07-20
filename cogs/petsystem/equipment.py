import discord
from discord.ext import commands
from discord import app_commands

from utils.database import get_or_migrate_data, save_legend_data, get_user_items, add_item, consume_item
from utils.data import (
    EQUIPMENTS, MAX_EQUIP_PER_PET,
    get_pet_total_stats, get_equipment_bonus, format_equip_effect,
)
from .locks import get_user_lock


class EquipmentView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.pet_idx = None

        self.pet_select = discord.ui.Select(placeholder="장비를 관리할 전설이를 선택하세요")
        self.pet_select.callback = self.on_pet_select
        self.add_item(self.pet_select)

        self.equip_select = None
        self.unequip_select = None

    def _guard(self, interaction):
        return interaction.user.id == self.user_id

    async def build(self):
        """현재 DB 상태를 읽어 셀렉트들을 재구성하고, 선택된 펫을 반환합니다."""
        wrapper = await get_or_migrate_data(self.user_id)
        pets = wrapper.get('pets', [])

        self.pet_select.options = [
            discord.SelectOption(label=f"{p.get('name','이름없음')} ({p.get('type','?')})",
                                 value=str(i), default=(i == self.pet_idx))
            for i, p in enumerate(pets[:25])
        ] or [discord.SelectOption(label="보유한 전설이가 없습니다", value="none")]

        # 기존 장착/해제 셀렉트 제거 후 필요 시 재생성
        for sel in (self.equip_select, self.unequip_select):
            if sel:
                self.remove_item(sel)
        self.equip_select = None
        self.unequip_select = None

        if self.pet_idx is None or self.pet_idx >= len(pets):
            return None

        pet = pets[self.pet_idx]
        equipped = pet.get('equipment', []) or []

        # 인벤토리에 있는 장비 아이템만 추림
        inv = await get_user_items(self.user_id)
        inv_equips = [(name, amt) for name, amt in inv if name in EQUIPMENTS]

        if len(equipped) < MAX_EQUIP_PER_PET and inv_equips:
            opts = [discord.SelectOption(label=f"{n} (보유 {amt})", value=n,
                                         description=format_equip_effect(n)[:100])
                    for n, amt in inv_equips[:25]]
            self.equip_select = discord.ui.Select(
                placeholder=f"장착할 장비 선택 ({len(equipped)}/{MAX_EQUIP_PER_PET})", options=opts)
            self.equip_select.callback = self.on_equip
            self.add_item(self.equip_select)

        if equipped:
            opts = [discord.SelectOption(label=n, value=f"{idx}:{n}",
                                         description=format_equip_effect(n)[:100])
                    for idx, n in enumerate(equipped)]
            self.unequip_select = discord.ui.Select(placeholder="해제할 장비 선택", options=opts)
            self.unequip_select.callback = self.on_unequip
            self.add_item(self.unequip_select)

        return pet

    def build_embed(self, pet):
        if not pet:
            return discord.Embed(title="🎽 장비 관리",
                                 description="아래에서 전설이를 선택하세요.\n전설이 한 마리당 장비는 최대 3개까지 장착할 수 있습니다.",
                                 color=discord.Color.blurple())
        equipped = pet.get('equipment', []) or []
        stats = get_pet_total_stats(pet)
        bonus = get_equipment_bonus(pet)

        embed = discord.Embed(title=f"🎽 {pet.get('name','?')} 장비 관리", color=discord.Color.blurple())
        eq_lines = [f"• {n} — {format_equip_effect(n)}" for n in equipped]
        embed.add_field(name=f"🔧 장착 장비 ({len(equipped)}/{MAX_EQUIP_PER_PET})",
                        value="\n".join(eq_lines) or "없음", inline=False)
        embed.add_field(name="📊 최종 스탯 (장비 포함)",
                        value=f"AD {stats['AD']} | DF {stats['DF']} | AP {stats['AP']} | MR {stats['MR']}", inline=False)
        embed.add_field(name="✨ 장비 보너스",
                        value=f"AD +{bonus['AD']} | DF +{bonus['DF']} | AP +{bonus['AP']} | MR +{bonus['MR']}", inline=False)
        return embed

    async def refresh(self, interaction):
        pet = await self.build()
        await interaction.response.edit_message(embed=self.build_embed(pet), view=self)

    async def on_pet_select(self, interaction: discord.Interaction):
        if not self._guard(interaction):
            return await interaction.response.send_message("❌ 본인만 사용할 수 있습니다.", ephemeral=True)
        val = self.pet_select.values[0]
        if val == "none":
            return await interaction.response.defer()
        self.pet_idx = int(val)
        await self.refresh(interaction)

    async def on_equip(self, interaction: discord.Interaction):
        if not self._guard(interaction):
            return await interaction.response.send_message("❌ 본인만 사용할 수 있습니다.", ephemeral=True)
        equip_name = self.equip_select.values[0]

        async with get_user_lock(self.user_id):
            wrapper = await get_or_migrate_data(self.user_id)
            pets = wrapper.get('pets', [])
            if self.pet_idx is None or self.pet_idx >= len(pets):
                return await interaction.response.send_message("❌ 전설이 데이터가 변경되었습니다. 다시 시도하세요.", ephemeral=True)
            pet = pets[self.pet_idx]
            equipped = pet.get('equipment', []) or []
            if len(equipped) >= MAX_EQUIP_PER_PET:
                return await interaction.response.send_message(f"❌ 장비는 최대 {MAX_EQUIP_PER_PET}개까지 장착할 수 있습니다.", ephemeral=True)
            if not await consume_item(self.user_id, equip_name, 1):
                return await interaction.response.send_message("❌ 해당 장비를 보유하고 있지 않습니다.", ephemeral=True)
            equipped.append(equip_name)
            pet['equipment'] = equipped
            await save_legend_data(self.user_id, wrapper)

        await self.refresh(interaction)

    async def on_unequip(self, interaction: discord.Interaction):
        if not self._guard(interaction):
            return await interaction.response.send_message("❌ 본인만 사용할 수 있습니다.", ephemeral=True)
        slot_str, name = self.unequip_select.values[0].split(":", 1)

        async with get_user_lock(self.user_id):
            wrapper = await get_or_migrate_data(self.user_id)
            pets = wrapper.get('pets', [])
            if self.pet_idx is None or self.pet_idx >= len(pets):
                return await interaction.response.send_message("❌ 전설이 데이터가 변경되었습니다. 다시 시도하세요.", ephemeral=True)
            pet = pets[self.pet_idx]
            equipped = pet.get('equipment', []) or []

            slot = int(slot_str)
            if slot >= len(equipped) or equipped[slot] != name:
                # 슬롯이 어긋났으면 이름으로 재탐색
                if name in equipped:
                    slot = equipped.index(name)
                else:
                    return await interaction.response.send_message("❌ 이미 해제된 장비입니다.", ephemeral=True)

            removed = equipped.pop(slot)
            pet['equipment'] = equipped
            # 특수 장비(메자이/오만) 누적 스택은 해제 시 초기화
            stacks = pet.get('equip_stacks', {})
            if removed in stacks:
                del stacks[removed]
            await add_item(self.user_id, removed, 1)  # 인벤토리로 반환
            await save_legend_data(self.user_id, wrapper)

        await self.refresh(interaction)


class EquipmentCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="장비", description="전설이에게 장비를 장착하거나 해제합니다. (한 마리당 최대 3개)")
    async def equipment(self, interaction: discord.Interaction):
        wrapper = await get_or_migrate_data(interaction.user.id)
        if not wrapper.get('pets'):
            return await interaction.response.send_message("❌ 아직 전설이가 없습니다. `/알까기`로 시작하세요!", ephemeral=True)
        view = EquipmentView(interaction.user.id)
        await view.build()
        await interaction.response.send_message(embed=view.build_embed(None), view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(EquipmentCog(bot))
