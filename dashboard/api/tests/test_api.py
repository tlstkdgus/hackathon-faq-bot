# -*- coding: utf-8 -*-
"""
현황판 API 회귀 테스트.

봇에서 실제로 겪은 문제를 그대로 고정한다:
    - 구(3칸)/신(4칸) 로그 형식이 섞여 있어도 둘 다 집계해야 한다
    - 형식이 깨진 줄은 버리되, 몇 줄 버렸는지는 드러나야 한다
    - 디스코드 사용자 ID가 응답에 그대로 나가면 안 된다

실행 (저장소 루트에서):  python -m pytest dashboard/api/tests -q
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dashboard/api

from app import config, logs, main  # noqa: E402

RAW_ID = "111122223333444455"

STATS = "\n".join([
    # 구 형식(원문 없음) 3칸
    f"2026-08-18 09:00:00\t{RAW_ID}\thit:시연 영상",
    # 신 형식 4칸
    f"2026-08-18 10:30:00\t{RAW_ID}\thit:시연 영상\t시연 영상 몇 분까지예요?",
    "2026-08-18 21:05:00\t999\topenai\t예선 결과 어디서 확인해요?",
    "2026-08-20 13:00:00\t888\tnomatch\t와이파이 비번",
    # 깨진 줄 (칸 수가 안 맞음)
    "2026-08-20 13:00:00\t888",
    "",
]) + "\n"

MISSES = "\n".join([
    "2026-08-18 21:05:00\t[openai]\t999\t예선 결과 어디서 확인해요?",
    "2026-08-19 08:00:00\t[openai]\t777\t예선 결과 어디서 확인하나요",
    "2026-08-20 13:00:00\t[nomatch]\t888\t와이파이 비번",
    # 사용자ID가 없던 시절 3칸
    "2026-08-20 14:00:00\t[openai]\t커피 사서 들고갈 수 있어?",
]) + "\n"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    (tmp_path / "stats.log").write_text(STATS, encoding="utf-8")
    (tmp_path / "unanswered.log").write_text(MISSES, encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "STATS_LOG_FILE", tmp_path / "stats.log")
    monkeypatch.setattr(config, "MISS_LOG_FILE", tmp_path / "unanswered.log")
    monkeypatch.setattr(main, "ACCESS_TOKEN", "")
    return TestClient(main.app)


def test_mixed_formats_are_counted_and_broken_lines_reported(client):
    s = client.get("/api/summary").json()
    assert s["total"] == 4                       # 3칸 1줄 + 4칸 3줄
    assert (s["faq"], s["llm"], s["nomatch"]) == (2, 1, 1)
    assert s["faq_rate"] == 0.5
    assert s["unique_users"] == 3
    assert client.get("/api/health").json()["skipped_lines"] == 1


def test_raw_user_id_never_leaves_the_api(client):
    for path in ["/api/summary", "/api/questions?limit=200", "/api/suggestions", "/api/daily"]:
        assert RAW_ID not in client.get(path).text
    users = {row["user"] for row in client.get("/api/questions").json()["items"]}
    assert all(u.startswith("U-") for u in users)


def test_daily_fills_empty_days(client):
    rows = client.get("/api/daily").json()
    assert [r["date"] for r in rows] == ["2026-08-18", "2026-08-19", "2026-08-20"]
    assert rows[1]["total"] == 0                 # 질문이 없던 날도 0으로 남는다
    assert rows[0] == {"date": "2026-08-18", "total": 3, "faq": 2, "llm": 1, "nomatch": 0}


def test_date_range_filter(client):
    s = client.get("/api/summary?start=2026-08-20&end=2026-08-20").json()
    assert s["total"] == 1 and s["nomatch"] == 1
    assert client.get("/api/summary?start=2026-08-21&end=2026-08-20").status_code == 400


def test_question_search_ignores_spaces_and_filters_route(client):
    page = client.get("/api/questions?q=예선결과").json()
    assert page["total"] == 1 and page["items"][0]["route"] == "llm"
    page = client.get("/api/questions?route=faq").json()
    assert page["total"] == 2
    # 최근순
    assert page["items"][0]["ts"] == "2026-08-18 10:30"


def test_suggestions_group_similar_questions(client):
    rep = client.get("/api/suggestions").json()
    assert rep["questions"] == 4
    top = rep["items"][0]
    assert top["count"] == 2                     # '예선 결과 어디서 확인…' 두 건이 한 묶음
    assert "예선 결과" in top["sample"]


def test_hourly_has_24_buckets(client):
    rows = client.get("/api/hourly").json()
    assert len(rows) == 24 and sum(r["total"] for r in rows) == 4


def test_token_is_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(main, "ACCESS_TOKEN", "secret")
    assert client.get("/api/summary").status_code == 401
    assert client.get("/api/summary", headers={"X-Dashboard-Token": "secret"}).status_code == 200
    assert client.get("/api/health").status_code == 200  # 헬스체크는 열어 둔다


def test_sample_data_matches_retrospective(monkeypatch):
    """예시 데이터는 RETROSPECTIVE.md의 실제 집계와 맞아야 한다."""
    sample = Path(__file__).resolve().parents[2] / "sample-data"
    monkeypatch.setattr(config, "STATS_LOG_FILE", sample / "stats.log")
    monkeypatch.setattr(config, "MISS_LOG_FILE", sample / "unanswered.log")
    monkeypatch.setattr(main, "ACCESS_TOKEN", "")
    s = TestClient(main.app).get("/api/summary").json()
    assert (s["total"], s["faq"], s["llm"], s["nomatch"], s["unique_users"]) == (229, 185, 44, 0, 53)
    assert round(s["faq_rate"] * 100, 1) == 80.8
    assert s["busiest_day"] == "2026-08-18" and s["busiest_day_count"] == 40
