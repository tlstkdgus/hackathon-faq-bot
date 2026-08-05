# -*- coding: utf-8 -*-
"""
digest.py — 키워드로 못 잡은 질문(unanswered.log)을 분석해 운영진용 요약을 만든다.

무엇을 해주나:
    1. 로그를 읽어 지정 기간의 질문만 추린다
    2. 비슷한 질문끼리 묶는다 (같은 걸 여러 명이 물었으면 우선순위가 높다)
    3. 각 묶음이 기존 FAQ 중 어디에 가장 가까운지 찾는다
    4. 그 항목에 넣으면 좋을 키워드 후보를 뽑는다

왜 '제안'까지만 하나:
    키워드를 봇이 알아서 faq.md에 써넣게 만들면, 잘못된 키워드 하나가
    엉뚱한 답변을 내보내기 시작한다. 그것도 아무도 모르는 채로.
    (실제로 '감점'이라는 범용 키워드 하나가 노코드 항목에 들어가서
     "AI 안 쓰면 감점인가요?" 질문을 가로챈 적이 있다.)
    그래서 찾는 일까지만 자동화하고, 반영 여부는 사람이 판단한다.

LLM을 쓰지 않는 이유:
    전부 문자열 처리로 해결되는 작업이라 API 비용도, 실패 지점도 없다.
    봇이 꺼져 있거나 API가 죽어도 이 분석은 항상 동작한다.

discord 의존성 없음 → 단독 테스트 가능.
"""

import datetime
import re
from collections import Counter
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

from faq_engine import _normalize, score_entry
from paths import MISS_LOG_FILE, DIGEST_STATE_FILE, ensure_data_dir

KST = ZoneInfo("Asia/Seoul")

# 두 질문을 '같은 질문'으로 묶을 유사도 기준
SIMILARITY = 0.6

# 한 리포트에 보여줄 최대 묶음 수 (디스코드 2000자 제한 대비)
MAX_GROUPS = 10

# '가까운 항목'이라고 말하려면 최소 이 정도 점수는 나와야 한다.
#
# 여기 올라오는 질문은 애초에 키워드 매칭에 실패한 것들(MIN_SCORE 미만)이라
# 점수가 낮을 수밖에 없다. 그렇다고 0보다 크기만 하면 다 붙여버리면
# "의료진 상주하나요 → 상금 시상" 같은 엉뚱한 안내가 나간다.
# 그럴 바엔 '맞는 항목 없음'이라고 하는 편이 운영진에게 정직하다.
MIN_NEAREST = 2.0

# 단어 끝에 붙는 조사·어미. 긴 것부터 떼어낸다.
# 이걸 안 떼면 '제공되나요'가 통째로 후보가 되어 실제 질문("제공되요?")을 못 잡는다.
_ENDINGS = [
    "되나요", "인가요", "은가요", "습니까", "할까요", "하나요", "되요", "돼요",
    "있나요", "없나요", "예요", "에요", "이에요", "인지", "하는지", "되는지",
    "나요", "가요", "까요", "어요", "아요", "해요", "요",
    "에서", "으로", "에게", "한테", "까지", "부터", "보다", "처럼", "라도",
    "은", "는", "이", "가", "을", "를", "에", "의", "도", "만", "과", "와", "랑",
]

# 후보에서 제외할 표현. 이런 게 키워드로 들어가면 아무 질문에나 걸린다.
STOPWORDS = {
    "어떻게", "어떡", "무엇", "뭐", "뭔가", "언제", "어디", "누가", "왜", "얼마",
    "알려주", "알려", "궁금", "질문", "혹시", "그리고", "저희", "우리", "제가",
    "해도", "하면", "되면", "있는", "없는", "하고", "이거", "그거", "저거",
    "안녕하세", "감사합니", "부탁드립니", "문의", "관련", "경우", "정도", "생각",
}

# 조사·어미를 떼고 남은 동사 조각들. 뜻이 없어서 키워드로 쓸 수 없다.
# ('주나요' → '주나', '나오나요' → '나오' 처럼 남는 것들)
# 형태소 분석기를 붙이면 더 정확하겠지만, 그 정도 무게의 의존성을 더할 만한
# 작업은 아니라서 자주 나오는 것만 목록으로 막는다.
_VERB_FRAGMENTS = {
    "주나", "주시", "주는", "나오", "되나", "하나", "있나", "없나", "가나", "오나",
    "받나", "쓰나", "가도", "오도", "되도", "드리", "드릴", "됩니", "합니", "입니",
    "인가", "한가", "된가", "이나", "거나", "든지", "해서", "돼서", "하기", "되기",
}


def _parse_line(line: str):
    """로그 한 줄 → (시각, 처리주체, 질문). 형식이 깨졌으면 None."""
    parts = line.rstrip("\n").split("\t")
    if len(parts) != 3:
        return None
    ts_raw, handled, question = parts
    try:
        ts = datetime.datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    except ValueError:
        return None
    return ts, handled.strip("[]"), question.strip()


def read_questions(since: datetime.datetime | None = None, path=MISS_LOG_FILE) -> list:
    """unanswered.log에서 since 이후의 (시각, 처리주체, 질문) 목록을 읽는다."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []

    out = []
    for line in lines:
        rec = _parse_line(line)
        if rec and (since is None or rec[0] > since):
            out.append(rec)
    return out


def group_questions(questions: list, threshold: float = SIMILARITY) -> list:
    """비슷한 질문끼리 묶는다. 큰 묶음이 앞에 오도록 정렬해서 반환.

    질문 수가 많아도 하루치라 규모가 작으므로 단순 비교로 충분하다.
    """
    groups: list = []
    for q in questions:
        qn = _normalize(q)
        for g in groups:
            if SequenceMatcher(None, qn, _normalize(g[0])).ratio() >= threshold:
                g.append(q)
                break
        else:
            groups.append([q])
    return sorted(groups, key=len, reverse=True)


def _existing_keywords(entries) -> set:
    """모든 항목의 키워드를 정규화해 모아둔다 (중복 제안을 피하기 위해)."""
    return {_normalize(k) for e in entries for k in e.keywords}


def _strip_ending(word: str) -> str:
    """단어 끝의 조사·어미를 하나 떼어낸다. ('제공되나요' → '제공')"""
    for e in _ENDINGS:
        if word.endswith(e) and len(word) - len(e) >= 2:
            return word[: -len(e)]
    return word


def _tokens(question: str) -> list:
    """질문에서 의미 있는 낱말만 뽑는다.

    글자 단위로 자르면 '심제공되' 같은 단어 중간 조각이 후보로 올라온다.
    띄어쓰기와 문장부호로 먼저 나눈 뒤 조사·어미를 떼는 편이 훨씬 깨끗하다.
    """
    raw = re.split(r"[^가-힣a-zA-Z0-9]+", question.lower())
    out = []
    for w in raw:
        w = _strip_ending(w)
        if len(w) < 2 or w in STOPWORDS or w in _VERB_FRAGMENTS:
            continue
        out.append(w)
    return out


def suggest_keywords(group: list, entries, limit: int = 3) -> list:
    """이 질문 묶음을 잡아줄 키워드 후보를 뽑는다.

    묶음 안 질문들의 낱말과 '붙어 나온 두 낱말'을 후보로 놓고,
    이미 등록된 키워드와 겹치는 것은 걸러낸다.
    두 낱말 조합('점심제공')을 함께 보는 이유는, 낱말 하나('제공')만으로는
    다른 주제까지 걸려버리는 경우가 많기 때문이다.
    """
    known = _existing_keywords(entries)
    counts: Counter = Counter()

    for q in group:
        words = _tokens(q)
        seen = set(words)
        seen |= {words[i] + words[i + 1] for i in range(len(words) - 1)}
        for w in seen:
            counts[w] += 1

    need = max(1, len(group) // 2)  # 묶음의 절반 이상에 나오는 표현만
    cands = []
    for word, cnt in counts.items():
        if cnt < need or word in STOPWORDS:
            continue
        if any(word in k or k in word for k in known):
            continue  # 기존 키워드와 겹치면 새로 넣을 이유가 없다
        if not re.search(r"[가-힣a-z]", word):
            continue
        cands.append((cnt, len(word), word))

    # 자주 나오고 긴 것부터. 길수록 그 주제에만 쓰이는 구체적인 표현이다.
    cands.sort(reverse=True)

    # 서로 포함관계인 후보는 하나만 남긴다 ('밥'과 '밥제공'을 둘 다 제안하지 않도록)
    picked: list = []
    for _, _, word in cands:
        if any(word in p or p in word for p in picked):
            continue
        picked.append(word)
        if len(picked) >= limit:
            break
    return picked


def nearest_entry(group: list, entries):
    """이 묶음이 기존 FAQ 중 어디에 가장 가까운지. (항목, 점수) 또는 (None, 0)."""
    if not entries:
        return None, 0.0
    best, best_score = None, 0.0
    for e in entries:
        s = max(score_entry(q, e) for q in group)
        if s > best_score:
            best, best_score = e, s
    return best, best_score


def analyze(questions: list, entries: list) -> list:
    """질문 목록 → 제안 목록. 각 원소는 dict."""
    texts = [q for _, _, q in questions]
    result = []
    for group in group_questions(texts):
        entry, score = nearest_entry(group, entries)
        result.append(
            {
                "count": len(group),
                "sample": group[0],
                "all": group,
                "entry": entry.title if entry else None,
                "score": score,
                "keywords": suggest_keywords(group, entries),
            }
        )
    return result


def build_report(questions: list, entries: list, since=None, limit: int = MAX_GROUPS) -> str:
    """디스코드로 보낼 요약 메시지를 만든다."""
    if not questions:
        return (
            "📊 **미답변 질문 리포트**\n"
            "지난 기간 동안 키워드로 못 잡은 질문이 없었어요. 👍"
        )

    period = f" (기준: {since:%m/%d %H:%M} 이후)" if since else ""
    lines = [
        f"📊 **미답변 질문 리포트**{period}",
        f"총 **{len(questions)}건**이 키워드로 잡히지 않았어요.",
        "",
    ]

    suggestions = analyze(questions, entries)
    for i, s in enumerate(suggestions[:limit], 1):
        head = f"**{i}. \"{s['sample']}\"**"
        if s["count"] > 1:
            head += f"  (비슷한 질문 {s['count']}건)"
        lines.append(head)

        # 같은 묶음의 다른 표현도 보여준다. 어떤 말로들 물어보는지 봐야
        # 어떤 키워드를 넣을지 판단할 수 있기 때문이다.
        for other in s["all"][1:3]:
            lines.append(f"   ┊ \"{other}\"")

        if s["entry"] and s["score"] >= MIN_NEAREST:
            lines.append(f"   └ 가까운 항목: **{s['entry']}**")
        else:
            lines.append("   └ ⚠️ 맞는 항목이 없어요. 새 항목이 필요해 보여요")

        if s["keywords"]:
            kws = ", ".join(f"`{k}`" for k in s["keywords"])
            lines.append(f"   └ 키워드 후보: {kws}")
        lines.append("")

    if len(suggestions) > limit:
        lines.append(f"…외 {len(suggestions) - limit}개 묶음 더 있어요.")
        lines.append("")

    lines.append("💡 `faq.md`의 해당 항목에 키워드를 추가하고 `!리로드` 하면 바로 반영돼요.")
    return "\n".join(lines)


# ── 마지막 실행 시각 기록 (중복·누락 방지) ────────────────────────

def load_last_run() -> datetime.datetime | None:
    """마지막으로 리포트를 보낸 시각. 기록이 없으면 None."""
    try:
        raw = DIGEST_STATE_FILE.read_text(encoding="utf-8").strip()
        return datetime.datetime.fromisoformat(raw)
    except (FileNotFoundError, ValueError):
        return None


def save_last_run(when: datetime.datetime | None = None) -> None:
    """리포트를 보낸 시각을 기록한다."""
    when = when or datetime.datetime.now(KST)
    try:
        ensure_data_dir()
        DIGEST_STATE_FILE.write_text(when.isoformat(), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ 다이제스트 상태 저장 실패: {e}")


def make_digest(entries: list, fallback_hours: int = 24) -> tuple:
    """리포트 문자열과 대상 기간 시작 시각을 돌려준다.

    마지막 실행 기록이 있으면 그 이후만, 없으면 최근 fallback_hours 시간만 본다.
    (기록을 쓰는 쪽은 호출한 곳이다 — 전송에 성공했을 때만 저장하기 위해.)
    """
    since = load_last_run()
    if since is None:
        since = datetime.datetime.now(KST) - datetime.timedelta(hours=fallback_hours)
    questions = read_questions(since=since)
    return build_report(questions, entries, since=since), since


if __name__ == "__main__":
    # 터미널에서 바로 확인용:  python digest.py
    import sys
    from faq_engine import load_faq
    from paths import FAQ_FILE

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    hours_back = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    entries = load_faq(str(FAQ_FILE))
    since = datetime.datetime.now(KST) - datetime.timedelta(hours=hours_back)
    print(build_report(read_questions(since=since), entries, since=since))
