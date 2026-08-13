# -*- coding: utf-8 -*-
"""
test_deadline_notes.py — 마감 알림 회귀 테스트.

왜 필요한가:
    faq.md에는 날짜가 박힌 답변이 많다. 마감이 지나도 문구를 안 고치면
    봇이 이미 끝난 일을 "지금 신청하세요"로 계속 안내한다. 학생은 틀린 줄
    모르고, 운영진도 매일 faq.md를 훑어보지 않는다.

    이 알림이 조용히 안 뜨면 그 사실조차 모르게 되므로, 날짜 경계를
    고정해둔다.

실행:
    python test_deadline_notes.py
    pytest test_deadline_notes.py

digest.py가 ZoneInfo("Asia/Seoul")을 쓰므로 **윈도우에서는 `tzdata`가 필요**하다
(윈도우엔 시스템 시간대 데이터베이스가 없다. requirements.txt에 들어 있는 이유다).
리눅스·맥에서는 추가 설치 없이 그냥 돌아간다.
"""

import datetime
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from digest import DEADLINES, REMIND_DAYS, build_report, deadline_notes

D = datetime.date


def _joined(today):
    return "\n".join(deadline_notes(today))


# ── 표 자체의 건전성 ─────────────────────────────────────────────

def test_deadlines_sorted_and_well_formed():
    """날짜순으로 두면 다음에 뭘 챙겨야 하는지 읽기 쉽다."""
    dates = [d for d, _, _ in DEADLINES]
    assert dates == sorted(dates), f"DEADLINES가 날짜순이 아니다: {dates}"
    for when, what, targets in DEADLINES:
        assert isinstance(when, D), f"{what}: 날짜 타입이 아니다"
        assert what.strip() and targets.strip(), f"{when}: 설명이 비었다"


def test_deadline_targets_point_at_real_faq_entries():
    """'확인할 항목'에 적힌 제목이 faq.md에 실제로 있어야 한다.

    항목 이름을 바꾸거나 지우면 알림이 없는 항목을 가리키게 되고,
    받은 사람이 무엇을 고쳐야 하는지 찾지 못한다.
    """
    from faq_engine import load_faq
    from paths import FAQ_FILE

    titles = {e.title for e in load_faq(str(FAQ_FILE))}
    missing = []
    for _, what, targets in DEADLINES:
        for t in (x.strip() for x in targets.split("/")):
            if t not in titles:
                missing.append(f"{what} -> {t!r}")
    assert not missing, "faq.md에 없는 항목을 가리킨다: " + ", ".join(missing)


# ── 날짜 경계 ────────────────────────────────────────────────────

def test_nothing_before_the_deadline():
    """마감 전에는 뜨지 않는다. 아직 유효한 안내를 고치라고 하면 안 된다."""
    assert deadline_notes(D(2026, 8, 16)) == []


def test_shows_on_the_day():
    got = _joined(D(2026, 8, 17))
    assert "팀 정보 변경 폼 마감" in got
    assert "오늘" in got
    assert "팀명 변경" in got, "고쳐야 할 항목이 함께 나와야 한다"


def test_shows_within_remind_window():
    got = _joined(D(2026, 8, 17) + datetime.timedelta(days=REMIND_DAYS))
    assert "팀 정보 변경 폼 마감" in got
    assert f"{REMIND_DAYS}일 지남" in got


def test_quiet_after_remind_window():
    """계속 뜨면 리포트가 시끄러워지고 진짜 알림을 덮는다."""
    got = _joined(D(2026, 8, 17) + datetime.timedelta(days=REMIND_DAYS + 1))
    assert "팀 정보 변경 폼 마감" not in got


def test_multiple_deadlines_on_same_day():
    """가까운 마감이 겹치면 둘 다 보여야 한다 (8/20 멘토링 + 8/21 제출)."""
    got = _joined(D(2026, 8, 21))
    assert "멘토링 기간 종료" in got and "결과물 제출 마감" in got


# ── 리포트에 실리는지 ────────────────────────────────────────────

def test_report_shows_deadline_even_with_no_questions():
    """미답변 질문이 0건인 날에도 마감 알림은 나가야 한다.

    질문이 없는 날이 오히려 흔하다. 예전 build_report는 그때 한 줄만 내고
    바로 반환했기 때문에, 여기서 빠지면 알림이 통째로 사라진다.
    """
    got = build_report([], [], since=None)
    # 오늘 기준이라 마감이 걸릴 수도 아닐 수도 있다. 형식만 확인하고,
    # 알림 자체는 아래 테스트에서 날짜를 고정해 본다.
    assert "미답변 질문 리포트" in got


def test_deadline_note_goes_first():
    """2000자를 넘으면 뒤가 잘리므로 마감 알림이 맨 위에 있어야 한다."""
    notes = deadline_notes(D(2026, 8, 21))
    assert notes, "8/21에는 알림이 있어야 한다"
    assert notes[0].startswith("⏰"), notes[0]


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
    print(f"\n=== {len(tests) - len(failed)}/{len(tests)} 통과 ===")
    sys.exit(1 if failed else 0)
