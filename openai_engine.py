# -*- coding: utf-8 -*-
"""
openai_engine.py — OpenAI 모델로 FAQ 자료를 근거로 자연어 답변을 생성하는 모듈.

claude_engine.py와 **완전히 같은 인터페이스**(is_enabled / answer)를 제공한다.
그래야 llm.py가 두 백엔드를 똑같이 다룰 수 있다.

- faq.md 전체를 컨텍스트로 넣고, 자료에 있는 내용만 답하도록 제한.
- 자료에 없으면 "모른다 + 운영진 문의"로 답하게 함 (엉뚱한 답 방지).
- discord 의존성 없음 → 단독 테스트 가능.
- 키가 없거나 오류가 나면 llm.py가 다른 백엔드나 키워드 매칭으로 폴백한다.
"""

import os

from openai import OpenAI

# 쓸 모델은 환경변수로 바꿀 수 있게 열어둔다.
#
# OpenAI 모델 라인업은 자주 바뀐다. 코드에 특정 모델명을 못박아두면
# 나중에 그 모델이 사라졌을 때 봇이 조용히 실패한다. 그래서 기본값은 두되,
# 잘못된 모델명일 때 "지금 계정에서 쓸 수 있는 모델 목록"을 로그에 찍어준다.
# 콘솔에서도 확인 가능: https://platform.openai.com/docs/models
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")

MAX_TOKENS = 1024

# 응답 대기 상한(초). 길면 학생이 로딩만 보게 되므로 짧게 끊는다.
TIMEOUT_SECONDS = float(os.environ.get("OPENAI_TIMEOUT", "20"))
MAX_RETRIES = 1

# claude_engine과 동일한 규칙을 쓴다. 두 백엔드의 답변 톤을 맞추기 위함.
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


def _get_client() -> OpenAI:
    """OpenAI 클라이언트 (OPENAI_API_KEY 환경변수를 읽음). 최초 1회만 생성."""
    global _client
    if _client is None:
        _client = OpenAI(timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
    return _client


def is_enabled() -> bool:
    """API 키가 설정돼 있어 OpenAI를 쓸 수 있는지."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def build_faq_context(entries) -> str:
    """FaqEntry 리스트를 하나의 텍스트 자료로 합친다."""
    return "\n\n".join(f"## {e.title}\n{e.answer}" for e in entries)


def _hint_available_models() -> str:
    """모델명이 틀렸을 때 쓸 수 있는 모델 목록을 뽑아 힌트 문자열로 만든다.

    라인업이 바뀌어 모델명이 안 맞을 때, 로그만 보고도 바로 고칠 수 있게 한다.
    이 조회 자체가 실패하면 조용히 빈 문자열을 돌려준다(2차 오류 방지).
    """
    try:
        names = sorted(m.id for m in _get_client().models.list())
        chat_models = [n for n in names if n.startswith("gpt")][:15]
        if chat_models:
            return " 사용 가능한 모델 예시: " + ", ".join(chat_models)
    except Exception:
        pass
    return ""


def answer(question: str, entries) -> str:
    """질문 + FAQ 자료를 OpenAI에 보내 답변 문자열을 받는다.

    오류는 호출 측(llm.py)에서 잡아 다른 백엔드나 키워드 매칭으로 폴백한다.
    """
    client = _get_client()
    context = build_faq_context(entries)

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            max_completion_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_RULES},
                {"role": "system", "content": f"해커톤 FAQ 자료:\n\n{context}"},
                {"role": "user", "content": question},
            ],
        )
    except Exception as e:
        # 모델명이 틀린 경우가 가장 흔하므로, 그때만 친절한 힌트를 붙인다.
        text = str(e)
        if "model" in text.lower() and ("not" in text.lower() or "exist" in text.lower()):
            raise RuntimeError(
                f"OpenAI 모델 '{MODEL}' 을(를) 쓸 수 없습니다. "
                f".env의 OPENAI_MODEL을 확인하세요.{_hint_available_models()}"
            ) from e
        raise

    return (resp.choices[0].message.content or "").strip()
