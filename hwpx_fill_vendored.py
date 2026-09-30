# -*- coding: utf-8 -*-
"""hwpx_fill.py — HWPX 표 셀 텍스트를 **좌표로** 채운다 (L3: python-hwpx + lxml 직접 편집).

왜 좌표인가
-----------
한국 공식양식은 표 셀 텍스트가 run으로 파편화돼 있어 `replace_text_in_runs()`·
`find_cell_by_label()` 같은 고수준 API가 **0건/None을 반환하면서 성공을 보고한다**
(`.claude/rules/hwpx-editing.md`). 좌표(`<hp:cellAddr>`) 지정은 병합셀에도 강하고
문자열 매칭에 의존하지 않는다 — 「패턴 5: 정확좌표 지정」.

이 모듈이 지키는 불변식
-----------------------
1. 표 인덱스는 `section0.xml`의 `<hp:tbl>` **문서순 1-based**(중첩표 포함).
2. 셀은 **그 표의 직계 `<hp:tc>`만** 대상 — 중첩표의 tc는 절대 섞이지 않는다.
3. 셀 텍스트 읽기·쓰기도 **그 셀 직계 문단만** — 중첩표 안의 `<hp:t>`는 건드리지 않는다.
4. 없는 좌표는 **조용히 넘어가지 않고 KeyError를 던진다**.
5. 빈 셀에 run을 맨바닥에서 만들지 않는다 — 기존 run 재사용 또는 deepcopy.
6. 회색·파란 안내문 charPr은 같은 서식의 **검정 charPr로 교체**한다(없으면 경고로 보고).
7. 저장 3수칙: `remove_layout_caches()` → `mark_dirty()` → `save_to_path()`.

python-hwpx 2.29.1 평면 API만 쓴다. 6.x API(`doc.text`·`doc.shapes`·`return_report=`)는 없다.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from lxml import etree

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"

#: 이름으로 지정할 수 있는 폼 컨트롤 태그. `value` 속성을 갖는 것만 넣는다.
FORM_TAGS = ("checkBtn", "radioBtn")

#: `value`에 허용하는 값. OWPML 열거형이다 — 임의 문자열을 쓰면 한글이 조용히
#: UNCHECKED로 되돌린다. `CHECKED`는 한글 2024 왕복(HWPX→HWP→HWPX)으로 실증했다.
FORM_VALUES = ("CHECKED", "UNCHECKED", "INDETERMINATE")

__all__ = ["fill_cells", "read_cells", "read_cell_paragraphs", "read_forms",
           "apply_edits", "table_report", "dump_all_cells",
           "CellNotFoundError", "FormControlNotFoundError", "ReplaceCountError"]


class CellNotFoundError(KeyError):
    """좌표가 문서에 없다. 조용히 넘어가면 안 되는 상황."""


class FormControlNotFoundError(KeyError):
    """그 `name`의 폼 컨트롤이 문서에 없다. 음성 대조가 여기서 걸려야 한다."""


class ReplaceCountError(AssertionError):
    """치환 건수가 기대와 다르다. **0건 치환을 성공으로 보고하지 않기 위한 관문**이다."""


# --------------------------------------------------------------------------
# 트리 탐색 헬퍼 — 전부 "직계" 기준. 중첩표 오염을 구조적으로 막는다.
# --------------------------------------------------------------------------
def _nearest_ancestor(el, tag: str):
    a = el.getparent()
    while a is not None:
        if a.tag == tag:
            return a
        a = a.getparent()
    return None


def _tables(section_root) -> List[Any]:
    """문서순 `<hp:tbl>` 전부 (중첩표 포함)."""
    return section_root.findall(".//" + HP + "tbl")


def _direct_cells(tbl) -> List[Any]:
    """그 표의 직계 `<hp:tc>`만. 중첩표의 tc는 제외."""
    return [tc for tc in tbl.findall(".//" + HP + "tc")
            if _nearest_ancestor(tc, HP + "tbl") is tbl]


def _cell_index(tbl) -> Dict[Tuple[int, int], Any]:
    """(rowAddr, colAddr) 0-based → tc. 병합셀은 좌상단 좌표 하나만 존재한다."""
    out: Dict[Tuple[int, int], Any] = {}
    for tc in _direct_cells(tbl):
        ca = tc.find(HP + "cellAddr")
        if ca is None:
            continue
        out[(int(ca.get("rowAddr")), int(ca.get("colAddr")))] = tc
    return out


def _own_paragraphs(tc) -> List[Any]:
    """그 셀 직계 `<hp:p>`만 (중첩표 안 문단 제외)."""
    return [p for p in tc.findall(".//" + HP + "p")
            if _nearest_ancestor(p, HP + "tc") is tc]


def _own_texts(tc) -> List[Any]:
    """그 셀 직계 `<hp:t>`만 (중첩표 안 텍스트 제외)."""
    return [t for t in tc.findall(".//" + HP + "t")
            if _nearest_ancestor(t, HP + "tc") is tc]


def _own_runs(tc) -> List[Any]:
    return [r for r in tc.findall(".//" + HP + "run")
            if _nearest_ancestor(r, HP + "tc") is tc]


def _cell_text(tc) -> str:
    return "".join(t.text or "" for t in _own_texts(tc))


def _para_texts(p) -> List[Any]:
    """그 문단 직계 `<hp:t>`만 (문단 안에 박힌 중첩표의 텍스트는 제외)."""
    return [t for t in p.findall(".//" + HP + "t")
            if _nearest_ancestor(t, HP + "p") is p]


def _para_text(p) -> str:
    return "".join(t.text or "" for t in _para_texts(p))


def _para_runs(p) -> List[Any]:
    return [r for r in p.findall(".//" + HP + "run")
            if _nearest_ancestor(r, HP + "p") is p]


# --------------------------------------------------------------------------
# 색 상속 방지 — 회색/파란 안내문 charPr을 같은 서식의 검정 charPr로
# --------------------------------------------------------------------------
def _charpr_table(header_root) -> Dict[str, Any]:
    return {cp.get("id"): cp for cp in header_root.findall(".//" + HH + "charPr")}


def _charpr_sig(cp, ignore_italic: bool = False):
    """id·textColor를 뺀 서식 지문. ignore_italic이면 <hh:italic/> 유무도 무시."""
    attrs = tuple(sorted((k, v) for k, v in cp.attrib.items()
                         if k not in ("id", "textColor")))
    kids = []
    for k in cp:
        name = etree.QName(k).localname
        if ignore_italic and name == "italic":
            continue
        kids.append((name, tuple(sorted(k.attrib.items())),
                     tuple((etree.QName(g).localname, tuple(sorted(g.attrib.items())))
                           for g in k)))
    return attrs, tuple(kids)


def _build_black_map(header_root) -> Tuple[Dict[str, str], Dict[str, str]]:
    """비검정 charPr id → 검정 charPr id 매핑.

    1순위: 색만 다른 완전 동일 서식.
    2순위: 색 + `<hh:italic/>` 유무만 다른 서식 (안내문은 보통 기울임 회색이다).
    못 찾으면 매핑에 넣지 않고 사유를 남긴다 — header.xml을 새로 쓰지 않는다.
    """
    cps = _charpr_table(header_root)
    black = {i: cp for i, cp in cps.items() if cp.get("textColor") == "#000000"}
    mapping: Dict[str, str] = {}
    unresolved: Dict[str, str] = {}
    for cid, cp in cps.items():
        if cp.get("textColor") == "#000000":
            continue
        sig = _charpr_sig(cp)
        hit = [i for i, b in black.items() if _charpr_sig(b) == sig]
        if not hit:
            sig2 = _charpr_sig(cp, ignore_italic=True)
            hit = [i for i, b in black.items()
                   if _charpr_sig(b, ignore_italic=True) == sig2]
        if hit:
            mapping[cid] = sorted(hit, key=lambda x: int(x))[0]
        else:
            unresolved[cid] = cp.get("textColor") or "?"
    return mapping, unresolved


# --------------------------------------------------------------------------
# 문서 열기 / 구조 단언
# --------------------------------------------------------------------------
def _open(path: str):
    from hwpx.document import HwpxDocument  # 지연 import — CLI --help가 빨라진다
    return HwpxDocument.open(path)


def _section_root(doc, section: Optional[int] = None):
    """section=None이면 단일 섹션만 허용(원본 규율). 다중 섹션은 호출자가 섹션 번호(0-based)를 명시한다."""
    if section is None:
        if len(doc.sections) != 1:
            # 다중 섹션 문서는 표 인덱스 정의가 달라진다 — 조용히 첫 섹션만 쓰지 않는다.
            raise ValueError(f"섹션이 {len(doc.sections)}개다. 이 도구는 단일 섹션 전제로 좌표를 센다 (section= 으로 지정)")
        return doc.sections[0]
    return doc.sections[section]


def table_report(path: str, section: Optional[int] = None) -> List[Dict[str, Any]]:
    """표별 (인덱스, rowCnt, colCnt, 직계셀수). 좌표계 문서와 대조용."""
    doc = _open(path)
    root = _section_root(doc, section).element
    out = []
    for i, t in enumerate(_tables(root), 1):
        out.append({"table": i,
                    "rows": int(t.get("rowCnt")),
                    "cols": int(t.get("colCnt")),
                    "cells": len(_direct_cells(t))})
    return out


def _assert_structure(root, expect: Optional[Sequence[Sequence[int]]]) -> List[Dict[str, int]]:
    """표 개수와 각 표 크기가 기대와 맞는지 **첫 동작으로** 단언한다."""
    tbls = _tables(root)
    actual = [{"table": i, "rows": int(t.get("rowCnt")), "cols": int(t.get("colCnt"))}
              for i, t in enumerate(tbls, 1)]
    if expect is None:
        return actual
    if len(tbls) != len(expect):
        raise AssertionError(
            f"표 개수 불일치: 기대 {len(expect)}개, 실제 {len(tbls)}개 — {actual}")
    for got, want in zip(actual, expect):
        if [got["rows"], got["cols"]] != list(want):
            raise AssertionError(
                f"표#{got['table']} 크기 불일치: 기대 {want[0]}x{want[1]}, "
                f"실제 {got['rows']}x{got['cols']}")
    return actual


def _locate(tbls, table: int, row: int, col: int):
    """1-based (표, 행, 열) → tc. 없으면 CellNotFoundError."""
    if not isinstance(table, int) or table < 1 or table > len(tbls):
        raise CellNotFoundError(
            f"표#{table} 없음 (문서의 표는 1..{len(tbls)})")
    tbl = tbls[table - 1]
    idx = _cell_index(tbl)
    key = (row - 1, col - 1)
    if key not in idx:
        raise CellNotFoundError(
            f"표#{table} r{row}c{col} 없음 "
            f"(표 크기 {tbl.get('rowCnt')}x{tbl.get('colCnt')}, "
            f"병합셀은 좌상단 좌표만 존재한다)")
    return idx[key]


def _locate_para(tbls, table: int, row: int, col: int, para: int):
    """1-based (표, 행, 열, 문단) → hp:p. 없으면 CellNotFoundError."""
    tc = _locate(tbls, table, row, col)
    paras = _own_paragraphs(tc)
    if not isinstance(para, int) or para < 1 or para > len(paras):
        raise CellNotFoundError(
            f"표#{table} r{row}c{col}: 문단 {para} 없음 (이 셀의 문단은 1..{len(paras)})")
    return tc, paras[para - 1]


def _form_controls(root, tbls) -> List[Tuple[Any, Dict[str, Any]]]:
    """(요소, 위치정보) 목록. 위치는 그 컨트롤을 품은 셀 좌표(없으면 None)."""
    out: List[Tuple[Any, Dict[str, Any]]] = []
    for tag in FORM_TAGS:
        for el in root.findall(".//" + HP + tag):
            tc = _nearest_ancestor(el, HP + "tc")
            loc: Dict[str, Any] = {"table": None, "row": None, "col": None}
            if tc is not None:
                ca = tc.find(HP + "cellAddr")
                tbl = _nearest_ancestor(tc, HP + "tbl")
                if ca is not None and tbl is not None and tbl in tbls:
                    loc = {"table": tbls.index(tbl) + 1,
                           "row": int(ca.get("rowAddr")) + 1,
                           "col": int(ca.get("colAddr")) + 1}
            out.append((el, loc))
    # 문서순 정렬 — 태그별로 모아 찾았으므로 순서를 되돌린다
    order = {id(el): i for i, el in enumerate(root.iter())}
    out.sort(key=lambda x: order.get(id(x[0]), 1 << 30))
    return out


def _form_index(root, tbls) -> Dict[str, Tuple[Any, Dict[str, Any]]]:
    """`name` → (요소, 위치). 이름이 중복되면 즉시 실패한다 — 어느 쪽을 고칠지 알 수 없다."""
    idx: Dict[str, Tuple[Any, Dict[str, Any]]] = {}
    for el, loc in _form_controls(root, tbls):
        name = el.get("name")
        if not name:
            continue
        if name in idx:
            raise ValueError(f"폼 컨트롤 이름 중복: {name!r} — 이름으로 지정할 수 없다")
        idx[name] = (el, loc)
    return idx


# --------------------------------------------------------------------------
# 공개 API
# --------------------------------------------------------------------------
def read_cells(path: str, coords: Iterable[Dict[str, Any]], section: Optional[int] = None) -> Dict[str, Any]:
    """좌표별 현재 셀 텍스트를 재파싱해 돌려준다 (검증용).

    coords: [{"table":1,"row":3,"col":4}, ...]  ("value" 키가 있어도 무시)
    반환:   {"ok":bool, "cells":[{table,row,col,text,runs,paragraphs,charPrIDRefs}], "errors":[...]}
    """
    doc = _open(path)
    root = _section_root(doc, section).element
    tbls = _tables(root)
    cells, errors = [], []
    for c in coords:
        t, r, col = int(c["table"]), int(c["row"]), int(c["col"])
        try:
            tc = _locate(tbls, t, r, col)
        except CellNotFoundError as e:
            errors.append({"table": t, "row": r, "col": col, "error": str(e)})
            continue
        cells.append({
            "table": t, "row": r, "col": col,
            "text": _cell_text(tc),
            "paragraphs": len(_own_paragraphs(tc)),
            "runs": len(_own_runs(tc)),
            "charPrIDRefs": [ru.get("charPrIDRef") for ru in _own_runs(tc)],
        })
    return {"ok": not errors, "cells": cells, "errors": errors}


def dump_all_cells(path: str, section: Optional[int] = None) -> Dict[str, str]:
    """모든 표의 모든 직계 셀 텍스트 → {"T1r3c4": "..."} (오염 검사 diff용)."""
    doc = _open(path)
    root = _section_root(doc, section).element
    out: Dict[str, str] = {}
    for ti, tbl in enumerate(_tables(root), 1):
        for (r0, c0), tc in sorted(_cell_index(tbl).items()):
            out[f"T{ti}r{r0 + 1}c{c0 + 1}"] = _cell_text(tc)
    return out


def read_cell_paragraphs(path: str, coords: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """좌표별 **문단 단위** 텍스트를 돌려준다 (부분치환 전후 대조용).

    coords: [{"table":8,"row":5,"col":3}, ...]
    반환:   {"ok", "cells":[{table,row,col,paragraphs:[{index,text,runs:[[charPrIDRef,text]]}]}]}
    """
    doc = _open(path)
    root = _section_root(doc).element
    tbls = _tables(root)
    cells, errors = [], []
    for c in coords:
        t, r, col = int(c["table"]), int(c["row"]), int(c["col"])
        try:
            tc = _locate(tbls, t, r, col)
        except CellNotFoundError as e:
            errors.append({"table": t, "row": r, "col": col, "error": str(e)})
            continue
        paras = []
        for i, p in enumerate(_own_paragraphs(tc), 1):
            runs = [[ru.get("charPrIDRef"), "".join(x.text or "" for x in ru.findall(HP + "t"))]
                    for ru in _para_runs(p)]
            paras.append({"index": i, "text": _para_text(p), "runs": runs})
        cells.append({"table": t, "row": r, "col": col, "paragraphs": paras})
    return {"ok": not errors, "cells": cells, "errors": errors}


def read_forms(path: str) -> Dict[str, Any]:
    """폼 컨트롤 전수 — `name` → `value` 매핑과 위치. 체크박스 검증의 정본이다."""
    doc = _open(path)
    root = _section_root(doc).element
    tbls = _tables(root)
    controls = []
    for el, loc in _form_controls(root, tbls):
        controls.append({
            "tag": etree.QName(el).localname,
            "name": el.get("name"),
            "value": el.get("value"),
            "caption": el.get("caption"),
            "table": loc["table"], "row": loc["row"], "col": loc["col"],
        })
    return {"ok": True, "count": len(controls), "controls": controls}


def count_chars(path: str, chars: Sequence[str]) -> Dict[str, int]:
    """문서 전체 `<hp:t>`에서 문자별 등장 횟수 (치환 전후 대조용)."""
    doc = _open(path)
    root = _section_root(doc).element
    out = {ch: 0 for ch in chars}
    for t in root.findall(".//" + HP + "t"):
        for ch in (t.text or ""):
            if ch in out:
                out[ch] += 1
    return out


def apply_edits(src: str, dst: str, *,
                checks: Sequence[Dict[str, Any]] = (),
                replacements: Sequence[Dict[str, Any]] = (),
                expect_tables: Optional[Sequence[Sequence[int]]] = None) -> Dict[str, Any]:
    """폼 체크박스 `value` 변경 + 문단 내 부분치환을 **한 번의 저장으로** 적용한다.

    checks: [{"name":"CheckBox13","value":"CHECKED"}, ...]
        - `name` 속성으로만 지정한다. caption에는 앞 공백이 붙어 있어 문자열 매칭이 미끄러진다.
        - 없는 이름은 **FormControlNotFoundError**. 조용히 넘어가지 않는다.
        - 값은 `FORM_VALUES` 열거형만 허용. 글자를 써넣는 것이 아니라 속성 변경이다.

    replacements: [{"table":8,"row":5,"col":3,"paragraph":1,
                    "find":"□","replace":"☑","expect":3,"before":"...(선택)"}, ...]
        - **문단 1개로 범위를 좁힌다.** 전역 치환을 하지 않는다.
        - `expect`는 필수. 그 문단의 실제 등장 횟수와 다르면 **ReplaceCountError**로 죽는다
          (0건 치환이 성공으로 보고되는 이 도메인의 함정을 막는 유일한 장치다).
        - `before`를 주면 치환 전 문단 전체 텍스트가 그것과 같은지 먼저 단언한다.
        - `find`가 run 경계에 걸치면 건수가 0으로 세어져 실패한다 — 조용히 넘어가지 않는다.

    반환: {"ok", "checks":[...], "replacements":[...], "tables":[...]}
    """
    doc = _open(src)
    sec = _section_root(doc)
    root = sec.element

    tables = _assert_structure(root, expect_tables)   # ★ 첫 동작
    tbls = _tables(root)

    # ---- 폼 체크박스 ----
    check_results: List[Dict[str, Any]] = []
    if checks:
        fidx = _form_index(root, tbls)
        seen_names = set()
        for ck in checks:
            name = ck["name"]
            value = ck["value"]
            if name in seen_names:
                raise ValueError(f"중복 폼 이름: {name!r}")
            seen_names.add(name)
            if value not in FORM_VALUES:
                raise ValueError(
                    f"{name}: value {value!r}는 허용값이 아니다 (허용: {', '.join(FORM_VALUES)})")
            if name not in fidx:
                raise FormControlNotFoundError(
                    f"폼 컨트롤 {name!r} 없음 (문서의 이름: {sorted(fidx)})")
            el, loc = fidx[name]
            before = el.get("value")
            el.set("value", value)
            check_results.append({"name": name, "caption": el.get("caption"),
                                  "table": loc["table"], "row": loc["row"], "col": loc["col"],
                                  "before": before, "after": value,
                                  "changed": before != value})

    # ---- 문단 내 부분치환 ----
    rep_results: List[Dict[str, Any]] = []
    seen_para = set()
    for rp in replacements:
        t, r, c = int(rp["table"]), int(rp["row"]), int(rp["col"])
        pi = int(rp["paragraph"])
        find, repl = rp["find"], rp["replace"]
        if not isinstance(find, str) or not find:
            raise ValueError(f"표#{t} r{r}c{c} 문단{pi}: find는 비어있지 않은 문자열이어야 한다")
        if not isinstance(repl, str):
            raise TypeError(f"표#{t} r{r}c{c} 문단{pi}: replace는 문자열이어야 한다")
        if "expect" not in rp:
            raise ValueError(
                f"표#{t} r{r}c{c} 문단{pi}: expect(기대 치환건수)는 필수다 — "
                "0건 치환을 성공으로 보고하지 않기 위한 장치다")
        expect = int(rp["expect"])
        key = (t, r, c, pi, find)
        if key in seen_para:
            raise ValueError(f"중복 치환 지정: 표#{t} r{r}c{c} 문단{pi} {find!r}")
        seen_para.add(key)

        tc, p = _locate_para(tbls, t, r, c, pi)
        before_text = _para_text(p)
        if "before" in rp and rp["before"] != before_text:
            raise AssertionError(
                f"표#{t} r{r}c{c} 문단{pi}: 치환 전 문단 텍스트 불일치\n"
                f"  기대: {rp['before']!r}\n  실제: {before_text!r}")

        texts = _para_texts(p)
        hits = sum((tx.text or "").count(find) for tx in texts)
        if hits != expect:
            raise ReplaceCountError(
                f"표#{t} r{r}c{c} 문단{pi}: {find!r} 등장 {hits}건, 기대 {expect}건 — "
                f"문단 텍스트={before_text!r} "
                "(0이면 검색어가 run 경계에 걸쳐 있을 수 있다)")
        touched = []
        for tx in texts:
            s = tx.text or ""
            n = s.count(find)
            if n:
                tx.text = s.replace(find, repl)
                run = _nearest_ancestor(tx, HP + "run")
                touched.append({"charPrIDRef": run.get("charPrIDRef") if run is not None else None,
                                "count": n})
        after_text = _para_text(p)
        rep_results.append({"table": t, "row": r, "col": c, "paragraph": pi,
                            "find": find, "replace": repl,
                            "count": hits, "expect": expect,
                            "before": before_text, "after": after_text,
                            "runs_touched": touched})

    if not check_results and not rep_results:
        raise ValueError("적용할 편집이 하나도 없다 — 빈 저장을 성공으로 보고하지 않는다")

    # ---- 저장 3수칙. 하나라도 빠지면 조용히 유실된다 ----
    sec.remove_layout_caches()
    sec.mark_dirty()
    doc.save_to_path(dst)

    return {"ok": True, "tables": tables,
            "checks": check_results, "replacements": rep_results}


def fill_cells(src: str, dst: str,
               items: Sequence[Dict[str, Any]],
               expect_tables: Optional[Sequence[Sequence[int]]] = None,
               fix_color: bool = True, section: Optional[int] = None) -> Dict[str, Any]:
    """좌표로 표 셀 텍스트를 채워 dst에 저장한다.

    items: [{"table":1,"row":3,"col":4,"value":"김지우"}, ...]
    expect_tables: [[29,9],[3,2],...] — 주면 **첫 동작으로** 구조를 단언하고 틀리면 즉시 실패.
    fix_color: 안내문 색(회색·파랑) charPr을 같은 서식의 검정으로 교체.

    반환: {"ok", "written", "tables", "results":[...], "color_unresolved":[...]}
    실패는 예외로 던진다 — 0건 채움을 성공으로 보고하지 않는다.
    """
    doc = _open(src)
    sec = _section_root(doc, section)
    root = sec.element

    tables = _assert_structure(root, expect_tables)   # ★ 첫 동작
    tbls = _tables(root)

    black_map: Dict[str, str] = {}
    unresolved: Dict[str, str] = {}
    if fix_color:
        headers = getattr(doc, "headers", None)
        if headers:
            black_map, unresolved = _build_black_map(headers[0].element)

    # 좌표 중복은 마지막 값이 조용히 이기므로 미리 막는다
    seen = set()
    for it in items:
        key = (int(it["table"]), int(it["row"]), int(it["col"]))
        if key in seen:
            raise ValueError(f"중복 좌표: 표#{key[0]} r{key[1]}c{key[2]}")
        seen.add(key)

    results: List[Dict[str, Any]] = []
    color_unresolved: List[Dict[str, Any]] = []

    for it in items:
        t, r, c = int(it["table"]), int(it["row"]), int(it["col"])
        value = it["value"]
        if not isinstance(value, str):
            raise TypeError(f"표#{t} r{r}c{c}: value는 문자열이어야 한다 ({type(value).__name__})")
        tc = _locate(tbls, t, r, c)                 # 없으면 여기서 실패

        before = _cell_text(tc)
        texts = _own_texts(tc)

        if texts:
            mode = "overwrite"
            target_t = texts[0]
            target_t.text = value
            for extra in texts[1:]:                 # 파편화된 나머지 run 텍스트 정리
                extra.getparent().remove(extra)
            target_run = _nearest_ancestor(target_t, HP + "run")
        else:
            runs = _own_runs(tc)
            if runs:
                mode = "insert-existing-run"        # 빈 run이 이미 있다 → charPrIDRef 유효
                target_run = runs[0]
            else:
                mode = "insert-deepcopy-run"        # ★ 맨바닥 생성 금지 → 같은 표에서 run을 빌려온다
                donor = None
                for other in _direct_cells(tbls[t - 1]):
                    cand = _own_runs(other)
                    if cand:
                        donor = cand[0]
                        break
                if donor is None:
                    raise RuntimeError(
                        f"표#{t} r{r}c{c}: deepcopy할 기존 run이 표 안에 없다 — 맨바닥 생성은 하지 않는다")
                target_run = copy.deepcopy(donor)
                for junk in target_run.findall(HP + "t"):
                    target_run.remove(junk)
                paras = _own_paragraphs(tc)
                if not paras:
                    raise RuntimeError(f"표#{t} r{r}c{c}: 셀에 <hp:p>가 없다")
                paras[0].insert(0, target_run)
            target_t = etree.SubElement(target_run, HP + "t")
            target_t.text = value

        old_cpr = target_run.get("charPrIDRef")
        new_cpr = old_cpr
        if fix_color and old_cpr is not None:
            if old_cpr in black_map:
                new_cpr = black_map[old_cpr]
                target_run.set("charPrIDRef", new_cpr)
            elif old_cpr in unresolved:
                color_unresolved.append({"table": t, "row": r, "col": c,
                                         "charPrIDRef": old_cpr,
                                         "textColor": unresolved[old_cpr]})

        results.append({"table": t, "row": r, "col": c, "value": value,
                        "mode": mode, "before": before,
                        "charPr": {"from": old_cpr, "to": new_cpr,
                                   "changed": old_cpr != new_cpr}})

    # ---- 저장 3수칙. 하나라도 빠지면 조용히 유실된다 ----
    sec.remove_layout_caches()
    sec.mark_dirty()
    doc.save_to_path(dst)

    return {"ok": True, "written": len(results), "tables": tables,
            "results": results, "color_unresolved": color_unresolved}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _load_spec(path: str) -> Tuple[List[Dict[str, Any]], Optional[List[List[int]]]]:
    # ⚠️ utf-8-sig — PS 5.1의 `Out-File -Encoding utf8`이 BOM을 붙인다(utf-8이면 rc=1로 죽는다)
    with open(path, "r", encoding="utf-8-sig") as f:
        spec = json.load(f)
    if isinstance(spec, list):
        return spec, None
    return spec["items"], spec.get("expect_tables")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="HWPX 표 셀을 좌표로 채운다")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fill", help="좌표대로 채워 새 파일로 저장")
    f.add_argument("src"); f.add_argument("dst")
    f.add_argument("--spec", required=True, help="items(+expect_tables) JSON")
    f.add_argument("--no-color-fix", action="store_true")

    r = sub.add_parser("read", help="좌표별 현재 셀 텍스트 재파싱")
    r.add_argument("path")
    r.add_argument("--spec", required=True)

    t = sub.add_parser("tables", help="표 목록(인덱스·크기·직계셀수)")
    t.add_argument("path")

    d = sub.add_parser("dumpall", help="모든 셀 텍스트 덤프 (오염 검사 diff용)")
    d.add_argument("path")

    e = sub.add_parser("edit", help="폼 체크박스 value 변경 + 문단 내 부분치환")
    e.add_argument("src"); e.add_argument("dst")
    e.add_argument("--spec", required=True,
                   help="{checks:[...], replacements:[...], expect_tables:[[r,c],...]} JSON")

    fo = sub.add_parser("forms", help="폼 컨트롤 전수 (name → value)")
    fo.add_argument("path")

    pa = sub.add_parser("paras", help="좌표별 문단 단위 텍스트 덤프")
    pa.add_argument("path")
    pa.add_argument("--spec", required=True)

    a = ap.parse_args(argv)
    try:
        if a.cmd == "fill":
            items, expect = _load_spec(a.spec)
            out = fill_cells(a.src, a.dst, items, expect_tables=expect,
                             fix_color=not a.no_color_fix)
        elif a.cmd == "read":
            items, _ = _load_spec(a.spec)
            out = read_cells(a.path, items)
        elif a.cmd == "tables":
            out = {"ok": True, "tables": table_report(a.path)}
        elif a.cmd == "forms":
            out = read_forms(a.path)
        elif a.cmd == "paras":
            items, _ = _load_spec(a.spec)
            out = read_cell_paragraphs(a.path, items)
        elif a.cmd == "edit":
            # ⚠️ utf-8-sig — PS 5.1의 `Out-File -Encoding utf8`이 BOM을 붙인다(utf-8이면 rc=1로 죽는다)
            with open(a.spec, "r", encoding="utf-8-sig") as fh:
                spec = json.load(fh)
            out = apply_edits(a.src, a.dst,
                              checks=spec.get("checks", ()),
                              replacements=spec.get("replacements", ()),
                              expect_tables=spec.get("expect_tables"))
        else:
            out = {"ok": True, "cells": dump_all_cells(a.path)}
    except Exception as e:                                   # 실패를 성공으로 포장하지 않는다
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"},
                         ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
