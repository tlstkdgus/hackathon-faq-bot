# -*- coding: utf-8 -*-
"""
faq_engine.py — faq.md 파일을 읽어서 키워드 매칭으로 답변을 찾는 모듈.
디스코드와 무관한 순수 로직이라 단독으로 테스트할 수 있습니다.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class FaqEntry:
    title: str                      # 주제 이름 (목록에 표시됨)
    keywords: list = field(default_factory=list)  # 매칭에 쓰이는 키워드들
    answer: str = ""                # 답변 본문
    category: str = ""              # 소속 카테고리 (topic_list 그룹핑용, 매칭에는 안 쓰임)


def load_faq(path: str = "faq.md") -> list:
    """faq.md를 파싱해서 FaqEntry 리스트로 반환.

    faq.md 형식:

        ## 주제이름 | 키워드1, 키워드2, 키워드3
        답변 내용 (여러 줄 가능, 노션에서 복사해 붙여넣기 OK)

        ## 다음주제 | 키워드...
        ...

    한 줄짜리 `# 카테고리 이름` (해시 1개)은 그 아래 이어지는 "## 주제"들이 속할
    카테고리 이름을 지정한다. 매칭/답변 내용엔 전혀 영향을 주지 않고,
    faq.md를 VS Code 아웃라인/미리보기에서 한눈에 보거나 /해커톤주제 목록을
    카테고리별로 묶어서 보여주는 용도로만 쓰인다.
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    entries = []
    category = ""
    current = None  # 현재 파싱 중인 항목: {"title", "keywords", "category", "body": [줄...]}

    def flush():
        if current is None:
            return
        body = "\n".join(current["body"]).strip()
        if body:
            entries.append(FaqEntry(
                title=current["title"],
                keywords=current["keywords"],
                answer=body,
                category=current["category"],
            ))

    for line in lines:
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            flush()
            header = m.group(1).strip()
            if "|" in header:
                title, kw_part = header.split("|", 1)
                keywords = [k.strip() for k in kw_part.split(",") if k.strip()]
            else:
                title, keywords = header, []
            title = title.strip()
            if title and title not in keywords:
                keywords.append(title)  # 제목 자체도 키워드로 사용
            current = {"title": title, "keywords": keywords, "category": category, "body": []}
            continue

        m = re.match(r"^#\s+(.*)$", line)  # 해시 1개 = 구획용 카테고리 제목
        if m:
            flush()
            current = None
            category = m.group(1).strip()
            continue

        if current is not None:
            current["body"].append(line)

    flush()
    return entries


# 이 점수 미만이면 "확실한 매칭 없음"으로 보고 None을 반환한다.
# (그래야 bot.py가 LLM 폴백으로 넘길 수 있음.)
# 1.0 = 정확히 일치하는 한 글자 키워드(예: '밥', '팀') 하나면 통과.
# 애매한 유사매칭(0.82×길이)은 걸러지고, 키워드가 전혀 안 겹치는 질문만 LLM으로 넘어간다.
# 오답이 잦으면 이 값을 높이고(→ LLM 호출 ↑), 너무 자주 LLM으로 넘어가면 낮춰라.
MIN_SCORE = 1.0

# 부분/유사 매칭으로 인정할 최소 유사도 (0~1). 오타나 살짝 다른 표기를 잡는다.
FUZZY_THRESHOLD = 0.82


def _normalize(s: str) -> str:
    """비교를 위해 전각→반각 정규화 + 소문자화 + 공백 제거.

    NFKC를 먼저 거치는 이유: 입력기 상태에 따라 전각 문자로 치는 학생이 있다.
    실제로 `ＩＲＤＥＣＫ`(전각)가 어떤 항목에도 안 걸려 LLM으로 넘어간 적이
    있는데, 눈으로는 `IRDECK`과 똑같아 보여서 왜 못 잡는지 알아내기 어렵다.
    NFKC가 전각 영숫자·전각 공백·호환 한글 자모를 표준형으로 바꿔준다.
    """
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s).lower())


def _keyword_match_ratio(keyword_norm: str, q_norm: str) -> float:
    """정규화된 키워드가 질문에 얼마나 맞는지 0~1로 반환.

    1) 키워드가 질문에 그대로 포함되면 1.0 (가장 강한 신호)
    2) 아니면 질문을 키워드 길이만큼 훑으며 최대 유사도를 재고,
       FUZZY_THRESHOLD 이상일 때만 그 값을 인정 (오타/변형 대응)
    """
    if not keyword_norm:
        return 0.0
    if keyword_norm in q_norm:
        return 1.0

    k_len = len(keyword_norm)
    if k_len > len(q_norm):
        r = SequenceMatcher(None, keyword_norm, q_norm).ratio()
        return r if r >= FUZZY_THRESHOLD else 0.0

    best = 0.0
    for i in range(len(q_norm) - k_len + 1):
        window = q_norm[i : i + k_len]
        r = SequenceMatcher(None, keyword_norm, window).ratio()
        if r > best:
            best = r
    return best if best >= FUZZY_THRESHOLD else 0.0


def score_entry(question: str, entry: "FaqEntry") -> float:
    """질문에 대한 한 항목의 매칭 점수. 키워드별 (일치도 × 키워드 길이)의 합.

    길이로 가중하므로 '와이파이'(4자) 같은 구체적 키워드가 '팀'(1자) 같은
    짧은 키워드보다 크게 기여한다.
    """
    return _score_detail(question, entry)[0]


def _score_detail(question: str, entry: "FaqEntry"):
    """(총점, 맞은 키워드 수, 가장 긴 키워드 길이)를 함께 돌려준다.

    총점만으로는 동점이 자주 나기 때문에 순위를 가를 보조 지표가 필요하다.
    - 맞은 키워드 수: 여러 키워드가 걸린 쪽이 그 주제일 가능성이 높다
      (예: "시연 영상 몇분" → '시연영상'과 '영상' 둘 다 걸리는 항목)
    - 가장 긴 키워드: 긴 키워드일수록 그 주제에만 쓰이는 구체적인 표현이다
      (예: '아무거나'보다 '부스벽사이즈'가 훨씬 변별력 있다)
    """
    q = _normalize(question)
    total = 0.0
    matched = 0
    longest = 0
    for k in entry.keywords:
        k_norm = _normalize(k)
        ratio = _keyword_match_ratio(k_norm, q)
        if ratio > 0:
            matched += 1
            longest = max(longest, len(k_norm))
        total += ratio * len(k_norm)
    return total, matched, longest


def find_answer(question: str, entries: list, min_score: float = MIN_SCORE):
    """질문에 가장 잘 맞는 항목을 반환. 확실한 매칭이 없으면 None.

    None을 돌려주면 bot.py가 LLM 폴백(있을 경우)으로 넘긴다.
    min_score를 낮추면 더 관대하게(오답 위험 ↑), 높이면 더 엄격하게(LLM 호출 ↑) 동작.
    """
    # 점수가 높은 순으로 정렬. 총점이 같으면 (맞은 키워드 수 → 가장 긴 키워드) 순으로
    # 순위를 가른다. 마지막에 제목을 넣는 이유는 완전 동점일 때도 결과가 항상
    # 같도록 만들기 위해서다. 예전에는 동점이면 faq.md에서 먼저 나온 항목이
    # 이겼는데, 그러면 항목 순서만 바꿔도 답이 조용히 달라져서 위험했다.
    ranked = sorted(
        ((_score_detail(question, e), e) for e in entries),
        key=lambda x: (x[0][0], x[0][1], x[0][2], x[1].title),
        reverse=True,
    )
    if not ranked:
        return None

    (top_score, top_matched, top_longest), best = ranked[0]
    if top_score < min_score:
        return None

    # 1·2위가 모든 지표에서 완전히 같다면 키워드만으로는 판단할 수 없는 질문이다.
    # 둘 중 하나를 임의로 고르면 절반은 틀린 답이 나가므로, 차라리 None을 돌려
    # LLM에게 넘긴다. LLM은 FAQ 전체를 보고 판단하니 훨씬 나은 선택을 한다.
    if len(ranked) > 1 and ranked[1][0] == (top_score, top_matched, top_longest):
        return None

    return best


def topic_list(entries: list) -> str:
    """등록된 주제 목록 문자열. faq.md의 카테고리(# 제목)별로 묶어서 보여준다."""
    groups: dict = {}
    for e in entries:
        groups.setdefault(e.category or "기타", []).append(e.title)

    parts = []
    for category, titles in groups.items():
        header = f"**{category}**" if category else "**기타**"
        parts.append(header + "\n" + "\n".join(f"• {t}" for t in titles))
    return "\n\n".join(parts)
