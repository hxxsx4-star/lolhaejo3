# 💡 획득 가능한 전설이 목록
PET_POOLS = {
    "서사": ["🐧 펭구", "🗡️ 깃털기사", "🦄 뿔보", "👻 말랑이", "🐢 꾸릉이"],
    "전설": ["🥷 미니 아칼리", "⚔️ 미니 요네", "✨ 미니 럭스", "🎸 미니 유나라", "🦊 미니 아리", "🍙 해방된 포로 뭉치", "🍄‍🟫 미니 티모", "👮‍♀️ 미니 케이틀린", "🗡️ 미니 카타리나", "🥱 미니 조이", "🪖 미니 이렐리아", "🐱 미니 유미", "⚙️ 미니 오리아나"],
    "신화": ["🍌 미니 바나나 소라카", "🌹 미니 수정 장미 그웬", "🏆 미니 T1 요네", "🗡️ 미니 불멸의 영웅 이렐리아", "🐮 내가 젖소 포로", "🌕 미니 핏빛 달 아트록스", "🎵 미니 칠현금 소나", "⚔️ 미니 전투사관학교 카타리나", "😈 미니 작은 악마 티모", "🤖 미니 우주 그루브 블리츠크랭크"],
    "프레스티지": ["👼 프레스티지 미니 빛의 인도자 요네", "🌸 프레스티지 미니 영혼의 꽃 아리", "☕ 프레스티지 미니 귀염둥이 카페 그웬", "🎧 미니 헤드라이너 K/DA POP/STAR 카이사", "🔫 미니 프레스티지 핏빛 달 미스포츈", "🐉 미니 프레스티지 용의 권 리신", "🤺 미니 프레스티지 용술사 야스오", "🧙 미니 프레스티지 아케인 열혈 팬 애니", "🦸 미니 프레스티지 불멸의 영웅 리븐", "💛 미니 프레스티지 도자기 수호자 이즈리얼"],
    "고귀": ["🔫 아케인 분열 징크스", "🌊 찬란한 바다뱀 세트", "🧑🏻‍🦲 산-우잘 모데카이저", "💮 영혼의 꽃 모르가나", "⚰️ 망령의 지배자 비에고"],
    "초월": ["♥️ 불멸의 전설 아리", "💜 불멸의 전설 카이사"]
}

# 💡 등급 순서(하위 -> 상위). 가챠 가중치·알 환전/분해가 이 순서를 공유하는 단일 소스입니다.
RARITY_ORDER = list(PET_POOLS.keys())

# 💡 상위 알 1개 = 직전 하위 알 N개 (알환전/알분해 공용 비율)
#    예) 서사 50개 = 전설 1개, 프레스티지 10개 = 고귀 1개, 고귀 10개 = 초월 1개
EGG_EXCHANGE_RATE = {
    "전설": 50,
    "신화": 20,
    "프레스티지": 10,
    "고귀": 10,
    "초월": 10,
}

def egg_item_name(rarity: str) -> str:
    """등급명 -> 알 아이템 이름 (예: '고귀' -> '고귀급 알')"""
    return f"{rarity}급 알"

def prev_rarity(rarity: str):
    """한 단계 낮은 등급을 반환 (가장 낮은 등급이면 None)"""
    idx = RARITY_ORDER.index(rarity)
    return RARITY_ORDER[idx - 1] if idx > 0 else None

# 💡 전설이 기본 스탯
PET_STATS = {
    "🐧 펭구": {"AD": 15, "DF": 15, "AP": 15, "MR": 15},
    "🗡️ 깃털기사": {"AD": 25, "DF": 10, "AP": 5, "MR": 10},
    "🦄 뿔보": {"AD": 10, "DF": 25, "AP": 5, "MR": 20},
    "👻 말랑이": {"AD": 5, "DF": 10, "AP": 25, "MR": 15},
    "🐢 꾸릉이": {"AD": 10, "DF": 30, "AP": 5, "MR": 20},
    "🥷 미니 아칼리": {"AD": 48, "DF": 18, "AP": 42, "MR": 19},
    "⚔️ 미니 요네": {"AD": 60, "DF": 27, "AP": 13, "MR": 27},
    "✨ 미니 럭스": {"AD": 13, "DF": 20, "AP": 67, "MR": 27},
    "🎸 미니 유나라": {"AD": 43, "DF": 24, "AP": 37, "MR": 24},
    "🦊 미니 아리": {"AD": 19, "DF": 19, "AP": 58, "MR": 32},
    "🍙 해방된 포로 뭉치": {"AD": 18, "DF": 45, "AP": 15, "MR": 45},
    "🍄‍🟫 미니 티모": {"AD": 25, "DF": 14, "AP": 75, "MR": 13},
    "👮‍♀️ 미니 케이틀린": {"AD": 88, "DF": 15, "AP": 10, "MR": 15},
    "🗡️ 미니 카타리나": {"AD": 25, "DF": 13, "AP": 78, "MR": 13},
    "🥱 미니 조이": {"AD": 22, "DF": 14, "AP": 80, "MR": 13},
    "🪖 미니 이렐리아": {"AD": 46, "DF": 36, "AP": 12, "MR": 36},
    "🐱 미니 유미": {"AD": 5, "DF": 13, "AP": 95, "MR": 12},
    "⚙️ 미니 오리아나": {"AD": 18, "DF": 10, "AP": 92, "MR": 9},
    "🍌 미니 바나나 소라카": {"AD": 26, "DF": 39, "AP": 92, "MR": 53},
    "🌹 미니 수정 장미 그웬": {"AD": 50, "DF": 40, "AP": 50, "MR": 40},
    "🏆 미니 T1 요네": {"AD": 115, "DF": 43, "AP": 29, "MR": 43},
    "🗡️ 미니 불멸의 영웅 이렐리아": {"AD": 75, "DF": 35, "AP": 25, "MR": 35},
    "🐮 내가 젖소 포로": {"AD": 30, "DF": 80, "AP": 30, "MR": 80},
    "🌕 미니 핏빛 달 아트록스": {"AD": 55, "DF": 50, "AP": 50, "MR": 55},
    "🎵 미니 칠현금 소나": {"AD": 25, "DF": 28, "AP": 145, "MR": 28},
    "⚔️ 미니 전투사관학교 카타리나": {"AD": 45, "DF": 23, "AP": 140, "MR": 22},
    "😈 미니 작은 악마 티모": {"AD": 30, "DF": 27, "AP": 145, "MR": 26},
    "🤖 미니 우주 그루브 블리츠크랭크": {"AD": 45, "DF": 80, "AP": 25, "MR": 80},
    "👼 프레스티지 미니 빛의 인도자 요네": {"AD": 173, "DF": 72, "AP": 43, "MR": 72},
    "🌸 프레스티지 미니 영혼의 꽃 아리": {"AD": 43, "DF": 58, "AP": 173, "MR": 87},
    "☕ 프레스티지 미니 귀염둥이 카페 그웬": {"AD": 109, "DF": 72, "AP": 109, "MR": 72},
    "🎧 미니 헤드라이너 K/DA POP/STAR 카이사": {"AD": 120, "DF": 60, "AP": 120, "MR": 63},
    "🔫 미니 프레스티지 핏빛 달 미스포츈": {"AD": 220, "DF": 55, "AP": 34, "MR": 55},
    "🐉 미니 프레스티지 용의 권 리신": {"AD": 165, "DF": 90, "AP": 20, "MR": 90},
    "🤺 미니 프레스티지 용술사 야스오": {"AD": 180, "DF": 83, "AP": 20, "MR": 83},
    "🧙 미니 프레스티지 아케인 열혈 팬 애니": {"AD": 34, "DF": 50, "AP": 220, "MR": 60},
    "🦸 미니 프레스티지 불멸의 영웅 리븐": {"AD": 150, "DF": 98, "AP": 20, "MR": 98},
    "💛 미니 프레스티지 도자기 수호자 이즈리얼": {"AD": 200, "DF": 36, "AP": 90, "MR": 36},
    "🔫 아케인 분열 징크스": {"AD": 400, "DF": 50, "AP": 0, "MR": 50},
    "🌊 찬란한 바다뱀 세트": {"AD": 64, "DF": 220, "AP": 0, "MR": 220},
    "🧑🏻‍🦲 산-우잘 모데카이저": {"AD": 120, "DF": 120, "AP": 150, "MR": 113},
    "💮 영혼의 꽃 모르가나": {"AD": 40, "DF": 60, "AP": 340, "MR": 60},
    "⚰️ 망령의 지배자 비에고": {"AD": 200, "DF": 152, "AP": 0, "MR": 151},
    "♥️ 불멸의 전설 아리": {"AD": 60, "DF": 100, "AP": 520, "MR": 120},
    "💜 불멸의 전설 카이사": {"AD": 300, "DF": 100, "AP": 297, "MR": 100}
}

def get_pet_stats(pet_type: str, level: int) -> dict:
    """전설이 종류/레벨에 따른 최종 스탯을 계산합니다.

    💡 성급이 오를 때마다 모든 능력치가 2배가 됩니다.
       (1성 = 기본 스탯, 2성 = ×2, 3성 = ×4)
    스탯 명령·상태창·배틀이 모두 이 함수를 공유합니다.
    """
    base = PET_STATS.get(pet_type, {"AD": 5, "DF": 5, "AP": 5, "MR": 5})
    multiplier = 2 ** (level - 1) if level > 0 else 1  # 0성(알)은 기본 스탯 그대로
    return {stat: int(value * multiplier) for stat, value in base.items()}

# 💡 레벨별 필요 경험치 (고귀, 초월 가용 테이블 연동)
EXP_TABLE = {
    "서사": {0: 100, 1: 10000, 2: 15000, 3: 0},
    "전설": {0: 100, 1: 20000, 2: 30000, 3: 0},
    "신화": {0: 100, 1: 30000, 2: 60000, 3: 0},
    "프레스티지": {0: 100, 1: 50000, 2: 100000, 3: 0},
    "고귀": {0: 100, 1: 100000, 2: 200000, 3: 0},
    "초월": {0: 100, 1: 200000, 2: 300000, 3: 0}
}

# 💡 전설이 이미지 URL
PET_IMAGES = {
    "🐧 펭구": "https://i.ibb.co/DH2Gc8sx/image.webp",
    "🗡️ 깃털기사": "https://i.ibb.co/vvQdXcrr/image.webp",
    "🦄 뿔보": "https://i.ibb.co/1YDHJv3H/image.webp",
    "👻 말랑이": "https://i.ibb.co/DfCGW2C5/image.webp",
    "🐢 꾸릉이": "https://i.ibb.co/8gFTGg7C/image.webp",
    "🥷 미니 아칼리": "https://i.ibb.co/gL6wXXQ0/image.webp",
    "⚔️ 미니 요네": "https://i.ibb.co/8LHct37j/image.webp",
    "✨ 미니 럭스": "https://i.ibb.co/JRdcSsTL/image.webp",
    "🎸 미니 유나라": "https://i.ibb.co/QFY5Yx8W/image.webp",
    "🦊 미니 아리": "https://i.ibb.co/svWD5MPz/image.webp",
    "🍌 미니 바나나 소라카": "https://i.ibb.co/Lz7hQBMy/image.jpg",
    "🌹 미니 수정 장미 그웬": "https://i.ibb.co/xSBB7kQ5/image.png",
    "🏆 미니 T1 요네": "https://i.ibb.co/5XbgxL57/T1.png",
    "🗡️ 미니 불멸의 영웅 이렐리아": "https://i.ibb.co/7NpFbL7q/image.webp",
    "🐮 내가 젖소 포로": "https://i.ibb.co/Dg9Bgv5g/image.png",
    "👼 프레스티지 미니 빛의 인도자 요네": "https://i.ibb.co/0VfHhQ75/image.png",
    "🌸 프레스티지 미니 영혼의 꽃 아리": "https://i.ibb.co/WWBPvH7Y/image.png",
    "☕ 프레스티지 미니 귀염둥이 카페 그웬": "https://i.ibb.co/tM8rCsyg/image.png",
    "🍙 해방된 포로 뭉치": "https://i.ibb.co/zHtBHg7J/image.webp",
    "🍄‍🟫 미니 티모": "https://i.ibb.co/XxTGZDwK/image.webp",
    "👮‍♀️ 미니 케이틀린": "https://i.ibb.co/qMdfB1jG/image.webp",
    "🗡️ 미니 카타리나": "https://i.ibb.co/7dx3jqwH/image.webp",
    "🥱 미니 조이": "https://i.ibb.co/ZRjkHDtf/image.webp",
    "🪖 미니 이렐리아": "https://i.ibb.co/JWRk7Kzb/image.webp",
    "🐱 미니 유미": "https://i.ibb.co/bgJ5t3nV/image.webp",
    "⚙️ 미니 오리아나": "https://i.ibb.co/jPCRK30P/image.png",
    "🌕 미니 핏빛 달 아트록스": "https://i.ibb.co/FkkwtB6F/image.png",
    "🎵 미니 칠현금 소나": "https://i.ibb.co/99tPpP1R/image.png",
    "⚔️ 미니 전투사관학교 카타리나": "https://i.ibb.co/n9fcLZX/image.png",
    "😈 미니 작은 악마 티모": "https://i.ibb.co/397t9QmW/image.png",
    "🤖 미니 우주 그루브 블리츠크랭크": "https://i.ibb.co/7xv4nJhF/image.png",
    "🎧 미니 헤드라이너 K/DA POP/STAR 카이사": "https://i.ibb.co/pvD00D1g/KDA-POP-STAR.png",
    "🔫 미니 프레스티지 핏빛 달 미스포츈": "https://i.ibb.co/cS0Zz5Kq/image.png",
    "🐉 미니 프레스티지 용의 권 리신": "https://i.ibb.co/cXQbPPLZ/image.webp",
    "🤺 미니 프레스티지 용술사 야스오": "https://i.ibb.co/5hymsGwf/image.webp",
    "🧙 미니 프레스티지 아케인 열혈 팬 애니": "https://i.ibb.co/rDj1dbn/image.png",
    "🦸 미니 프레스티지 불멸의 영웅 리븐": "https://i.ibb.co/C5n6KrqW/image.png",
    "💛 미니 프레스티지 도자기 수호자 이즈리얼": "https://i.ibb.co/R4PjQ68F/image.png",
    "🔫 아케인 분열 징크스": "https://i.ibb.co/d4MhfQbt/image.png",
    "🌊 찬란한 바다뱀 세트": "https://i.ibb.co/LXFBtbYs/image.png",
    "🧑🏻‍🦲 산-우잘 모데카이저": "https://i.ibb.co/hRnfcX5R/image.png",
    "💮 영혼의 꽃 모르가나": "https://i.ibb.co/KxxX6qWz/image.png",
    "⚰️ 망령의 지배자 비에고": "https://i.ibb.co/YTDbY3R6/image.png",
    # 초월 등급은 1·2성 이미지를 여기에, 3성 진화 이미지는 아래 PET_IMAGES_EVOLVED에 등록
    "♥️ 불멸의 전설 아리": "https://i.ibb.co/NngzhVgS/1-2.png",
    "💜 불멸의 전설 카이사": "https://i.ibb.co/qLpTR7B1/1-2.png"
}

# 💡 3성 도달 시 이미지가 바뀌는 전설이(초월 등급)의 진화 이미지 URL
# key가 여기에 있으면 3성일 때 이 이미지를, 그 외 레벨은 위 PET_IMAGES를 사용합니다.
PET_IMAGES_EVOLVED = {
    "♥️ 불멸의 전설 아리": "https://i.ibb.co/HfCGNx9M/3.png",
    "💜 불멸의 전설 카이사": "https://i.ibb.co/d4rZgtzy/3.png"
}

# 💡 아이템 정보 및 효과
ITEMS_INFO = {
    "배부름을 부르는 약": {"rarity": "서사", "desc": "사용 시 24시간 동안 전설이의 포만도를 MAX로 유지합니다."},
    "쌩쌩한약": {"rarity": "신화", "desc": "사용 시 24시간 동안 산책을 무리하게 시켜도 피로도가 0으로 유지됩니다."},
    "트위치 나가라약": {"rarity": "전설", "desc": "사용 시 24시간 동안 청결도를 MAX로 유지합니다."},
    "아무무도 인싸로 만드는 약": {"rarity": "신화", "desc": "사용 시 24시간 동안 전설이의 친밀도를 MAX로 유지합니다."},
    "100회 산책 할인권": {"rarity": "전설", "desc": "보유 중일 때 100회 산책 시 자동으로 소모되며 100P 대신 30P만 소비합니다. (일회용)"},
    "경험치 부스터 X2": {"rarity": "전설", "desc": "사용 시 통화방 3시간 동안 경험치 획득량이 2배가 됩니다."},
    "경험치 부스터 X5": {"rarity": "신화", "desc": "사용 시 통화방 3시간 동안 경험치 획득량이 5배가 됩니다."},
    "경험치 부스터 X10": {"rarity": "프레스티지", "desc": "사용 시 통화방 3시간 동안 경험치 획득량이 10배가 됩니다."},
    "신비한 알약": {"rarity": "프레스티지", "desc": "사용 시 2주(14일) 동안 모든 상태가 최상으로 고정됩니다."},
    "전설이 이름 변경권": {"rarity":"신화", "desc": "전설이의 이름을 새로 지어줄 수 있는 신비한 변경권입니다."},
    # rarity "특수" -> 산책 아이템 드랍 대상에서 제외됨(상점 전용). /알상점 에서만 구매 가능.
    "합성 방어권": {"rarity": "특수", "desc": "보유 시 전설이 합성에 실패해도 재료 전설이가 소멸하지 않습니다. (합성 실패 시 1개 자동 소모)"}
}

# 💡 등급 아이콘 이미지 URL (요청하신 신규/변경 이미지로 전면 교체)
RARITY_IMAGES = {
    "서사": "https://i.ibb.co/JWqtSKyB/image.webp",
    "전설": "https://i.ibb.co/fz8C42ZT/image.webp",
    "신화": "https://i.ibb.co/23mnQTzC/image.webp",
    "프레스티지": "https://i.ibb.co/QFbvp8Rw/image.png",
    "고귀": "https://i.ibb.co/7xXqRnMf/image.png",
    "초월": "https://i.ibb.co/PGKqDdXF/image.png"
}