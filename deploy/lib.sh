#!/usr/bin/env bash
#
# lib.sh — setup.sh / update.sh가 함께 쓰는 헬퍼.
#
# 이 파일은 직접 실행하지 않고 `source` 해서 쓴다.
#     source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# ── 봇이 실제로 떴는지 확인하기 ──────────────────────────────────
#
# 예전에는 재시작 3초 뒤 `systemctl is-active` 하나로 판정했다. 두 가지가 틀렸다.
#
#   1) 봇이 디스코드에 로그인하기까지 보통 5~15초가 걸린다. 3초 시점의
#      is-active는 "아직 안 죽었다"는 뜻일 뿐이다. 토큰이 틀려서 뜨자마자
#      죽는 경우에도 systemd가 곧바로 재시작하므로 그 순간엔 active로 보인다.
#      → 배포는 초록불인데 봇은 죽어 있는 상태가 된다.
#
#   2) 같은 시점에 찍던 `journalctl -n 15`에는 새 기동 로그가 아직 없어서
#      '직전 기동'의 로그가 나왔다. 실제로 이 로그를 보고 설정이 안 바뀐 줄
#      착각한 적이 있다. 배포 로그로 현재 상태를 판단할 수 없었던 것이다.
#
# 그래서 재시작 시각 이후의 저널만 보면서 '로그인 성공'이 찍히기를 기다린다.
# 재시작 루프에 빠진 봇은 이 줄을 영영 못 찍으므로 타임아웃으로 걸러진다.
#
# 사용법:  wait_until_ready <서비스명> <재시작-기준시각> [타임아웃초]
# 반환값:  0 = 로그인 확인, 1 = 실패(타임아웃 또는 서비스 죽음)

# bot.py가 기동 성공 시 찍는 문구. bot.py의 on_ready() 출력과 맞춰야 한다.
# (문구를 바꾸면 여기도 바꿀 것 — 안 그러면 멀쩡한 배포가 실패로 뜬다)
READY_PATTERN='로그인 성공'

# 로그인까지 기다려줄 최대 시간(초). 디스코드 응답이 느린 날을 감안해 넉넉히 잡는다.
READY_TIMEOUT="${READY_TIMEOUT:-60}"


restart_mark() {
    # journalctl --since 에 넘길 기준 시각. 1초 여유를 둬서 경계에서
    # 새 로그를 놓치지 않게 한다.
    date '+%Y-%m-%d %H:%M:%S' -d '1 second ago'
}


wait_until_ready() {
    local service="$1"
    local since="$2"
    local timeout="${3:-$READY_TIMEOUT}"
    local i

    for ((i = 0; i < timeout; i++)); do
        if sudo journalctl -u "$service" --since "$since" --no-pager 2>/dev/null \
            | grep -q "$READY_PATTERN"; then
            return 0
        fi
        # 서비스가 아예 내려갔으면 더 기다릴 이유가 없다.
        # (재시작 루프 중이면 active로 보이므로 여기서는 안 걸리고,
        #  위의 타임아웃이 대신 잡아준다.)
        if ! systemctl is-active --quiet "$service"; then
            return 1
        fi
        sleep 1
    done
    return 1
}


show_startup_log() {
    # 이번 기동의 로그만 보여준다. -n 으로 자르면 또 직전 기동이 섞인다.
    local service="$1"
    local since="$2"
    sudo journalctl -u "$service" --since "$since" --no-pager
}
