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
from utils.data import PET_IMAGES, PET_IMAGES_EVOLVED, RARITY_IMAGES, get_pet_total_stats
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
    return {"idx": idx, "name": pet.get("name", "이름없음"), "type": ptype,
            "rarity": pet.get("rarity", "서사"), "level": level, "img": img,
            "fullness": pet.get("fullness", 0), "cleanliness": pet.get("cleanliness", 0),
            "intimacy": pet.get("intimacy", 0), "fatigue": pet.get("fatigue", 0),
            "exp": pet.get("exp", 0), "stats": stats,
            "power": calc_pet_power(pet) if level > 0 else 0,
            "equipment": pet.get("equipment", []) or []}


async def dashboard_state(uid: int) -> dict:
    wrapper = await get_or_migrate_data(uid)
    pets = [pet_view(p, i) for i, p in enumerate(wrapper.get("pets", []))]
    items = await get_user_items(uid)
    points = await get_points(uid)
    quest = await game.get_quest_status(uid)
    expedition = await game.get_expedition_status(uid)
    return {"pets": pets, "items": [{"name": n, "amount": a} for n, a in items],
            "points": points, "quest": quest, "expedition": expedition,
            "durations": game.EXPEDITION_DURATIONS}


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
    return render("me.html", user=user, s=state, now=time.time(), oauth_ready=OAUTH_READY)


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(WEB.get("port", 8080)))
