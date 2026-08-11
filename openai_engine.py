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

from llm import SYSTEM_RULES, build_faq_context  # 답변 규칙은 백엔드 공용

# 쓸 모델은 환경변수로 바꿀 수 있게 열어둔다.
#
# 기본값 gpt-5.6-luna를 고른 이유:
#   FAQ 답변은 "주어진 자료에서 찾아 옮기는" 일이라 고성능 추론이 필요 없다.
#   Luna는 비용 최적화 모델($0.20/$1.20 per MTok)이라 상위 모델(Sol: $5/$30)의
#   25분의 1 가격인데, 이 용도에서는 답변 품질 차이를 체감하기 어렵다.
#   컨텍스트도 1M이 넘어 faq.md 전체를 넣고도 여유가 크다.
#
# 주의: OpenAI 라인업은 자주 바뀐다. 코드에 못박아두면 그 모델이 사라졌을 때
# 봇이 조용히 실패한다. 그래서 환경변수로 열어두고, 모델명이 틀리면
# "지금 계정에서 쓸 수 있는 모델 목록"을 로그에 찍어준다.
# 최신 목록: https://platform.openai.com/docs/models
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")

# 추론(reasoning) 강도: none | low | medium | high | xhigh | max
#
# 기본값을 none으로 두는 이유:
#   추론 토큰은 출력 토큰과 같은 단가로 과금되고, 그만큼 응답도 느려진다.
#   FAQ 봇은 자료에 있는 내용을 찾아 정리하는 일이라 추론이 필요 없다.
#   medium 이상을 쓰면 학생 대기시간과 비용만 몇 배로 늘고 답변 품질은
#   거의 그대로다. 답변이 이상하다 싶을 때만 low로 올려보면 된다.
REASONING_EFFORT = os.environ.get("OPENAI_REASONING", "none").strip().lower()

MAX_TOKENS = 1024

# 응답 대기 상한(초). 길면 학생이 로딩만 보게 되므로 짧게 끊는다.
TIMEOUT_SECONDS = float(os.environ.get("OPENAI_TIMEOUT", "20"))
MAX_RETRIES = 1

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

    kwargs = {
        "model": MODEL,
        "max_completion_tokens": MAX_TOKENS,
        "messages": [
            {"role": "system", "content": SYSTEM_RULES},
            {"role": "system", "content": f"해커톤 FAQ 자료:\n\n{context}"},
            {"role": "user", "content": question},
        ],
    }
    if REASONING_EFFORT:
        kwargs["reasoning_effort"] = REASONING_EFFORT

    try:
        resp = _create(client, kwargs)
    except Exception as e:
        # 모델명 오타/폐기가 가장 흔한 실패 원인이라, 그때만 힌트를 붙여준다.
        text = str(e).lower()
        if "model" in text and ("not" in text or "exist" in text):
            raise RuntimeError(
                f"OpenAI 모델 '{MODEL}' 을(를) 쓸 수 없습니다. "
                f".env의 OPENAI_MODEL을 확인하세요.{_hint_available_models()}"
            ) from e
        raise

    return (resp.choices[0].message.content or "").strip()


def _create(client, kwargs: dict):
    """API를 호출한다. reasoning_effort를 못 받는 조합이면 빼고 재시도한다.

    reasoning_effort는 추론 모델에만 있는 옵션이라, 비추론 모델로 바꿔 끼우거나
    SDK 버전이 낮으면 오류가 난다. 그 경우 파라미터만 빼고 한 번 더 시도해서
    모델을 갈아끼웠다는 이유만으로 봇이 답을 못 하는 상황을 막는다.
    """
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as e:
        if "reasoning_effort" not in kwargs:
            raise
        if isinstance(e, TypeError) or "reasoning" in str(e).lower():
            retry = {k: v for k, v in kwargs.items() if k != "reasoning_effort"}
            return client.chat.completions.create(**retry)
        raise
