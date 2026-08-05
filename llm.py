# -*- coding: utf-8 -*-
"""
llm.py — 어떤 LLM 백엔드로 자연어 답변을 만들지 고르는 스위치.

설정 (.env)
    LLM_PROVIDER=openai     주 백엔드 (openai | claude). 기본 claude
    LLM_FALLBACK=claude     주 백엔드가 실패하면 넘어갈 백엔드. 빈 값이면 폴백 안 함

왜 폴백이 필요한가:
    해커톤 당일에 한쪽 API가 흔들리거나(장애, 레이트리밋, 크레딧 소진) 하면
    학생 질문에 답을 못 하게 된다. 주 백엔드가 실패했을 때 자동으로 다른 쪽으로
    넘기면 그런 상황에서도 답변이 계속 나간다.
    두 백엔드 다 실패하면 bot.py가 키워드 매칭 결과나 안내 메시지로 마무리한다.

bot.py는 이 모듈의 is_enabled() / answer() / PROVIDER 만 사용한다.

새 백엔드를 붙이려면 claude_engine.py와 같은 인터페이스
(is_enabled(), answer(question, entries))로 모듈을 만들고 _ENGINES에 등록하면 된다.
"""

import os

PROVIDER = os.environ.get("LLM_PROVIDER", "claude").strip().lower()
FALLBACK = os.environ.get("LLM_FALLBACK", "").strip().lower()

# 마지막 답변을 실제로 처리한 백엔드 이름.
# 통계 로그(stats.log)에 "무엇이 답했는지" 남기기 위해 bot.py가 읽어간다.
last_used = PROVIDER


def _load(name: str):
    """백엔드 모듈을 지연 import한다. 패키지가 없으면 None.

    지연 import인 이유: openai만 쓰는 사람이 anthropic 패키지를 깔지 않아도
    (또는 그 반대여도) 봇이 정상 동작해야 하기 때문이다.
    """
    try:
        if name == "openai":
            import openai_engine
            return openai_engine
        if name == "claude":
            import claude_engine
            return claude_engine
    except ImportError as e:
        print(f"⚠️ {name} 백엔드를 불러오지 못했습니다: {e}")
    return None


def _usable(name: str):
    """이름에 해당하는 백엔드가 지금 쓸 수 있는 상태면 모듈을, 아니면 None."""
    if not name:
        return None
    eng = _load(name)
    if eng is None:
        return None
    try:
        return eng if eng.is_enabled() else None
    except Exception:
        return None


def _chain() -> list:
    """실제로 시도할 백엔드 순서. [(이름, 모듈), ...]

    주 백엔드 → 폴백 순. 키가 없는 백엔드는 애초에 목록에서 빠진다.
    """
    result = []
    for name in (PROVIDER, FALLBACK):
        if name and name not in [n for n, _ in result]:
            eng = _usable(name)
            if eng is not None:
                result.append((name, eng))
    return result


def is_enabled() -> bool:
    """자연어 답변이 가능한 백엔드가 하나라도 있는지."""
    return bool(_chain())


def describe() -> str:
    """현재 구성을 사람이 읽을 수 있게 (시작 로그용)."""
    chain = _chain()
    if not chain:
        return "없음(키워드 전용)"
    names = [n for n, _ in chain]
    head = names[0]
    if len(names) > 1:
        return f"{head} (실패 시 {' → '.join(names[1:])} 폴백)"
    return head


def answer(question: str, entries) -> str:
    """사용 가능한 백엔드를 순서대로 시도해 답변을 만든다.

    앞의 백엔드가 예외를 던지면 다음 것으로 넘어간다.
    전부 실패하면 마지막 예외를 그대로 올려보내고, bot.py가 잡아서
    키워드 결과나 안내 메시지로 마무리한다.
    """
    global last_used

    chain = _chain()
    if not chain:
        raise RuntimeError(
            "사용 가능한 LLM 백엔드가 없습니다. "
            ".env에 OPENAI_API_KEY 또는 ANTHROPIC_API_KEY를 넣으세요."
        )

    last_error = None
    for name, eng in chain:
        try:
            result = eng.answer(question, entries)
            if result:
                last_used = name
                return result
            last_error = RuntimeError(f"{name}이(가) 빈 답변을 반환했습니다.")
        except Exception as e:
            last_error = e
            print(f"⚠️ LLM({name}) 오류: {e}")
            # 폴백이 남아 있으면 다음 백엔드로 계속 진행한다
            continue

    raise last_error if last_error else RuntimeError("LLM 답변 생성 실패")
