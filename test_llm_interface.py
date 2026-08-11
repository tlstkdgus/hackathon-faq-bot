# -*- coding: utf-8 -*-
"""
test_llm_interface.py — LLM 백엔드 인터페이스 회귀 테스트.

왜 필요한가:
    llm.py는 백엔드를 구분하지 않고 `eng.answer(...)`를 부른다. 예전에
    claude_engine이 함수를 `claude_answer`로 두는 바람에 Claude 폴백이
    호출될 때마다 AttributeError로 죽고 있었는데, describe()는 "폴백 걸림"으로
    표시해서 아무도 눈치채지 못했다. OpenAI가 살아 있는 동안엔 증상이 없고,
    정작 폴백이 필요한 순간에만 답이 멈추는 종류의 고장이다.

실행:
    python test_llm_interface.py     # 의존성 없이 그대로 실행
    pytest test_llm_interface.py     # pytest가 있으면 이것도 동작

API를 호출하지 않는다. import·속성·체인 구성만 본다.
anthropic/openai 패키지가 없는 환경도 있으므로(llm.py가 지연 import하는 이유)
엔진 검사는 패키지가 있을 때만 돌린다.
"""

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import llm


def _installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


HAS_ANTHROPIC = _installed("anthropic")
HAS_OPENAI = _installed("openai")


def _fake_engine(answer_name: str):
    """is_enabled()는 True고, 답변 함수 이름만 다른 가짜 백엔드."""
    mod = types.ModuleType("fake_engine")
    mod.is_enabled = lambda: True
    setattr(mod, answer_name, lambda q, entries: "fake answer")
    return mod


def _with_fake(name: str, mod):
    """sys.modules에 가짜 백엔드를 끼워 넣는 컨텍스트 매니저."""

    class _Ctx:
        def __enter__(self):
            self.saved = sys.modules.get(name, ...)
            sys.modules[name] = mod

        def __exit__(self, *exc):
            if self.saved is ...:
                del sys.modules[name]
            else:
                sys.modules[name] = self.saved

    return _Ctx()


# ── 공용 프롬프트 ────────────────────────────────────────────────

def test_shared_prompt_exists():
    """답변 규칙과 자료 조립은 llm.py에 한 벌만 있어야 한다."""
    assert isinstance(llm.SYSTEM_RULES, str) and llm.SYSTEM_RULES.strip()
    assert callable(llm.build_faq_context)


def test_build_faq_context_format():
    entry = types.SimpleNamespace
    got = llm.build_faq_context([
        entry(title="식사", answer="제공 안 됨"),
        entry(title="와이파이", answer="8월 공지"),
    ])
    assert got == "## 식사\n제공 안 됨\n\n## 와이파이\n8월 공지"


def test_build_faq_context_empty():
    assert llm.build_faq_context([]) == ""


# ── 핵심: answer() 이름 규칙과 가드 ──────────────────────────────

def test_usable_accepts_answer():
    """answer()를 가진 백엔드는 체인에 들어간다."""
    with _with_fake("openai_engine", _fake_engine("answer")):
        assert llm._usable("openai") is not None


def test_usable_rejects_wrong_function_name():
    """answer()가 없으면 체인에서 빠진다 — 이번 버그의 재발 방지선.

    이 가드가 없으면 describe()는 폴백이 걸린 것처럼 안내하면서
    실제 호출 시점에 AttributeError로 죽는다.
    """
    with _with_fake("openai_engine", _fake_engine("claude_answer")):
        assert llm._usable("openai") is None


def test_describe_does_not_lie_when_backend_broken():
    """깨진 백엔드는 describe()에도 나타나지 않아야 한다."""
    saved = (llm.PROVIDER, llm.FALLBACK)
    llm.PROVIDER, llm.FALLBACK = "openai", "claude"
    try:
        with _with_fake("openai_engine", _fake_engine("claude_answer")):
            with _with_fake("claude_engine", _fake_engine("answer")):
                assert [n for n, _ in llm._chain()] == ["claude"]
                assert llm.describe() == "claude"
    finally:
        llm.PROVIDER, llm.FALLBACK = saved


def test_chain_order_and_dedup():
    """주 백엔드 → 폴백 순서, 같은 이름이 두 번 들어가지 않는다."""
    saved = (llm.PROVIDER, llm.FALLBACK)
    try:
        with _with_fake("openai_engine", _fake_engine("answer")):
            with _with_fake("claude_engine", _fake_engine("answer")):
                llm.PROVIDER, llm.FALLBACK = "openai", "claude"
                assert [n for n, _ in llm._chain()] == ["openai", "claude"]

                llm.PROVIDER, llm.FALLBACK = "claude", "claude"
                assert [n for n, _ in llm._chain()] == ["claude"]

                llm.PROVIDER, llm.FALLBACK = "openai", ""
                assert [n for n, _ in llm._chain()] == ["openai"]
    finally:
        llm.PROVIDER, llm.FALLBACK = saved


def test_answer_falls_back_and_records_backend():
    """주 백엔드가 죽으면 폴백이 답하고, last_used에 실제로 답한 쪽이 남는다."""
    saved = (llm.PROVIDER, llm.FALLBACK, llm.last_used)
    broken = _fake_engine("answer")
    broken.answer = lambda q, e: (_ for _ in ()).throw(RuntimeError("레이트리밋"))
    good = _fake_engine("answer")
    good.answer = lambda q, e: "폴백이 답했어요"
    try:
        llm.PROVIDER, llm.FALLBACK = "openai", "claude"
        with _with_fake("openai_engine", broken):
            with _with_fake("claude_engine", good):
                assert llm.answer("밥 주나요?", []) == "폴백이 답했어요"
                assert llm.last_used == "claude"
    finally:
        llm.PROVIDER, llm.FALLBACK, llm.last_used = saved


# ── 실제 엔진 모듈 (패키지가 있을 때만) ──────────────────────────

def test_real_engines_expose_answer():
    """설치된 엔진 모듈은 반드시 answer()를 가져야 한다."""
    checked = 0
    if HAS_ANTHROPIC:
        import claude_engine
        assert callable(getattr(claude_engine, "answer", None))
        assert not hasattr(claude_engine, "claude_answer"), "옛 함수명이 남아 있다"
        assert claude_engine.SYSTEM_RULES is llm.SYSTEM_RULES
        assert claude_engine.build_faq_context is llm.build_faq_context
        checked += 1
    if HAS_OPENAI:
        import openai_engine
        assert callable(getattr(openai_engine, "answer", None))
        assert openai_engine.SYSTEM_RULES is llm.SYSTEM_RULES
        assert openai_engine.build_faq_context is llm.build_faq_context
        checked += 1
    if not checked:
        print("      (anthropic/openai 미설치 — 실제 엔진 검사 건너뜀)")


def test_engine_import_alone_has_no_cycle():
    """엔진을 먼저 단독 import해도 순환 참조가 나지 않아야 한다.

    엔진이 `from llm import ...`를 하므로 순서에 따라 깨질 수 있다.
    최악의 순서를 별도 프로세스에서 확인한다.
    """
    if not HAS_ANTHROPIC:
        print("      (anthropic 미설치 — 순환 참조 검사 건너뜀)")
        return
    code = (
        "import sys; sys.path.insert(0, r'%s'); import claude_engine as c; "
        "assert callable(c.answer); print('OK')" % BASE_DIR
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr[-800:]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"[OK ] {name}")
        except AssertionError as e:
            failed.append(name)
            print(f"[FAIL] {name}: {e}")
    print(f"\n=== {len(tests) - len(failed)}/{len(tests)} 통과 ===")
    sys.exit(1 if failed else 0)
