"""llama-server(/completion) 클라이언트 — 문법 제약 디코딩으로 JSON을 강제한다."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional, Tuple

import httpx


class LlamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8097", timeout: float = 300.0,
                 transport: Optional[httpx.BaseTransport] = None):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport)

    def health(self) -> bool:
        try:
            r = self._client.get("/health")
            return r.status_code == 200 and r.json().get("status") == "ok"
        except httpx.HTTPError:
            return False

    def extract(self, prompt: str, grammar: str, n_predict: int = 512) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        body = {"prompt": prompt, "n_predict": n_predict, "temperature": 0, "grammar": grammar,
                "cache_prompt": True}
        t0 = time.time()
        r = self._client.post("/completion", json=body)
        r.raise_for_status()
        d = r.json()
        tm = d.get("timings", {}) or {}
        meta = {"seconds": round(time.time() - t0, 2),
                "prompt_tokens": d.get("tokens_evaluated"), "gen_tokens": d.get("tokens_predicted"),
                "pp_per_s": tm.get("prompt_per_second"), "tg_per_s": tm.get("predicted_per_second"),
                "model": d.get("model")}
        return json.loads(d["content"]), meta
