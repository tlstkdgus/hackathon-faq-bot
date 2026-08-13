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
    """/해커톤주제 출력이 디스코드 2000자를 넘으면 안 된다.

    넘으면 bot.clip()이 뒤를 잘라내는데, 학생 입장에서는 마지막 카테고리들이
    목록에 아예 없는 것처럼 보이고 잘렸다는 사실도 알 수 없다.
    항목이 늘어나 이 선을 넘으면 표시 방식을 바꿔야 한다
    (카테고리별로 나눠 보내거나, 제목만 쉼표로 잇기 등).
    """
    got = len(topic_list(ENTRIES))
    assert got < 2000, f"주제 목록이 {got}자 — 2000자를 넘어 뒤가 잘린다"


# ── 키워드 충돌 ──────────────────────────────────────────────────

def test_no_new_single_char_keywords():
    """1글자 키워드는 그것만 걸려도 MIN_SCORE(1.0)를 통과한다.

    흔한 단어의 일부로 걸리면 엉뚱한 답이 나간다. 실제로 이런 게 있었다.

        '상'(상금 시상) <- "7인 이상 가능해요?"
        '술'(그라운드 룰) <- "예술 분야 주제도 되나요"
        '차'(주차)      <- "절차 알려주세요"

    아래 목록은 남겨둔 것들이다. 다른 항목에 더 긴 키워드가 있어서
    실제 질문에서는 밀리는 게 확인됐다. 새로 추가하려면 정말 필요한지
    다시 보고, 넣는다면 여기에도 함께 적을 것.
    """
    allowed = {"덱", "돈", "밥", "앱", "웹", "잠", "짐", "툴", "팀"}
    found = {}
    for e in ENTRIES:
        for k in e.keywords:
            n = _normalize(k)
            if len(n) == 1 and n not in allowed:
                found.setdefault(n, []).append(e.title)
    assert not found, (
        "1글자 키워드가 새로 생겼다. 두 글자 이상으로 바꾸거나, "
        f"안전한 이유를 확인하고 allowed에 추가할 것: {found}"
    )


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
    # 다치거나 아플 때 — 구급약품 안내는 '그라운드 룰'에 있다.
    # 예전에는 '위치 교통'이 가로채 행사장 주소를 답했다.
    ("다친 사람 있으면 어디로 가요", "그라운드 룰"),
    ("구급약 있어요?", "그라운드 룰"),
    # 1글자 키워드가 흔한 단어의 일부로 걸리지 않는지.
    # '상'(상금 시상)이 "7인 이상"을, '술'(그라운드 룰)이 "예술"을,
    # '차'(주차)가 "절차"를 끌어가던 것을 정리했다.
    ("7인 이상 가능해요?", "팀 빌딩"),
    ("제출 절차 알려주세요", "제출 항목"),
    ("기술 스택 제한 있어요?", "개발 요건"),
    ("1차 예선 언제예요?", "서류 심사"),
    # "해커톤 언제예요"가 전 항목 0점으로 아무데도 안 걸리던 것을 고쳤다.
    # '언제'는 여러 주제에 걸치는 말이라 단독으로 넣지 않고, 주제어를 붙인
    # 복합 키워드(해커톤언제/행사언제/대회언제)로만 잡는다.
    ("해커톤 언제예요", "일정"),
    ("해커톤 언제 해요?", "일정"),
    ("행사 언제인가요", "일정"),
    ("대회 언제 시작해요", "일정"),
    ("며칠이에요?", "일정"),
    ("무슨 요일이에요", "일정"),
    # 위 키워드가 다른 '언제' 질문을 가로채면 안 된다.
    ("툴 크레딧 언제 지급되나요", "후원 툴 전체"),
    ("참가 신청 언제까지예요", "참가 신청"),
    # 범용 키워드가 엉뚱한 곳으로 끌고 가지 않는지 (실제 사고 이력)
    ("AI 안 쓰면 감점인가요?", "개발 요건"),
    # 앱 질문과 영상 '규격' 질문은 목적지가 다르다.
    # "앱 서비스는 시연 영상만으로도 인정되나요?"가 영상 규격 항목으로 가던 것을
    # 고쳤다. 두 항목 모두 '시연 영상'이라는 말을 쓰기 때문에 총점이 동점까지
    # 갔었다 — 한쪽 키워드를 건드리면 다시 뒤집히기 쉬우니 양쪽을 함께 고정한다.
    ("앱 서비스는 시연 영상만으로도 인정되나요?", "앱 배포 URL"),
    ("앱은 시연영상만으로 되나요", "앱 배포 URL"),
    ("마켓 출시 안 했는데 어떡해요", "앱 배포 URL"),
    ("테스트플라이트 링크 내도 되나요", "앱 배포 URL"),
    ("시연영상 용량 얼마", "시연 영상"),
    ("영상 길이 제한 있어요", "시연 영상"),
    # 가비아 서버는 신청 / 생성 / 삭제 세 항목으로 나눠져 있다.
    # 셋 다 '서버'라는 말을 공유해서 서로 끌어가기 쉬우므로 경계를 고정한다.
    # ('서버 언제 삭제돼요'가 '서버언제' 때문에 신청 항목으로 가던 것을 고쳤다)
    ("가비아 서버 어떻게 신청해요", "가비아 서버"),
    ("서버 지원 되나요", "가비아 서버"),
    ("클라우드 서버 언제부터 써요", "가비아 서버"),
    ("서버 만들 때 뭐 골라야 해요", "가비아 서버 생성"),
    ("윈도우 서버 되나요", "가비아 서버 생성"),
    ("터미널 접속 어떻게 해요", "가비아 서버 생성"),
    ("서버 언제 삭제돼요", "가비아 서버 삭제"),
    ("서버 백업해야 하나요", "가비아 서버 삭제"),
    ("가비아 기술지원 문의 어디로", "가비아 서버 삭제"),
    # 8/13 디스코드 QnA로 확정된 내용들.
    # '점심 먹으러 나갔다 와도 되나요'가 '나갔다'(등록 출입) 때문에 출입 안내로
    # 가던 것을 고쳤다. 외출 규정 자체는 '등록 출입'이 맞으므로 둘을 함께 고정한다.
    ("올해도 AI가 심사하나요?", "심사 기준"),
    ("외부 서비스 연동해도 되나요", "외부 서비스 연동"),
    ("api 키 하드코딩해도 되나요", "외부 서비스 연동"),
    ("테스트 계정 꼭 내야 하나요", "외부 서비스 연동"),
    ("배포 링크 외부에 공개되나요", "개발 요건"),
    ("21일 이후에 코드 수정 가능한가요", "깃허브 제출"),
    ("점심 먹으러 나갔다 와도 되나요", "식사"),
    ("외출 언제 되나요", "등록 출입"),
    ("정수기 있나요", "식사"),
    ("시연영상 양식 있나요", "시연 영상"),
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

    '병원 어디예요'는 예전에 `위치 교통`이 가로채서 행사장 주소를 답했다.
    `어디예요` 같은 의문형 조각이 키워드로 들어가 있었기 때문이다.
    (다친 경우는 `그라운드 룰`에 구급약품 안내가 있어서 ROUTING에서 다룬다.)
    """
    for q in [
        "반려동물 데려가도 되나요",
        "여기서 제일 가까운 병원 어디예요",
        "이상한 상황이면 어떻게 해요",
        "예술 분야 주제도 되나요",
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
