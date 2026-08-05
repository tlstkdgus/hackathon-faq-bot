#!/usr/bin/env bash
#
# setup.sh — 오라클 클라우드(우분투 22.04+) 서버에 FAQ 봇을 설치한다.
#
# 사용법 (서버에 SSH로 접속한 뒤):
#   git clone https://github.com/tlstkdgus/hackathon-faq-bot.git
#   cd hackathon-faq-bot
#   bash deploy/setup.sh
#
# 여러 번 실행해도 안전하다(이미 된 건 건너뛴다).
# 자세한 배포 절차는 deploy/DEPLOY.md 참고.

set -euo pipefail

# -e : 명령이 실패하면 즉시 중단 (실패를 못 보고 지나치는 사고 방지)
# -u : 정의 안 된 변수를 쓰면 에러
# -o pipefail : 파이프 중간이 실패해도 실패로 처리

SERVICE_NAME="faq-bot"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
RUN_USER="$(id -un)"
RUN_GROUP="$(id -gn)"

info()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()    { printf '    \033[1;32m✔\033[0m %s\n' "$*"; }
warn()  { printf '    \033[1;33m!\033[0m %s\n' "$*"; }
die()   { printf '\n\033[1;31m✘ %s\033[0m\n' "$*" >&2; exit 1; }

# ─────────────────────────────────────────────────────────────
info "0/7  환경 확인"
# ─────────────────────────────────────────────────────────────

[ "$(id -u)" -ne 0 ] || die "root(sudo)로 실행하지 마세요. 일반 사용자로 'bash deploy/setup.sh' 하세요."
command -v apt-get >/dev/null 2>&1 || die "우분투/데비안 계열이 아닙니다. DEPLOY.md의 수동 설치를 참고하세요."
sudo -v || die "sudo 권한이 필요합니다."

ok "프로젝트 폴더: $PROJECT_DIR"
ok "실행 사용자  : $RUN_USER"

# ─────────────────────────────────────────────────────────────
info "1/7  시스템 패키지 설치"
# ─────────────────────────────────────────────────────────────

sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip git tzdata
ok "패키지 설치 완료"

# 이 프로젝트는 파이썬 3.10 이상이 필요하다 (bot.py 상단에서도 검사한다).
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,10) else 0)')
PY_VER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
[ "$PY_OK" = "1" ] || die "파이썬 3.10 이상이 필요합니다 (현재 $PY_VER). 우분투 22.04 이상을 사용하세요."
ok "python3 $PY_VER"

# ─────────────────────────────────────────────────────────────
info "2/7  서버 시간대를 한국시간으로"
# ─────────────────────────────────────────────────────────────

# 봇 코드 자체는 KST를 명시해서 쓰므로 이게 없어도 동작은 정상이다.
# 다만 journalctl 로그 시각이 UTC로 찍히면 사람이 보기 헷갈려서 맞춰둔다.
if [ "$(timedatectl show -p Timezone --value 2>/dev/null || echo)" = "Asia/Seoul" ]; then
    ok "이미 Asia/Seoul"
else
    sudo timedatectl set-timezone Asia/Seoul && ok "Asia/Seoul 로 변경"
fi

# ─────────────────────────────────────────────────────────────
info "3/7  스왑 메모리 확인"
# ─────────────────────────────────────────────────────────────

# 오라클 무료 티어 AMD 인스턴스는 RAM이 1GB뿐이라, pip 설치 중에
# 메모리가 모자라 프로세스가 죽는 일이 있다. 스왑 2GB를 만들어 예방한다.
if [ "$(swapon --show --noheadings | wc -l)" -gt 0 ]; then
    ok "스왑이 이미 있음"
elif [ -f /swapfile ]; then
    ok "/swapfile 이 이미 있음"
else
    warn "스왑이 없습니다. 2GB 스왑 파일을 만듭니다 (메모리 부족 방지)"
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile >/dev/null
    sudo swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
    ok "스왑 2GB 생성 (재부팅 후에도 유지)"
fi

# ─────────────────────────────────────────────────────────────
info "4/7  파이썬 가상환경 + 의존성"
# ─────────────────────────────────────────────────────────────

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    ok "가상환경 생성: $VENV_DIR"
else
    ok "가상환경이 이미 있음"
fi

"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"
ok "의존성 설치 완료"

# ─────────────────────────────────────────────────────────────
info "5/7  .env 파일 준비"
# ─────────────────────────────────────────────────────────────

ENV_FILE="$PROJECT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"   # 토큰이 들어가므로 본인만 읽게 제한
    warn ".env 파일을 새로 만들었습니다. 아직 토큰이 비어 있습니다!"
    NEEDS_TOKEN=1
else
    chmod 600 "$ENV_FILE"
    ok ".env 파일이 이미 있음"
    NEEDS_TOKEN=0
fi

# 토큰이 예시값 그대로면 봇을 시작하지 않는다 (시작해봐야 바로 죽는다).
if grep -qE '^DISCORD_TOKEN=(여기에_디스코드_봇_토큰)?$' "$ENV_FILE"; then
    NEEDS_TOKEN=1
fi

# ─────────────────────────────────────────────────────────────
info "6/7  systemd 서비스 등록"
# ─────────────────────────────────────────────────────────────

# 템플릿의 기본 경로/사용자를 실제 값으로 치환해서 설치한다.
# (경로에 /가 들어가므로 sed 구분자로 |를 쓴다)
sed -e "s|^User=.*|User=$RUN_USER|" \
    -e "s|^Group=.*|Group=$RUN_GROUP|" \
    -e "s|^WorkingDirectory=.*|WorkingDirectory=$PROJECT_DIR|" \
    -e "s|^ExecStart=.*|ExecStart=$VENV_DIR/bin/python $PROJECT_DIR/bot.py|" \
    "$PROJECT_DIR/deploy/faq-bot.service" | sudo tee "/etc/systemd/system/$SERVICE_NAME.service" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
ok "서비스 등록 완료 (부팅 시 자동 시작)"

# ─────────────────────────────────────────────────────────────
info "7/7  마무리"
# ─────────────────────────────────────────────────────────────

if [ "$NEEDS_TOKEN" = "1" ]; then
    cat <<EOF

  ⚠️  아직 봇을 시작하지 않았습니다. 토큰을 먼저 넣으세요.

     1) nano $ENV_FILE
        → DISCORD_TOKEN= 뒤에 디스코드 봇 토큰 붙여넣기
        → (선택) ANTHROPIC_API_KEY= 에 Claude API 키
        → Ctrl+O, Enter, Ctrl+X 로 저장 후 종료

     2) sudo systemctl start $SERVICE_NAME

     3) journalctl -u $SERVICE_NAME -f     ← 로그 확인 (Ctrl+C로 나가기)
        "✅ 로그인 성공" 이 보이면 성공입니다.

EOF
else
    sudo systemctl restart "$SERVICE_NAME"
    sleep 3
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        ok "봇이 실행 중입니다!"
        echo
        echo "  로그 보기 : journalctl -u $SERVICE_NAME -f"
        echo "  재시작    : sudo systemctl restart $SERVICE_NAME"
        echo "  중지      : sudo systemctl stop $SERVICE_NAME"
        echo
    else
        warn "봇이 시작되지 못했습니다. 아래 로그를 확인하세요:"
        echo
        sudo journalctl -u "$SERVICE_NAME" -n 30 --no-pager
        exit 1
    fi
fi
