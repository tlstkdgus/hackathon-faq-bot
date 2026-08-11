# -*- coding: utf-8 -*-
"""
stats_cli.py — 디스코드 안 켜고 터미널(VS Code 등)에서 바로 기록 확인.

사용법:
    python stats_cli.py                 # 전체 사용 통계 요약
    python stats_cli.py --누가          # 키워드로 못 잡은 질문 + 질문한 사람
    python stats_cli.py --누가 시연영상  # 그중 '시연영상'이 들어간 질문만

stats.log(질문 사용 기록) / unanswered.log(질문 원문 + 사용자ID)를 읽는다.
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

# '누가 물었는지' 조회 모드로 들어가는 플래그. 한글/영문 둘 다 받는다.
WHO_FLAGS = {"--누가", "--who", "-w"}


def main(argv: list) -> None:
    if argv and argv[0] in WHO_FLAGS:
        keyword = " ".join(argv[1:])
        rows = search_questions(keyword)
        if keyword:
            print(f"=== '{keyword}' 가 들어간 미답변 질문 (최근순) ===\n")
        else:
            print("=== 키워드로 못 잡은 질문 (최근순) ===\n")
        print(format_questions_plain(rows))
        return

    stats = collect_stats()
    if stats["total"] == 0:
        print("아직 기록된 질문이 없어요. (stats.log 파일이 없거나 비어 있음)")
    else:
        print(format_stats_plain(stats))
        print("\n누가 물었는지 보려면: python stats_cli.py --누가")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 깨짐 방지

    main(sys.argv[1:])
