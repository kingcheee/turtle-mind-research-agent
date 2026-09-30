# 연구비 판정관 — N100 미니PC(Windows) 설치. PowerShell 5.1에서 실행. 본선 이틀만 쓴다(나비 서비스 8097/8098과 포트 분리).
# 1) Python 3.12: https://www.python.org/downloads/windows/ (Add to PATH 체크)  2) Tesseract: https://github.com/UB-Mannheim/tesseract/wiki (설치 시 Korean 언어 데이터 선택)
# 3) llama-server: C:\nabi 의 llama.cpp 빌드(10991)를 재사용하거나 https://github.com/ggml-org/llama.cpp/releases 의 win-avx2 zip을 C:\panjeong\llama 에 푼다
# 4) 모델: qwen2.5-1.5b-instruct-q4_k_m.gguf 를 C:\panjeong\models 에 복사(노트북 ~/models 에서)
$ErrorActionPreference = "Stop"
$root = "C:\panjeong"; New-Item -ItemType Directory -Force -Path "$root\models","$root\llama","$root\data" | Out-Null
Set-Location "$root\mvp"   # 이 폴더(mvp)를 통째로 복사해 둔 위치
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" jinja2 python-multipart httpx pytesseract pillow python-hwpx==2.29.1 lxml pyyaml pytest
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) { Write-Warning "tesseract가 PATH에 없다. C:\Program Files\Tesseract-OCR 를 PATH에 넣거나 run.ps1의 TESSERACT 변수를 고친다" }
.\.venv\Scripts\python.exe -m pytest -q
Write-Host "설치 끝. run.ps1 로 실행."
