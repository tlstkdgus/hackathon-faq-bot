# -*- coding: utf-8 -*-
"""
paths.py — 프로젝트가 쓰는 파일 경로를 한곳에서 정한다.

왜 필요한가:
    예전에는 코드 곳곳에서 "faq.md", "stats.log" 처럼 상대경로를 썼다.
    상대경로는 "현재 작업 디렉터리(cwd)" 기준이라, 실행 위치가 달라지면
    엉뚱한 곳을 보게 된다. 로컬에서 `python bot.py`로 실행할 땐 우연히
    맞아떨어지지만, 서버에서 systemd로 띄우면 cwd가 `/` 가 되어
    faq.md를 못 찾고 "FAQ 0개 로드" 상태로 조용히 실행된다.
    (에러도 안 나서 원인 찾기가 제일 어려운 종류의 버그다.)

    그래서 여기서 __file__ 기준 절대경로로 못 박는다. 어디서 실행하든 동일하다.

DATA_DIR:
    로그 파일(stats.log, unanswered.log)만 따로 다른 폴더에 두고 싶을 때
    .env에 DATA_DIR=/var/lib/faq-bot 처럼 지정하면 된다.
    지정 안 하면 프로젝트 폴더에 그대로 쌓인다(기존 동작과 동일).
    서버에서 git pull로 코드를 업데이트해도 로그가 안전하게 남는 장점이 있다.

discord 의존성 없음 → 단독 테스트 가능.
"""

import os
from pathlib import Path

# 이 파일이 있는 폴더 = 프로젝트 루트
BASE_DIR = Path(__file__).resolve().parent

# 로그 등 "실행하면서 쌓이는 데이터"를 둘 폴더 (기본: 프로젝트 루트)
DATA_DIR = Path(os.environ.get("DATA_DIR") or BASE_DIR).expanduser().resolve()

# FAQ 원본 (코드와 함께 git으로 관리되는 파일이라 항상 BASE_DIR)
FAQ_FILE = BASE_DIR / "faq.md"

# 실행 중 생성되는 파일들 (git에 올리지 않음 — .gitignore 참고)
MISS_LOG_FILE = DATA_DIR / "unanswered.log"   # 키워드로 못 잡은 질문
STATS_LOG_FILE = DATA_DIR / "stats.log"       # 사용 통계

# 일일 다이제스트를 마지막으로 보낸 시각을 적어두는 파일.
# 이게 있어야 봇이 잠깐 꺼졌다 켜져도 그 사이 질문을 빠뜨리지 않고,
# 하루에 두 번 실행돼도 같은 내용을 중복 전송하지 않는다.
DIGEST_STATE_FILE = DATA_DIR / "digest_state.txt"


def ensure_data_dir() -> None:
    """DATA_DIR이 없으면 만든다. 로그를 처음 쓰기 전에 한 번 호출하면 된다."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # 권한 문제 등 — 로그를 못 남길 뿐 봇은 계속 동작해야 한다
        print(f"⚠️ 데이터 폴더({DATA_DIR})를 만들지 못했습니다: {e}")
