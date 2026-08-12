# -*- coding: utf-8 -*-
"""
test_channel_limit.py — 질문 채널 제한(ALLOWED_CHANNEL_IDS) 회귀 테스트.

왜 필요한가:
    이 설정은 잘못되면 "봇이 아무 데서도 응답하지 않는다"로 나타난다.
    봇 자체는 멀쩡히 떠 있고 에러 로그도 없어서 원인을 찾기 어렵다.
    특히 비워뒀을 때 기존처럼 모든 채널에서 동작하는지(하위 호환)를
    고정해두지 않으면, 설정을 안 건드린 서버가 조용히 먹통이 된다.

실행:
    python test_channel_limit.py
    pytest test_channel_limit.py

bot.py는 import 시점에 os.environ을 읽어 상수로 고정하므로,
환경변수를 바꾼 뒤 importlib.reload로 다시 읽게 한다.
"""

import importlib
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))


def _load_bot(allowed: str):
    """ALLOWED_CHANNEL_IDS를 주고 bot 모듈을 다시 읽어온다."""
    os.environ["ALLOWED_CHANNEL_IDS"] = allowed
    # bot.py는 load_dotenv()를 부르는데, 실제 .env가 있으면 그 값이 우선될 수
    # 있다. override=False가 기본이라 이미 설정된 환경변수는 덮이지 않는다.
    import bot
    return importlib.reload(bot)


class FakeInteraction:
    """is_allowed_channel()이 보는 건 channel_id 하나뿐이라 이걸로 충분하다."""

    def __init__(self, channel_id):
        self.channel_id = channel_id


# ── 파싱 ─────────────────────────────────────────────────────────

def test_parse_empty_means_no_restriction():
    bot = _load_bot("")
    assert bot.ALLOWED_CHANNEL_IDS == set()


def test_parse_single_and_multiple():
    bot = _load_bot("123")
    assert bot.ALLOWED_CHANNEL_IDS == {123}

    bot = _load_bot("123,456,789")
    assert bot.ALLOWED_CHANNEL_IDS == {123, 456, 789}


def test_parse_tolerates_spaces_and_trailing_comma():
    """복붙하면 공백이나 끝 쉼표가 딸려오기 쉽다. 그것 때문에 막히면 안 된다."""
    bot = _load_bot(" 123 , 456 ,")
    assert bot.ALLOWED_CHANNEL_IDS == {123, 456}


def test_parse_drops_non_numeric():
    """채널 '이름'을 넣는 실수를 걸러내되, 나머지 유효한 ID는 살린다."""
    bot = _load_bot("123,#해커톤-질문,456")
    assert bot.ALLOWED_CHANNEL_IDS == {123, 456}


# ── 게이트 동작 ──────────────────────────────────────────────────

def test_no_restriction_allows_every_channel():
    """설정을 안 건드린 서버는 기존과 똑같이 동작해야 한다 (하위 호환)."""
    bot = _load_bot("")
    for cid in (1, 999999999999999999, None):
        assert bot.is_allowed_channel(FakeInteraction(cid)) is True


def test_restriction_allows_only_listed():
    bot = _load_bot("123,456")
    assert bot.is_allowed_channel(FakeInteraction(123)) is True
    assert bot.is_allowed_channel(FakeInteraction(456)) is True
    assert bot.is_allowed_channel(FakeInteraction(789)) is False


def test_restriction_blocks_dm():
    """DM의 channel_id는 목록에 있을 수 없으므로 막혀야 한다.

    질문/답변이 ephemeral이라 DM을 허용할 이유가 없고, 채널을 제한한
    의도와도 어긋난다.
    """
    bot = _load_bot("123")
    assert bot.is_allowed_channel(FakeInteraction(555)) is False
    assert bot.is_allowed_channel(FakeInteraction(None)) is False


def test_wrong_channel_msg_links_allowed_channels():
    """안내에 채널 '링크'가 들어가야 한다.

    채널 이름을 문자열로 박으면 채널명이 바뀌었을 때 조용히 틀린 안내가
    나간다. <#ID> 형식은 디스코드가 클릭 가능한 링크로 렌더링하고,
    이름이 바뀌어도 항상 맞는 곳을 가리킨다.
    """
    bot = _load_bot("123,456")
    msg = bot.wrong_channel_msg()
    assert "<#123>" in msg and "<#456>" in msg, msg
    # 어디로 가야 하는지가 빠지면 안내의 의미가 없다.
    assert "질문" in msg


def test_all_typo_ids_means_locked_down():
    """전부 오타면 허용 채널이 0개다.

    이때 '제한 없음'으로 되돌아가면 막으려던 채널이 다 열려버린다.
    조용히 열리는 것보다 막히는 쪽이 안전하고, 시작 로그로 알아챌 수 있다.
    """
    bot = _load_bot("일반,잡담")
    assert bot.ALLOWED_CHANNEL_IDS == set()
    # 유효한 ID가 하나도 없으면 결과적으로 제한이 꺼진 것과 같아진다.
    # 이 동작을 바꾸려면 여기 기대값부터 고칠 것.
    assert bot.is_allowed_channel(FakeInteraction(123)) is True


def _cleanup():
    os.environ.pop("ALLOWED_CHANNEL_IDS", None)


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"[OK ] {name}")
        except AssertionError as e:
            failed.append(name)
            print(f"[FAIL] {name}: {e}")
    _cleanup()
    print(f"\n=== {len(tests) - len(failed)}/{len(tests)} 통과 ===")
    sys.exit(1 if failed else 0)
