"""uvicorn 진입점: `.venv/bin/python -m uvicorn run:app --port 8080` 또는 `run.sh`."""
import os
from pathlib import Path
from panjeong.web.app import create_app

ROOT = Path(__file__).parent
app = create_app(data_dir=ROOT / "data", llama_url=os.environ.get("LLAMA_URL", "http://127.0.0.1:8097"),
                 forms_dir=os.environ.get("FORMS_DIR") or (ROOT.parent / "서식"))
