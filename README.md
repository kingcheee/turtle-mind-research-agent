# 연구비 판정관 — MVP

집행 순간에 영수증·회의록·출장 문서를 「국가연구개발사업 연구개발비 사용 기준」(과기정통부 고시) 조문으로 **가능·보완·불가** 판정하는 온디바이스 연구행정 에이전트. 판정은 결정론 규칙엔진이 내리고, AI(소형 언어모델)는 문서에서 필드를 뽑는 한 자리에만 쓰인다. 보완 건은 임시 승인으로 심판 큐에 가고, 행정팀의 인정이 예외 사전에 쌓인다. 결과는 공식 서식 hwpx(사용실적보고서·자체 회계감사 의견서·정산 이의신청서)에 채워진다.

설계·결정 기록: `../02-MVP-설계.md` · 만다라트: `../01-만다라트.md`

## 실행 (노트북·Linux)

```bash
# 준비: tesseract(kor), llama-server(llama.cpp), ~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf, Python 3.12
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r <(sed -n '/dependencies/,/]/p' pyproject.toml | tr -d '[]",' | tail -n +2)   # 또는 deploy/linux/setup.sh
./run.sh                 # llama-server(8097) + 웹(8080). WEB_PORT·LLAMA_PORT·MODEL·THREADS 환경변수
LLAMA_PORT=18097 WEB_PORT=18080 THREADS=8 ./run.sh   # 이 노트북: 8097은 nabi-llama(MiniCPM), 8080은 다른 서버가 쓰는 중
.venv/bin/python -m tools.seed_demo                  # (선택) 정답지 60건을 모델 없이 판정해 목록을 채움 — 시연 리허설은 빈 DB로
.venv/bin/python -m tools.seed_mock                  # (선택) UI 검토용 16건 — 영수증 사진 10장(Gemini 합성 5장 data/photos/ + 렌더 PNG 5장)·심판 대기/기한 초과/인정/불인정·예외 사전·재판정 이력까지 모델 없이
```

브라우저에서 http://localhost:8080 (위 둘째 줄이면 18080). 시연 전 DB 초기화: 서버를 끄고 `rm data/panjeong.db` 후 다시 띄운다.

화면(2026-09-27 개편, 시안 02 「고밀도 작업대」 — 규격 정본은 `design.md`): 위 막대(과제·검색 ⌘K) · 왼쪽 사이드바(건 목록·새 증빙·행정팀·보고서·실측 + 과제·적용 기준) · 본문 · 아래 상태바(모델 연결·실측). URL이 곧 화면이다.

| 화면 | 주소 | 내용 |
|---|---|---|
| 건 목록 | `/` | 판정 필터(전체·가능·보완·불가) · 검색(`?q=`) · 합계 · 아래 미리보기(j/k 이동, Enter 열기) |
| 새 증빙 | `/new` | 사진·텍스트 올리기 + 시연 케이스 6개 → 「추출 ⌘↵」 |
| 확인 | (추출 결과, HTMX) | 왼쪽 원문 줄번호 뷰어 ↔ 오른쪽 추출 필드 표 — 원문에서 찾은 값은 번호 마크(01·02…)와 출처(「회의록 L2」), 원문에 없거나 추정한 값(업종 등)은 「▲ 확인 요망」, 빈 필수값(집행일·금액)은 「■ 차단 오류」. 표시일 뿐 판정은 고친 값으로 규칙엔진이 한다 → 「판정 ⌘↵」 |
| 판정 상세 | `/case/{id}` | 영수증 사진 \| 큰 판정(가능·보완·불가) 아래 접이식 세 칸(PC·폰 같은 틀): ▸요건 대조(요건 ↔ 확인된 사실) · ▸안 되는 이유(걸린 규칙·조항 번호·필요 조치 + 이의 신청·임시 승인·재판정 버튼·심판 상태, 가능 건은 ▸판정 근거 + 「사용실적보고서에 합산됨」) · ▸조항(펼치면 고시·law.go.kr·법 원문, 제25조 제4항은 시행 구간 3개 전환) |
| 수정 | `/case/{id}/edit` | 저장된 값·원문으로 확인 화면 → 판정하면 같은 건에 새 판정(이력에 쌓임) |
| 행정팀 | `/admin` | 심판 큐 목록 → 상세 + 결정(인정·불인정·예외 사전 등록) · 예외 사전 · 기록 |
| 보고서·실측 | `/reports` · `/bench` | 공식 서식 hwpx 내려받기 · 환경별 실측 표 |

색·폭은 `panjeong/web/static/app.css` 머리의 `:root` 토큰 한 블록에서만 바꾼다. 화면 동작(필터·미리보기·원문 대조·분할선·키보드)은 `static/app.js` 하나. 폰트는 IBM Plex Sans KR·Plex Mono 로컬(woff2), CDN 0.
행정팀(선집행·사후심판) 축을 시연에서 빼려면 `data/project.json`에 `"행정팀": false`를 넣는다 — 사이드바 항목·「임시 승인」·「이의 신청」 버튼이 숨고(라우트·테스트는 그대로), 시연 순서 3번은 건너뛴다. 기본은 켜짐.

N100(Windows): `deploy/n100/setup.ps1` → `run.ps1` (포트 18097/18080, 나비 서비스와 분리). Linux VM: `deploy/linux/setup.sh`.

## 구조

```
panjeong/rules/statutes.py   조문 스냅샷·시행일 구간 — 제25조④ W0 ~2024-11-30(구 조문: 기관 내부자만 불가, 기본사업 단서) / W1 2024-12-01~2026-05-05(제2023-49호: 기관 외부인 + 사전결재) / W2 2026-05-06~(제2026-38호: 과제 참여연구자만 불가, 제25조의2⑥ 연구혁신비 예외 2026-06-11~). 원문은 고시 hwpx 신구조문대비표에서 옮김
panjeong/rules/engine.py     규칙엔진 — rule_id는 조문을 따른다(M-25-4-EXT, M-25-5-DOC, T-25-8-PLAN …). 예외 사전 X-DICT
panjeong/extract/            OCR(Tesseract) · 프롬프트 · GBNF 문법 · llama-server 클라이언트 · 텍스트 기반 확정(refine_with_text)
panjeong/store.py            SQLite 추가 전용: cases · judgments · queue · exceptions · events
panjeong/rules/checks.py     요건 대조 줄(요건 ↔ 사실 ↔ 결과) — 엔진이 건 규칙에서만 만든다
panjeong/web/                FastAPI + Jinja2 + HTMX(벤더링) + 자체 CSS·JS. CDN 0. app.py(라우트) · view.py(표시 헬퍼·조문 패널) · templates/{base(셸),list,new,review(확인 조각)·review_page,case,preview,admin·admin_panel·queue_detail,reports,bench}.html · static/{app.css(머리 :root 토큰),app.js,fonts/}
design.md                    화면 규격 정본(토큰·부품·화면·문구·키보드·함정)
tools/                       seed_demo.py(시연 시드, 선택) · ocr_smoke.py · e2e/(demo_e2e.js 시연 E2E · shots_new.js 화면 캡처·검사 · video_cuts.js 발표 영상 컷 캡처)
panjeong/reports/fill.py     공식 서식 hwpx 좌표 채움(hwp-agent 도구 벤더링) + 별첨 HTML
bench/                       실측(문서당 초·tok/s·필드 정확도) · Colab 노트북
data/                        project.json(과제·기관명·참여연구자) · 업로드 · DB · 생성 보고서 · gen.py(합성 정답지 생성기) · answer_key.json(60건) · images/(영수증 PNG 20장, render_receipts.js) · photos/(Gemini 합성 영수증 사진 5장 + cases.json — 시연 1·2·3·4·6번과 목데이터 5건) · seeds/(공개 집행내역 발췌)
tests/                       pytest 149 (규칙·구간·요건 대조·추출·저장소·웹 화면·웹 셸·서식·벤치·정답지 생성기·시드)
```

## 시연 순서 (5분)

1. 「새 증빙」(N) → 시연 케이스 「외부 참석 회의」 행(사진 칸에 Gemini 영수증 사진 썸네일이 붙고 텍스트 칸에 회의록이 채워진다 — 1·2·3·4·6번) → 「추출」(⌘↵, 사진 OCR 포함 약 16초 — 텍스트만이면 약 11초) → 확인 화면에서 원문 번호 마크·「확인 요망」(업종 추정) 보여 주기 → 「판정」(⌘↵) → `/case/1` 영수증 | 「가능」 → ▸요건 대조를 펼쳐 전부 +
2. 「참여연구자만 회의 식비」 → 불가(제2026-38호 제25조 제4항, 요건 대조 − 줄) → 「수정」(E) → 집행일 2025-03-10 → 판정: 「불가」에 M-25-4-PRE(사전 내부결재)가 더 붙음(제2023-49호: 기관 외부인 + 사전결재) → 다시 「수정」 → 2024-10-15 + 「출연연 기본사업」 체크 → 「가능」(구 조문 단서) — 버전 관리. ▸조항을 펼쳐 시행 구간 3칸을 눌러 구간별 원문 비교. 「같은 기관 과제 미참여자 참석」은 2026-38호 완화의 예: 같은 건을 2025-03-10으로 수정하면 「불가」(그때는 기관 기준)
3. 「주말 회의」 → 보완 → 판정 상세의 ▸안 되는 이유를 펼쳐 「임시 승인 — 먼저 집행, 7일 내 심판」 → 「행정팀 · 심판 큐」에서 그 행 클릭 → 인정 + 예외 사전 등록(M-INST-WKD) → 「결정」 → 새 증빙에서 같은 건 재투입 → 「가능」(X-DICT 예외 사전)
4. 「출장 — 국외, 계획서 없음」 → 보완(제25조 제8항). 확인 화면에서 모델이 합산한 금액이 원문에 없어 「확인 요망」으로 뜨는 것도 보여 줄 수 있다
5. 건 목록(판정 필터·검색 ⌘K·j/k 미리보기) → 보고서 → 사용실적보고서·감사의견서·이의신청서 hwpx 내려받기

## 검증

```bash
.venv/bin/python -m pytest -q          # 단위·통합 (정답지 생성기 검산 포함)
.venv/bin/python -m data.gen           # 정답지 재생성 (결정적, seed 7) → data/answer_key.json
NODE_PATH=~/workspace/03-agents/naver-agent/node_modules node data/render_receipts.js   # 영수증 PNG 20장
.venv/bin/python tools/ocr_smoke.py    # OCR 경로 스모크 (Tesseract kor)
.venv/bin/python bench/run_bench.py --host 노트북 --n 20   # 추출 실측 (llama-server 필요) → bench/results/ → /bench
# 브라우저 E2E — 빈 DB의 서버(PJ_URL, 기본 http://127.0.0.1:18080)와 실제 모델로. 끝나면 예외 사전이 남으니 DB 초기화
export NODE_PATH=~/workspace/03-agents/naver-agent/node_modules
node tools/e2e/demo_e2e.js ../화면/e2e-0927     # 시연 1~5 전부 + 기대 판정 단언 → 「E2E PASS」
node tools/e2e/shots_new.js ../화면/new-0927 4  # 화면 한 바퀴 캡처 + 페이지 스크롤·가로 넘침·콘솔 에러·외부 요청 0 검사
node tools/e2e/video_cuts.js ../화면/발표-0929     # 발표 영상 40초(03-발표-대본.md §3) 컷별 화면 1920×1080 — 빈 DB에서
```

## 고지

- 모델 Qwen2.5-1.5B-Instruct(Alibaba, Apache-2.0) GGUF Q4_K_M · 추론 llama.cpp(MIT) · OCR Tesseract(Apache-2.0) · hwpx 처리 python-hwpx + hwp-agent `hwpx_fill.py`(자체) · 웹 FastAPI·HTMX
- 법령 원문: 국가법령정보센터(「국가연구개발사업 연구개발비 사용 기준」 제2026-38호, 「국가연구개발혁신법 시행규칙」 별지 제7호서식 등). 고시에 없는 규칙(주류·1인 한도·주말)은 「기관 지침」 출처로 낮춰 보완까지만 판정
- 데이터: 합성(생성형 AI로 제작, 실제 개인정보·연구비 데이터 없음). 이 코드의 초안 작성에 Claude(Anthropic)를 활용
- 판정 결과는 참고용이며 최종 판단은 기관 규정 담당자에게 있다
