import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite

from .ui_predict import create_prediction_embed, PredictionView, BetModal
from ..petsystem.database import add_item, consume_item

class PredictCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.init_predict_db())

    async def init_predict_db(self):
        async with aiosqlite.connect('predictions.db') as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS topics
                                (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, options TEXT,
                                 message_id INTEGER, channel_id INTEGER, is_open INTEGER DEFAULT 1)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS bets
                                (topic_id INTEGER, user_id INTEGER, choice TEXT,
                                 PRIMARY KEY (topic_id, user_id))''')
            await db.commit()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("predict_"):
            return

        parts = custom_id.split("_")
        topic_id, choice = int(parts[1]), "_".join(parts[2:])
        
        modal = BetModal(topic_id, choice)
        await interaction.response.send_modal(modal)
        await modal.wait()

        if modal.children[0].value.lower() in ['네', '예', 'ㅇ', 'ㅇㅇ']:
            user_id = interaction.user.id
            if not await consume_item(user_id, "서사급 알", 1):
                return await interaction.followup.send("베팅에 필요한 '서사급 알'이 부족합니다!", ephemeral=True)

            async with aiosqlite.connect('predictions.db') as db:
                cursor = await db.execute("SELECT * FROM bets WHERE topic_id = ? AND user_id = ?", (topic_id, user_id))
                if await cursor.fetchone():
                    await add_item(user_id, "서사급 알", 1)
                    return await interaction.followup.send("이미 이 주제에 베팅하셨습니다.", ephemeral=True)
                
                await db.execute("INSERT INTO bets VALUES (?, ?, ?)", (topic_id, user_id, choice))
                await db.commit()
            
            await interaction.followup.send(f"✅ [{choice}]에 성공적으로 베팅했습니다!", ephemeral=True)
            await self.update_prediction_message(topic_id)

    async def update_prediction_message(self, topic_id: int):
        async with aiosqlite.connect('predictions.db') as db:
            topic_row = await (await db.execute("SELECT * FROM topics WHERE id = ?", (topic_id,))).fetchone()
            if not topic_row: return

            bets_rows = await (await db.execute("SELECT choice, COUNT(*) FROM bets WHERE topic_id = ? GROUP BY choice", (topic_id,))).fetchall()
            bets = dict(bets_rows)

            channel = self.bot.get_channel(topic_row[3])
            if not channel: return
            
            try:
                msg = await channel.fetch_message(topic_row[2])
                embed = create_prediction_embed(topic_id, topic_row[1], topic_row[2].split(','), bets)
                await msg.edit(embed=embed)
            except discord.NotFound:
                pass

    @app_commands.command(name="예측생성", description="[관리자] 새로운 예측 주제를 생성합니다.")
    @app_commands.describe(주제="예측할 내용", 선택지="쉼표(,)로 구분된 선택지 목록 (예: 승리,패배)")
    @app_commands.default_permissions(manage_guild=True)
    async def create_prediction(self, interaction: discord.Interaction, 주제: str, 선택지: str):
        options = [opt.strip() for opt in 선택지.split(',')]
        if len(options) < 2:
            return await interaction.response.send_message("선택지는 최소 2개 이상이어야 합니다.", ephemeral=True)

        async with aiosqlite.connect('predictions.db') as db:
            cursor = await db.execute("INSERT INTO topics (title, options) VALUES (?, ?)", (주제, 선택지))
            topic_id = cursor.lastrowid
            await db.commit()

        embed = create_prediction_embed(topic_id, 주제, options)
        view = PredictionView(topic_id, options)
        msg = await interaction.channel.send(embed=embed, view=view)

        async with aiosqlite.connect('predictions.db') as db:
            await db.execute("UPDATE topics SET message_id = ?, channel_id = ? WHERE id = ?", (msg.id, msg.channel.id, topic_id))
            await db.commit()
        
        await interaction.response.send_message(f"✅ 예측 #{topic_id}이 생성되었습니다.", ephemeral=True)

    @app_commands.command(name="예측마감", description="[관리자] 예측을 마감하고 결과를 발표합니다.")
    @app_commands.describe(예측id="마감할 예측의 ID", 결과="최종 결과 선택지")
    @app_commands.default_permissions(manage_guild=True)
    async def end_prediction(self, interaction: discord.Interaction, 예측id: int, 결과: str):
        await interaction.response.defer(ephemeral=True)
        async with aiosqlite.connect('predictions.db') as db:
            topic = await (await db.execute("SELECT * FROM topics WHERE id = ? AND is_open = 1", (예측id,))).fetchone()
            if not topic:
                return await interaction.followup.send("존재하지 않거나 이미 마감된 예측입니다.", ephemeral=True)

            await db.execute("UPDATE topics SET is_open = 0 WHERE id = ?", (예측id,))
            
            winners = await (await db.execute("SELECT user_id FROM bets WHERE topic_id = ? AND choice = ?", (예측id, 결과))).fetchall()
            total_bets = await (await db.execute("SELECT COUNT(*) FROM bets WHERE topic_id = ?", (예측id,))).fetchone()
            total_bets = total_bets[0] if total_bets else 0

            if not winners:
                return await interaction.followup.send(f"예측 #{예측id}이 마감되었습니다. 승자가 없습니다.", ephemeral=True)

            prize_per_winner = total_bets // len(winners)
            for (user_id,) in winners:
                await add_item(user_id, "서사급 알", prize_per_winner)

            await db.commit()

        winner_mentions = [f"<@{w[0]}>" for w in winners]
        result_embed = discord.Embed(title=f"🔮 예측 #{예측id} 결과 발표!", color=discord.Color.green())
        result_embed.add_field(name="주제", value=topic[1], inline=False)
        result_embed.add_field(name="결과", value=f"**{결과}**", inline=False)
        result_embed.add_field(name="승자", value=", ".join(winner_mentions) or "없음", inline=False)
        result_embed.add_field(name="배당", value=f"각 '서사급 알' {prize_per_winner}개", inline=False)
        
        await interaction.channel.send(embed=result_embed)
        await interaction.followup.send(f"✅ 예측 #{예측id}이 마감되고 결과가 발표되었습니다.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PredictCog(bot))
