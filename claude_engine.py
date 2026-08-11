# -*- coding: utf-8 -*-
"""
claude_engine.py — Claude Haiku로 FAQ 자료를 근거로 자연어 답변을 생성하는 모듈.

- faq.md 전체를 컨텍스트로 넣고, 자료에 있는 내용만 답하도록 시스템 프롬프트로 제한.
- 자료에 없으면 "모른다 + 운영진 문의"로 답하게 함 (엉뚱한 답 방지).
- discord 의존성 없음 → 단독 테스트 가능.
- API 키(ANTHROPIC_API_KEY)가 없거나 오류가 나면 llm.py가 다른 백엔드나
  키워드 매칭으로 폴백한다.
- llm.py가 백엔드를 구분하지 않고 `answer()`를 부르므로 함수명을 바꾸지 말 것.
"""

import os

from anthropic import Anthropic

from llm import SYSTEM_RULES, build_faq_context  # 답변 규칙은 백엔드 공용

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")  # 빠르고 저렴한 기본 모델
MAX_TOKENS = 1024

# 응답 대기 상한(초). SDK 기본값은 10분이라 그대로 두면 API가 느려질 때
# 학생이 몇 분씩 로딩 표시를 보게 된다. 짧게 끊고 키워드 매칭으로 폴백하는 편이 낫다.
TIMEOUT_SECONDS = float(os.environ.get("ANTHROPIC_TIMEOUT", "20"))
MAX_RETRIES = 1  # 일시적 오류만 한 번 재시도 (총 대기 최악 약 40초)

_client = None


def _get_client() -> Anthropic:
    """Anthropic 클라이언트 (ANTHROPIC_API_KEY 환경변수를 읽음). 최초 1회만 생성."""
    global _client
    if _client is None:
        # api_key 미지정 시 ANTHROPIC_API_KEY 환경변수에서 자동으로 읽음
        _client = Anthropic(timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
    return _client


def is_enabled() -> bool:
    """API 키가 설정돼 있어 Claude를 쓸 수 있는지."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def answer(question: str, entries) -> str:
    """질문 + FAQ 자료를 Claude에 보내 답변 문자열을 받는다.

    이름이 반드시 `answer`여야 한다 — llm.py가 백엔드를 구분하지 않고
    `eng.answer(...)`로 부르기 때문이다. (예전엔 `claude_answer`로 되어 있어서
    Claude 폴백이 호출 시점마다 AttributeError로 죽고 있었다.)

    FAQ 자료는 매 요청 동일하므로 prompt caching을 걸어 비용을 아낀다
    (자료가 캐시 최소 크기 미만이면 캐시가 안 걸릴 수 있으나, 걸어둬도 무해).
    오류는 호출 측(llm.py)에서 잡아 다른 백엔드나 키워드 매칭으로 폴백한다.
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
