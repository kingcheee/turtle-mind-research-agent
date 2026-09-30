"""녹화용 임시 판정관 서버 — data_dir만 따로(빈 DB·목데이터 DB), 모델은 LLAMA_URL(폰 터널 18097)."""
import os, sys
from pathlib import Path
import uvicorn
MVP = Path(os.environ["MVP"]); sys.path.insert(0, str(MVP))
from panjeong.web.app import create_app
app = create_app(data_dir=Path(sys.argv[1]), llama_url=os.environ.get("LLAMA_URL", "http://127.0.0.1:18097"), forms_dir=MVP.parent / "서식")
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[2]), log_level="warning")
