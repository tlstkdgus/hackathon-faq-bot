#!/usr/bin/env bash
#
# update.sh — 서버에서 최신 코드를 받아 봇을 재시작한다.
#
# 사용법 (서버에서):
#   cd ~/hackathon-faq-bot && bash deploy/update.sh
#
# faq.md만 고쳤을 때는 재시작 없이 디스코드에서 `!리로드` 명령을 써도 된다.
# (봇이 안 끊기므로 그쪽이 더 부드럽다)

set -euo pipefail

SERVICE_NAME="faq-bot"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

# 봇이 실제로 떴는지 확인하는 헬퍼 (wait_until_ready / restart_mark / show_startup_log)
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

info() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[1;32m✔\033[0m %s\n' "$*"; }

cd "$PROJECT_DIR"

info "1/3  최신 코드 받기"
# .env는 .gitignore에 있으므로 git pull이 덮어쓰지 않는다.
git pull --ff-only
ok "$(git log -1 --pretty='%h %s')"

info "2/3  의존성 갱신"
"$VENV_DIR/bin/pip" install --quiet --upgrade -r requirements.txt
ok "완료"

info "3/3  재시작"
SINCE="$(restart_mark)"
sudo systemctl restart "$SERVICE_NAME"

printf '    디스코드 로그인 대기 중 (최대 %s초)...\n' "$READY_TIMEOUT"
if wait_until_ready "$SERVICE_NAME" "$SINCE"; then
    ok "봇이 디스코드에 로그인했습니다"
    echo
    # 이번 기동의 로그. FAQ 항목 수·질문 채널 등 현재 설정이 여기 찍힌다.
    show_startup_log "$SERVICE_NAME" "$SINCE"
else
    printf '\n\033[1;31m✘ 봇이 정상 기동하지 못했습니다. 이번 기동 로그:\033[0m\n\n'
    show_startup_log "$SERVICE_NAME" "$SINCE"
    printf '\n\033[1;31m  (재시작 루프에 빠졌다면 systemctl status %s 도 확인하세요)\033[0m\n' "$SERVICE_NAME"
    exit 1
fi
