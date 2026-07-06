# 💡 획득 가능한 전설이 목록
PET_POOLS = {
    "서사": ["🐧 펭구", "🗡️ 깃털기사", "🦄 뿔보", "👻 말랑이", "🐢 꾸릉이"],
    "전설": ["🥷 미니 아칼리", "⚔️ 미니 요네", "✨ 미니 럭스", "🎸 미니 유나라", "🦊 미니 아리"],
    "신화": ["🍌 미니 바나나 소라카", "🌹 미니 수정 장미 그웬", "🏆 미니 T1 요네", "🗡️ 미니 불멸의 영웅 이렐리아", "🐮 내가 젖소 포로"],
    "프레스티지": ["👼 프레스티지 미니 빛의 인도자 요네", "🌸 프레스티지 미니 영혼의 꽃 아리", "☕ 프레스티지 미니 귀염둥이 카페 그웬"]
}

# 💡 전설이 기본 스탯 (추후 자유롭게 숫자 수정 가능)
PET_STATS = {
    "🐧 펭구": {"AD": 15, "DF": 15, "AP": 15, "MR": 15},
    "🗡️ 깃털기사": {"AD": 25, "DF": 10, "AP": 5, "MR": 10},
    "🦄 뿔보": {"AD": 10, "DF": 25, "AP": 5, "MR": 20},
    "👻 말랑이": {"AD": 5, "DF": 10, "AP": 25, "MR": 15},
    "🐢 꾸릉이": {"AD": 10, "DF": 30, "AP": 5, "MR": 20},
    "🥷 미니 아칼리": {"AD": 40, "DF": 15, "AP": 35, "MR": 15},
    "⚔️ 미니 요네": {"AD": 45, "DF": 20, "AP": 10, "MR": 20},
    "✨ 미니 럭스": {"AD": 10, "DF": 15, "AP": 50, "MR": 20},
    "🎸 미니 유나라": {"AD": 35, "DF": 20, "AP": 30, "MR": 20},
    "🦊 미니 아리": {"AD": 15, "DF": 15, "AP": 45, "MR": 25},
    "🍌 미니 바나나 소라카": {"AD": 20, "DF": 30, "AP": 70, "MR": 40},
    "🌹 미니 수정 장미 그웬": {"AD": 50, "DF": 40, "AP": 50, "MR": 40},
    "🏆 미니 T1 요네": {"AD": 80, "DF": 30, "AP": 20, "MR": 30},
    "🗡️ 미니 불멸의 영웅 이렐리아": {"AD": 75, "DF": 35, "AP": 25, "MR": 35},
    "🐮 내가 젖소 포로": {"AD": 30, "DF": 80, "AP": 30, "MR": 80},
    "👼 프레스티지 미니 빛의 인도자 요네": {"AD": 120, "DF": 50, "AP": 30, "MR": 50},
    "🌸 프레스티지 미니 영혼의 꽃 아리": {"AD": 30, "DF": 40, "AP": 120, "MR": 60},
    "☕ 프레스티지 미니 귀염둥이 카페 그웬": {"AD": 90, "DF": 60, "AP": 90, "MR": 60}
}

# 💡 레벨별 필요 경험치 (0성은 100 경험치 고정이며, 부화 후 레벨업 요구량)
EXP_TABLE = {
    "서사": {0: 5000, 1: 10000, 2: 15000, 3: 0},
    "전설": {0: 5000, 1: 20000, 2: 30000, 3: 0},
    "신화": {0: 5000, 1: 30000, 2: 60000, 3: 0},
    "프레스티지": {0: 5000, 1: 50000, 2: 100000, 3: 0}
}

# 💡 전설이 이미지 URL 모음
PET_IMAGES = {
    "🐧 펭구": "https://cdn.discordapp.com/attachments/1523108729845841931/1523110618322964530/eb8dde11f76ff075.webp",
    "🗡️ 깃털기사": "https://cdn.discordapp.com/attachments/1523108729845841931/1523110760597684455/110a3f527e853a37.webp",
    "🦄 뿔보": "https://cdn.discordapp.com/attachments/1523108729845841931/1523111061384073276/c80b732986fc6f98.webp",
    "👻 말랑이": "https://cdn.discordapp.com/attachments/1523108729845841931/1523111243483975740/8b1a8a0f2fc9b6ab.webp",
    "🐢 꾸릉이": "https://cdn.discordapp.com/attachments/1523108729845841931/1523111748868247562/0b1d8113a8b053e4.webp",
    "🥷 미니 아칼리": "https://cdn.discordapp.com/attachments/1523108729845841931/1523111812084797440/8rBNeQwfU-aEc_mLZZ3zlH_a1zxpjv0AImKTpUc3hwt5lMnctdic_CbwRc8zn8f4QiwvJCRr6LWl9wlZKG09O6-O7U4GU56ZtQozFBD7p0Lp8c7x7uPp94zFIgJ9XGG4n1XhrDqv-fyuwpVKdd0Kkg.webp",
    "⚔️ 미니 요네": "https://cdn.discordapp.com/attachments/1523108729845841931/1523111901939240980/dc9NzQMvdebbhXGkzF0o6pDkgxP8JTgy1qg8bAXIp2zcrneEc-9eE6cDiZK67OBUtfejo0q5UFJzJeoF-zt2L2-GYMoItzurX6PsbZi2akMEDUmGZ0_Ena4yf1BfJORuBMly8k0rFx8Z6PwvvS5pbw.webp",
    "✨ 미니 럭스": "https://cdn.discordapp.com/attachments/1523108729845841931/1523111980280582204/4msZPa3P0waNxdWUygWD0JM_pKz2Oh-VgiPaYh0MYWQjgWxV4tY3nQfmmq96h9LfQaEuiSz5XE1ZjcfcXzltR7UOmWG7Y5RHVxWW5QKgktSxcgURzhQhqY2LIGN30WQbX6u5LTbOQ8wxAqE1nLKwdA.webp",
    "🎸 미니 유나라": "https://cdn.discordapp.com/attachments/1523108729845841931/1523112087759491172/604c5d89d6b50505.webp",
    "🦊 미니 아리": "https://cdn.discordapp.com/attachments/1523108729845841931/1523112175689011270/3812b68d738c01d2.webp",
    "🍌 미니 바나나 소라카": "https://media.discordapp.net/attachments/1523108729845841931/1523112465343184926/91ab6c1a68d46a10.jfif",
    "🌹 미니 수정 장미 그웬": "https://cdn.discordapp.com/attachments/1523108729845841931/1523112718993719318/image.png",
    "🏆 미니 T1 요네": "https://cdn.discordapp.com/attachments/1523108729845841931/1523112852670648472/image.png",
    "🗡️ 미니 불멸의 영웅 이렐리아": "https://cdn.discordapp.com/attachments/1523108729845841931/1523112953619022055/98ee487cbc9c232b.webp",
    "🐮 내가 젖소 포로": "https://cdn.discordapp.com/attachments/1523108729845841931/1523113213586051162/image.png",
    "👼 프레스티지 미니 빛의 인도자 요네": "https://cdn.discordapp.com/attachments/1523108729845841931/1523113377151451319/image.png",
    "🌸 프레스티지 미니 영혼의 꽃 아리": "https://cdn.discordapp.com/attachments/1523108729845841931/1523113573499408454/image.png",
    "☕ 프레스티지 미니 귀염둥이 카페 그웬": "https://cdn.discordapp.com/attachments/1523108729845841931/1523113700318253076/image.png"
}

# 💡 아이템 정보 및 효과
ITEMS_INFO = {
    "배부름을 부르는 약": {"rarity": "서사", "desc": "사용 시 24시간 동안 전설이의 포만도를 MAX로 유지합니다."},
    "쌩쌩한약": {"rarity": "신화", "desc": "사용 시 24시간 동안 산책을 무리하게 시켜도 피로도가 0으로 유지됩니다."},
    "트위치 나가라약": {"rarity": "전설", "desc": "사용 시 24시간 동안 청결도를 MAX로 유지합니다."},
    "아무무도 인싸로 만드는 약": {"rarity": "신화", "desc": "사용 시 24시간 동안 전설이의 친밀도를 MAX로 유지합니다."},
    "100회 산책 할인권": {"rarity": "전설", "desc": "보유 중일 때 100회 산책 시 자동으로 소모되며 100P 대신 30P만 소비합니다. (일회용)"},
    "경험치 부스터 X2": {"rarity": "전설", "desc": "사용 시 통화방 3시간 동안 경험치 획득량이 2배가 됩니다. (청결도 MAX 상태와 중복 불가)"},
    "경험치 부스터 X5": {"rarity": "신화", "desc": "사용 시 통화방 3시간 동안 경험치 획득량이 5배가 됩니다. (청결도 MAX 상태와 중복 불가)"},
    "경험치 부스터 X10": {"rarity": "프레스티지", "desc": "사용 시 통화방 3시간 동안 경험치 획득량이 10배가 됩니다. (청결도 MAX 상태와 중복 불가)"},
    "50포인트 교환권": {"rarity": "서사", "desc": "사용 시 50P를 획득합니다."},
    "100포인트 교환권": {"rarity": "전설", "desc": "사용 시 100P를 획득합니다."},
    "500포인트 교환권": {"rarity": "신화", "desc": "사용 시 500P를 획득합니다."},
    "1000포인트 교환권": {"rarity": "프레스티지", "desc": "사용 시 1,000P를 획득합니다."},
    "신비한 알약": {"rarity": "프레스티지", "desc": "사용 시 2주(14일) 동안 포만감 MAX, 피로도 0, 친밀도 MAX, 청결도 MAX 상태가 고정됩니다."},
    "전설이 이름 변경권": {"rarity":"신화", "desc": "전설이의 이름을 새로 지어줄 수 있는 신비한 변경권입니다. (/이름변경 명령어 사용)"}
}

# 💡 아이템 판매 가격 (현재는 판매 기능이 제거되었으나 데이터 보존용)
ITEM_PRICES = {"서사": 10, "전설": 50, "신화": 250, "프레스티지": 500}

# 💡 등급 아이콘 이미지 URL
RARITY_IMAGES = {
    "서사": "https://media.discordapp.net/attachments/1523108729845841931/1523316041747529768/a0879e2a5280e7ae.webp",
    "전설": "https://media.discordapp.net/attachments/1523108729845841931/1523316027130380358/abd22132851db392.webp",
    "신화": "https://media.discordapp.net/attachments/1523108729845841931/1523316008574779574/35497edbaa34bc93.webp",
    "프레스티지": "https://media.discordapp.net/attachments/1523108729845841931/1523324569748766730/image.png?ex=6a4c5acf&is=6a4b094f&hm=d985ff493f3d69ba6ca4b17e28dc253f77d0b6c3be601d3b2ba6ab4f28b0a45c&=&format=webp&quality=lossless"
}