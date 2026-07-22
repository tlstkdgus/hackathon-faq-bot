# -*- coding: utf-8 -*-
"""
claude_engine.py — Claude Haiku로 FAQ 자료를 근거로 자연어 답변을 생성하는 모듈.

- faq.md 전체를 컨텍스트로 넣고, 자료에 있는 내용만 답하도록 시스템 프롬프트로 제한.
- 자료에 없으면 "모른다 + 운영진 문의"로 답하게 함 (엉뚱한 답 방지).
- discord 의존성 없음 → 단독 테스트 가능.
- API 키(ANTHROPIC_API_KEY)가 없거나 오류가 나면 bot.py 쪽에서 키워드 매칭으로 폴백.
"""

import os

from anthropic import Anthropic

MODEL = "claude-haiku-4-5"  # FAQ 봇에 적합한 가장 빠르고 저렴한 모델
MAX_TOKENS = 1024

# 답변 규칙. FAQ 자료 밖의 내용은 지어내지 않도록 강하게 제약한다.
SYSTEM_RULES = (
    "너는 해커톤 운영을 돕는 친절한 디스코드 FAQ 봇이야. "
    "학생들의 질문에 아래에 제공된 '해커톤 FAQ 자료'만 근거로 한국어로 답해줘.\n\n"
    "규칙:\n"
    "1. 자료에 있는 내용이면 핵심만 간결하게, 친근한 말투로 답해줘. (이모지 조금은 OK)\n"
    "2. 자료에 없거나 확실하지 않은 내용은 절대 지어내지 말고, "
    "'그건 제가 가진 자료엔 없어요. 운영진에게 직접 문의해 주세요!' 라고 안내해줘.\n"
    "3. 일정·장소·비밀번호 같은 구체적인 정보는 자료에 적힌 값을 그대로 알려줘.\n"
    "4. 답변은 디스코드 메시지로 나가니 너무 길지 않게 해줘."
)

_client = None


def _get_client() -> Anthropic:
    """Anthropic 클라이언트 (ANTHROPIC_API_KEY 환경변수를 읽음). 최초 1회만 생성."""
    global _client
    if _client is None:
        _client = Anthropic()  # api_key 미지정 시 환경변수에서 자동으로 읽음
    return _client


def is_enabled() -> bool:
    """API 키가 설정돼 있어 Claude를 쓸 수 있는지."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def build_faq_context(entries) -> str:
    """FaqEntry 리스트를 하나의 텍스트 자료로 합친다."""
    parts = []
    for e in entries:
        parts.append(f"## {e.title}\n{e.answer}")
    return "\n\n".join(parts)


def claude_answer(question: str, entries) -> str:
    """질문 + FAQ 자료를 Claude에 보내 답변 문자열을 받는다.

    FAQ 자료는 매 요청 동일하므로 prompt caching을 걸어 비용을 아낀다
    (자료가 캐시 최소 크기 미만이면 캐시가 안 걸릴 수 있으나, 걸어둬도 무해).
    오류는 호출 측(bot.py)에서 잡아 키워드 매칭으로 폴백한다.
    """
    client = _get_client()
    context = build_faq_context(entries)

    system = [
        {"type": "text", "text": SYSTEM_RULES},
        {
            "type": "text",
            "text": f"해커톤 FAQ 자료:\n\n{context}",
            "cache_control": {"type": "ephemeral"},
        },
    ]

    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": question}],
    )

    return "".join(b.text for b in resp.content if b.type == "text").strip()
