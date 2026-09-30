#!/usr/bin/env bash
# 노트북·Linux VM용 실행: llama-server(CPU) + 웹. 포트는 나비(8097/8098)와 겹치지 않게 환경변수로 바꿀 수 있다.
set -e
cd "$(dirname "$0")"
MODEL="${MODEL:-$HOME/models/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
LLAMA_PORT="${LLAMA_PORT:-8097}"; WEB_PORT="${WEB_PORT:-8080}"; THREADS="${THREADS:-$(nproc)}"
if ! curl -s "localhost:$LLAMA_PORT/health" | grep -q '"ok"'; then
  echo "llama-server 시작 (포트 $LLAMA_PORT, 스레드 $THREADS)"; nohup llama-server -m "$MODEL" --port "$LLAMA_PORT" -c 2048 -t "$THREADS" --host 127.0.0.1 > data/llama.log 2>&1 &
  for i in $(seq 1 90); do curl -s "localhost:$LLAMA_PORT/health" | grep -q '"ok"' && break; sleep 1; done
fi
export LLAMA_URL="http://127.0.0.1:$LLAMA_PORT"
exec .venv/bin/python -m uvicorn run:app --host 0.0.0.0 --port "$WEB_PORT"
