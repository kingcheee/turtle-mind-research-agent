#!/usr/bin/env bash
# 연구비 판정관 — Linux VM(NCP 저사양 CPU)·노트북 설치. Ubuntu 22.04 기준.
set -e
sudo apt-get update -qq && sudo apt-get install -y -qq tesseract-ocr tesseract-ocr-kor curl unzip python3-venv >/dev/null
cd "$(dirname "$0")/../.."
python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q fastapi "uvicorn[standard]" jinja2 python-multipart httpx pytesseract pillow python-hwpx==2.29.1 lxml pyyaml pytest
mkdir -p "$HOME/models"
[ -f "$HOME/models/qwen2.5-1.5b-instruct-q4_k_m.gguf" ] || curl -L -o "$HOME/models/qwen2.5-1.5b-instruct-q4_k_m.gguf" \
  https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf
if ! command -v llama-server >/dev/null; then
  echo "llama-server가 없다: https://github.com/ggml-org/llama.cpp/releases 의 ubuntu-x64 zip을 풀어 PATH에 두거나 소스 빌드(cmake -B build && cmake --build build -j)"
fi
.venv/bin/python -m pytest -q && echo "설치 끝. ./run.sh 로 실행 (WEB_PORT·LLAMA_PORT 환경변수로 포트 변경)"
