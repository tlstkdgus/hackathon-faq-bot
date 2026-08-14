# -*- coding: utf-8 -*-
"""
test_stats_logging.py — 질문 기록/집계 회귀 테스트.

왜 필요한가:
    로그 형식을 바꿀 때마다 "예전 줄이 조용히 버려지는" 사고가 반복됐다.
    형식이 안 맞는 줄은 에러 없이 skip되기 때문에, 통계가 0으로 나오거나
    리포트가 "미답변 없음"으로 나가도 아무도 이상하다고 느끼지 못한다.
    (digest._parse_line에서 한 번, collect_stats에서 또 한 번 겪었다.)

    그래서 '구 형식 + 신 형식이 섞인 로그'를 항상 읽을 수 있는지 고정해둔다.

실행:
    python test_stats_logging.py     # 외부 패키지 필요 없음
    pytest test_stats_logging.py

discord 의존성 없음.
"""

import importlib
import os
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))


def _fresh(tmpdir: str):
    """DATA_DIR을 임시 폴더로 두고 paths/stats_engine을 다시 읽어온다.

    paths.py가 import 시점에 DATA_DIR을 상수로 굳히므로 reload가 필요하다.
    """
    os.environ["DATA_DIR"] = tmpdir
    import paths
    importlib.reload(paths)
    import stats_engine
    return importlib.reload(stats_engine)


# ── 기록 ─────────────────────────────────────────────────────────

def test_log_usage_writes_question():
    with tempfile.TemporaryDirectory() as d:
        se = _fresh(d)
        se.log_usage(111, "hit:식사", "밥 주나요?")
        line = Path(se.STATS_LOG_FILE).read_text(encoding="utf-8").rstrip("\n")
        parts = line.split("\t")
        assert len(parts) == 4, f"4칸이어야 한다: {parts}"
        assert parts[1] == "111"
        assert parts[2] == "hit:식사"
        assert parts[3] == "밥 주나요?"


def test_newline_and_tab_are_flattened():
    """줄바꿈·탭이 그대로 들어가면 로그 한 줄이 깨져 이후 파싱이 전부 어긋난다."""
    with tempfile.TemporaryDirectory() as d:
        se = _fresh(d)
        se.log_usage(111, "nomatch", "첫 줄\n둘째\t줄")
        body = Path(se.STATS_LOG_FILE).read_text(encoding="utf-8")
        assert body.count("\n") == 1, "질문 안의 줄바꿈이 새 줄을 만들었다"
        assert body.rstrip("\n").split("\t")[3] == "첫 줄 둘째 줄"


def test_log_usage_without_question_still_works():
    """question 인자를 안 넘겨도 죽지 않아야 한다 (기존 호출 호환)."""
    with tempfile.TemporaryDirectory() as d:
        se = _fresh(d)
        se.log_usage(111, "hit:식사")
        assert Path(se.STATS_LOG_FILE).read_text(encoding="utf-8").rstrip("\n").split("\t")[3] == ""


# ── 집계 (구/신 형식 혼재) ───────────────────────────────────────

def _mixed_log(se):
    """원문 없던 3칸 줄과 원문 있는 4칸 줄을 섞어 쓴다."""
    Path(se.STATS_LOG_FILE).write_text(
        "2026-08-01 10:00:00\t111\thit:식사\n"              # 구 형식
        "2026-08-02 10:00:00\t222\tnomatch\n"               # 구 형식
        "2026-08-03 10:00:00\t111\thit:식사\t밥 주나요?\n"   # 신 형식
        "2026-08-04 10:00:00\t333\topenai\t가비아 서버 신청\n"
        "깨진 줄\n",                                          # 버려져야 함
        encoding="utf-8",
    )


def test_collect_stats_reads_old_and_new_lines():
    with tempfile.TemporaryDirectory() as d:
        se = _fresh(d)
        _mixed_log(se)
        s = se.collect_stats()
        assert s["total"] == 4, f"구 형식이 버려졌다: {s}"
        assert s["unique_users"] == 3
        assert s["hit"] == 2
        assert s["nomatch"] == 1
        assert s["claude"] == 1          # 백엔드가 답한 건수
        assert s["top_topics"][0] == ("식사", 2)


def test_search_reads_old_and_new_lines():
    with tempfile.TemporaryDirectory() as d:
        se = _fresh(d)
        _mixed_log(se)
        rows = se.search_questions()
        assert len(rows) == 4, f"구 형식이 버려졌다: {rows}"
        # 최근 것이 위로
        assert rows[0][3] == "가비아 서버 신청"
        # 원문이 없던 줄은 빈 문자열로 오되 목록에서 사라지면 안 된다
        assert any(q == "" for _, _, _, q in rows)


def test_search_keyword_filters():
    with tempfile.TemporaryDirectory() as d:
        se = _fresh(d)
        _mixed_log(se)
        rows = se.search_questions("가비아")
        assert len(rows) == 1 and rows[0][2] == "333"
        # 공백을 무시하고 비교한다
        assert len(se.search_questions("가비아 서버")) == 1


def test_missing_question_text_is_labeled():
    """원문이 없는 옛 기록을 빈칸으로 보여주면 '질문을 안 했다'처럼 읽힌다."""
    with tempfile.TemporaryDirectory() as d:
        se = _fresh(d)
        _mixed_log(se)
        out = se.format_questions_plain(se.search_questions())
        assert "원문 미기록" in out


def test_misses_only_reads_unanswered_log():
    with tempfile.TemporaryDirectory() as d:
        se = _fresh(d)
        se.log_miss("피그마 링크 주세요", "nomatch", 444)
        se.log_usage(111, "hit:식사", "밥 주나요?")
        misses = se.search_questions(misses_only=True)
        assert len(misses) == 1 and misses[0][3] == "피그마 링크 주세요"
        assert len(se.search_questions()) == 1  # stats.log 쪽은 따로


def _cleanup():
    os.environ.pop("DATA_DIR", None)


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"[OK ] {name}")
        except AssertionError as e:
            failed.append(name)
            print(f"[FAIL] {name}: {e}")
    _cleanup()
    print(f"\n=== {len(tests) - len(failed)}/{len(tests)} 통과 ===")
    sys.exit(1 if failed else 0)
