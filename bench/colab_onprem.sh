#!/bin/bash
# Colab VM을 「온프레미스 판정관 기기」로 띄운다 (2026-09-27) — colab_cpu.sh가 받아 둔 llama.cpp·모델·번들을 그대로 쓴다.
# VM에서: THREADS=4 bash /content/colab_onprem.sh  → llama-server(8097, CPU THREADS개) + 웹(18080 — VM의 8080은 Colab node가 쓴다). 로그 /content/onprem.log
# 로컬에서 터널: ssh -N -L 18081:127.0.0.1:18080 -o ProxyCommand="colab ssh --proxy-mode -s <세션>" \
#   -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@colab-runtime   → http://127.0.0.1:18081
exec > /content/onprem.log 2>&1
cd /content
THREADS="${THREADS:-$(nproc)}"
export TZ=Asia/Seoul
BIN=$(dirname "$(find /content/llama -name llama-server -type f | head -1)")
[ -x "$BIN/llama-server" ] && [ -f qwen.gguf ] && [ -d mvp/panjeong ] || { echo "colab_cpu.sh를 먼저 돌릴 것"; exit 1; }

echo "== DEPS $(date +%T)"
apt-get -qq update && apt-get -qq install -y tesseract-ocr tesseract-ocr-kor > /dev/null
pip -q install fastapi "uvicorn[standard]" jinja2 python-multipart httpx pytesseract pillow python-hwpx==2.29.1 lxml pyyaml
tesseract --list-langs 2>&1 | tr '\n' ' '; echo

echo "== START threads=$THREADS $(date +%T)"
pkill -f "[l]lama-server -m qwen" ; pkill -f "[u]vicorn run:app"
rm -f mvp/data/panjeong.db
nohup "$BIN/llama-server" -m qwen.gguf --port 8097 -c 2048 -t "$THREADS" --host 127.0.0.1 > llama.log 2>&1 &
for i in $(seq 1 120); do curl -s localhost:8097/health | grep -q '"ok"' && break; sleep 1; done
cd mvp && LLAMA_URL=http://127.0.0.1:8097 FORMS_DIR=/content/mvp/서식 nohup python3 -m uvicorn run:app --host 127.0.0.1 --port 18080 > ../web.log 2>&1 &
for i in $(seq 1 60); do [ "$(curl -s -o /dev/null -w '%{http_code}' localhost:18080/)" = 200 ] && break; sleep 1; done
echo "web: $(curl -s -o /dev/null -w '%{http_code}' localhost:18080/)  llama: $(curl -s localhost:8097/health)"
echo "== READY $(date +%T)"
