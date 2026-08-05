# -*- coding: utf-8 -*-
"""
hours.py — 질문 운영시간 판단.

기본 운영시간은 한국시간(KST) 기준 10:00~17:00. .env의 QA_START_HOUR /
QA_END_HOUR로 조정 가능.

설정 예시:
    QA_START_HOUR=10, QA_END_HOUR=17  → 낮 10시~오후 5시 (기본값)
    QA_START_HOUR=0,  QA_END_HOUR=24  → 24시간 항상 받기
    QA_START_HOUR=20, QA_END_HOUR=4   → 밤 8시~새벽 4시 (자정을 넘김. 밤샘 해커톤용)

discord 의존성 없음 → 단독 테스트 가능.
"""

import datetime
import os
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def _read_hour(name: str, default: int) -> int:
    """환경변수에서 시각(정수)을 읽는다. 값이 이상하면 기본값으로 되돌린다.

    .env에 오타(QA_START_HOUR=10시)가 있으면 int()가 예외를 던지고,
    그게 모듈 import 시점이라 봇이 통째로 안 뜬다. 그런 사고를 막는다.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        print(f"⚠️ {name} 값이 숫자가 아닙니다({raw!r}). 기본값 {default}을(를) 사용합니다.")
        return default
    if not 0 <= value <= 24:
        print(f"⚠️ {name}은(는) 0~24 사이여야 합니다({value}). 기본값 {default}을(를) 사용합니다.")
        return default
    return value


# 기본값은 24시간 개방(0~24).
# 해커톤은 밤샘이 기본이고 질문이 몰리는 시간대가 오히려 새벽이다.
# 봇은 사람과 달리 밤에 답한다고 지치지 않으므로 열어두는 쪽이 합리적이다.
# 낮에만 받고 싶으면 .env에서 QA_START_HOUR=10, QA_END_HOUR=17 처럼 지정하면 된다.
QA_START_HOUR = _read_hour("QA_START_HOUR", 0)
QA_END_HOUR = _read_hour("QA_END_HOUR", 24)


def is_operating_hours(now: datetime.datetime | None = None) -> bool:
    """지금이 질문 운영시간인지 판단 (한국시간 기준).

    시작 < 종료 : 같은 날 안의 구간 (예: 10~17 → 10시 이상 17시 미만)
    시작 > 종료 : 자정을 넘기는 구간 (예: 20~4 → 20,21,22,23,0,1,2,3시)
                 밤샘 해커톤에서 실제로 자주 쓰는 설정이라 지원한다.
    시작 == 종료: 구분이 불가능하므로 항상 열린 것으로 본다.
    """
    now = now or datetime.datetime.now(KST)
    hour = now.hour

    if QA_START_HOUR == QA_END_HOUR:
        return True
    if QA_START_HOUR < QA_END_HOUR:
        return QA_START_HOUR <= hour < QA_END_HOUR
    return hour >= QA_START_HOUR or hour < QA_END_HOUR


def describe() -> str:
    """사람이 읽을 수 있는 운영시간 문구 (안내 메시지용)."""
    if QA_START_HOUR == QA_END_HOUR or (QA_START_HOUR == 0 and QA_END_HOUR == 24):
        return "24시간 언제나"
    if QA_START_HOUR > QA_END_HOUR:
        return f"{QA_START_HOUR}:00 ~ 다음날 {QA_END_HOUR}:00"
    return f"{QA_START_HOUR}:00 ~ {QA_END_HOUR}:00"
