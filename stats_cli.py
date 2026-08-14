# -*- coding: utf-8 -*-
"""
stats_cli.py — 디스코드 안 켜고 터미널(VS Code 등)에서 바로 기록 확인.

사용법:
    python stats_cli.py                  # 전체 사용 통계 요약
    python stats_cli.py --질문           # 지금까지 들어온 질문 원문 (최근순)
    python stats_cli.py --질문 가비아     # 그중 '가비아'가 들어간 질문만
    python stats_cli.py --질문 -n 100    # 100건까지 보기 (기본 30)
    python stats_cli.py --미답변         # 키워드로 못 잡은 질문만

stats.log(전수 기록) / unanswered.log(못 잡은 질문)를 읽는다.
봇을 실행 중이 아니어도 로그 파일만 있으면 언제든 실행 가능.

⚠️ 출력에 학생 질문 원문과 사용자ID가 그대로 나온다. 운영진만 쓸 것.
"""

import sys

from stats_engine import (
    collect_stats,
    format_questions_plain,
    format_stats_plain,
    search_questions,
)

# 조회 모드 플래그. 한글/영문 둘 다 받는다.
ALL_FLAGS = {"--질문", "--전체", "--누가", "--all", "-a"}
MISS_FLAGS = {"--미답변", "--misses", "-m"}

DEFAULT_LIMIT = 30


def _take_limit(args: list) -> tuple:
    """`-n 100` 을 뽑아내고 나머지를 검색어로 돌려준다."""
    limit = DEFAULT_LIMIT
    rest = []
    i = 0
    while i < len(args):
        if args[i] in ("-n", "--개수") and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                print(f"⚠️ 개수는 숫자여야 합니다: {args[i + 1]!r} — 기본값 {DEFAULT_LIMIT}을 씁니다.")
            i += 2
            continue
        rest.append(args[i])
        i += 1
    return limit, " ".join(rest)


def main(argv: list) -> None:
    if argv and (argv[0] in ALL_FLAGS or argv[0] in MISS_FLAGS):
        misses_only = argv[0] in MISS_FLAGS
        limit, keyword = _take_limit(argv[1:])
        rows = search_questions(keyword, limit=limit, misses_only=misses_only)

        scope = "키워드로 못 잡은 질문" if misses_only else "전체 질문"
        if keyword:
            print(f"=== {scope} 중 '{keyword}' 포함 (최근순, 최대 {limit}건) ===\n")
        else:
            print(f"=== {scope} (최근순, 최대 {limit}건) ===\n")
        print(format_questions_plain(rows, misses_only=misses_only))
        return

    stats = collect_stats()
    if stats["total"] == 0:
        print("아직 기록된 질문이 없어요. (stats.log 파일이 없거나 비어 있음)")
    else:
        print(format_stats_plain(stats))
        print("\n질문 원문을 보려면: python stats_cli.py --질문")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 깨짐 방지

    main(sys.argv[1:])
