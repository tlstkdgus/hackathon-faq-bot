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
sudo systemctl restart "$SERVICE_NAME"
sleep 3

if systemctl is-active --quiet "$SERVICE_NAME"; then
    ok "봇이 정상 실행 중입니다"
    echo
    sudo journalctl -u "$SERVICE_NAME" -n 15 --no-pager
else
    printf '\n\033[1;31m✘ 봇이 시작되지 못했습니다. 로그:\033[0m\n\n'
    sudo journalctl -u "$SERVICE_NAME" -n 40 --no-pager
    exit 1
fi
