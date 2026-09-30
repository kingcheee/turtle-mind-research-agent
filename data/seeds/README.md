# 합성 데이터 시드 (공개 데이터 발췌)

`data/gen.py`가 회의비 케이스의 상호·주소·인원·금액·시각·목적을 여기서 뽑아 R&D 회의비 문맥으로 옮겨 쓴다(도메인 전이). 개인 식별 정보는 없다.

- `seoul_meals.csv` — 서울특별시 업무추진비 집행내역(서울 정보소통광장 공개 데이터, 2016~2018 정제본) 중 2~12명·1인 7천~6만 원·유흥업종 제외 400건 무작위 발췌. 열: vendor, address, headcount, amount, time, purpose, date
- `mou_meals.csv` — 통일부 기관장 업무추진비 건별 내역(공공데이터포털 15112240) 200건 발췌. 열: vendor, amount, purpose, date
- 출장비 시드는 없다 — 국가평생교육진흥원 출장비 데이터셋(공공데이터포털 15087980)은 열 구조(운임·일비·식비·숙박비)만 참고했다(실데이터 1행).

원본 파일과 출처 원장: `~/projects/00-research/2026-09/w3/2026-09-24-rnd-meeting-travel-expense-docs/`(FINDINGS §4, SOURCES [25][26][27]).
