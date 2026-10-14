# -*- coding: utf-8 -*-
"""
config.py — 현황판 API가 읽을 파일 위치를 한곳에서 정한다.

봇과 같은 규칙을 따른다:
    - 로그(stats.log, unanswered.log)는 DATA_DIR에 있다. (봇의 .env와 같은 값)
    - faq.md와 봇 모듈(faq_engine.py, digest.py)은 BOT_ROOT에 있다.

로컬에서는 저장소 루트가 곧 BOT_ROOT라 아무것도 설정하지 않아도 된다.
도커에서는 Dockerfile이 봇 모듈을 /app/bot에 복사하고 BOT_ROOT를 지정한다.
"""

import os
import sys
from pathlib import Path

# dashboard/api/app/config.py 기준으로 세 단계 위 = 저장소 루트
_REPO_ROOT = Path(__file__).resolve().parents[3]

BOT_ROOT = Path(os.environ.get("BOT_ROOT") or _REPO_ROOT).expanduser().resolve()
DATA_DIR = Path(os.environ.get("DATA_DIR") or BOT_ROOT).expanduser().resolve()

STATS_LOG_FILE = DATA_DIR / "stats.log"
MISS_LOG_FILE = DATA_DIR / "unanswered.log"
FAQ_FILE = BOT_ROOT / "faq.md"

# git 기록에서 뽑아 둔 'FAQ 항목 수 추이' (scripts/build_faq_history.py가 만든다)
FAQ_HISTORY_FILE = Path(
    os.environ.get("FAQ_HISTORY_FILE") or Path(__file__).resolve().parent / "data" / "faq_history.json"
)

# 빌드된 화면(dashboard/web/dist)을 API 서버가 직접 내보낼지.
# 서버에 nginx·도커 없이 uvicorn 하나로 띄울 때 쓴다 (dashboard/deploy/setup.sh).
# 폴더가 없으면 화면은 내보내지 않고 API만 동작한다 (도커에서는 nginx가 화면을 맡는다).
WEB_DIST = Path(os.environ.get("WEB_DIST") or _REPO_ROOT / "dashboard" / "web" / "dist")

# 사용자 ID는 화면에 그대로 내보내지 않는다. 같은 사람인지만 구분되도록
# 이 값을 섞어 해시한 짧은 별칭으로 바꾼다. 배포할 때는 .env에서 바꿔 두는 게 좋다.
ID_SALT = os.environ.get("DASHBOARD_ID_SALT", "faq-bot-dashboard")

# 개발 중 Vite 서버(5173)에서 API를 부를 수 있게 허용할 출처
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

# 봇 모듈(faq_engine, digest)을 그대로 재사용하기 위해 import 경로에 추가한다.
# 같은 로직을 복사해 두면 봇과 현황판의 판정 기준이 어긋나기 쉽다.
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))
