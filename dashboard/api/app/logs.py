# -*- coding: utf-8 -*-
"""
logs.py — 봇이 남긴 로그를 현황판이 쓰기 좋은 레코드로 읽는다.

봇의 stats_engine.collect_stats()는 '전체 합계'만 돌려주고 날짜를 버린다.
현황판은 날짜·시간대별로 나눠 봐야 하므로 같은 파일을 직접 읽되,
줄 해석 규칙은 봇과 똑같이 맞춘다 (CLAUDE.md '로그 형식' 참고).

    stats.log      3칸(구): 시각 / 사용자ID / 결과
                   4칸(신): 시각 / 사용자ID / 결과 / 질문 원문
    unanswered.log 는 digest._parse_line()을 그대로 재사용한다.

형식이 깨진 줄은 조용히 건너뛰되, 몇 줄을 건너뛰었는지는 세어 둔다.
봇에서 '형식이 안 맞는 줄이 조용히 버려져 통계가 0으로 나간' 일을 두 번 겪었기
때문에, 현황판에서는 그 숫자를 화면에 보이게 한다.
"""

import datetime
import hashlib
from dataclasses import dataclass
from pathlib import Path

from . import config

FAQ = "faq"          # 키워드로 FAQ가 바로 답함
LLM = "llm"          # LLM이 답함 (openai, claude 등)
NOMATCH = "nomatch"  # 아무도 못 답함


@dataclass(frozen=True)
class Record:
    ts: datetime.datetime
    user: str              # 화면용 별칭 (원래 ID는 보관하지 않는다)
    route: str             # FAQ / LLM / NOMATCH
    handled_by: str        # 로그에 적힌 원래 값 (hit:주제, openai, nomatch ...)
    topic: str | None      # FAQ로 답했을 때의 주제명
    question: str          # 원문 미기록 시절의 줄은 빈 문자열


@dataclass
class Parsed:
    records: list
    skipped: int           # 형식이 맞지 않아 건너뛴 줄 수


def alias(user_id: str | None) -> str:
    """디스코드 사용자 ID → 'U-1a2b3c' 같은 짧은 별칭.

    현황판에서 필요한 건 '같은 사람이 여러 번 물었는가'까지다.
    실제 ID를 화면에 노출하면 운영진 외의 사람이 보게 됐을 때 바로 신원이 드러난다.
    """
    if not user_id or user_id == "-":
        return "-"
    digest = hashlib.sha256(f"{config.ID_SALT}:{user_id}".encode()).hexdigest()
    return f"U-{digest[:6]}"


def route_of(handled_by: str) -> tuple:
    """로그의 결과 칸 → (경로, 주제). 봇의 collect_stats()와 같은 기준."""
    if handled_by.startswith("hit:"):
        return FAQ, handled_by.split(":", 1)[1]
    if handled_by == NOMATCH:
        return NOMATCH, None
    return LLM, None  # 백엔드 이름이 그대로 들어온다 (openai, claude 등)


def _parse_ts(raw: str):
    try:
        return datetime.datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


# 파일이 바뀌지 않았으면 다시 읽지 않는다. (경로, 수정시각, 크기)로 판단한다.
_cache: dict = {}


def _read_lines(path: Path):
    try:
        st = path.stat()
    except FileNotFoundError:
        return None, []
    key = (str(path), st.st_mtime_ns, st.st_size)
    return key, path.read_text(encoding="utf-8").splitlines()


def read_stats(path: Path | None = None) -> Parsed:
    """stats.log 전체를 Record 목록으로 읽는다 (시간순)."""
    path = path or config.STATS_LOG_FILE
    key, lines = _read_lines(path)
    if key is None:
        return Parsed([], 0)
    if key in _cache:
        return _cache[key]

    records, skipped = [], 0
    for line in lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) == 3:
            ts_raw, uid, handled = parts
            question = ""
        elif len(parts) == 4:
            ts_raw, uid, handled, question = parts
        else:
            skipped += 1
            continue
        ts = _parse_ts(ts_raw)
        if ts is None:
            skipped += 1
            continue
        route, topic = route_of(handled)
        records.append(Record(ts, alias(uid), route, handled, topic, question.strip()))

    records.sort(key=lambda r: r.ts)
    parsed = Parsed(records, skipped)
    _cache.clear()  # 오래된 버전은 버린다 (파일 하나당 최신본 하나면 충분)
    _cache[key] = parsed
    return parsed


def read_misses(path: Path | None = None) -> list:
    """unanswered.log → digest가 쓰는 (시각, 처리주체, 질문) 목록. 봇 함수를 그대로 쓴다."""
    import digest  # 봇 모듈 (config가 import 경로를 잡아 둔다)

    path = path or config.MISS_LOG_FILE
    return digest.read_questions(since=None, path=path)


def in_range(records: list, start: datetime.date | None, end: datetime.date | None) -> list:
    """날짜 범위(양끝 포함)로 거른다. 범위를 안 주면 전체."""
    return [
        r for r in records
        if (start is None or r.ts.date() >= start) and (end is None or r.ts.date() <= end)
    ]
