# 연구비 판정관 — 웹·규칙엔진·OCR 컨테이너. 모델(llama-server)은 compose.yaml의 llm 서비스가 따로 돈다.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LANG=C.UTF-8
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-kor \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# 의존성 목록은 pyproject.toml 하나가 정본 — 패키지로 설치하지 않고 목록만 읽어 깐다
COPY pyproject.toml .
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
 && pip install --no-cache-dir -r /tmp/requirements.txt
COPY . .
ENV FORMS_DIR=/app/forms LLAMA_URL=http://llm:8080
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8080"]
