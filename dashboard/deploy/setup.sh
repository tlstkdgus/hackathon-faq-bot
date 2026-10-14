#!/usr/bin/env bash
#
# setup.sh — 봇이 돌고 있는 오라클 서버에 운영 현황판을 띄운다.
#
# 사용법 (서버에 SSH로 접속한 뒤, 봇 저장소 폴더에서):
#   cd ~/hackathon-faq-bot
#   git pull
#   bash dashboard/deploy/setup.sh
#
# 여러 번 실행해도 안전하다. 코드를 갱신한 뒤 다시 실행하면 화면을 새로 빌드하고 재시작한다.
#
# 도커를 쓰지 않는 이유:
#   무료 AMD 인스턴스는 RAM이 1GB라, 도커 데몬 + 이미지 빌드를 올리기엔 빠듯하다.
#   봇과 같은 가상환경에 FastAPI만 더 깔고 uvicorn 하나로 화면까지 내보내면
#   메모리를 거의 더 쓰지 않는다. (도커 구성은 dashboard/docker-compose*.yml에 따로 있다)

set -euo pipefail

SERVICE_NAME="faq-dashboard"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
WEB_DIR="$PROJECT_DIR/dashboard/web"
ENV_FILE="$PROJECT_DIR/dashboard/.env.server"
PORT=8080
RUN_USER="$(id -un)"
RUN_GROUP="$(id -gn)"

info()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()    { printf '    \033[1;32m✔\033[0m %s\n' "$*"; }
warn()  { printf '    \033[1;33m!\033[0m %s\n' "$*"; }
die()   { printf '\n\033[1;31m✘ %s\033[0m\n' "$*" >&2; exit 1; }

# ─────────────────────────────────────────────────────────────
info "1/5  환경 확인"
# ─────────────────────────────────────────────────────────────
[ "$(id -u)" -ne 0 ] || die "root(sudo)로 실행하지 마세요. 'bash dashboard/deploy/setup.sh' 로 실행하세요."
[ -x "$VENV_DIR/bin/python" ] || die "봇 가상환경($VENV_DIR)이 없습니다. 먼저 'bash deploy/setup.sh'로 봇을 설치하세요."
ok "프로젝트 폴더: $PROJECT_DIR"

# ─────────────────────────────────────────────────────────────
info "2/5  파이썬 패키지 (FastAPI, uvicorn)"
# ─────────────────────────────────────────────────────────────
# 봇과 같은 가상환경에 설치한다. 봇이 쓰는 패키지와 겹치지 않는다.
"$VENV_DIR/bin/pip" install --quiet "fastapi>=0.115" "uvicorn>=0.30"
ok "설치 완료"

# ─────────────────────────────────────────────────────────────
info "3/5  화면 빌드 (React)"
# ─────────────────────────────────────────────────────────────
# Vite 5는 Node 18 이상이 필요하다. 우분투 기본 apt의 nodejs는 너무 오래돼서
# NodeSource 저장소의 Node 20을 쓴다. 이미 18 이상이 있으면 건너뛴다.
node_ok() {
    command -v node >/dev/null 2>&1 && [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 18 ]
}
if node_ok; then
    ok "node $(node -v)"
else
    warn "Node 18 이상이 없습니다. Node 20을 설치합니다 (약 1~2분)"
    export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a NEEDRESTART_SUSPEND=1
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - >/dev/null
    sudo -E apt-get install -y -qq nodejs >/dev/null
    node_ok || die "Node 설치에 실패했습니다. 'node -v'로 확인해 주세요."
    ok "node $(node -v) 설치 완료"
fi

# RAM 1GB 서버에서는 빌드가 1~3분 걸린다 (봇 setup.sh가 만든 스왑 2GB를 쓴다).
(
    cd "$WEB_DIR"
    npm ci --no-audit --no-fund --loglevel=error
    npm run build --silent
)
[ -f "$WEB_DIR/dist/index.html" ] || die "화면 빌드 결과(dist/index.html)가 없습니다."
ok "빌드 완료: dashboard/web/dist"

# ─────────────────────────────────────────────────────────────
info "4/5  설정 파일 (.env.server)"
# ─────────────────────────────────────────────────────────────
# 봇 .env에 DATA_DIR이 있으면 같은 곳을 본다. 없으면 봇 저장소 폴더(봇의 기본값).
BOT_DATA_DIR="$(grep -E '^DATA_DIR=' "$PROJECT_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
BOT_DATA_DIR="${BOT_DATA_DIR:-$PROJECT_DIR}"

if [ ! -f "$ENV_FILE" ]; then
    TOKEN="$("$VENV_DIR/bin/python" -c 'import secrets; print(secrets.token_urlsafe(24))')"
    SALT="$("$VENV_DIR/bin/python" -c 'import secrets; print(secrets.token_hex(16))')"
    cat > "$ENV_FILE" <<EOF
# 운영 현황판 서버 설정 (setup.sh가 만듦, git에 올리지 않음)
DASHBOARD_TOKEN=$TOKEN
DASHBOARD_ID_SALT=$SALT
DATA_DIR=$BOT_DATA_DIR
WEB_DIST=$WEB_DIR/dist
EOF
    ok "새로 만들었습니다 (접근 토큰 자동 생성)"
else
    ok "이미 있음 — 기존 토큰을 그대로 씁니다"
fi
chmod 600 "$ENV_FILE"   # 토큰이 들어 있으므로 본인만 읽게
ok "로그 폴더: $(grep -E '^DATA_DIR=' "$ENV_FILE" | cut -d= -f2-)"

# ─────────────────────────────────────────────────────────────
info "5/5  서비스 등록 및 시작"
# ─────────────────────────────────────────────────────────────
sed -e "s|^User=.*|User=$RUN_USER|" \
    -e "s|^Group=.*|Group=$RUN_GROUP|" \
    -e "s|^WorkingDirectory=.*|WorkingDirectory=$PROJECT_DIR|" \
    -e "s|^ExecStart=.*|ExecStart=$VENV_DIR/bin/uvicorn app.main:app --app-dir dashboard/api --host 127.0.0.1 --port $PORT|" \
    -e "s|^EnvironmentFile=.*|EnvironmentFile=$ENV_FILE|" \
    "$PROJECT_DIR/dashboard/deploy/faq-dashboard.service" | sudo tee "/etc/systemd/system/$SERVICE_NAME.service" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
sudo systemctl restart "$SERVICE_NAME"

# systemctl is-active만으로는 '뜨자마자 죽는' 경우를 못 거른다 (봇에서 겪은 함정).
# 실제로 /api/health가 응답하고, 로그 파일까지 보이는지 확인한다.
printf '    현황판 응답 대기 중'
HEALTH=""
for _ in $(seq 1 30); do
    if HEALTH="$(curl -fsS "http://127.0.0.1:$PORT/api/health" 2>/dev/null)"; then break; fi
    printf '.'; sleep 1
done
echo
if [ -z "$HEALTH" ]; then
    warn "현황판이 응답하지 않습니다. 로그:"
    sudo journalctl -u "$SERVICE_NAME" -n 30 --no-pager
    exit 1
fi
ok "현황판 동작 중: $HEALTH"
echo "$HEALTH" | grep -q '"stats_log":true' || warn "stats.log를 찾지 못했습니다. .env.server의 DATA_DIR을 확인하세요."

TOKEN="$(grep -E '^DASHBOARD_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
PUBLIC_IP="$(curl -fsS --max-time 3 https://ifconfig.me 2>/dev/null || echo '<서버 IP>')"
cat <<EOF

  ✅ 현황판이 서버 안(127.0.0.1:$PORT)에서 돌고 있습니다.
     밖에서는 SSH 터널로만 볼 수 있습니다 (방화벽 포트를 열지 않습니다).

  내 컴퓨터에서:
     1) 터미널에서 (평소 서버 접속 명령에 -L 옵션만 붙이면 됩니다)
        ssh -L $PORT:127.0.0.1:$PORT $RUN_USER@$PUBLIC_IP
     2) 그 창을 켜 둔 채로 브라우저에서
        http://localhost:$PORT/?token=$TOKEN

  관리:
     로그 보기 : journalctl -u $SERVICE_NAME -f
     재시작    : sudo systemctl restart $SERVICE_NAME
     중지      : sudo systemctl stop $SERVICE_NAME
     코드 갱신 : git pull && bash dashboard/deploy/setup.sh

EOF
