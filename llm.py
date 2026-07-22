# -*- coding: utf-8 -*-
"""
llm.py — 어떤 LLM 백엔드로 자연어 답변을 만들지 고르는 스위치.

LLM_PROVIDER 환경변수로 선택 (기본: claude).
- "claude" → claude_engine (현재 동작)
- "openai" → openai_engine (추후 OpenAI 크레딧 생기면 openai_engine.py 추가)

bot.py는 이 모듈의 is_enabled() / answer() 두 함수만 사용한다.
새 백엔드를 붙일 때:
  1) claude_engine.py와 같은 인터페이스(is_enabled(), answer(question, entries))로
     openai_engine.py를 만든다.
  2) .env에 LLM_PROVIDER=openai 를 넣는다.
  → 그 외 bot.py / faq_engine.py는 손대지 않아도 된다.
"""

import os

import claude_engine

PROVIDER = os.environ.get("LLM_PROVIDER", "claude").strip().lower()


def _load_openai():
    """openai_engine을 지연 import한다 (아직 파일이 없으면 None)."""
    try:
        import openai_engine
        return openai_engine
    except ImportError:
        return None


def is_enabled() -> bool:
    """현재 선택된 백엔드로 자연어 답변이 가능한지 (키 설정 여부 등)."""
    if PROVIDER == "openai":
        eng = _load_openai()
        return bool(eng and eng.is_enabled())
    # 기본: claude
    return claude_engine.is_enabled()


def answer(question: str, entries) -> str:
    """선택된 백엔드로 답변 생성. is_enabled()가 True일 때만 호출할 것."""
    if PROVIDER == "openai":
        eng = _load_openai()
        if eng is None:
            raise RuntimeError(
                "LLM_PROVIDER=openai 인데 openai_engine.py가 없습니다. "
                "OpenAI 크레딧이 생기면 claude_engine.py와 같은 구조로 "
                "openai_engine.py를 만들어 추가하세요."
            )
        return eng.answer(question, entries)
    # 기본: claude
    return claude_engine.claude_answer(question, entries)
