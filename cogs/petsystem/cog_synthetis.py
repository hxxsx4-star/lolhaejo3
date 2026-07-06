import discord
from discord.ext import commands
from discord import app_commands
import random
import time

from .data import PET_POOLS
from .database import get_or_migrate_data, save_legend_data

class SynthesisCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="전설이합성", description="같은 등급 3성 2마리를 합성하여 확률적으로 상위 등급을 획득합니다.")
    @app_commands.choices(등급=[
        app_commands.Choice(name="서사 (전설급 확률 80%)", value="서사"),
        app_commands.Choice(name="전설 (신화급 확률 50%)", value="전설"),
        app_commands.Choice(name="신화 (프레스티지급 확률 20%)", value="신화")
    ])
    async def synthesis_cmd(self, interaction: discord.Interaction, 등급: str):
        wrapper = await get_or_migrate_data(interaction.user.id)
        pets = wrapper.get('pets', [])

        # 💡 해당 등급이고, 3성인 펫들의 인덱스 찾기
        eligible_pets = []
        for i, p in enumerate(pets):
            if p.get('rarity') == 등급 and p.get('level', 0) == 3:
                eligible_pets.append((i, p))

        if len(eligible_pets) < 2:
            return await interaction.response.send_message(f"❌ 파티에 합성을 위한 `{등급}`급 3성 전설이가 2마리 이상 필요합니다.\n*(박스에 있다면 파티로 데려오세요!)*", ephemeral=True)

        options = [discord.SelectOption(label=f"{p['name']} ({p['type']})", description=f"레벨: 3성 | 스탯 재료", value=str(i)) for i, p in eligible_pets[:25]]

        select = discord.ui.Select(min_values=2, max_values=2, placeholder="합성할 전설이 2마리를 선택하세요 (서로 다른 종류)", options=options)

        async def select_callback(sel_inter: discord.Interaction):
            if sel_inter.user.id != interaction.user.id:
                return await sel_inter.response.send_message("❌ 본인만 선택할 수 있습니다.", ephemeral=True)

            # 선택한 인덱스 파싱
            idx1, idx2 = int(select.values[0]), int(select.values[1])

            # 최신 데이터 다시 로드
            wrapper = await get_or_migrate_data(interaction.user.id)
            pet1 = wrapper['pets'][idx1]
            pet2 = wrapper['pets'][idx2]

            # 💡 [요청사항] 종류(type)가 달라야 함
            if pet1.get('type') == pet2.get('type'):
                return await sel_inter.response.send_message("❌ 합성에 쓰이는 두 전설이는 서로 다른 종류(PET_POOLS)여야 합니다!", ephemeral=True)

            # 타겟 등급 및 확률 설정
            target_rarity = ""
            prob = 0.0
            if 등급 == "서사":
                target_rarity = "전설"
                prob = 0.8
            elif 등급 == "전설":
                target_rarity = "신화"
                prob = 0.5
            elif 등급 == "신화":
                target_rarity = "프레스티지"
                prob = 0.2

            # ⚠️ 두 전설이 희생 (삭제 시 인덱스 꼬임 방지를 위해 뒤에서부터 pop)
            indices_to_remove = sorted([idx1, idx2], reverse=True)
            for i in indices_to_remove:
                wrapper['pets'].pop(i)

            wrapper['active_idx'] = max(0, len(wrapper['pets']) - 1)

            # 성공/실패 판정
            is_success = random.random() < prob

            if is_success:
                new_type = random.choice(PET_POOLS[target_rarity])
                new_pet_data = {
                    'name': f"합성된 {new_type} 알", 'type': new_type, 'rarity': target_rarity, 'level': 0, 'exp': 0, 'fullness': 100,
                    'intimacy': 50, 'fatigue': 0, 'cleanliness': 100, 'walk_count': 0, 'total_walk_count': 0,
                    'last_fatigue_calc': time.time()
                }
                wrapper['pets'].append(new_pet_data)

                embed = discord.Embed(title="✨ 전설이 합성 대성공!! ✨", color=discord.Color.gold())
                embed.description = f"희생된 두 마리의 힘이 모여...\n\n🎉 [{target_rarity}급] {new_type} 알이 탄생했습니다!\n*(새로운 알이 파티에 합류했습니다)*"
                embed.set_thumbnail(url="https://i.imgur.com/2sR9O1j.gif") # 예시 빛나는 효과 GIF
            else:
                embed = discord.Embed(title="💥 합성 실패...", color=discord.Color.dark_gray())
                embed.description = "두 전설이의 힘이 엇갈려 폭발해버렸습니다...\n\n💀 합성에 사용된 두 마리의 전설이가 모두 소멸했습니다."

            await save_legend_data(interaction.user.id, wrapper)
            await sel_inter.response.edit_message(embed=embed, view=None)

        select.callback = select_callback
        view = discord.ui.View(timeout=60)
        view.add_item(select)

        await interaction.response.send_message("합성로에 넣을 전설이 두 마리를 선택하세요.\n⚠️ 주의: 합성 성공 여부와 상관없이 선택한 두 마리는 소멸합니다!", view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(SynthesisCog(bot))