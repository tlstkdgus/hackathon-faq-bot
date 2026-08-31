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

from digest import DEADLINES, REMIND_DAYS, RESOLVED, build_report, deadline_notes, stale_notice

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
    """마감 전에는 뜨지 않는다. 아직 유효한 안내를 고치라고 하면 안 된다.

    기준 날짜를 DEADLINES에서 끌어온다. 날짜를 박아두면 더 이른 마감이
    추가될 때마다 무고하게 실패한다 (실제로 가비아 8/14를 넣자 깨졌다).
    """
    earliest = min(when for when, _, _ in DEADLINES)
    assert deadline_notes(earliest - datetime.timedelta(days=1)) == []


# 알림 동작을 시험하려면 '아직 문구를 안 고친 마감'이 하나는 있어야 한다.
# 그걸 실제 표에서 끌어오면 마감을 RESOLVED로 옮길 때마다 테스트가 무고하게
# 깨진다 — 8/17, 8/20, 8/21에 이어 **행사가 끝나 전부 반영한 날 또 깨졌다**
# (그때는 남은 마감이 0개라 StopIteration).
#
# 알림 로직은 표에 뭐가 들어 있든 똑같이 동작해야 하므로, 표를 읽지 않고
# 시험용 마감을 넣어 본다. 이제 어떤 마감을 반영 표시해도 깨지지 않는다.
# 날짜를 2099년으로 두는 이유: 실제 마감과 REMIND_DAYS 안에서 겹치면
# 리포트에 함께 실려 검사가 흔들린다.
# 둘이 **같은 항목**을 가리킨다. 한 항목에 마감이 두 번 걸리는 경우
# (가장 최근 것만 알린다)를 검사해야 하기 때문이다.
# '부스 꾸미기'를 쓰는 이유: faq.md에 실재하면서 실제 마감 표에는
# 걸려 있지 않아, 진짜 마감과 섞여 검사가 흔들리지 않는다.
_FIXTURE = [
    (D(2099, 1, 1), "시험용 마감 A", "부스 꾸미기"),
    (D(2099, 1, 3), "시험용 마감 B", "부스 꾸미기"),
]
for _e in _FIXTURE:
    if _e not in DEADLINES:
        DEADLINES.append(_e)


def _pending():
    """알림이 떠야 하는 시험용 마감."""
    return _FIXTURE[0]


def test_shows_on_the_day():
    when, what, targets = _pending()
    got = _joined(when)
    assert what in got
    assert "오늘" in got
    first_target = targets.split("/")[0].strip()
    assert first_target in got, "고쳐야 할 항목이 함께 나와야 한다"


def test_shows_within_remind_window():
    when, what, _ = _pending()
    got = _joined(when + datetime.timedelta(days=REMIND_DAYS))
    assert what in got
    assert f"{REMIND_DAYS}일 지남" in got


def test_quiet_after_remind_window():
    """계속 뜨면 리포트가 시끄러워지고 진짜 알림을 덮는다."""
    when, what, _ = _pending()
    got = _joined(when + datetime.timedelta(days=REMIND_DAYS + 1))
    assert what not in got


def test_multiple_deadlines_on_same_day():
    """가까운 마감이 겹치면 한 리포트에 둘 다 보여야 한다.

    날짜를 박지 않고 표에서 끌어온다. 마감을 RESOLVED로 옮길 때마다
    무고하게 실패하기 때문이다 (8/20 멘토링과 8/21 제출 마감을 옮길 때
    각각 깨졌다).
    """
    pending = [(w, x) for w, x, _ in DEADLINES if (w, x) not in RESOLVED]
    assert len(pending) >= 2, "미반영 마감이 2개 미만이라 검사할 수 없다"
    # 시험용 마감 두 개가 항상 들어 있으므로 표가 다 반영돼도 검사할 수 있다.
    # REMIND_DAYS 안에 함께 걸리는 두 마감을 찾는다
    pair = next(
        ((a, b) for a in pending for b in pending
         if a[0] < b[0] <= a[0] + datetime.timedelta(days=REMIND_DAYS)),
        None,
    )
    assert pair, "가까운 마감 쌍이 없다"
    (_, first), (later, second) = pair
    got = _joined(later)
    assert first in got and second in got, got


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
    """2000자를 넘으면 뒤가 잘리므로 마감 알림이 맨 위에 있어야 한다.

    기준 날짜를 박아두면 그 마감을 RESOLVED로 옮길 때마다 무고하게 실패한다
    (8/21 제출 마감을 반영 표시하자 실제로 깨졌다). 표에서 끌어온다.
    """
    when, what, _ = _pending()
    notes = deadline_notes(when)
    assert notes, f"{when}에는 알림이 있어야 한다"
    assert notes[0].startswith("⏰"), notes[0]


# ── 학생 답변에 붙는 경고 (stale_notice) ─────────────────────────

def test_no_notice_before_or_on_the_day():
    """마감 당일까지는 안내가 아직 유효하다. 경고를 붙이면 틀린 말이 된다."""
    when, what, targets = _pending()
    title = targets.split("/")[0].strip()
    assert what not in stale_notice(title, when - datetime.timedelta(days=1))
    assert what not in stale_notice(title, when)


def test_notice_after_the_day():
    when, what, targets = _pending()
    title = targets.split("/")[0].strip()
    got = stale_notice(title, when + datetime.timedelta(days=1))
    assert f"{when.month}/{when.day}" in got and what in got, got
    assert got.endswith("\n\n"), "답변 본문과 줄이 붙으면 안 된다"


def test_notice_never_expires():
    """운영진 알림(REMIND_DAYS)과 달리 계속 떠야 한다.

    마감이 지났다는 사실은 시간이 지나도 변하지 않고,
    그 사이에도 학생은 같은 질문을 한다.
    """
    when, _, target = _pending()
    long_after = when + datetime.timedelta(days=REMIND_DAYS + 30)
    assert stale_notice(target, long_after) != ""


def test_notice_picks_most_recent_deadline():
    """한 항목이 여러 마감에 걸리면 가장 최근 것을 알린다.

    실제 표에서 끌어오면 그 마감들을 반영 표시할 때 깨진다
    ('가비아 서버'가 8/14·8/28 두 번 걸렸는데, 둘 다 반영하자 깨졌다).
    시험용 마감 두 개가 같은 항목을 가리키게 해두고 본다.
    """
    (early, first, target), (late, second, _) = _FIXTURE
    got = stale_notice(target, late + datetime.timedelta(days=1))
    assert second in got, got
    assert first not in got, got


def test_unrelated_entry_gets_nothing():
    """마감과 무관한 항목에 경고가 붙으면 멀쩡한 답변이 의심스러워진다."""
    for title in ("식사", "와이파이", "위치 교통"):
        assert stale_notice(title, D(2026, 9, 30)) == ""


def test_notice_targets_exist_in_faq():
    """경고가 붙을 항목 제목이 faq.md에 실제로 있어야 한다.

    (deadline_notes와 같은 표를 쓰므로 한 번 더 확인하는 셈이지만,
     stale_notice는 제목 완전일치로 찾기 때문에 여기서도 고정해둔다.)
    """
    from faq_engine import load_faq
    from paths import FAQ_FILE

    titles = {e.title for e in load_faq(str(FAQ_FILE))}
    hit = [t for _, _, targets in DEADLINES
           for t in (x.strip() for x in targets.split("/")) if t in titles]
    assert hit, "DEADLINES의 항목이 하나도 faq.md와 안 맞는다"


# ── 반영 완료 표시 (RESOLVED) ────────────────────────────────────

def test_resolved_entries_exist_in_deadlines():
    """RESOLVED에 오타가 있으면 조용히 안 걸린다.

    (날짜, 설명) 문자열을 손으로 옮겨 적는 구조라 오타가 나기 쉽고,
    틀리면 '표시했는데 알림이 계속 뜨는' 상태가 된다.
    """
    known = {(when, what) for when, what, _ in DEADLINES}
    unknown = [r for r in RESOLVED if r not in known]
    assert not unknown, f"DEADLINES에 없는 항목을 RESOLVED에 적었다: {unknown}"


def test_resolved_stops_both_alerts():
    """문구를 고쳤으면 운영진 알림과 학생 경고가 둘 다 멈춰야 한다."""
    for when, what in RESOLVED:
        day = when + datetime.timedelta(days=1)
        assert what not in _joined(day), f"운영진 알림이 계속 뜬다: {what}"
        targets = next(t for w, x, t in DEADLINES if (w, x) == (when, what))
        for title in (x.strip() for x in targets.split("/")):
            got = stale_notice(title, day)
            assert what not in got, f"학생 경고가 계속 뜬다: {title} -> {got}"


def test_unresolved_still_alerts():
    """RESOLVED가 다른 마감까지 덮으면 안 된다."""
    pending = [(w, x) for w, x, _ in DEADLINES if (w, x) not in RESOLVED]
    assert pending, "표에 미반영 마감이 하나도 없다 (테스트가 의미를 잃었다)"
    when, what = pending[0]
    assert what in _joined(when)


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
