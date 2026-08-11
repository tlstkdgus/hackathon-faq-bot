# -*- coding: utf-8 -*-
"""
test_faq_matching.py — faq.md 매칭 회귀 테스트.

왜 필요한가:
    키워드를 하나 추가하면 그 키워드가 인접 주제의 질문까지 끌어갈 수 있다.
    실제로 `감점`을 노코드 항목에 넣었더니 "AI 안 쓰면 감점인가요?"가
    노코드 답변을 받은 적이 있다. 오답이 나가도 아무도 모른다는 게 문제라,
    자주 나오는 질문의 목적지를 여기 고정해둔다.

실행:
    python test_faq_matching.py      # 외부 패키지 필요 없음
    pytest test_faq_matching.py      # pytest가 있으면 이것도 동작

faq.md를 고친 뒤 이걸 돌리면 기존 라우팅이 깨졌는지 바로 알 수 있다.
"""

import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from faq_engine import _normalize, find_answer, load_faq, topic_list
from paths import FAQ_FILE

ENTRIES = load_faq(str(FAQ_FILE))

# 항목 수는 계속 늘어나므로 정확한 값을 박지 않는다 (박으면 항목을 추가할
# 때마다 무고한 실패가 난다). 파싱이 통째로 깨지는 것만 잡는 하한선.
MIN_ENTRIES = 60

# 이미 여러 항목에 걸쳐 있는 키워드. 새로 늘어나면 테스트가 실패한다.
# 여기 있는 것들은 동점 처리(find_answer가 None 반환)로 안전하게 넘어가거나
# 길이 가중으로 갈리는 게 확인된 것들이다. 추가할 땐 왜 안전한지 함께 적을 것.
KNOWN_DUPLICATE_KEYWORDS = {
    "라운드",        # 일정 / 본선 토너먼트
    "명찰",          # 등록 출입 / 준비물
    "트랙qna",       # SJF 트랙 QnA / AAC 트랙 QnA
    "트랙큐앤에이",  # 위와 같음
    "트랙변경",      # 트랙 선택 / 트랙 변경
}


# ── 파싱 기본 ────────────────────────────────────────────────────

def test_entries_loaded():
    assert len(ENTRIES) >= MIN_ENTRIES, f"항목이 {len(ENTRIES)}개뿐 — 파싱이 깨졌을 수 있다"


def test_every_entry_has_keywords_and_answer():
    for e in ENTRIES:
        assert e.title.strip(), "제목이 빈 항목이 있다"
        assert e.keywords, f"'{e.title}'에 키워드가 없다"
        assert e.answer.strip(), f"'{e.title}'에 답변이 없다"


def test_entries_are_categorized():
    """모든 항목이 `# 카테고리` 아래에 있어야 /해커톤주제 목록이 깔끔하다."""
    uncategorized = [e.title for e in ENTRIES if not e.category]
    assert not uncategorized, f"카테고리 없는 항목: {uncategorized}"


def test_titles_unique():
    titles = [e.title for e in ENTRIES]
    dupes = {t for t in titles if titles.count(t) > 1}
    assert not dupes, f"제목이 중복된 항목: {dupes}"


def test_topic_list_fits_discord_limit():
    """/해커톤주제 출력은 clip()으로 잘리지만, 통째로 잘리면 쓸모가 없다."""
    assert len(topic_list(ENTRIES)) < 2000 * 2, "주제 목록이 너무 길어졌다 — 표시 방식을 손봐야 한다"


# ── 키워드 충돌 ──────────────────────────────────────────────────

def test_no_new_duplicate_keywords():
    """같은 키워드가 여러 항목에 있으면 그 질문의 답이 불안정해진다."""
    owners = defaultdict(set)
    for e in ENTRIES:
        for k in e.keywords:
            owners[_normalize(k)].add(e.title)

    dupes = {k: v for k, v in owners.items() if len(v) > 1}
    unexpected = {k: sorted(v) for k, v in dupes.items() if k not in KNOWN_DUPLICATE_KEYWORDS}
    assert not unexpected, (
        "새로 중복된 키워드가 생겼다. 한쪽을 더 구체적으로 바꾸거나, "
        f"안전한 이유를 적고 KNOWN_DUPLICATE_KEYWORDS에 추가할 것: {unexpected}"
    )


# ── 라우팅 ───────────────────────────────────────────────────────

# (질문, 기대하는 항목 제목). None이면 "키워드로 판단 불가 → LLM에 넘겨야 함".
ROUTING = [
    # 자주 나오는 기본 질문
    ("밥 주나요?", "식사"),
    ("와이파이 비번 뭐예요", "와이파이"),
    ("시연 영상 몇 분이에요?", "시연 영상"),
    ("부스 벽 사이즈 알려주세요", "부스 벽 사이즈"),
    ("세션 신청 어떻게 해요?", "1대1 세션"),
    ("상금 얼마예요?", "상금 시상"),
    ("몇 시에 끝나요?", "행사 종료 시간"),
    ("주차 되나요?", "주차"),
    # 장소 질문은 여러 표현으로 들어온다. '어디예요' 같은 의문형 조각을
    # 키워드에서 뺀 뒤에도 이들이 계속 잡히는지 확인한다.
    ("장소 어디예요?", "위치 교통"),
    ("행사장 어디예요", "위치 교통"),
    ("해커톤 어디서 해요?", "위치 교통"),
    ("오는 길 알려주세요", "위치 교통"),
    ("마곡나루역에서 몇 분 걸려요", "위치 교통"),
    # 범용 키워드가 엉뚱한 곳으로 끌고 가지 않는지 (실제 사고 이력)
    ("AI 안 쓰면 감점인가요?", "개발 요건"),
    # 트랙 QnA 분기
    ("MCM 타깃 고객이 누구예요?", "SJF 트랙 QnA"),
    ("합성 데이터로 검증해도 되나요?", "SJF 트랙 QnA"),
    ("고객 데이터 제공되나요?", "AAC 트랙 QnA"),
    ("더미 데이터 써도 되나요?", "AAC 트랙 QnA"),
    ("추천 로직 알려주세요", "AAC 트랙 QnA"),
    # 데이터/인프라 항목
    ("매장 평면도 받을 수 있나요?", "SJF 데이터 활용"),
    ("재고 이동 가능한가요?", "SJF 데이터 활용"),
    # 키워드만으로는 판단할 수 없는 질문은 찍지 않고 LLM에 넘긴다.
    # '부스'(부스 운영)와 '도면'(부스 벽 사이즈)이 모든 지표에서 동점이다.
    # 이 케이스는 'SJF 데이터 활용'의 '매장도면'이 가로채지 않는지도 함께 본다.
    ("부스 도면 있어요?", None),
]


def test_routing():
    wrong = []
    for question, expected in ROUTING:
        got = find_answer(question, ENTRIES)
        title = got.title if got else None
        if title != expected:
            wrong.append(f"{question!r}: 기대 {expected!r} → 실제 {title!r}")
    assert not wrong, "라우팅이 바뀌었다:\n  " + "\n  ".join(wrong)


def test_unrelated_question_goes_to_llm():
    """FAQ와 무관한 질문은 억지로 답하지 말고 LLM에 넘겨야 한다.

    아래 두 개는 예전에 `위치 교통`이 가로채서 행사장 주소를 답했다.
    `어디예요` / `어디로` 같은 의문형 조각이 키워드로 들어가 있었기 때문이다.
    다친 사람을 묻는 질문에 주소가 나가는 건 특히 나쁘다
    (구급약품 안내는 `그라운드 룰` 항목에 있다).
    """
    for q in [
        "반려동물 데려가도 되나요",
        "여기서 제일 가까운 병원 어디예요",
        "다친 사람 있으면 어디로 가요",
    ]:
        assert find_answer(q, ENTRIES) is None, f"{q!r}에 엉뚱한 답이 붙었다"


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    print(f"faq.md: {len(ENTRIES)}개 항목\n")
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
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
