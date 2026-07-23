# -*- coding: utf-8 -*-
"""
stats_cli.py — 디스코드 안 켜고 터미널(VS Code 등)에서 바로 사용 통계 확인.

사용법:
    python stats_cli.py

stats.log(질문 사용 기록)를 읽어서 요약해서 보여준다. 봇을 실행 중이 아니어도,
같은 폴더에 stats.log 파일만 있으면 언제든 실행 가능.
"""

import sys

from stats_engine import collect_stats, format_stats_plain

if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 깨짐 방지

    stats = collect_stats()
    if stats["total"] == 0:
        print("아직 기록된 질문이 없어요. (stats.log 파일이 없거나 비어 있음)")
    else:
        print(format_stats_plain(stats))
