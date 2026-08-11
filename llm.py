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

# ── 백엔드 공용 프롬프트 ──────────────────────────────────────
# 답변 규칙과 자료 조립은 백엔드가 달라도 같아야 한다. 예전에는 두 엔진 파일에
# 똑같은 내용을 복사해 두었는데, 한쪽만 고치면 백엔드에 따라 답변 톤이 조용히
# 갈라진다. 어느 쪽이 답했는지는 학생이 알 수 없으니 여기서 한 벌만 둔다.

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


def build_faq_context(entries) -> str:
    """FaqEntry 리스트를 하나의 텍스트 자료로 합친다."""
    return "\n\n".join(f"## {e.title}\n{e.answer}" for e in entries)


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
    # answer()가 없는 모듈은 아예 체인에서 뺀다.
    # 없으면 describe()가 "실패 시 claude 폴백"이라고 안내하면서도 실제로는
    # 호출 시점에 AttributeError로 죽는다. 실제로 claude_engine이 함수명을
    # claude_answer로 두는 바람에 폴백이 내내 동작하지 않았는데, 로그에는
    # 폴백이 걸린 것처럼 표시돼서 눈치채기 어려웠다.
    if not callable(getattr(eng, "answer", None)):
        print(f"⚠️ {name} 백엔드에 answer() 함수가 없습니다. 이 백엔드는 건너뜁니다.")
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
