# -*- coding: utf-8 -*-
"""
main.py — FAQ 봇 운영 현황판 API (FastAPI).

봇이 쌓은 로그(stats.log, unanswered.log)와 faq.md를 읽기만 한다.
봇 코드나 로그 파일을 고치지 않으므로, 봇이 돌아가는 서버에 함께 띄워도 안전하다.

실행 (저장소 루트에서):
    pip install -r dashboard/api/requirements.txt
    DATA_DIR=dashboard/sample-data uvicorn app.main:app --app-dir dashboard/api --reload
    → http://localhost:8000/docs 에서 API 문서 확인
"""

import datetime
import json
import os
from collections import Counter
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import config, logs
from .schemas import (
    DailyRow, FaqInfo, Health, HourlyRow, QuestionPage, QuestionRow,
    Suggestion, SuggestionReport, Summary, TopicRow,
)

# 접근 토큰. 설정하면 모든 /api 요청에 X-Dashboard-Token 헤더가 필요하다.
# 실제 로그(학생 질문 원문 포함)를 띄울 때는 반드시 설정할 것.
ACCESS_TOKEN = os.environ.get("DASHBOARD_TOKEN", "")

# 예시 데이터로 띄운 시연용 배포인지. 화면 상단에 '예시 데이터' 표시를 띄운다.
DEMO = os.environ.get("DASHBOARD_DEMO", "") == "1"


def require_token(x_dashboard_token: str = Header(default="")) -> None:
    if ACCESS_TOKEN and x_dashboard_token != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="접근 토큰이 필요합니다.")


app = FastAPI(
    title="FAQ 봇 운영 현황판 API",
    description="해커톤 FAQ 봇의 질문 로그를 집계해 운영진이 볼 현황판에 제공합니다.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

guard = [Depends(require_token)]


# ── 공통 ──────────────────────────────────────────────────────────

def _faq_entries() -> list:
    """faq.md를 봇과 같은 파서로 읽는다."""
    from faq_engine import load_faq  # 봇 모듈

    if not config.FAQ_FILE.exists():
        return []
    return load_faq(str(config.FAQ_FILE))


def _range(start: datetime.date | None, end: datetime.date | None) -> list:
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="start가 end보다 늦습니다.")
    return logs.in_range(logs.read_stats().records, start, end)


def DateParam():
    """날짜 쿼리 파라미터. 매번 새 Query를 만든다.

    Query 객체 하나를 start·end에 같이 쓰면 FastAPI가 둘을 같은 값으로 묶어 버려
    end에 start 값이 들어간다(실제로 겪음 — test_date_range_filter가 지킨다).
    """
    return Query(default=None, description="YYYY-MM-DD (포함)")


# ── 엔드포인트 ────────────────────────────────────────────────────

@app.get("/api/health", response_model=Health)
def health():
    """데이터 파일이 제대로 보이는지 확인용. 토큰 없이 열려 있다 (집계값 없음)."""
    recs = logs.read_stats().records
    return Health(
        status="ok",
        demo=DEMO,
        first_date=recs[0].ts.date().isoformat() if recs else None,
        last_date=recs[-1].ts.date().isoformat() if recs else None,
        data_dir=str(config.DATA_DIR),
        stats_log=config.STATS_LOG_FILE.exists(),
        unanswered_log=config.MISS_LOG_FILE.exists(),
        faq_entries=len(_faq_entries()),
        skipped_lines=logs.read_stats().skipped,
    )


@app.get("/api/summary", response_model=Summary, dependencies=guard)
def summary(start: datetime.date | None = DateParam(), end: datetime.date | None = DateParam()):
    """핵심 지표: 총 질문, 사용 인원, 응답 경로별 건수, FAQ 즉시 응답률."""
    recs = _range(start, end)
    routes = Counter(r.route for r in recs)
    days = Counter(r.ts.date().isoformat() for r in recs)
    busiest = days.most_common(1)
    entries = _faq_entries()
    used = {r.topic for r in recs if r.route == logs.FAQ}
    total = len(recs)
    return Summary(
        start=start.isoformat() if start else None,
        end=end.isoformat() if end else None,
        total=total,
        unique_users=len({r.user for r in recs}),
        faq=routes[logs.FAQ],
        llm=routes[logs.LLM],
        nomatch=routes[logs.NOMATCH],
        faq_rate=round(routes[logs.FAQ] / total, 4) if total else 0.0,
        faq_entries=len(entries),
        faq_entries_used=len(used & {e.title for e in entries}) if entries else len(used),
        busiest_day=busiest[0][0] if busiest else None,
        busiest_day_count=busiest[0][1] if busiest else 0,
    )


@app.get("/api/daily", response_model=list[DailyRow], dependencies=guard)
def daily(start: datetime.date | None = DateParam(), end: datetime.date | None = DateParam()):
    """날짜별 질문 수를 응답 경로별로 나눠서. 질문이 없던 날도 0으로 채운다."""
    recs = _range(start, end)
    if not recs:
        return []
    by_day: dict = {}
    for r in recs:
        row = by_day.setdefault(r.ts.date(), Counter())
        row[r.route] += 1
    first, last = min(by_day), max(by_day)
    out, d = [], first
    while d <= last:  # 빈 날을 건너뛰면 그래프에서 간격이 왜곡된다
        c = by_day.get(d, Counter())
        out.append(DailyRow(date=d.isoformat(), total=sum(c.values()),
                            faq=c[logs.FAQ], llm=c[logs.LLM], nomatch=c[logs.NOMATCH]))
        d += datetime.timedelta(days=1)
    return out


@app.get("/api/hourly", response_model=list[HourlyRow], dependencies=guard)
def hourly(start: datetime.date | None = DateParam(), end: datetime.date | None = DateParam()):
    """시간대(0~23시)별 질문 수. 운영진이 언제 대기해야 하는지 보는 용도."""
    c = Counter(r.ts.hour for r in _range(start, end))
    return [HourlyRow(hour=h, total=c[h]) for h in range(24)]


@app.get("/api/topics", response_model=list[TopicRow], dependencies=guard)
def topics(
    start: datetime.date | None = DateParam(),
    end: datetime.date | None = DateParam(),
    limit: int = Query(default=10, ge=1, le=100),
):
    """FAQ로 답한 질문의 주제별 건수 (많은 순)."""
    c = Counter(r.topic for r in _range(start, end) if r.route == logs.FAQ)
    cat = {e.title: e.category for e in _faq_entries()}
    return [TopicRow(topic=t, count=n, category=cat.get(t)) for t, n in c.most_common(limit)]


@app.get("/api/questions", response_model=QuestionPage, dependencies=guard)
def questions(
    q: str = Query(default="", description="질문에 포함된 단어 (공백·대소문자 무시)"),
    route: str = Query(default="", pattern="^(|faq|llm|nomatch)$"),
    start: datetime.date | None = DateParam(),
    end: datetime.date | None = DateParam(),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """질문 원문 검색 (최근순). 사용자는 별칭으로만 보인다."""
    needle = "".join(q.lower().split())
    rows = [
        r for r in _range(start, end)
        if (not route or r.route == route)
        and (not needle or needle in "".join(r.question.lower().split()))
    ]
    rows.reverse()
    page = rows[offset: offset + limit]
    return QuestionPage(
        total=len(rows),
        items=[QuestionRow(ts=r.ts.strftime("%Y-%m-%d %H:%M"), user=r.user, route=r.route,
                           handled_by=r.handled_by, topic=r.topic, question=r.question) for r in page],
    )


@app.get("/api/suggestions", response_model=SuggestionReport, dependencies=guard)
def suggestions(
    start: datetime.date | None = DateParam(),
    end: datetime.date | None = DateParam(),
    limit: int = Query(default=10, ge=1, le=50),
):
    """키워드가 못 잡은 질문을 묶어 'FAQ 보완 후보'로 보여준다.

    봇의 일일 리포트(digest.analyze)와 같은 계산이다. 여기서도 제안만 하고
    faq.md는 고치지 않는다 — 잘못된 키워드 하나가 조용히 오답을 만들기 때문이다.
    """
    analyzed, n_questions = _analyze_cached(start, end, str(config.MISS_LOG_FILE), _stamp(config.MISS_LOG_FILE), _stamp(config.FAQ_FILE))
    items = [
        Suggestion(
            count=s["count"],
            sample=s["sample"],
            others=s["all"][1:4],
            nearest_entry=s["entry"] if s["entry"] and s["score"] >= _min_nearest() else None,
            score=round(float(s["score"]), 2),
            keywords=s["keywords"],
        )
        for s in analyzed[:limit]
    ]
    return SuggestionReport(questions=n_questions, groups=len(analyzed), items=items)


def _stamp(path) -> tuple:
    """파일이 바뀌었는지 판단할 표식 (수정시각, 크기). 없으면 (0, 0)."""
    try:
        st = path.stat()
        return (st.st_mtime_ns, st.st_size)
    except FileNotFoundError:
        return (0, 0)


def _min_nearest() -> float:
    import digest  # 봇 모듈

    return digest.MIN_NEAREST


@lru_cache(maxsize=32)
def _analyze_cached(start, end, _miss_path, _miss_stamp, _faq_stamp):
    """질문 묶기는 문자열 유사도를 전부 비교해서 수 초가 걸린다 (봇은 하루 한 번이라 괜찮다).
    현황판은 기간을 바꿀 때마다 부르므로, 로그·faq.md가 그대로면 이전 결과를 재사용한다.
    파일 표식(_miss_stamp, _faq_stamp)이 캐시 키에 들어가 있어 파일이 바뀌면 다시 계산한다."""
    import digest  # 봇 모듈

    misses = [
        m for m in logs.read_misses()
        if (start is None or m[0].date() >= start) and (end is None or m[0].date() <= end)
    ]
    return digest.analyze(misses, _faq_entries()), len(misses)


@app.get("/api/faq", response_model=FaqInfo, dependencies=guard)
def faq():
    """FAQ 규모: 현재 항목 수, 카테고리별 항목 수, 날짜별 항목 수 추이."""
    entries = _faq_entries()
    cats = Counter(e.category or "(미분류)" for e in entries)
    history = []
    if config.FAQ_HISTORY_FILE.exists():
        history = json.loads(config.FAQ_HISTORY_FILE.read_text(encoding="utf-8"))
    return FaqInfo(
        entries=len(entries),
        categories=[{"category": c, "entries": n} for c, n in cats.items()],
        history=history,
    )
