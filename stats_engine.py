# -*- coding: utf-8 -*-
"""
stats_engine.py — 질문 로그 기록/집계 로직.

discord 의존성 없음 → bot.py에서도, VS Code 터미널에서 돌리는
stats_cli.py에서도 그대로 재사용할 수 있다 (단독 테스트도 가능).
"""

import datetime
from zoneinfo import ZoneInfo

from paths import MISS_LOG_FILE, STATS_LOG_FILE, ensure_data_dir

# 로그 시각은 항상 한국시간으로 남긴다.
# 서버(오라클 등)의 시스템 시간대는 보통 UTC라, 그냥 datetime.now()를 쓰면
# 로그가 9시간 어긋나서 "새벽 3시에 질문이 몰렸다" 같은 엉뚱한 해석을 하게 된다.
KST = ZoneInfo("Asia/Seoul")


def _now() -> str:
    """로그에 찍을 현재 시각(한국시간) 문자열."""
    return datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def _append(path, line: str, label: str) -> None:
    """로그 한 줄을 파일에 덧붙인다. 실패해도 예외를 밖으로 던지지 않는다.

    로그를 못 남기는 건 아쉬운 일이지만, 그것 때문에 학생 질문에 대한 답변이
    실패하면 안 된다. 그래서 여기서 삼키고 콘솔에만 경고를 찍는다.
    """
    try:
        ensure_data_dir()
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"⚠️ {label} 실패: {e}")


def log_miss(question: str, handled_by: str) -> None:
    """키워드로 못 잡은 질문을 로그 파일에 남긴다.

    handled_by: 'claude'(Claude가 대신 답함) 또는 'nomatch'(아무도 못 답함).
    운영진은 이 로그를 보고 자주 나오는 표현을 faq.md 키워드에 추가하면 된다.
    """
    # 질문에 줄바꿈/탭이 들어오면 로그 한 줄이 깨지므로 공백으로 바꿔서 저장한다.
    safe = " ".join(question.split())
    _append(MISS_LOG_FILE, f"{_now()}\t[{handled_by}]\t{safe}\n", "로그 기록")


def log_usage(user_id: int, category: str) -> None:
    """모든 질문을 통계용으로 기록한다 (질문 본문 없이 사용자ID + 결과만 → 가볍고 프라이버시 최소화).

    category: 'hit:<주제명>'(키워드 매칭 성공) / 'claude'(LLM이 답함) / 'nomatch'(둘 다 실패)
    """
    _append(STATS_LOG_FILE, f"{_now()}\t{user_id}\t{category}\n", "통계 기록")


def collect_stats() -> dict:
    """stats.log를 읽어 집계 결과를 dict로 반환. 파일이 없으면 total=0인 빈 결과."""
    try:
        with open(STATS_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    users = set()
    topic_counts: dict[str, int] = {}
    hit = claude = nomatch = 0
    total = 0  # 형식이 올바른 줄만 센다 (아래 주석 참고)

    for line in lines:
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 3:
            continue
        total += 1
        _, user_id, category = parts
        users.add(user_id)
        if category.startswith("hit:"):
            hit += 1
            topic = category.split(":", 1)[1]
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        elif category == "nomatch":
            nomatch += 1
        else:
            claude += 1  # llm.PROVIDER 값 (claude, openai 등)

    top_topics = sorted(topic_counts.items(), key=lambda x: -x[1])[:5]

    # total을 len(lines)로 세면 빈 줄이나 깨진 줄까지 질문 수에 포함돼서
    # 아래 hit/claude/nomatch의 합과 숫자가 안 맞는다(운영진이 보면 혼란).
    # 위에서 유효한 줄만 센 total을 쓴다.
    return {
        "total": total,
        "unique_users": len(users),
        "hit": hit,
        "claude": claude,
        "nomatch": nomatch,
        "top_topics": top_topics,
    }


def format_stats_markdown(stats: dict) -> str:
    """디스코드 메시지용 (마크다운 굵게 사용)."""
    top = stats["top_topics"]
    top_str = "\n".join(f"  {i+1}. {t} ({c}회)" for i, (t, c) in enumerate(top)) or "  (아직 없음)"
    return (
        "**📊 해커톤 FAQ 봇 사용 통계**\n"
        f"- 총 질문 수: **{stats['total']}건**\n"
        f"- 사용한 인원(중복 제외): **{stats['unique_users']}명**\n"
        f"- 키워드로 바로 답함: {stats['hit']}건 / LLM이 답함: {stats['claude']}건 / 못 찾음: {stats['nomatch']}건\n\n"
        f"**🔥 인기 주제 TOP5**\n{top_str}"
    )


def format_stats_plain(stats: dict) -> str:
    """터미널(VS Code 등)용 (마크다운 기호 없이 보기 좋게)."""
    top = stats["top_topics"]
    top_str = "\n".join(f"  {i+1}. {t} ({c}회)" for i, (t, c) in enumerate(top)) or "  (아직 없음)"
    return (
        "=== 해커톤 FAQ 봇 사용 통계 ===\n"
        f"총 질문 수        : {stats['total']}건\n"
        f"사용 인원(중복제외) : {stats['unique_users']}명\n"
        f"키워드로 바로 답함   : {stats['hit']}건\n"
        f"LLM이 답함        : {stats['claude']}건\n"
        f"못 찾음           : {stats['nomatch']}건\n\n"
        f"[인기 주제 TOP5]\n{top_str}"
    )


def compute_stats() -> str:
    """디스코드 /해커톤통계 명령에서 쓰는 요약 문자열 (마크다운 포함)."""
    stats = collect_stats()
    if stats["total"] == 0:
        return "아직 기록된 질문이 없어요."
    return format_stats_markdown(stats)
