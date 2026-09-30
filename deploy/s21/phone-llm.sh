#!/usr/bin/env bash
# 모델(llama-server)만 S21 Ultra(Termux)에서 돌리고, 노트북 웹은 ssh 터널로 붙는다 — 노트북 발열을 폰으로 옮기는 구성(2026-09-30).
#   노트북 127.0.0.1:18097  ──ssh -L──▶  S21 127.0.0.1:8097 (llama-server, 빅코어 4~7에 4스레드)
# 웹(run.sh)은 LLAMA_PORT가 이미 응답하면 로컬 llama-server를 띄우지 않으므로 코드 수정 없이 `LLAMA_PORT=18097 ./run.sh` 그대로 쓴다.
# 폰 준비(한 번): Termux `pkg install llama-cpp` + ~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf. ssh 별칭 `s21`(~/.ssh/config, Termux sshd 8022).
# 사용: phone-llm.sh up | down | status
set -u
HOST="${PHONE_HOST:-s21}"
LOCAL_PORT="${LLAMA_PORT:-18097}"
PHONE_PORT=8097
MODEL='~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf'
# Exynos 2100 = A55 4개(cpu0~3) + A78 3개(cpu4~6) + X1 1개(cpu7). 폰에서 8스레드는 리틀코어가 벽이 돼 생성이 붕괴한다
# (Note20 실측 tg 0.13 → 빅코어 4스레드 9.21 tok/s, ~/projects/03-personal/sllm-machine/bench/스레드-설정-실측.md).
CORES="${PHONE_CORES:-4-7}"; THREADS="${PHONE_THREADS:-4}"

rsh() { ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" "$@" 2>&1 | grep -v '^WARNING'; }
local_owner() { ss -ltnpH "sport = :$LOCAL_PORT" 2>/dev/null | grep -o 'users:(("[^"]*",pid=[0-9]*' | head -1; }
local_pid() { local_owner | grep -o 'pid=[0-9]*' | cut -d= -f2; }

phone_up() {
  rsh "termux-wake-lock >/dev/null 2>&1; cd ~
    if curl -s -m 3 localhost:$PHONE_PORT/health | grep -q ok; then echo '폰 llama-server 이미 떠 있음'; exit 0; fi
    ( setsid nohup taskset -c $CORES llama-server -m $MODEL --host 127.0.0.1 --port $PHONE_PORT -c 2048 -t $THREADS \
        > ~/panjeong-llm.log 2>&1 < /dev/null & echo \$! > ~/panjeong-llm.pid )
    for i in \$(seq 1 90); do curl -s -m 2 localhost:$PHONE_PORT/health | grep -q ok && { echo \"폰 llama-server 시작 (PID \$(cat ~/panjeong-llm.pid), \${i}초)\"; exit 0; }; sleep 1; done
    echo '폰 llama-server 90초 안에 안 뜸 — ~/panjeong-llm.log 확인'; tail -5 ~/panjeong-llm.log; exit 1"
}

tunnel_up() {
  local owner; owner="$(local_owner)"
  case "$owner" in
    *'"ssh"'*) echo "터널 이미 있음 (127.0.0.1:$LOCAL_PORT, PID $(local_pid))"; return 0 ;;
    *'"llama-server"'*) echo "노트북 로컬 llama-server가 $LOCAL_PORT를 잡고 있음 → 끈다 (PID $(local_pid))"; kill "$(local_pid)"; sleep 1 ;;
    '') ;;
    *) echo "127.0.0.1:$LOCAL_PORT 주인이 예상 밖: $owner — 손대지 않음"; return 1 ;;
  esac
  ssh -f -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
      -L "127.0.0.1:$LOCAL_PORT:127.0.0.1:$PHONE_PORT" "$HOST" 2>&1 | grep -v '^WARNING'
  curl -s -m 5 "localhost:$LOCAL_PORT/health" | grep -q ok && echo "터널 연결 127.0.0.1:$LOCAL_PORT → $HOST:$PHONE_PORT (PID $(local_pid))" \
    || { echo "터널 뒤 health 실패"; return 1; }
}

status() {
  echo "노트북 $LOCAL_PORT: $(local_owner || true)"
  echo "터널 경유 health: $(curl -s -m 5 "localhost:$LOCAL_PORT/health" || echo 응답없음)"
  rsh "echo \"폰 health: \$(curl -s -m 3 localhost:$PHONE_PORT/health || echo 응답없음)\"; [ -f ~/panjeong-llm.pid ] && ps -o pid,etime,args -p \$(cat ~/panjeong-llm.pid) 2>/dev/null | tail -n +2 | cut -c1-120"
}

case "${1:-status}" in
  up) phone_up && tunnel_up ;;
  down)
    case "$(local_owner)" in *'"ssh"'*) kill "$(local_pid)" && echo "터널 닫음" ;; esac
    rsh '[ -f ~/panjeong-llm.pid ] && kill $(cat ~/panjeong-llm.pid) 2>/dev/null && echo "폰 llama-server 끔"; rm -f ~/panjeong-llm.pid; termux-wake-unlock >/dev/null 2>&1; true' ;;
  status) status ;;
  *) echo "사용: $0 up | down | status"; exit 2 ;;
esac
