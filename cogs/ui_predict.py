import discord

class BetModal(discord.ui.Modal, title="베팅 확인"):
    def __init__(self, topic_id: int, choice: str):
        super().__init__()
        self.topic_id = topic_id
        self.choice = choice
        self.add_item(discord.ui.TextInput(label=f"[{choice}]에 '서사급 알' 1개를 베팅합니다.",
                                           style=discord.TextStyle.short,
                                           placeholder="확인하시려면 '네'라고 입력하세요.",
                                           required=True))

    async def on_submit(self, interaction: discord.Interaction):
        # 실제 베팅 로직은 Cog의 리스너에서 처리됩니다.
        # 이 모달은 데이터를 전달하는 역할만 합니다.
        if self.children[0].value.lower() in ['네', '예', 'ㅇ', 'ㅇㅇ']:
            await interaction.response.defer() # Cog에서 후속 처리
        else:
            await interaction.response.send_message("베팅이 취소되었습니다.", ephemeral=True)

class PredictionView(discord.ui.View):
    def __init__(self, topic_id: int, options: list):
        super().__init__(timeout=None)
        self.topic_id = topic_id
        for option in options:
            # 각 버튼에 고유한 custom_id를 부여합니다.
            self.add_item(discord.ui.Button(label=option, style=discord.ButtonStyle.primary, custom_id=f"predict_{topic_id}_{option}"))

def create_prediction_embed(topic_id: int, title: str, options: list, bets: dict = None):
    embed = discord.Embed(title=f"🔮 예측 #{topic_id}: {title}", color=discord.Color.dark_purple())
    
    if not bets:
        embed.description = "아래 버튼을 눌러 '서사급 알' 1개를 소모하여 예측에 참여하세요!"
    else:
        total_bets = sum(bets.values())
        embed.description = f"**총 베팅: {total_bets}개**"
        for option, count in bets.items():
            percentage = (count / total_bets * 100) if total_bets > 0 else 0
            embed.add_field(name=f"ㄴ {option}", value=f"{count}개 ({percentage:.1f}%)", inline=False)
            
    return embed
