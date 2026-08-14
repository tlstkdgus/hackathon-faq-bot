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


def log_miss(question: str, handled_by: str, user_id: int | None = None) -> None:
    """키워드로 못 잡은 질문을 로그 파일에 남긴다.

    handled_by: 실제로 답한 백엔드 이름('openai'·'claude' 등) 또는 'nomatch'(아무도 못 답함).
    운영진은 이 로그를 보고 자주 나오는 표현을 faq.md 키워드에 추가하면 된다.

    user_id를 같은 줄에 함께 남기는 이유: 예전에는 질문 원문(이 파일)과
    사용자ID(stats.log)가 다른 파일로 나뉘어 있어서, "이 질문 누가 했지?"를
    확인하려면 두 파일을 시각으로 대조해야 했다. 같은 초에 여러 명이 물으면
    누가 누군지 가릴 수도 없었다. 어차피 시각 대조로 복원되는 정보라
    분리가 실질적인 보호가 되지도 못했으므로, 차라리 한 줄에 두고
    조회를 정확하게 만든다. (파일 자체가 운영진 전용이고 커밋 금지 대상)
    """
    # 질문에 줄바꿈/탭이 들어오면 로그 한 줄이 깨지므로 공백으로 바꿔서 저장한다.
    safe = " ".join(question.split())
    who = "-" if user_id is None else str(user_id)
    _append(MISS_LOG_FILE, f"{_now()}\t[{handled_by}]\t{who}\t{safe}\n", "로그 기록")


def log_usage(user_id: int, category: str, question: str = "") -> None:
    """모든 질문을 기록한다. stats.log가 질문의 전체 기록이 된다.

    category: 'hit:<주제명>'(키워드 매칭 성공) / 백엔드 이름('openai'·'claude') / 'nomatch'(둘 다 실패)

    예전에는 질문 본문 없이 사용자ID + 결과만 남겼다. 그래서 키워드로 답한
    질문은 "누가 어떤 주제를 물었다"까지만 알 수 있고 문장은 복원할 수 없었다.
    행사 회고와 다음 기수 FAQ 준비에 원문이 필요하다는 판단으로 함께 남긴다.
    (학생 공지에 "질문 내용과 질문한 사람이 기록된다"고 이미 안내돼 있다.)

    unanswered.log와 겹치는 부분이 생기지만, 그쪽은 '키워드가 못 잡은 질문'만
    모아 digest가 읽는 파일이라 목적이 다르다. 여기는 전수 기록이다.
    """
    # 질문에 줄바꿈/탭이 들어오면 로그 한 줄이 깨지므로 공백으로 바꿔서 저장한다.
    safe = " ".join(question.split())
    _append(STATS_LOG_FILE, f"{_now()}\t{user_id}\t{category}\t{safe}\n", "통계 기록")


def search_questions(keyword: str = "", limit: int = 30, misses_only: bool = False) -> list:
    """질문을 찾아 (시각, 처리주체, 사용자ID, 질문) 목록으로 돌려준다.

    기본은 stats.log(전수 기록)를 본다. misses_only=True면 unanswered.log만 본다.
    keyword가 비어 있으면 최근 것부터 전부. 대소문자·공백은 무시하고 비교한다.

    원문이 없던 시절에 쌓인 줄은 question이 빈 문자열로 나온다.
    """
    path = MISS_LOG_FILE if misses_only else STATS_LOG_FILE
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []

    needle = "".join(keyword.lower().split())
    out = []
    for line in lines:
        parts = line.rstrip("\n").split("\t")
        if misses_only:
            # unanswered.log — 3칸(구) / 4칸(신)
            if len(parts) == 3:
                ts, handled, question = parts
                user_id = None
            elif len(parts) == 4:
                ts, handled, raw_id, question = parts
                user_id = None if raw_id == "-" else raw_id
            else:
                continue
            handled = handled.strip("[]")
        else:
            # stats.log — 3칸(구, 원문 없음) / 4칸(신)
            if len(parts) == 3:
                ts, user_id, handled = parts
                question = ""
            elif len(parts) == 4:
                ts, user_id, handled, question = parts
            else:
                continue

        if needle and needle not in "".join(question.lower().split()):
            continue
        out.append((ts, handled, user_id, question))

    # 최근 것이 위로 오게. 로그는 시간순으로 덧붙여지므로 뒤집으면 된다.
    out.reverse()
    return out[:limit]


def format_questions_plain(rows: list, misses_only: bool = False) -> str:
    """search_questions() 결과를 터미널에서 보기 좋게."""
    if not rows:
        return "조건에 맞는 질문이 없어요."
    lines = []
    for ts, handled, user_id, question in rows:
        who = user_id or "기록 없음(사용자ID 도입 전)"
        # 원문이 없는 옛 기록은 그 사실을 분명히 알려준다.
        # 빈칸으로 두면 "질문을 안 했다"처럼 읽힌다.
        text = question or "(원문 미기록 — 원문 저장 도입 전)"
        lines.append(f"{ts}  [{handled}]\n  질문   : {text}\n  사용자ID: {who}")
    tail = [
        "\n※ 사용자ID로 사람을 찾으려면 디스코드 설정 → 고급 → 개발자 모드를 켠 뒤",
        "  서버 멤버 목록에서 검색하거나, 검색창에 ID를 붙여넣으세요.",
    ]
    if misses_only:
        tail.append("※ 키워드로 못 잡은 질문만 보고 있습니다. 전체는 --전체 로 보세요.")
    return "\n\n".join(lines) + "\n" + "\n".join(tail)


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
        # 3칸(구): 시각 / 사용자ID / 결과
        # 4칸(신): 시각 / 사용자ID / 결과 / 질문 원문
        # 질문 원문이 추가되기 전에 쌓인 줄도 그대로 집계해야 한다.
        # 3칸만 받으면 기존 기록이 통째로 버려져 통계가 조용히 0으로 나온다.
        parts = line.rstrip("\n").split("\t")
        if len(parts) not in (3, 4):
            continue
        total += 1
        user_id, category = parts[1], parts[2]
        users.add(user_id)
        if category.startswith("hit:"):
            hit += 1
            topic = category.split(":", 1)[1]
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        elif category == "nomatch":
            nomatch += 1
        else:
            claude += 1  # 백엔드 이름이 그대로 들어온다 (openai, claude 등)

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
