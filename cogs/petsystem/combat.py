"""전설이 전투/스탯 계산 로직 모음.

기존에는 get_pet_stats 가 ui_action.py(UI 코드) 안에 섞여 있었으나,
전투 계산과 UI 렌더링을 분리하기 위해 이 모듈로 옮겼습니다.
(ui_action.py 는 여기서 재노출하므로 기존 import 경로는 그대로 동작합니다.)
"""

from utils.data import PET_STATS


def get_pet_stats(pet_type, level):
    """전설이 종류/레벨에 따른 최종 스탯을 계산합니다.

    레벨 배율: 알(0성)=1배, 1성=1.5배, 2성=2.5배, 3성=3.5배
    """
    base_stats = PET_STATS.get(pet_type, {"AD": 5, "DF": 5, "AP": 5, "MR": 5})
    multiplier = (1.5 + max(0, level - 1)) if level > 0 else 1
    return {
        "AD": int(base_stats["AD"] * multiplier),
        "DF": int(base_stats["DF"] * multiplier),
        "AP": int(base_stats["AP"] * multiplier),
        "MR": int(base_stats["MR"] * multiplier),
    }


def calc_pet_power(pet_data):
    """단일 전설이의 순수 스탯 총합(전투력). 팀 선발 정렬 등에 사용합니다."""
    if pet_data.get('level', 0) == 0:
        return 0
    stats = get_pet_stats(pet_data['type'], pet_data['level'])
    return stats['AD'] + stats['DF'] + stats['AP'] + stats['MR']


def mitigation(resist):
    """방어 스탯에 따른 피해 감소 계수 (LoL식 100/(100+저항)).

    저항 0 -> 1.0(감소 없음), 100 -> 0.5, 300 -> 0.25 로 수렴합니다.
    이 계수 덕분에 DF는 AD를, MR은 AP를 카운터하게 됩니다.
    """
    return 100.0 / (100.0 + max(0, resist))


def calc_team_battle_score(team, enemy_team):
    """상대 팀 방어력을 고려한 '유효 전투력'을 계산합니다.

    - 우리 팀 총 AD 는 상대 팀 평균 DF 로 감쇄
    - 우리 팀 총 AP 는 상대 팀 평균 MR 로 감쇄
    성급/등급이 아니라 실제 스탯 상성(공격 vs 방어)이 승패를 좌우합니다.
    """
    team_stats = [get_pet_stats(p['type'], p['level']) for p in team if p.get('level', 0) > 0]
    enemy_stats = [get_pet_stats(p['type'], p['level']) for p in enemy_team if p.get('level', 0) > 0]
    if not team_stats:
        return 0.0

    total_ad = sum(s['AD'] for s in team_stats)
    total_ap = sum(s['AP'] for s in team_stats)

    n = len(enemy_stats) or 1
    avg_df = sum(s['DF'] for s in enemy_stats) / n
    avg_mr = sum(s['MR'] for s in enemy_stats) / n

    return total_ad * mitigation(avg_df) + total_ap * mitigation(avg_mr)


def calc_win_rate(p1_team, p2_team):
    """두 팀의 유효 전투력을 비교해 p1 승률(0~1)과 각 팀 점수를 돌려줍니다."""
    p1_score = calc_team_battle_score(p1_team, p2_team)
    p2_score = calc_team_battle_score(p2_team, p1_team)
    total = p1_score + p2_score
    p1_win_rate = p1_score / total if total > 0 else 0.5
    return p1_win_rate, p1_score, p2_score
