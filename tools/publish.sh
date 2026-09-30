#!/usr/bin/env bash
# 공개 시연 인스턴스 — mvp/의 스냅샷(../mvp-공개)을 Tailscale Funnel로 연다. 로컬 mvp/와 DB는 건드리지 않는다.
#   tools/publish.sh          코드·템플릿·정적 파일만 스냅샷에 반영(데이터는 그대로) → 서비스 재시작 → Funnel 켜기
#   tools/publish.sh down     Funnel 끄기 + 서비스 중지(절전 방지도 같이 풀린다)
#   tools/publish.sh reset    공개본 DB·업로드·보고서를 비우고 재시작(건 목록 0건으로)
#   tools/publish.sh seed     비운 뒤 Gemini 영수증 10건(tools/seed_gemini.py)을 넣는다
#   tools/publish.sh status   서비스·Funnel 상태
# 스냅샷은 DB 없이 시작한다(건·판정·심판 큐·예외 사전·이력 모두 빈 상태). 모델은 로컬 판정관 llama-server(18097, Qwen2.5-1.5B)를 같이 쓴다 — 8097은 나비(MiniCPM)다.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PUB="$(dirname "$ROOT")/mvp-공개"
PORT=18180 FUNNEL=8443 UNIT=panjeong-public
URL="https://$(tailscale status --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))'):$FUNNEL"

case "${1:-up}" in
  down)
    tailscale funnel --https=$FUNNEL off || true
    systemctl --user stop $UNIT || true
    echo "내림 — $URL"; exit 0 ;;
  reset)
    systemctl --user stop $UNIT
    rm -rf "$PUB"/data/panjeong.db "$PUB"/data/panjeong.db-* "$PUB"/data/uploads "$PUB"/data/reports
    systemctl --user start $UNIT
    for _ in $(seq 1 30); do curl -sf -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 1; done
    echo "비움 — $URL"; exit 0 ;;
  seed)
    "$0" reset
    (cd "$PUB" && "$ROOT/.venv/bin/python" -m tools.seed_gemini)
    exit 0 ;;
  status)
    systemctl --user --no-pager status $UNIT | head -5 || true
    tailscale funnel status; exit 0 ;;
  up) ;;
  *) echo "사용법: $0 [up|down|reset|seed|status]" >&2; exit 2 ;;
esac

mkdir -p "$PUB"
# --delete는 제외 목록을 지우지 않는다 — 스냅샷의 DB·업로드·보고서는 반영해도 남는다
rsync -a --delete \
  --exclude .venv/ --exclude __pycache__/ --exclude .pytest_cache/ \
  --exclude /data/panjeong.db --exclude '/data/panjeong.db-*' --exclude /data/uploads/ --exclude /data/reports/ \
  --exclude '/data/*.log' \
  "$ROOT/" "$PUB/"
# 10-01 사용자: 공개본은 행정팀·심판 큐 칸을 뺀다 — project.json 스위치(내비·임시 승인·이의 신청 숨김, 라우트는 남는다)
python3 - "$PUB/data/project.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p, encoding="utf-8")); d["행정팀"] = False
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
PY

mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/$UNIT.service <<EOF
[Unit]
Description=연구비 판정관 공개 시연 ($URL)

[Service]
WorkingDirectory=$PUB
Environment=LLAMA_URL=http://127.0.0.1:18097
ExecStart=/usr/bin/systemd-inhibit --what=sleep:handle-lid-switch --who=$UNIT --why=공개시연 --mode=block $ROOT/.venv/bin/python -m uvicorn run:app --host 127.0.0.1 --port $PORT
Restart=on-failure
RestartSec=3
EOF
systemctl --user daemon-reload
systemctl --user restart $UNIT
for _ in $(seq 1 30); do curl -sf -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 1; done
curl -sf -o /dev/null "http://127.0.0.1:$PORT/" || { journalctl --user -u $UNIT -n 20 --no-pager; exit 1; }

tailscale funnel --bg --https=$FUNNEL "http://127.0.0.1:$PORT"
echo "공개 — $URL"
