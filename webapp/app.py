"""전설이 키우기 웹앱 (FastAPI).

디스코드 봇과 같은 DB(legends.db)·게임 로직(utils/game.py)을 공유합니다.
레포 루트에서 실행하세요:
    uvicorn webapp.app:app --host 0.0.0.0 --port 8080

config.ini 에 [web] 섹션이 필요합니다 (webapp/README-web.md 참고):
    [web]
    client_id = 디스코드 앱 클라이언트 ID
    client_secret = 디스코드 앱 클라이언트 시크릿
    redirect_uri = http://서버IP:8080/callback
    secret_key = 아무 긴 무작위 문자열
"""

import os
import sys
import time
import configparser
import urllib.parse

# 레포 루트를 import 경로에 추가 (utils/, cogs/ 사용)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # legends.db, config.ini 상대경로 일치

import aiohttp
import aiosqlite
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from itsdangerous import URLSafeTimedSerializer, BadSignature

import utils.database as udb
from utils.data import (PET_IMAGES, PET_IMAGES_EVOLVED, RARITY_IMAGES, EQUIPMENTS,
                        MAX_EQUIP_PER_PET, PET_POOLS, RARITY_ORDER,
                        format_equip_effect, get_pet_total_stats,
                        get_equipment_bonus)
from utils.database import get_or_migrate_data, get_user_items
from utils.stats import get_points
from utils import game
from cogs.petsystem.combat import calc_pet_power

# ── 설정 로드 ──
_cfg = configparser.ConfigParser()
_cfg.read(os.path.join(ROOT, "config.ini"), encoding="utf-8")
WEB = dict(_cfg["web"]) if _cfg.has_section("web") else {}
CLIENT_ID = WEB.get("client_id", "")
CLIENT_SECRET = WEB.get("client_secret", "")
REDIRECT_URI = WEB.get("redirect_uri", "")
SECRET_KEY = WEB.get("secret_key", "")
OAUTH_READY = all([CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, SECRET_KEY])

# 권한 체계: 소유주(owner) > 관리자(admin). 둘 다 관리자 패널을 쓸 수 있고,
# 소유주는 별도 타이틀로 표시됩니다.
OWNER_IDS = {1505506970361139210, 1517544497817583739}
# 일반 관리자 (기본 + config.ini [web] admin_ids = 123, 456 로 추가 가능)
DEFAULT_ADMIN_IDS = {1514057131987308685}
ADMIN_IDS = set(DEFAULT_ADMIN_IDS)
for _a in WEB.get("admin_ids", "").replace(" ", "").split(","):
    if _a.isdigit():
        ADMIN_IDS.add(int(_a))
# 소유주도 관리자 권한을 포함
ADMIN_IDS |= OWNER_IDS


def is_owner(user) -> bool:
    return bool(user) and int(user.get("id", 0)) in OWNER_IDS


def is_admin(user) -> bool:
    return bool(user) and int(user.get("id", 0)) in ADMIN_IDS

signer = URLSafeTimedSerializer(SECRET_KEY or "placeholder")
SESSION_MAX_AGE = 7 * 24 * 3600

app = FastAPI(title="전설이 키우기")
_jinja = Environment(
    loader=FileSystemLoader(os.path.join(ROOT, "webapp", "templates")),
    autoescape=select_autoescape(["html"]),
)


def render(name: str, **ctx) -> HTMLResponse:
    resp = HTMLResponse(_jinja.get_template(name).render(**ctx))
    # 대시보드/랭킹은 매번 최신 DB 상태를 보여줘야 하므로 브라우저 캐시를 끕니다.
    # (뒤로가기·새로고침 시 예전 스탯이 남아 "동기화가 안 된 것처럼" 보이는 문제 방지)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.on_event("startup")
async def _startup():
    # 봇과 동일한 테이블 보장 (CREATE IF NOT EXISTS 라 기존 데이터에 안전)
    await udb.init_db()


# ── 세션 ──
def current_user(request: Request):
    token = request.cookies.get("session")
    if not token or not OAUTH_READY:
        return None
    try:
        return signer.loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None


async def save_web_user(user: dict):
    """랭킹에 이름을 표시하기 위해 로그인 유저 정보를 저장합니다."""
    async with aiosqlite.connect(udb.DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS web_users
                     (user_id INTEGER PRIMARY KEY, username TEXT, avatar TEXT, last_login REAL)''')
        await db.execute('''INSERT OR REPLACE INTO web_users VALUES (?, ?, ?, ?)''',
                         (int(user["id"]), user["username"], user.get("avatar") or "", time.time()))
        await db.commit()


async def get_usernames(user_ids: list) -> dict:
    if not user_ids:
        return {}
    async with aiosqlite.connect(udb.DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS web_users
                     (user_id INTEGER PRIMARY KEY, username TEXT, avatar TEXT, last_login REAL)''')
        q = f"SELECT user_id, username FROM web_users WHERE user_id IN ({','.join('?'*len(user_ids))})"
        async with db.execute(q, user_ids) as cur:
            return {r[0]: r[1] for r in await cur.fetchall()}


def display_name(uid: int, names: dict) -> str:
    return names.get(uid) or f"모험가#{str(uid)[-4:]}"


# ── OAuth ──
@app.get("/login")
async def login():
    if not OAUTH_READY:
        return RedirectResponse("/?setup=1")
    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
        "response_type": "code", "scope": "identify",
    })
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{params}")


@app.get("/callback")
async def callback(code: str = ""):
    if not code or not OAUTH_READY:
        return RedirectResponse("/")
    async with aiohttp.ClientSession() as s:
        async with s.post("https://discord.com/api/oauth2/token", data={
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"}) as r:
            tok = await r.json()
        access = tok.get("access_token")
        if not access:
            return RedirectResponse("/?error=oauth")
        async with s.get("https://discord.com/api/users/@me",
                         headers={"Authorization": f"Bearer {access}"}) as r:
            me = await r.json()

    user = {"id": me["id"], "username": me.get("global_name") or me.get("username", "?"),
            "avatar": me.get("avatar")}
    await save_web_user(user)
    resp = RedirectResponse("/me")
    resp.set_cookie("session", signer.dumps(user), max_age=SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/")
    resp.delete_cookie("session")
    return resp


# ── 데이터 조립 ──
def pet_view(pet: dict, idx: int) -> dict:
    level = pet.get("level", 0)
    ptype = pet.get("type", "?")
    if level >= 3 and ptype in PET_IMAGES_EVOLVED:
        img = PET_IMAGES_EVOLVED[ptype]
    else:
        img = PET_IMAGES.get(ptype, "")
    stats = get_pet_total_stats(pet) if level > 0 else None
    equipped = pet.get("equipment", []) or []
    return {"idx": idx, "name": pet.get("name", "이름없음"), "type": ptype,
            "rarity": pet.get("rarity", "서사"), "level": level, "img": img,
            "fullness": pet.get("fullness", 0), "cleanliness": pet.get("cleanliness", 0),
            "intimacy": pet.get("intimacy", 0), "fatigue": pet.get("fatigue", 0),
            "exp": pet.get("exp", 0), "stats": stats,
            "power": calc_pet_power(pet) if level > 0 else 0,
            "max_equip": MAX_EQUIP_PER_PET,
            "equipment": [{"name": n, "effect": format_equip_effect(n)} for n in equipped],
            "equip_bonus": get_equipment_bonus(pet) if level > 0 else None}


def _usable(name: str) -> bool:
    """보관함에서 '사용' 버튼을 붙일 아이템인지 (장비·자동사용 제외)."""
    if name in EQUIPMENTS or name == "100회 산책 할인권":
        return False
    if game.is_egg_item(name):
        return True
    return (name in game.BUFF_ITEMS_24H or name in game.BUFF_EXP_ITEMS
            or name == "신비한 알약" or name == "전설이 이름 변경권")


async def dashboard_state(uid: int) -> dict:
    wrapper = await get_or_migrate_data(uid)
    pets = [pet_view(p, i) for i, p in enumerate(wrapper.get("pets", []))]
    box = [{"idx": i, "name": p.get("name", "이름없음"), "type": p.get("type", "?"),
            "rarity": p.get("rarity", "서사"), "level": p.get("level", 0)}
           for i, p in enumerate(wrapper.get("box", []) or [])]
    items = await get_user_items(uid)
    points = await get_points(uid)
    quest = await game.get_quest_status(uid)
    expedition = await game.get_expedition_status(uid)
    # 인벤토리에서 장착 가능한 장비만 추림 (장비 관리 UI 용)
    owned_equips = [{"name": n, "amount": a, "rarity": EQUIPMENTS[n]["rarity"],
                     "effect": format_equip_effect(n)}
                    for n, a in items if n in EQUIPMENTS]
    usable_items = [{"name": n, "amount": a, "is_egg": game.is_egg_item(n)}
                    for n, a in items if _usable(n)]
    egg_counts = {n: a for n, a in items}
    egg_count = egg_counts.get("서사급 알", 0)
    synth = await game.synth_candidates(uid)
    attendance = await game.get_attendance_status(uid)
    achievement = await game.achievement_status(uid)
    return {"pets": pets, "box": box, "items": [{"name": n, "amount": a} for n, a in items],
            "points": points, "quest": quest, "expedition": expedition,
            "durations": game.EXPEDITION_DURATIONS,
            "owned_equips": owned_equips, "usable_items": usable_items,
            "egg_count": egg_count, "egg_counts": egg_counts,
            "egg_exchange": game.egg_exchange_info(),
            "shop": game.shop_catalog(), "synth": synth, "attendance": attendance,
            "achievement": achievement,
            "max_pets": game.MAX_PETS, "hatch_cost": game.HATCH_COST,
            "pet_count": len(pets)}


async def admin_list_users() -> list:
    """DB에 흔적이 있는 모든 유저를 모아 요약(포인트/펫수/알 등)과 함께 반환."""
    import json
    ids = set()
    pets_by_uid = {}
    egg_by_uid = {}
    async with aiosqlite.connect(udb.DB_PATH) as db:
        async with db.execute("SELECT user_id, pet_data FROM user_multi_pets") as cur:
            for uid, pj in await cur.fetchall():
                ids.add(uid)
                try:
                    w = json.loads(pj)
                    pets_by_uid[uid] = (len(w.get("pets", [])), len(w.get("box", [])))
                except Exception:
                    pets_by_uid[uid] = (0, 0)
        async with db.execute("SELECT user_id, amount FROM user_items WHERE item_name = '서사급 알'") as cur:
            for uid, amt in await cur.fetchall():
                ids.add(uid)
                egg_by_uid[uid] = amt
        async with db.execute("SELECT DISTINCT user_id FROM user_items") as cur:
            for (uid,) in await cur.fetchall():
                ids.add(uid)

    names = await get_usernames(list(ids))
    users = []
    for uid in ids:
        parties, box = pets_by_uid.get(uid, (0, 0))
        users.append({
            "id": str(uid), "name": display_name(uid, names),
            "points": await get_points(uid),
            "pets": parties, "box": box, "eggs": egg_by_uid.get(uid, 0),
        })
    users.sort(key=lambda u: (-u["eggs"], -u["points"]))
    return users


async def rankings() -> dict:
    async with aiosqlite.connect(udb.DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, amount FROM user_items WHERE item_name = '서사급 알' ORDER BY amount DESC LIMIT 10"
        ) as cur:
            eggs = await cur.fetchall()
        async with db.execute("SELECT user_id, pet_data FROM user_multi_pets") as cur:
            rows = await cur.fetchall()

    import json
    power = []
    for uid, pet_json in rows:
        try:
            pets = json.loads(pet_json).get("pets", [])
        except Exception:
            continue
        best = max((calc_pet_power(p) for p in pets), default=0)
        if best > 0:
            power.append((uid, best))
    power.sort(key=lambda x: -x[1])
    power = power[:10]

    ids = list({u for u, _ in eggs} | {u for u, _ in power})
    names = await get_usernames(ids)
    return {
        "eggs": [{"rank": i + 1, "name": display_name(u, names), "value": v} for i, (u, v) in enumerate(eggs)],
        "power": [{"rank": i + 1, "name": display_name(u, names), "value": v} for i, (u, v) in enumerate(power)],
    }


# ── 페이지 ──
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return render("index.html", user=current_user(request),
                  ranks=await rankings(), oauth_ready=OAUTH_READY,
                  rarity_images=RARITY_IMAGES)


@app.get("/me", response_class=HTMLResponse)
async def me(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login")
    state = await dashboard_state(int(user["id"]))
    return render("me.html", user=user, s=state, now=time.time(), oauth_ready=OAUTH_READY,
                  is_admin=is_admin(user), is_owner=is_owner(user),
                  pet_pools=PET_POOLS, rarity_order=RARITY_ORDER)


# ── 액션 API (전부 세션 유저 본인에게만 적용) ──
def _need_login(request: Request):
    user = current_user(request)
    if not user:
        return None, JSONResponse({"ok": False, "error": "로그인이 필요합니다."}, status_code=401)
    return int(user["id"]), None


@app.post("/api/feed")
async def api_feed(request: Request):
    uid, err = _need_login(request)
    if err: return err
    body = await request.json()
    return JSONResponse(await game.feed_pet(uid, int(body.get("pet_idx", 0))))


@app.post("/api/shower")
async def api_shower(request: Request):
    uid, err = _need_login(request)
    if err: return err
    body = await request.json()
    return JSONResponse(await game.shower_pet(uid, int(body.get("pet_idx", 0))))


@app.post("/api/walk")
async def api_walk(request: Request):
    uid, err = _need_login(request)
    if err: return err
    body = await request.json()
    n = int(body.get("n", 1))
    if n not in (1, 10, 100):
        return JSONResponse({"ok": False, "error": "산책 횟수는 1/10/100 중 하나입니다."})
    res = await game.do_walk(uid, int(body.get("pet_idx", 0)), n)
    if res.get("ok"):
        res["found_items"] = [list(t) for t in res.get("found_items", [])]
        res.pop("data", None)
    return JSONResponse(res)


@app.post("/api/expedition/start")
async def api_exp_start(request: Request):
    uid, err = _need_login(request)
    if err: return err
    body = await request.json()
    return JSONResponse(await game.start_expedition_for(
        uid, int(body.get("pet_idx", 0)), int(body.get("hours", 1)), calc_pet_power))


@app.post("/api/expedition/claim")
async def api_exp_claim(request: Request):
    uid, err = _need_login(request)
    if err: return err
    return JSONResponse(await game.claim_expedition(uid))


@app.post("/api/quest/claim")
async def api_quest_claim(request: Request):
    uid, err = _need_login(request)
    if err: return err
    return JSONResponse(await game.claim_daily_quests(uid))


@app.post("/api/attendance")
async def api_attendance(request: Request):
    uid, err = _need_login(request)
    if err: return err
    return JSONResponse(await game.check_in(uid))


@app.post("/api/exchange")
async def api_exchange(request: Request):
    uid, err = _need_login(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.exchange_egg(uid, b.get("rarity", ""), int(b.get("count", 1))))


@app.post("/api/decompose")
async def api_decompose(request: Request):
    uid, err = _need_login(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.decompose_egg(uid, b.get("rarity", ""), int(b.get("count", 1))))


@app.post("/api/use-item")
async def api_use_item(request: Request):
    uid, err = _need_login(request)
    if err: return err
    b = await request.json()
    name = b.get("item", "")
    # 알 아이템이면 부화 흐름으로 처리 (이름/종류 필요)
    if game.is_egg_item(name):
        return JSONResponse(await game.hatch_egg_item(
            uid, name, b.get("type", ""), b.get("name", "")))
    return JSONResponse(await game.use_item(
        uid, name, int(b.get("amount", 1)), int(b.get("pet_idx", 0)), b.get("name", "")))


@app.post("/api/box/store")
async def api_box_store(request: Request):
    uid, err = _need_login(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.box_store(uid, int(b.get("pet_idx", 0))))


@app.post("/api/box/retrieve")
async def api_box_retrieve(request: Request):
    uid, err = _need_login(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.box_retrieve(uid, int(b.get("box_idx", 0))))


@app.post("/api/reorder")
async def api_reorder(request: Request):
    uid, err = _need_login(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.reorder_pets(uid, int(b.get("from", 0)), int(b.get("to", 0))))


@app.post("/api/battle-sim")
async def api_battle_sim(request: Request):
    """무보상 배틀 시뮬레이터: 내 펫 1마리 vs 지정 상대 펫 1마리 승률·결과."""
    uid, err = _need_login(request)
    if err: return err
    b = await request.json()
    my = await get_or_migrate_data(uid)
    my_pets = my.get("pets", [])
    mi = int(b.get("my_idx", 0))
    if mi >= len(my_pets) or my_pets[mi].get("level", 0) == 0:
        return JSONResponse({"ok": False, "error": "출전할 내 전설이를 선택하세요. (알 제외)"})
    try:
        enemy_uid = int(b.get("enemy_id", 0))
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "상대 ID가 올바르지 않습니다."})
    enemy = await get_or_migrate_data(enemy_uid)
    enemy_pets = enemy.get("pets", [])
    ei = int(b.get("enemy_idx", 0))
    if ei >= len(enemy_pets) or enemy_pets[ei].get("level", 0) == 0:
        return JSONResponse({"ok": False, "error": "상대 전설이를 찾을 수 없습니다."})
    from cogs.petsystem.combat import calc_win_rate
    wr, ms, es = calc_win_rate([my_pets[mi]], [enemy_pets[ei]])
    import random as _r
    win = _r.random() < wr
    return JSONResponse({"ok": True, "win_rate": round(wr * 100, 1),
                         "my_score": round(ms, 1), "enemy_score": round(es, 1),
                         "result": "승리" if win else "패배",
                         "my_name": my_pets[mi].get("name"),
                         "enemy_name": enemy_pets[ei].get("name")})


# ── 관리자 패널 API (ADMIN_IDS 만 접근) ──
def _need_admin(request: Request):
    user = current_user(request)
    if not user:
        return None, JSONResponse({"ok": False, "error": "로그인이 필요합니다."}, status_code=401)
    if not is_admin(user):
        return None, JSONResponse({"ok": False, "error": "관리자 권한이 없습니다."}, status_code=403)
    return user, None


def _target(b) -> int:
    try:
        return int(b.get("target_id", 0))
    except (TypeError, ValueError):
        return 0


@app.post("/api/admin/users")
async def api_admin_users(request: Request):
    _, err = _need_admin(request)
    if err: return err
    return JSONResponse({"ok": True, "users": await admin_list_users()})


@app.post("/api/admin/lookup")
async def api_admin_lookup(request: Request):
    _, err = _need_admin(request)
    if err: return err
    b = await request.json()
    tid = _target(b)
    if not tid:
        return JSONResponse({"ok": False, "error": "유저 ID를 입력하세요."})
    pets = await game.admin_view_pets(tid)
    items = await game.admin_view_items(tid)
    pts = await get_points(tid)
    return JSONResponse({"ok": True, "points": pts,
                         "pets": pets["pets"], "box": pets["box"], "items": items["items"]})


@app.post("/api/admin/give-egg")
async def api_admin_give_egg(request: Request):
    _, err = _need_admin(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.admin_give_egg(_target(b), b.get("name", ""), b.get("rarity", ""), b.get("type", "")))


@app.post("/api/admin/take-pet")
async def api_admin_take_pet(request: Request):
    _, err = _need_admin(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.admin_take_pet(_target(b), int(b.get("pet_idx", 0))))


@app.post("/api/admin/give-item")
async def api_admin_give_item(request: Request):
    _, err = _need_admin(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.admin_give_item(_target(b), b.get("item", ""), int(b.get("count", 0))))


@app.post("/api/admin/reset-items")
async def api_admin_reset_items(request: Request):
    _, err = _need_admin(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.admin_reset_items(_target(b)))


@app.post("/api/admin/force-hatch")
async def api_admin_force_hatch(request: Request):
    _, err = _need_admin(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.admin_force_hatch(_target(b), int(b.get("pet_idx", 0))))


@app.post("/api/admin/set-star")
async def api_admin_set_star(request: Request):
    _, err = _need_admin(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.admin_set_star(_target(b), int(b.get("pet_idx", 0)), int(b.get("delta", 0))))


@app.post("/api/admin/rename")
async def api_admin_rename(request: Request):
    _, err = _need_admin(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.admin_rename(_target(b), int(b.get("pet_idx", 0)), b.get("name", "")))


@app.post("/api/admin/give-exp")
async def api_admin_give_exp(request: Request):
    _, err = _need_admin(request)
    if err: return err
    b = await request.json()
    return JSONResponse(await game.admin_give_exp(_target(b), int(b.get("pet_idx", 0)), int(b.get("amount", 0))))


@app.post("/api/equip")
async def api_equip(request: Request):
    uid, err = _need_login(request)
    if err: return err
    body = await request.json()
    return JSONResponse(await game.equip_pet(uid, int(body.get("pet_idx", 0)), body.get("equip", "")))


@app.post("/api/unequip")
async def api_unequip(request: Request):
    uid, err = _need_login(request)
    if err: return err
    body = await request.json()
    return JSONResponse(await game.unequip_pet(uid, int(body.get("pet_idx", 0)), body.get("equip", "")))


@app.post("/api/buy")
async def api_buy(request: Request):
    uid, err = _need_login(request)
    if err: return err
    body = await request.json()
    return JSONResponse(await game.buy_shop_item(uid, body.get("item", "")))


@app.post("/api/hatch/roll")
async def api_hatch_roll(request: Request):
    uid, err = _need_login(request)
    if err: return err
    body = await request.json()
    return JSONResponse(await game.hatch_roll(uid, body.get("name", "")))


@app.post("/api/hatch/pick")
async def api_hatch_pick(request: Request):
    uid, err = _need_login(request)
    if err: return err
    body = await request.json()
    return JSONResponse(await game.hatch_pick(uid, body.get("type", "")))


@app.post("/api/synthesize")
async def api_synthesize(request: Request):
    uid, err = _need_login(request)
    if err: return err
    body = await request.json()
    return JSONResponse(await game.synthesize(uid, int(body.get("idx1", -1)), int(body.get("idx2", -2))))


@app.get("/api/state")
async def api_state(request: Request):
    """대시보드 실시간 자동 갱신용 JSON 상태."""
    uid, err = _need_login(request)
    if err: return err
    resp = JSONResponse(await dashboard_state(uid))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/dogam", response_class=HTMLResponse)
async def dogam():
    """전설이 도감 (정적 페이지 통합)."""
    path = os.path.join(ROOT, "web", "dogam.html")
    if not os.path.exists(path):
        return HTMLResponse("<h1>도감 파일이 아직 생성되지 않았습니다.</h1>"
                            "<p>web/generate_dogam.py 를 실행해 dogam.html 을 만들어주세요.</p>",
                            status_code=404)
    with open(path, encoding="utf-8") as f:
        html = f.read()
    resp = HTMLResponse(html)
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(WEB.get("port", 8080)))
