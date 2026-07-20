"""도감 V2 확장 블록: 이름 검색 + 스탯순 정렬 + 배틀 시뮬레이터.

- generate_dogam.py 가 새 도감을 만들 때 이 블록을 포함합니다.
- patch_html() 로 기존(이미지 임베드된) 도감 HTML에도 그대로 주입할 수 있습니다.
- 시뮬레이터는 봇 combat.py 와 동일한 공식을 JS로 구현:
    스탯 = 기본 x 2^(성급-1) + 장비 보너스
    유효전투력 = AD x 100/(100+상대DF) + AP x 100/(100+상대MR)
    승률 = 내 유효전투력 / (양쪽 합)
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from utils.data import PET_POOLS, PET_STATS, EQUIPMENTS, RARITY_ORDER  # noqa: E402


def build_data_json() -> str:
    pets = []
    for rarity in RARITY_ORDER:
        for name in PET_POOLS[rarity]:
            s = PET_STATS.get(name, {"AD": 5, "DF": 5, "AP": 5, "MR": 5})
            pets.append({"name": name, "rarity": rarity, **s})
    equips = [{"name": n, "rarity": i["rarity"], "stats": i["stats"]} for n, i in EQUIPMENTS.items()]
    return json.dumps({"pets": pets, "equips": equips}, ensure_ascii=False)


EXTRA_CSS = """
/* ── V2: 검색/정렬 툴바 ── */
.toolbar{display:flex;gap:10px;justify-content:center;align-items:center;flex-wrap:wrap;margin:2px 0 8px;}
.searchbox{width:min(420px,86vw);padding:11px 18px;border-radius:100px;border:1px solid var(--border2);
background:var(--surface);color:var(--text);font-size:15px;font-family:inherit;outline:none;}
.searchbox::placeholder{color:var(--faint);}
.sortbtn{padding:11px 18px;border-radius:100px;border:1px solid var(--border2);background:var(--surface);
color:var(--dim);font-size:14px;font-weight:800;cursor:pointer;font-family:inherit;}
.sortbtn.on{color:var(--gold);border-color:color-mix(in srgb,var(--gold) 45%,transparent);}
.nohit{display:none;text-align:center;color:var(--faint);padding:30px 0;}
/* ── V2: 배틀 시뮬레이터 ── */
.sim{margin-top:60px;scroll-margin-top:80px;}
.sim h2{font-size:24px;font-weight:900;margin:0 0 6px;}
.sim .simdesc{color:var(--dim);font-size:14px;margin:0 0 18px;}
.simgrid{display:grid;grid-template-columns:1fr auto 1fr;gap:16px;align-items:stretch;}
.fighter{background:var(--surface);border:1px solid var(--border2);border-radius:16px;padding:18px;display:flex;flex-direction:column;gap:10px;}
.fighter h3{margin:0 0 2px;font-size:15px;font-weight:800;letter-spacing:.06em;}
.fighter select{width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--border);
background:var(--surface2);color:var(--text);font-size:14px;font-family:inherit;}
.fighter .fstats{font-size:13px;color:var(--dim);line-height:1.7;min-height:44px;}
.fighter .fstats b{color:var(--text);font-variant-numeric:tabular-nums;}
.vsmid{display:grid;place-items:center;font-weight:900;color:var(--gold);font-size:22px;padding:0 4px;}
.simres{margin-top:16px;background:var(--surface);border:1px solid var(--border2);border-radius:16px;padding:18px 20px;}
.simbar{display:flex;height:26px;border-radius:100px;overflow:hidden;border:1px solid var(--border2);margin-top:10px;}
.simbar .ba{background:linear-gradient(90deg,#4f9dff,#38d6c2);}
.simbar .bb{background:linear-gradient(90deg,#ff9d4e,#e5484d);}
.simlabels{display:flex;justify-content:space-between;font-weight:900;font-size:18px;margin-top:8px;}
.simlabels .la{color:#4fd6c8;} .simlabels .lb{color:#ff8a6b;}
.simnote{color:var(--faint);font-size:12px;margin-top:10px;}
@media (max-width:640px){.simgrid{grid-template-columns:1fr;}.vsmid{padding:2px 0;}}
"""

TOOLBAR_HTML = """
<div class="toolbar">
  <input class="searchbox" id="dsearch" type="search" placeholder="🔍 전설이 이름 검색 (예: 아리)">
  <button class="sortbtn" id="dsort">📊 스탯순 정렬</button>
  <a class="sortbtn" href="#sim">⚔️ 배틀 시뮬레이터</a>
</div>
<div class="nohit" id="dnohit">검색 결과가 없습니다 🥲</div>
"""

SIM_HTML = """
<section id="sim" class="sim">
  <h2>⚔️ 배틀 시뮬레이터</h2>
  <p class="simdesc">봇의 실제 배틀 공식 그대로! 전설이·성급·장비를 골라 승률을 미리 계산해보세요.</p>
  <div class="simgrid">
    <div class="fighter" id="fA"><h3 style="color:#4fd6c8">🔵 내 전설이</h3></div>
    <div class="vsmid">VS</div>
    <div class="fighter" id="fB"><h3 style="color:#ff8a6b">🔴 상대 전설이</h3></div>
  </div>
  <div class="simres" id="simres">👆 양쪽 전설이를 선택하면 승률이 표시됩니다.</div>
  <p class="simnote">※ 메자이/오만의 배틀 승리 누적 스택은 계산에 포함되지 않습니다 (기본 수치만 반영).</p>
</section>
"""


def build_js(data_json: str) -> str:
    return "<script>\nconst DOGAM=" + data_json + r""";
(function(){
// ── 검색 & 정렬 ──
const q=document.getElementById('dsearch'), nohit=document.getElementById('dnohit');
const sortBtn=document.getElementById('dsort'); let sorted=false;
function applySearch(){
  const t=(q.value||'').trim().toLowerCase(); let any=false;
  document.querySelectorAll('section.grade').forEach(sec=>{
    let vis=0;
    sec.querySelectorAll('.pet').forEach(card=>{
      const name=card.querySelector('.pname').textContent.toLowerCase();
      const show=!t||name.includes(t);
      card.style.display=show?'':'none'; if(show)vis++;
    });
    sec.style.display=vis?'':'none'; if(vis)any=true;
  });
  nohit.style.display=any?'none':'block';
}
if(q)q.addEventListener('input',applySearch);
function totalOf(card){const b=card.querySelector('.total b');return b?parseInt(b.textContent)||0:0;}
if(sortBtn)sortBtn.addEventListener('click',()=>{
  sorted=!sorted; sortBtn.classList.toggle('on',sorted);
  document.querySelectorAll('.petgrid').forEach(g=>{
    const cards=[...g.children];
    cards.sort((a,b)=>sorted? totalOf(b)-totalOf(a) : 0);
    if(sorted){cards.forEach(c=>g.appendChild(c));}
    else{ /* 원래 순서 복원: data-idx 사용 */
      cards.sort((a,b)=>(+a.dataset.idx||0)-(+b.dataset.idx||0)).forEach(c=>g.appendChild(c));
    }
  });
});
document.querySelectorAll('.petgrid').forEach(g=>[...g.children].forEach((c,i)=>c.dataset.idx=i));

// ── 배틀 시뮬레이터 ──
const EQ_NONE='(없음)';
function makeSelect(opts,ph){const s=document.createElement('select');
  s.innerHTML=opts.map(o=>`<option value="${o.v}">${o.t}</option>`).join('');
  if(ph){const p=document.createElement('option');p.value='';p.textContent=ph;p.selected=true;p.disabled=true;s.prepend(p);}
  return s;}
const petOpts=DOGAM.pets.map((p,i)=>({v:i,t:`[${p.rarity}] ${p.name}`}));
const eqOpts=[{v:'',t:EQ_NONE}].concat(DOGAM.equips.map((e,i)=>({v:i,t:`[${e.rarity}] ${e.name}`})));
const lvOpts=[{v:1,t:'1성'},{v:2,t:'2성'},{v:3,t:'3성'}];
function buildFighter(box){
  const pet=makeSelect(petOpts,'전설이 선택'); const lv=makeSelect(lvOpts); lv.value='3';
  const eqs=[0,1,2].map(()=>makeSelect(eqOpts));
  const st=document.createElement('div'); st.className='fstats'; st.textContent='전설이를 선택하세요';
  box.append(pet,lv,...eqs,st);
  return {pet,lv,eqs,st};
}
function statsOf(f){
  if(f.pet.value==='')return null;
  const p=DOGAM.pets[+f.pet.value]; const m=Math.pow(2,(+f.lv.value)-1);
  const s={AD:Math.floor(p.AD*m),DF:Math.floor(p.DF*m),AP:Math.floor(p.AP*m),MR:Math.floor(p.MR*m)};
  f.eqs.forEach(sel=>{ if(sel.value!==''){const e=DOGAM.equips[+sel.value];
    for(const k in e.stats){s[k]=(s[k]||0)+e.stats[k];}}});
  return {name:p.name,s};
}
function eff(a,b){return a.AD*100/(100+Math.max(0,b.DF))+a.AP*100/(100+Math.max(0,b.MR));}
const fA=buildFighter(document.getElementById('fA'));
const fB=buildFighter(document.getElementById('fB'));
const res=document.getElementById('simres');
function fmt(s){return `AD <b>${s.AD}</b> · DF <b>${s.DF}</b> · AP <b>${s.AP}</b> · MR <b>${s.MR}</b> (합 <b>${s.AD+s.DF+s.AP+s.MR}</b>)`;}
function update(){
  const A=statsOf(fA),B=statsOf(fB);
  fA.st.innerHTML=A?fmt(A.s):'전설이를 선택하세요';
  fB.st.innerHTML=B?fmt(B.s):'전설이를 선택하세요';
  if(!A||!B){res.textContent='👆 양쪽 전설이를 선택하면 승률이 표시됩니다.';return;}
  const ea=eff(A.s,B.s), eb=eff(B.s,A.s), tot=ea+eb||1;
  const wa=ea/tot*100, wb=eb/tot*100;
  res.innerHTML=`<div style="font-weight:800">🔵 ${A.name} <span style="color:var(--faint)">vs</span> 🔴 ${B.name}</div>
  <div class="simbar"><div class="ba" style="width:${wa}%"></div><div class="bb" style="width:${wb}%"></div></div>
  <div class="simlabels"><span class="la">${wa.toFixed(1)}%</span><span class="lb">${wb.toFixed(1)}%</span></div>
  <div class="simnote">유효 전투력: ${ea.toFixed(0)} vs ${eb.toFixed(0)} (방어/마저가 상대 공격을 감쇄)</div>`;
}
[fA,fB].forEach(f=>[f.pet,f.lv,...f.eqs].forEach(el=>el.addEventListener('change',update)));
})();
</script>"""


def patch_html(html: str) -> str:
    """기존 도감 HTML(이미지 임베드본 포함)에 V2 블록을 주입합니다."""
    data_json = build_data_json()
    html = html.replace("</style>", EXTRA_CSS + "\n</style>", 1)
    html = html.replace("</nav>", "</nav>\n" + TOOLBAR_HTML, 1)
    html = html.replace("<footer>", SIM_HTML + "\n<footer>", 1)
    js = build_js(data_json)
    if "</body>" in html:
        html = html.replace("</body>", js + "\n</body>", 1)
    else:
        html += js
    return html


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, "dogam_small.html")
    if not os.path.exists(src):
        src = os.path.join(here, "dogam.html")
    html = open(src, encoding="utf-8").read()
    if 'id="sim"' in html:
        print("이미 V2가 적용된 파일입니다:", src)
    else:
        out = patch_html(html)
        open(src, "w", encoding="utf-8").write(out)
        print(f"V2 적용 완료: {src} ({len(out):,} bytes)")
