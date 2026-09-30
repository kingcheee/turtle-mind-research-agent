# 연구비 판정관 — N100 실행. llama-server 18097 + 웹 18080 (나비 8097/8098과 분리). 방화벽에서 18080 허용하면 같은 Wi-Fi 노트북에서 http://n100-minipc:18080
$ErrorActionPreference = "Stop"
$root = "C:\panjeong"; Set-Location "$root\mvp"
$llama = if (Test-Path "$root\llama\llama-server.exe") { "$root\llama\llama-server.exe" } else { "C:\nabi\llama\llama-server.exe" }
$model = "$root\models\qwen2.5-1.5b-instruct-q4_k_m.gguf"
$tess = "C:\Program Files\Tesseract-OCR"; if (Test-Path $tess) { $env:PATH = "$tess;$env:PATH" }
$env:LLAMA_URL = "http://127.0.0.1:18097"; $env:FORMS_DIR = "$root\서식"
try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:18097/health" | Out-Null } catch {
  Start-Process -FilePath $llama -ArgumentList "-m `"$model`" --port 18097 -c 2048 -t 3 --host 127.0.0.1" -WindowStyle Minimized
  1..90 | ForEach-Object { try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:18097/health" | Out-Null; break } catch { Start-Sleep 1 } }
}
.\.venv\Scripts\python.exe -m uvicorn run:app --host 0.0.0.0 --port 18080
