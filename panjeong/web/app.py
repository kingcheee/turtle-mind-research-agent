"""연구비 판정관 웹 — FastAPI + Jinja2 + HTMX. 추출기는 주입(테스트는 가짜, 실행은 llama-server).

화면 = 라우트(design.md §8): / 건 목록 · /new 올리기 → POST /extract 확인 → POST /judge → 303 /case/{id} 판정 ·
/case/{id}/edit 수정 · /admin 심판 큐 · /reports 보고서 · /bench 실측.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile as StarletteUploadFile
from fastapi.templating import Jinja2Templates

from ..extract.ocr import image_to_text
from ..extract.prompt import GRAMMAR_PATH, build_prompt, refine_with_text, to_case_input
from ..rules.checks import requirement_rows
from ..rules.engine import exception_key, judge
from ..rules.models import CaseInput
from ..rules.statutes import WINDOWS
from ..store import Store
from . import view

HERE = Path(__file__).parent
Extractor = Callable[[Sequence[Tuple[str, str]]], Tuple[Dict[str, Any], Dict[str, Any]]]

FORMS = [
    {"key": "usage", "name": "연구개발비 사용실적보고서", "short": "사용실적보고서",
     "origin": "국가연구개발혁신법 시행규칙 별지 제7호서식 (개정 2026. 6. 9.)",
     "what": "연구활동비 현금 행 사용금액에 「가능」 판정 합계, 별첨에 건별 집행내역"},
    {"key": "audit", "name": "연구개발기관의 자체 회계감사 의견서", "short": "자체 회계감사 의견서",
     "origin": "연구개발비 사용 기준 고시 별지 제5호서식",
     "what": "3. 회계감사 및 검증 결과 — 연구활동비 행의 부적정 사용내역·금액에 「불가」 건"},
    {"key": "appeal", "name": "국가연구개발사업 정산 이의신청서", "short": "정산 이의신청서",
     "origin": "연구개발비 사용 기준 고시 별지 제7호서식",
     "what": "신청 대상 및 내용에 건 요약·판정 조문, 신청 요지에 사용자 소명"},
    {"key": "annex", "name": "별첨 — 건별 집행내역", "short": "건별 내역 별첨", "origin": "판정관 생성 표 (공식 별지 아님)",
     "what": "집행일·비목·업체·금액·판정·조문·기준일·심판"},
]

# 예시 영수증/회의록 전체 11개(옛 「시연 케이스」, E2E·영상 컷은 `/new?demo=all`로 이 순서 그대로) — 1~6 문구는 09-24 index.html DEMO 그대로, 문장 사이만 줄바꿈(원문 뷰어 줄번호가 뜻을 갖게).
DEMO_ALL = [
    ("가능", "외부 참석 회의", "회의록",
     "2026-06-12 12:00~13:30 과제 중간점검 회의(장소: 한식당 미가).\n참석: 김철수(한국전자통신연구원), 이영희(한국전자통신연구원), "
     "박민수(KAIST 교수), 정수진(한국전자통신연구원).\n영수증: 한식당 미가 2026-06-12 12:40 된장찌개 4 x 12,000 공기밥 4 x 1,200 "
     "합계 52,800원(부가세 포함)"),
    ("보완", "회의록 없음 8만 원", "영수증",
     "카페 브루잉 2026-06-15 15:10 아메리카노 6 x 5,000 케이크 2 x 25,000 합계 80,000원 (부가세 포함).\n메모: 외부 자문 미팅, "
     "참석 6명: 김철수·이영희·정수진·최민호(한국전자통신연구원), 박민수·한지원(KAIST)"),
    ("보완", "주말 회의", "회의록",
     "2026-06-13(토) 11:30 과제 워크숍 정리 회의(장소: 국밥집 온기).\n참석: 김철수(한국전자통신연구원), 박민수(KAIST 교수), "
     "이영희(한국전자통신연구원).\n영수증: 국밥집 온기 2026-06-13 12:20 돼지국밥 3 x 11,000 합계 33,000원"),
    ("불가", "참여연구자만 회의 식비", "회의록",
     "2026-06-12 12:00 과제 내부 점검 회의(장소: 한식당 미가).\n참석: 김철수(한국전자통신연구원), 이영희(한국전자통신연구원).\n"
     "영수증: 한식당 미가 2026-06-12 12:40 된장찌개 2 x 12,000 합계 24,000원(부가세 포함)"),
    ("보완", "출장 — 국외, 계획서 없음", "출장결과보고서",
     "국외 출장 결과보고서.\n출장자: 김철수(한국전자통신연구원).\n출장지: Boston, USA.\n기간: 2026-06-20 ~ 2026-06-25.\n"
     "목적: NeurIPS 워크숍 발표.\n항공료 1,850,000원, 숙박 4박 960,000원, 학회 측 점심 제공(3일)."),
    ("가능", "같은 기관 과제 미참여자 참석 (제2026-38호 완화)", "회의록",
     "2026-06-12 12:00 과제 점검 회의(장소: 한식당 미가).\n참석: 김철수(한국전자통신연구원), 이영희(한국전자통신연구원), "
     "최민호(한국전자통신연구원 행정팀, 과제 미참여).\n영수증: 한식당 미가 2026-06-12 12:40 된장찌개 3 x 12,000 합계 36,000원(부가세 포함)"),
    # 10-01 사용자: 아직 안 들어간 Gemini 영수증(R7·R8·R9·R13·R15, cases.json demo 7~11)도 누르면 사진·회의록이 채워지게.
    ("가능", "중식 점심 — 외부 2명 참석", "회의록",
     "2026-06-16 12:00~13:30 과제 협력 방향 논의 회의(장소: 중화요리 홍보각).\n참석: 김철수(한국전자통신연구원), 이영희(한국전자통신연구원), "
     "정수진(한국전자통신연구원), 이준호(서울대학교 부교수), 한지원(KAIST 박사과정).\n영수증: 중화요리 홍보각 2026-06-16 12:30 짜장면 3 x 8,000 "
     "짬뽕 2 x 9,000 탕수육(중) 1 x 28,000 합계 70,000원(부가세 포함)"),
    ("가능", "카페 — 내부결재 + 외부 자문", "내부결재문서",
     "[내부결재] 제목: 외부 자문 회의 개최 및 회의비 집행\n기안: 이영희(한국전자통신연구원)\n회의일시: 2026-06-17 15:00~16:30  장소: 카페 모모\n"
     "참석: 이영희(한국전자통신연구원), 정수진(한국전자통신연구원), 박민수(KAIST 교수)\n결재일: 2026-06-16\n"
     "영수증: 카페 모모 2026-06-17 15:20 아메리카노 2 x 4,500 카페라떼 1 x 5,500 딸기케이크 1 x 7,500 합계 22,000원(부가세 포함)"),
    ("보완", "한우 — 1인당 4만 2천 원", "회의록",
     "2026-06-18 12:20~13:50 실증 기관 요구사항 검토 회의(장소: 한우마을 다래).\n참석: 김철수(한국전자통신연구원), 이영희(한국전자통신연구원), "
     "박민수(KAIST 교수), 이준호(서울대학교 부교수).\n영수증: 한우마을 다래 2026-06-18 12:50 한우 갈비탕 4 x 18,000 한우 육회 1 x 38,000 "
     "한우 모둠구이(소) 1 x 58,000 합계 168,000원(부가세 포함)"),
    ("가능", "점심 회의 — 외부 교수 참석", "회의록",
     "2026-06-22 12:30~14:00 과제 진도 점검 회의(장소: 한식당 소반).\n참석: 김철수(한국전자통신연구원), 이영희(한국전자통신연구원), "
     "박민수(KAIST 교수).\n영수증: 한식당 소반 2026-06-22 12:40 불고기 정식 3 x 13,000 합계 39,000원(부가세 포함)"),
    ("가능", "연구혁신비 — 참여연구자만", "회의록",
     "2026-06-24 12:20~13:20 과제 연구혁신 워크숍 준비 회의(장소: 샐러드랩). 비목: 연구혁신비.\n참석: 김철수(한국전자통신연구원), "
     "이영희(한국전자통신연구원), 정수진(한국전자통신연구원).\n영수증: 샐러드랩 2026-06-24 12:40 샐러드 파스타 3 x 13,000 합계 39,000원(부가세 포함)"),
]
# 10-01 사용자: 화면에는 5개만, 텍스트에서 「영수증: …」 줄을 뺀다 — 영수증은 사진 OCR로만. 실제 모델로 10행을 사진만으로 돌려
# 8행이 판정·금액·날짜 정답과 같았고(10·11번은 OCR이 합계를 못 읽음) 그중 가능 2·보완 2·불가 1을 골랐다.
DEMO_NOS = [1, 3, 4, 8, 9]
DEMO = [(v, label, kind, "\n".join(l for l in text.split("\n") if not l.startswith("영수증:")))
        for v, label, kind, text in (DEMO_ALL[i - 1] for i in DEMO_NOS)]
DOC_KINDS = ["영수증", "회의록", "내부결재문서", "출장신청서", "출장결과보고서", "기타"]


def default_extractor(llama_url: str) -> Extractor:
    from ..extract.client import LlamaClient
    client = LlamaClient(llama_url)
    grammar = GRAMMAR_PATH.read_text(encoding="utf-8")

    def _run(docs):
        return client.extract(build_prompt(docs), grammar)
    _run.client = client  # type: ignore[attr-defined]
    return _run


def _b(v: Optional[str]) -> Optional[bool]:
    if v in (None, "", "null", "unknown"):
        return None
    return v in ("on", "true", "True", "1", "yes")


def _i(v: Optional[str]) -> Optional[int]:
    try:
        return int(str(v).replace(",", "").strip()) if v not in (None, "") else None
    except ValueError:
        return None


def _s(v: Optional[str]) -> Optional[str]:
    v = (v or "").strip()
    return None if v.lower() in ("", "none", "null") else v


def dday(deadline_iso: Optional[str], now: Optional[datetime] = None) -> str:
    """심판 기한을 달력일 기준 D-n / D-DAY / D+n으로 — 행정팀 큐 목록용(Jinja 필터)."""
    if not deadline_iso:
        return "—"
    try:
        d = datetime.fromisoformat(str(deadline_iso)).date()
    except ValueError:
        return "—"
    n = (d - (now or datetime.now()).date()).days
    return "D-DAY" if n == 0 else (f"D-{n}" if n > 0 else f"D+{-n}")


def form_to_case(f: Dict[str, Any], institution: Optional[str] = None,
                 participants: Optional[Sequence[str]] = None) -> Tuple[CaseInput, Dict[str, Any], List[str], List[str]]:
    extracted = json.loads(f.get("extracted_json") or "{}")
    doc_types = [d for d in (f.get("doc_types") or "").split(",") if d]
    source_files = [d for d in (f.get("source_files") or "").split(",") if d]
    try:
        attendees = json.loads(f.get("attendees_json") or "[]")
    except json.JSONDecodeError:
        attendees = []
    extracted = dict(extracted)
    extracted["attendees"] = attendees
    if "vendor_name" in f:  # 가맹점은 판정 입력이 아니지만 목록·보고서에 쓰므로 고친 값을 남긴다
        extracted["vendor_name"] = _s(f.get("vendor_name"))
    overrides: Dict[str, Any] = {
        "category": _s(f.get("category")) or "불명", "date": _s(f.get("date")), "time": _s(f.get("time")),
        "amount_total": _i(f.get("amount_total")), "vat_included": _b(f.get("vat_included")),
        "vendor_type": _s(f.get("vendor_type")), "has_alcohol": _b(f.get("has_alcohol")),
        "attendee_count": _i(f.get("attendee_count")), "purpose": _s(f.get("purpose")),
        "has_minutes": _b(f.get("has_minutes")) or False,
        "has_internal_approval": _b(f.get("has_internal_approval")) or False,
        "has_simplified_evidence": _b(f.get("has_simplified_evidence")) or False,
        "basic_project": _b(f.get("basic_project")) or False,
        "innovation_fund": _b(f.get("innovation_fund")) or False,
    }
    if overrides["category"] == "출장비":
        extracted["trip"] = {
            "destination": _s(f.get("trip_destination")), "start": _s(f.get("trip_start")), "end": _s(f.get("trip_end")),
            "domestic": _b(f.get("trip_domestic")), "meals_provided": _b(f.get("trip_meals_provided")),
        }
        overrides.update({"plan_doc": _b(f.get("trip_plan_doc")) or False, "report_doc": _b(f.get("trip_report_doc")) or False,
                          "meal_claimed_full": _b(f.get("trip_meal_claimed_full")),
                          "has_transport_evidence": _b(f.get("trip_has_transport_evidence"))})
    case = to_case_input(extracted, doc_types=doc_types, overrides=overrides, institution=institution,
                         participants=participants)
    return case, extracted, doc_types, source_files


def _docs_from_json(raw: Optional[str]) -> List[Dict[str, Any]]:
    try:
        docs = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [d for d in docs if isinstance(d, dict) and d.get("text") is not None]


def _latest_bench(results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """상태바의 「추출 실측」 — 노트북 결과 중 가장 최근 것."""
    mine = [r for r in results if str(r.get("host", "")).startswith("노트북")]
    return max(mine, key=lambda r: str(r.get("date", ""))) if mine else None


UPLOAD_MAX = 10 * 1024 * 1024  # 올린 사진 한 장 상한


def create_app(store: Optional[Store] = None, extractor: Optional[Extractor] = None,
               data_dir: Path | str = "data", llama_url: str = "http://127.0.0.1:8097",
               forms_dir: Optional[Path | str] = None, photos_dir: Optional[Path | str] = None) -> FastAPI:
    data_dir = Path(data_dir); data_dir.mkdir(parents=True, exist_ok=True)
    uploads = data_dir / "uploads"; uploads.mkdir(exist_ok=True)
    store = store or Store(data_dir / "panjeong.db")
    extractor = extractor or default_extractor(llama_url)
    project: Dict[str, Any] = {}
    if (data_dir / "project.json").exists():
        project = json.loads((data_dir / "project.json").read_text(encoding="utf-8"))
    institution = project.get("기관명")
    participants = project.get("참여연구자") or []
    # 행정팀(선집행·사후심판) 축 표시 스위치 — project.json에 "행정팀": false 면 내비·임시 승인·이의 신청을 숨긴다.
    # 라우트·저장소·테스트는 그대로다(숨김이지 삭제가 아님). 기본은 켜짐(기획서의 선집행·사후심판 축, 시연 시나리오 3).
    show_admin = bool(project.get("행정팀", True))
    # 시연 케이스 표 스위치 — "시연 케이스": false 면 /new 오른쪽 표를 숨긴다(10-01 발표 영상: 실제 사용자가 사진을 올리는 화면으로 찍기 위해).
    show_demo = bool(project.get("시연 케이스", True))
    # 09-29 사용자: 시연 케이스가 사용자가 Gemini로 만든 영수증 사진을 직접 쓰게 — cases.json의 demo 번호 → 사진 이름.
    # /demo-photos/와 /extract의 demo_photo는 이 이름들만 받는다(폴더의 다른 파일·경로 조작은 404·무시).
    photos_dir = Path(photos_dir) if photos_dir else HERE.parent.parent / "data" / "photos"
    demo_photos: Dict[int, str] = {}
    if (photos_dir / "cases.json").exists():
        for c in json.loads((photos_dir / "cases.json").read_text(encoding="utf-8")):
            if c.get("demo") and c.get("photo") and (photos_dir / c["photo"]).is_file():
                demo_photos[int(c["demo"])] = c["photo"]
    demo_photo_names = set(demo_photos.values())

    def load_bench() -> List[Dict[str, Any]]:
        out = []
        for p in sorted((HERE.parent.parent / "bench" / "results").glob("*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
        return out

    bench_now = _latest_bench(load_bench())

    app = FastAPI(title="연구비 판정관")
    app.state.store, app.state.extractor, app.state.data_dir = store, extractor, data_dir
    app.state.forms_dir = Path(forms_dir) if forms_dir else HERE.parent.parent.parent / "서식"
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    tpl = Jinja2Templates(directory=str(HERE / "templates"))
    tpl.env.filters["won"] = lambda v: f"{int(v):,}" if v not in (None, "") else "—"
    tpl.env.filters["dday"] = dday
    tpl.env.filters["mono"] = view.mono
    tpl.env.filters["vc"] = lambda v: view.VCLASS.get(v or "", "none")
    tpl.env.filters["weekday"] = view.weekday
    tpl.env.globals.update(MEANING=view.MEANING, FORMS=FORMS, DOC_KINDS=DOC_KINDS, rule_label=view.rule_label,
                           exception_text=view.exception_text, event_text=view.event_text, event_ref=view.event_ref)
    tpl.env.filters["unrule"] = view.humanize_rule_ids
    tpl.env.filters["rule_label"] = view.rule_label

    def page_ctx() -> Dict[str, Any]:
        """전체 페이지(셸이 있는 것)에만 붙는 컨텍스트 — 사이드바 개수·모델 상태·과제·상태바 집계."""
        q = store.list_queue()
        cases = store.list_cases()
        try:
            ok = getattr(getattr(extractor, "client", None), "health", lambda: None)()
        except Exception:
            ok = None
        counts = {v: sum(1 for c in cases if c["verdict"] == v) for v in ("가능", "보완", "불가")}
        return dict(nav={"cases": len(cases), "queue": len(q), "overdue": sum(1 for x in q if x["status"] == "기한초과")},
                    llama_ok=ok, project=project, counts=counts, bench_now=bench_now, current=WINDOWS[-1])

    def render(name: str, request: Request, **ctx):
        ctx.setdefault("request", request)
        ctx.setdefault("show_admin", show_admin)
        ctx.setdefault("show_demo", show_demo)
        # 브라우저가 app.css·app.js를 캐시해 고친 게 안 보였다(09-28) — 수정 시각을 쿼리로 붙인다
        ctx.setdefault("asset_v", int(max((HERE / "static" / f).stat().st_mtime for f in ("app.css", "app.js"))))
        if "tab" in ctx:
            for k, v in page_ctx().items():
                ctx.setdefault(k, v)
        return tpl.TemplateResponse(request, name, ctx)

    def get_case_or_404(cid: int) -> Dict[str, Any]:
        try:
            return store.get_case(cid)
        except KeyError:
            raise HTTPException(404, "건 없음")

    def review_ctx(case: CaseInput, extracted: Dict[str, Any], docs: List[Dict[str, Any]], meta: Optional[Dict[str, Any]],
                   case_id: Optional[int] = None) -> Dict[str, Any]:
        return dict(case=case, extracted=extracted, meta=meta, docs=docs, case_id=case_id,
                    institution=institution, participants=participants,
                    doc_types=",".join(d["kind"] for d in docs),
                    source_files=",".join(d["file"] for d in docs if d.get("file")),
                    docs_json=json.dumps(docs, ensure_ascii=False),
                    attendees_json=json.dumps([asdict(a) for a in case.attendees], ensure_ascii=False),
                    extracted_json=json.dumps(extracted, ensure_ascii=False))

    # ---------------- 연구자 ----------------
    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, q: str = ""):
        rows = store.list_case_rows()
        for r in rows:
            r["vc"] = view.VCLASS.get(r["verdict"] or "", "none")
        sums = {c: sum(r["amount"] or 0 for r in rows if r["vc"] == c) for c in ("ok", "warn", "bad")}
        return render("list.html", request, tab="list", rows=rows, q=q, sums=sums,
                      total=sum(r["amount"] or 0 for r in rows))

    @app.get("/new", response_class=HTMLResponse)
    def new(request: Request):
        rows = list(enumerate(DEMO_ALL, 1)) if request.query_params.get("demo") == "all" else list(zip(DEMO_NOS, DEMO))
        return render("new.html", request, tab="new", demo=rows, demo_photos=demo_photos)

    @app.get("/demo-photos/{name}")
    def demo_photo(name: str):
        if name not in demo_photo_names:
            raise HTTPException(404)
        return FileResponse(str(photos_dir / name), media_type="image/jpeg")

    @app.post("/extract", response_class=HTMLResponse)
    async def extract(request: Request):
        form = await request.form()
        # 공개 시연(Funnel) 방어 — 파일당 10MB 넘는 사진은 저장·OCR 전에 거절한다
        if any(isinstance(up, StarletteUploadFile) and (up.size or 0) > UPLOAD_MAX for up in form.getlist("files")):
            return HTMLResponse('<div class="bar"><h1>새 증빙</h1><span class="sep"></span>'
                                '<span class="vd warn"><i class="sh warn"></i>사진이 너무 크다 — 파일당 10MB까지 올릴 수 있다</span></div>')
        docs: List[Dict[str, Any]] = []
        demo_name = str(form.get("demo_photo") or "")
        if demo_name in demo_photo_names:  # 시연 행의 Gemini 영수증 사진 — 올린 사진과 똑같이 uploads로 복사해 OCR
            dest = uploads / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{demo_name}"
            shutil.copyfile(photos_dir / demo_name, dest)
            docs.append({"kind": "영수증", "text": image_to_text(dest), "file": dest.name})
        kind = form.get("file_doc_type") or "영수증"
        for up in form.getlist("files"):
            # request.form()의 파일은 starlette UploadFile — fastapi.UploadFile은 그 하위 클래스라 isinstance로 거르면 사진이 전부 버려진다(09-28)
            if not isinstance(up, StarletteUploadFile) or not up.filename:
                continue
            name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{Path(up.filename).name}"
            dest = uploads / name
            with dest.open("wb") as fh:
                shutil.copyfileobj(up.file, fh)
            docs.append({"kind": kind, "text": image_to_text(dest), "file": name})
        if str(form.get("text_doc", "")).strip():
            docs.append({"kind": form.get("text_doc_type") or "회의록", "text": str(form["text_doc"]), "file": None})
        if not docs:  # 「다시 추출」 — 확인 화면이 들고 있던 원문으로 모델만 다시 돌린다
            docs = _docs_from_json(form.get("docs_json"))
        if not docs:
            return HTMLResponse('<div class="bar"><h1>새 증빙</h1><span class="sep"></span>'
                                '<span class="vd warn"><i class="sh warn"></i>문서 없음 — 사진이나 텍스트를 넣어야 추출한다</span></div>')
        pairs = [(d["kind"], d["text"]) for d in docs]
        extracted, meta = extractor(pairs)
        extracted = refine_with_text(extracted, "\n".join(t for _, t in pairs))
        case = to_case_input(extracted, doc_types=[k for k, _ in pairs], institution=institution, participants=participants)
        ctx = review_ctx(case, extracted, docs, meta)
        if request.headers.get("HX-Request"):
            return render("review.html", request, **ctx)
        return render("review_page.html", request, tab="new", **ctx)

    @app.post("/judge")
    async def judge_route(request: Request):
        form = dict((await request.form()).items())
        case, extracted, doc_types, source_files = form_to_case(form, institution=institution, participants=participants)
        cid = _i(form.get("case_id"))
        if cid:
            get_case_or_404(cid)
            store.update_case(cid, case)
        else:
            cid = store.save_case(case, extracted=extracted, source_files=source_files,
                                  docs=_docs_from_json(form.get("docs_json")))
        store.save_judgment(cid, judge(case, store.context_for(case)))
        return RedirectResponse(f"/case/{cid}", status_code=303)

    def neighbours(cid: int) -> Tuple[Optional[int], Optional[int], int, int]:
        ids = [c["id"] for c in store.list_cases()]
        i = ids.index(cid) if cid in ids else 0
        prev_id = ids[i - 1] if i > 0 else None
        next_id = ids[i + 1] if i + 1 < len(ids) else None
        return prev_id, next_id, i + 1, len(ids)

    def case_view(cid: int) -> Dict[str, Any]:
        row = get_case_or_404(cid)
        case = row["case"]
        j = store.latest_judgment(cid)
        jd = _jdict(j) if j else None
        rows = requirement_rows(case, jd, cap=store.policy.per_person_cap) if jd else []
        queue = [q for q in store.list_queue(include_closed=True) if q["case_id"] == cid]
        return dict(row=row, case=case, j=jd, rows=rows, case_id=cid, extracted=row["extracted"], docs=row["docs"],
                    panels=view.statute_panels(jd, case) if jd else [],
                    vc=view.VCLASS.get(jd.verdict if jd else "", "none"),
                    queue=queue[-1] if queue else None)

    @app.get("/case/{cid}", response_class=HTMLResponse)
    def case_page(request: Request, cid: int):
        # 09-29 사용자 「하나하나씩 없애가보자」: 같은 조문 건 표·이력 칸을 뺐다 — store.cases_with_rule·case_history는 남겨 둠
        prev_id, next_id, pos, total = neighbours(cid)
        return render("case.html", request, tab="list", prev_id=prev_id, next_id=next_id, pos=pos, total=total,
                      **case_view(cid))

    @app.get("/case/{cid}/preview", response_class=HTMLResponse)
    def case_preview(request: Request, cid: int):
        return render("preview.html", request, **case_view(cid))

    @app.get("/case/{cid}/edit", response_class=HTMLResponse)
    def case_edit(request: Request, cid: int):
        row = get_case_or_404(cid)
        ctx = review_ctx(row["case"], row["extracted"], row["docs"], None, case_id=cid)
        return render("review_page.html", request, tab="list", **ctx)

    @app.post("/case/{cid}/approve")
    def approve(cid: int):
        get_case_or_404(cid)
        store.provisional_approve(cid)
        return RedirectResponse(f"/case/{cid}", status_code=303)

    @app.post("/case/{cid}/appeal")
    def appeal(cid: int, statement: str = Form("")):
        get_case_or_404(cid)
        store.appeal(cid, statement=statement)
        return RedirectResponse(f"/case/{cid}", status_code=303)

    @app.get("/uploads/{name}")
    def upload_file(name: str):
        p = uploads / name
        if "/" in name or "\\" in name or name.startswith(".") or not p.is_file():
            raise HTTPException(404)
        return FileResponse(str(p))

    # ---------------- 행정팀 ----------------
    def admin_ctx():
        store.refresh_overdue()
        return dict(queue=store.list_queue(), closed=[q for q in store.list_queue(include_closed=True) if q["status"] in ("인정", "불인정")],
                    exceptions=store.list_exceptions(), events=list(reversed(store.list_events(60))))

    @app.get("/admin", response_class=HTMLResponse)
    def admin(request: Request):
        return render("admin.html", request, tab="admin", **admin_ctx())

    @app.get("/admin/queue/{qid}", response_class=HTMLResponse)
    def queue_detail(request: Request, qid: int):
        q = store.get_queue_item(qid); row = store.get_case(q["case_id"]); j = store.latest_judgment(q["case_id"])
        jd = _jdict(j) if j else None
        keys = {r.rule_id: exception_key(r.rule_id, row["case"]) for r in jd.reasons} if jd else {}
        rows = requirement_rows(row["case"], jd) if jd else []
        return render("queue_detail.html", request, q=q, case=row["case"], j=jd, rows=rows, exception_keys=keys,
                      extracted=row["extracted"])

    @app.post("/admin/decide/{qid}", response_class=HTMLResponse)
    async def decide(request: Request, qid: int):
        form = dict((await request.form()).items())
        q = store.get_queue_item(qid); row = store.get_case(q["case_id"])
        rule_id = _s(form.get("rule_id"))
        store.decide(qid, form.get("decision", "불인정"), note=form.get("note", ""),
                     register_exception=_b(form.get("register_exception")) or False, rule_id=rule_id,
                     exception_key=exception_key(rule_id, row["case"]) if rule_id else None,
                     decided_by=form.get("decided_by") or "행정팀")
        return render("admin_panel.html", request, **admin_ctx())

    # ---------------- 보고서·실측 ----------------
    @app.get("/reports", response_class=HTMLResponse)
    def reports(request: Request):
        rows = store.list_case_rows()
        for r in rows:
            r["vc"] = view.VCLASS.get(r["verdict"] or "", "none")
        return render("reports.html", request, tab="reports", forms=FORMS, rows=rows)

    @app.get("/reports/{key}.hwpx")
    def report_download(key: str):
        from ..reports.fill import build_report
        out = build_report(key, store, app.state.forms_dir, data_dir / "reports")
        return FileResponse(str(out), filename=out.name)

    @app.get("/bench", response_class=HTMLResponse)
    def bench(request: Request):
        return render("bench.html", request, tab="bench", results=load_bench())

    return app


class _Obj(dict):
    __getattr__ = dict.get


def _jdict(j: Dict[str, Any]):
    """store가 돌려준 판정 dict를 템플릿이 dataclass처럼 읽게 한다."""
    o = _Obj(j)
    o["reasons"] = [_Obj(r) for r in j.get("reasons", [])]
    return o


app = None  # uvicorn용 팩토리는 run.py에서
