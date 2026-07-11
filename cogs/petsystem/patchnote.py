import io
import asyncio
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont

# 패치노트를 게시할 채널
PATCH_CHANNEL_ID = 1523262012359184514
FONT_PATH = "assets/font.ttf"

# 색상
BG      = (18, 15, 32)
GOLD    = (242, 194, 104)
GOLD_D  = (205, 155, 62)
HEAD    = (255, 217, 138)
TEXT    = (233, 228, 244)
DIM     = (172, 162, 200)
FAINT   = (120, 112, 150)
LINE    = (70, 60, 100)


def _wrap(draw, text, font, max_w):
    """픽셀 너비 기준 줄바꿈 (한글/영문 혼용 대응)."""
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        else:
            if cur:
                lines.append(cur)
            cur = ch
    lines.append(cur)
    return lines or [""]


def generate_patchnote_image(title: str, content: str) -> io.BytesIO:
    """제목 + 내용으로 패치노트 이미지를 그립니다.

    내용 규칙: 한 줄에 하나씩. '#'으로 시작하면 소제목, 빈 줄은 여백.
    """
    S = 2  # 슈퍼샘플링(선명도)
    W = 1160 * S
    margin = 70 * S
    cw = W - margin * 2

    f_title = ImageFont.truetype(FONT_PATH, 58 * S)
    f_kick  = ImageFont.truetype(FONT_PATH, 22 * S)
    f_head  = ImageFont.truetype(FONT_PATH, 33 * S)
    f_body  = ImageFont.truetype(FONT_PATH, 26 * S)

    dummy = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    # 헤더 좌표(측정·그리기 공용)
    kick_y    = 52 * S
    title_y   = kick_y + 42 * S
    title_lines = _wrap(dummy, title, f_title, cw)
    title_lh  = 68 * S
    divider_y = title_y + len(title_lines) * title_lh + 12 * S
    content_top = divider_y + 30 * S

    # 본문 블록 측정
    blocks = []
    for raw in content.split("\n"):
        line = raw.strip()
        if not line:
            blocks.append(("space", None, 18 * S))
        elif line.startswith("#"):
            wl = _wrap(dummy, line.lstrip("#").strip(), f_head, cw - 24 * S)
            blocks.append(("head", wl, 44 * S))
        else:
            wl = _wrap(dummy, line, f_body, cw - 34 * S)
            blocks.append(("bullet", wl, 40 * S))

    y = content_top
    for kind, wl, lh in blocks:
        if kind == "space":
            y += lh
        elif kind == "head":
            y += 22 * S + lh * len(wl) + 8 * S
        else:
            y += lh * len(wl) + 10 * S
    H = int(y + 66 * S)

    # 그리기
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 8 * S], fill=GOLD)  # 상단 골드 바

    d.text((margin, kick_y), "PATCH NOTES", font=f_kick, fill=GOLD)
    date = datetime.now().strftime("%Y.%m.%d")
    d.text((W - margin - d.textlength(date, font=f_kick), kick_y), date, font=f_kick, fill=FAINT)

    ty = title_y
    for tl in title_lines:
        d.text((margin, ty), tl, font=f_title, fill=GOLD)
        ty += title_lh
    d.line([(margin, divider_y), (W - margin, divider_y)], fill=LINE, width=2 * S)

    y = content_top
    for kind, wl, lh in blocks:
        if kind == "space":
            y += lh
        elif kind == "head":
            y += 22 * S
            d.rectangle([margin, y + 6 * S, margin + 10 * S, y + 30 * S], fill=GOLD)
            for ln in wl:
                d.text((margin + 26 * S, y), ln, font=f_head, fill=HEAD)
                y += lh
            y += 8 * S
        else:
            d.ellipse([margin + 2 * S, y + 12 * S, margin + 13 * S, y + 23 * S], fill=GOLD_D)
            for ln in wl:
                d.text((margin + 34 * S, y), ln, font=f_body, fill=TEXT)
                y += lh
            y += 10 * S

    d.text((margin, H - 46 * S), "전설이 키우기 · 패치노트", font=f_kick, fill=FAINT)

    img = img.resize((W // S, H // S), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


class PatchNoteModal(discord.ui.Modal, title="📢 패치노트 작성"):
    def __init__(self):
        super().__init__()
        self.제목 = discord.ui.TextInput(
            label="제목", placeholder="예: 대규모 업데이트 안내", max_length=40, required=True)
        self.내용 = discord.ui.TextInput(
            label="내용 (한 줄에 하나씩 · '#'로 시작하면 소제목)",
            style=discord.TextStyle.paragraph,
            placeholder="# 새로운 전설이\n미니 티모 추가!\n고귀·초월 등급 개방\n\n# 밸런스\n성급당 능력치 2배",
            max_length=1500, required=True)
        self.add_item(self.제목)
        self.add_item(self.내용)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.client.get_channel(PATCH_CHANNEL_ID)
        if channel is None:
            try:
                channel = await interaction.client.fetch_channel(PATCH_CHANNEL_ID)
            except Exception:
                return await interaction.followup.send("❌ 패치노트 채널을 찾을 수 없습니다.", ephemeral=True)

        try:
            buf = await asyncio.to_thread(generate_patchnote_image, self.제목.value, self.내용.value)
        except Exception as e:
            return await interaction.followup.send(f"❌ 이미지 생성 실패: {e}", ephemeral=True)

        await channel.send(file=discord.File(buf, filename="patchnote.png"))
        await interaction.followup.send(f"✅ {channel.mention}에 패치노트를 게시했습니다!", ephemeral=True)


class PatchNoteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="패치노트", description="[관리자] 패치노트를 이미지로 만들어 지정 채널에 게시합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def patchnote(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PatchNoteModal())

    @patchnote.error
    async def patchnote_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ 관리자만 사용할 수 있는 명령어입니다."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot):
    await bot.add_cog(PatchNoteCog(bot))
