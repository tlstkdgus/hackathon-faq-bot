# -*- coding: utf-8 -*-
"""
faq_engine.py — faq.md 파일을 읽어서 키워드 매칭으로 답변을 찾는 모듈.
디스코드와 무관한 순수 로직이라 단독으로 테스트할 수 있습니다.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class FaqEntry:
    title: str                      # 주제 이름 (목록에 표시됨)
    keywords: list = field(default_factory=list)  # 매칭에 쓰이는 키워드들
    answer: str = ""                # 답변 본문


def load_faq(path: str = "faq.md") -> list:
    """faq.md를 파싱해서 FaqEntry 리스트로 반환.

    faq.md 형식:

        ## 주제이름 | 키워드1, 키워드2, 키워드3
        답변 내용 (여러 줄 가능, 노션에서 복사해 붙여넣기 OK)

        ## 다음주제 | 키워드...
        ...

    한 줄짜리 `# 카테고리 이름` (해시 1개)은 봇 기능과 무관한 순수 구획용 제목으로,
    파싱 전에 제거되어 어떤 항목의 답변에도 섞이지 않는다. faq.md를 VS Code
    아웃라인/미리보기에서 큰 카테고리별로 한눈에 보기 위한 용도로만 쓰인다.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()

    # 구획용 "# 카테고리" 제목(해시 1개) 줄 제거 — "## 주제" 파싱엔 영향 없음
    text = re.sub(r"^#[ \t]+.*$\n?", "", text, flags=re.MULTILINE)

    entries = []
    # "## " 로 시작하는 줄을 기준으로 섹션 분리
    sections = re.split(r"^##\s+", text, flags=re.MULTILINE)
    for sec in sections[1:]:  # 첫 조각은 헤더 이전 내용이므로 무시
        lines = sec.strip().splitlines()
        if not lines:
            continue
        header = lines[0].strip()
        body = "\n".join(lines[1:]).strip()

        if "|" in header:
            title, kw_part = header.split("|", 1)
            keywords = [k.strip() for k in kw_part.split(",") if k.strip()]
        else:
            title, keywords = header, []
        title = title.strip()

        # 제목 자체도 키워드로 사용
        if title and title not in keywords:
            keywords.append(title)

        if body:
            entries.append(FaqEntry(title=title, keywords=keywords, answer=body))
    return entries


# 이 점수 미만이면 "확실한 매칭 없음"으로 보고 None을 반환한다.
# (그래야 bot.py가 Claude 폴백으로 넘길 수 있음.)
# 1.0 = 정확히 일치하는 한 글자 키워드(예: '밥', '팀') 하나면 통과.
# 애매한 유사매칭(0.82×길이)은 걸러지고, 키워드가 전혀 안 겹치는 질문만 Claude로 넘어간다.
# 오답이 잦으면 이 값을 높이고(→ Claude 호출 ↑), 너무 자주 Claude로 넘어가면 낮춰라.
MIN_SCORE = 1.0

# 부분/유사 매칭으로 인정할 최소 유사도 (0~1). 오타나 살짝 다른 표기를 잡는다.
FUZZY_THRESHOLD = 0.82


def _normalize(s: str) -> str:
    """비교를 위해 소문자화 + 공백 제거."""
    return re.sub(r"\s+", "", s.lower())


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
    q = _normalize(question)
    total = 0.0
    for k in entry.keywords:
        k_norm = _normalize(k)
        ratio = _keyword_match_ratio(k_norm, q)
        total += ratio * len(k_norm)
    return total


def find_answer(question: str, entries: list, min_score: float = MIN_SCORE):
    """질문에 가장 잘 맞는 항목을 반환. 확실한 매칭이 없으면 None.

    None을 돌려주면 bot.py가 Claude 폴백(있을 경우)으로 넘긴다.
    min_score를 낮추면 더 관대하게(오답 위험 ↑), 높이면 더 엄격하게(Claude 호출 ↑) 동작.
    """
    best, best_score = None, 0.0
    for e in entries:
        s = score_entry(question, e)
        if s > best_score:
            best, best_score = e, s
    return best if best_score >= min_score else None


def topic_list(entries: list) -> str:
    """등록된 주제 목록 문자열."""
    return "\n".join(f"• {e.title}" for e in entries)
