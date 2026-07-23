# -*- coding: utf-8 -*-
"""
hours.py — 질문 운영시간 판단.

기본 운영시간은 한국시간(KST) 기준 10:00~17:00. .env의 QA_START_HOUR /
QA_END_HOUR로 조정 가능 (예: 하루 종일 받으려면 0과 24로 설정).
discord 의존성 없음 → 단독 테스트 가능.
"""

import datetime
import os
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
QA_START_HOUR = int(os.environ.get("QA_START_HOUR", "10"))
QA_END_HOUR = int(os.environ.get("QA_END_HOUR", "17"))


def is_operating_hours(now: datetime.datetime | None = None) -> bool:
    """지금이 질문 운영시간(기본 매일 10:00~17:00, 한국시간)인지 판단."""
    now = now or datetime.datetime.now(KST)
    return QA_START_HOUR <= now.hour < QA_END_HOUR
