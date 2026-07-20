import sys, os, html
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from utils.data import (PET_POOLS, PET_STATS, PET_IMAGES, PET_IMAGES_EVOLVED,
                        EQUIPMENTS, EQUIP_PRICE, RARITY_ORDER, format_equip_effect)

RARITY = {
    "서사":      {"color": "#3d8bf0"},
    "전설":      {"color": "#e5484d"},
    "신화":      {"color": "#a855f7"},
    "프레스티지": {"color": "#f0b73f"},
    "고귀":      {"color": "#2fb8a8", "grad": "linear-gradient(95deg,#f5d64a,#38d6c2)"},
    "초월":      {"color": "#a56bff", "grad": "linear-gradient(95deg,#ff6b6b,#ffb14e,#ffe14e,#4fe08a,#4f9dff,#b96bff)"},
}
STAT_META = [("AD", "공격", "#e5686b"), ("DF", "방어", "#5aa9e6"), ("AP", "주문", "#b07be8"), ("MR", "마저", "#4fd6c8")]
ANCHOR = {r: f"g{i}" for i, r in enumerate(RARITY_ORDER)}

def esc(s): return html.escape(str(s))

def rarity_chip(r):
    m = RARITY[r]
    if "grad" in m:
        return (f'<a href="#{ANCHOR[r]}" class="navchip grad" style="--c:{m["color"]};--g:{m["grad"]}">'
                f'<span class="dot"></span><span class="nm">{esc(r)}</span></a>')
    return (f'<a href="#{ANCHOR[r]}" class="navchip" style="--c:{m["color"]}">'
            f'<span class="dot"></span>{esc(r)}</a>')

def pet_card(name, rarity):
    s = PET_STATS.get(name, {"AD": 0, "DF": 0, "AP": 0, "MR": 0})
    total = sum(s.values())
    img = PET_IMAGES.get(name, "")
    evolved = name in PET_IMAGES_EVOLVED
    stat_rows = "".join(
        f'<div class="st"><span class="sdot" style="background:{c}"></span>'
        f'<span class="sl">{k}</span><span class="sv">{s.get(k,0)}</span></div>'
        for k, _, c in STAT_META
    )
    badge = '<span class="evo">3성 진화</span>' if evolved else ""
    emoji = esc(name.split(" ", 1)[0]) if " " in name else "🥚"
    return f'''<article class="pet">
      <div class="thumb"><span class="emo">{emoji}</span><img src="{esc(img)}" loading="lazy" alt="{esc(name)}"
           onerror="this.remove()">{badge}</div>
      <div class="pname">{esc(name)}</div>
      <div class="stats">{stat_rows}</div>
      <div class="total">합계 <b>{total}</b> <span class="hint">· 기본(1성) 스탯</span></div>
    </article>'''

def grade_section(r):
    m = RARITY[r]
    accent = m.get("grad", m["color"])
    pets = "".join(pet_card(n, r) for n in PET_POOLS[r])
    return f'''<section id="{ANCHOR[r]}" class="grade">
      <div class="ghead"><span class="gbar" style="background:{accent}"></span>
        <h2>{esc(r)}</h2><span class="gcount">{len(PET_POOLS[r])}종</span></div>
      <div class="petgrid">{pets}</div>
    </section>'''

def equip_section():
    blocks = []
    for r in RARITY_ORDER:
        items = [n for n, i in EQUIPMENTS.items() if i["rarity"] == r]
        if not items:
            continue
        m = RARITY[r]; accent = m.get("grad", m["color"])
        rows = "".join(
            f'<div class="erow"><span class="ename">{esc(n)}</span>'
            f'<span class="eeff">{esc(format_equip_effect(n))}</span></div>'
            for n in items
        )
        price = EQUIP_PRICE[r]
        blocks.append(f'''<div class="ecard">
          <div class="ehead"><span class="gbar" style="background:{accent}"></span>
            <h3>{esc(r)} 장비</h3><span class="eprice">서사급 알 {price:,}</span></div>
          {rows}</div>''')
    return f'<section id="equip" class="equip"><h2 class="etitle">🎽 장비 도감</h2><div class="egrid">{"".join(blocks)}</div></section>'

total_pets = sum(len(v) for v in PET_POOLS.values())
nav = "".join(rarity_chip(r) for r in RARITY_ORDER) + '<a href="#equip" class="navchip" style="--c:#f2c268"><span class="dot"></span>장비</a>'
sections = "".join(grade_section(r) for r in RARITY_ORDER) + equip_section()

HTML = f'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>전설이 도감</title>
<style>
:root{{--bg:#0d0a17;--bg2:#0a0813;--surface:#16112a;--surface2:#1d1636;
--border:rgba(185,165,255,.14);--border2:rgba(205,185,255,.26);
--text:#ece7f7;--dim:#a89ec6;--faint:#7a7196;--gold:#f2c268;--accent:#927ce8;}}
*{{box-sizing:border-box;}}
body{{margin:0;background:radial-gradient(1100px 560px at 50% -6%,#16112b,transparent 62%),linear-gradient(180deg,var(--bg),var(--bg2));
color:var(--text);font-family:'Pretendard','NanumGothic','Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif;
line-height:1.6;word-break:keep-all;-webkit-font-smoothing:antialiased;}}
a{{text-decoration:none;color:inherit;}}
.wrap{{max-width:1180px;margin:0 auto;padding:0 20px 90px;}}
header.hero{{text-align:center;padding:64px 0 20px;}}
.hero .eye{{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:var(--gold);font-weight:800;}}
.hero h1{{margin:14px 0 6px;font-size:clamp(40px,8vw,68px);font-weight:900;letter-spacing:-.02em;
background:linear-gradient(100deg,var(--gold),#fff4d6 45%,#d6a13e);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;}}
.hero p{{color:var(--dim);margin:6px 0 0;font-size:16px;}}
.hero .count{{color:var(--gold);font-weight:800;}}
nav.gnav{{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:8px;justify-content:center;
padding:14px 10px;margin:14px -20px 30px;background:color-mix(in srgb,var(--bg) 82%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--border);}}
.navchip{{display:inline-flex;align-items:center;gap:7px;padding:7px 14px;border-radius:100px;font-weight:800;font-size:14px;
background:color-mix(in srgb,var(--c) 12%,var(--surface));border:1px solid color-mix(in srgb,var(--c) 42%,transparent);}}
.navchip .dot{{width:9px;height:9px;border-radius:50%;background:var(--c);box-shadow:0 0 8px color-mix(in srgb,var(--c) 70%,transparent);}}
.navchip.grad{{border-color:var(--border2);background:var(--surface2);}}
.navchip.grad .dot{{background:var(--g);}}
.navchip.grad .nm{{background:var(--g);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;}}
.grade{{margin:38px 0;scroll-margin-top:80px;}}
.ghead{{display:flex;align-items:center;gap:12px;margin-bottom:18px;}}
.gbar{{width:6px;height:26px;border-radius:6px;flex:none;}}
.ghead h2{{margin:0;font-size:26px;font-weight:900;letter-spacing:-.01em;}}
.gcount{{color:var(--faint);font-size:14px;font-weight:700;}}
.petgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px;}}
.pet{{background:linear-gradient(180deg,var(--surface2),var(--surface));border:1px solid var(--border);border-radius:16px;padding:14px;}}
.thumb{{position:relative;aspect-ratio:1/1;border-radius:12px;overflow:hidden;background:radial-gradient(circle at 50% 35%,#1d1636,#0e0b1a);border:1px solid var(--border);display:grid;place-items:center;}}
.thumb .emo{{font-size:62px;line-height:1;filter:drop-shadow(0 4px 10px rgba(0,0,0,.5));}}
.thumb img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;}}
.evo{{position:absolute;top:8px;right:8px;font-size:10px;font-weight:800;letter-spacing:.04em;color:#0d0a17;
background:linear-gradient(95deg,#ff6b6b,#ffe14e,#4f9dff,#b96bff);padding:3px 8px;border-radius:8px;}}
.pname{{margin:12px 2px 10px;font-weight:800;font-size:15px;line-height:1.35;}}
.stats{{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;}}
.st{{display:flex;align-items:center;gap:6px;font-size:13px;}}
.sdot{{width:8px;height:8px;border-radius:50%;flex:none;}}
.sl{{color:var(--dim);width:22px;}}
.sv{{margin-left:auto;font-weight:800;font-variant-numeric:tabular-nums;}}
.total{{margin-top:11px;padding-top:10px;border-top:1px solid var(--border);font-size:12.5px;color:var(--dim);}}
.total b{{color:var(--gold);font-size:15px;}}
.total .hint{{color:var(--faint);}}
.equip{{margin-top:56px;scroll-margin-top:80px;}}
.etitle{{font-size:24px;font-weight:900;margin:0 0 20px;}}
.egrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;}}
.ecard{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:16px 18px;}}
.ehead{{display:flex;align-items:center;gap:10px;margin-bottom:12px;}}
.ehead h3{{margin:0;font-size:17px;font-weight:800;}}
.eprice{{margin-left:auto;font-size:12px;color:var(--gold);font-weight:700;}}
.erow{{display:flex;gap:12px;justify-content:space-between;padding:7px 0;border-top:1px solid var(--border);font-size:14px;}}
.ename{{font-weight:700;flex:none;}}
.eeff{{color:var(--dim);text-align:right;}}
footer{{text-align:center;margin-top:60px;padding-top:24px;border-top:1px solid var(--border);color:var(--faint);font-size:13px;}}
@media (max-width:520px){{.petgrid{{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));}}}}
</style></head><body>
<div class="wrap">
  <header class="hero">
    <div class="eye">LEGEND COMPENDIUM</div>
    <h1>전설이 도감</h1>
    <p>전체 <span class="count">{total_pets}종</span>의 전설이와 <span class="count">{len(EQUIPMENTS)}종</span>의 장비</p>
  </header>
  <nav class="gnav">{nav}</nav>
  {sections}
  <footer>전설이 키우기 · 전설이 도감 · 총 {total_pets}종</footer>
</div></body></html>'''

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dogam.html")
import os
os.makedirs(os.path.dirname(out), exist_ok=True)
# V2 확장(검색/정렬/배틀 시뮬레이터) 자동 적용
from dogam_v2 import patch_html
HTML = patch_html(HTML)

open(out, "w", encoding="utf-8").write(HTML)
print("생성 완료:", out, f"({len(HTML):,} bytes)")
