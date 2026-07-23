# -*- coding: utf-8 -*-
"""
stats_engine.py — 질문 로그 기록/집계 로직.

discord 의존성 없음 → bot.py에서도, VS Code 터미널에서 돌리는
stats_cli.py에서도 그대로 재사용할 수 있다 (단독 테스트도 가능).
"""

import datetime

MISS_LOG_FILE = "unanswered.log"  # 키워드로 못 잡은 질문 기록 (운영진 FAQ 보강용)
STATS_LOG_FILE = "stats.log"  # 모든 질문 사용 기록 (통계용: 사용자ID + 결과만, 질문 본문 없음)


def log_miss(question: str, handled_by: str) -> None:
    """키워드로 못 잡은 질문을 로그 파일에 남긴다.

    handled_by: 'claude'(Claude가 대신 답함) 또는 'nomatch'(아무도 못 답함).
    운영진은 이 로그를 보고 자주 나오는 표현을 faq.md 키워드에 추가하면 된다.
    """
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts}\t[{handled_by}]\t{question}\n"
    try:
        with open(MISS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"⚠️ 로그 기록 실패: {e}")


def log_usage(user_id: int, category: str) -> None:
    """모든 질문을 통계용으로 기록한다 (질문 본문 없이 사용자ID + 결과만 → 가볍고 프라이버시 최소화).

    category: 'hit:<주제명>'(키워드 매칭 성공) / 'claude'(LLM이 답함) / 'nomatch'(둘 다 실패)
    """
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts}\t{user_id}\t{category}\n"
    try:
        with open(STATS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"⚠️ 통계 기록 실패: {e}")


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

    for line in lines:
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 3:
            continue
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

    return {
        "total": len(lines),
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
