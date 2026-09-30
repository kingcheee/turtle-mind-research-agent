"""SQLite 저장소 — 케이스·판정·심판 큐·예외 사전·이벤트. 모든 변경은 events에 남는다(추가 전용)."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .rules.models import Attendee, CaseInput, Context, Judgment, Policy, Trip

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases(id INTEGER PRIMARY KEY, created_at TEXT, category TEXT, basis_date TEXT,
  amount INTEGER, case_json TEXT, extracted_json TEXT, source_files TEXT, docs_json TEXT);
CREATE TABLE IF NOT EXISTS judgments(id INTEGER PRIMARY KEY, case_id INTEGER, verdict TEXT, judgment_json TEXT,
  notice_no TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY, case_id INTEGER, kind TEXT, status TEXT,
  provisional_at TEXT, deadline_at TEXT, statement TEXT, decided_at TEXT, decision_note TEXT, decided_by TEXT);
CREATE TABLE IF NOT EXISTS exceptions(id INTEGER PRIMARY KEY, key TEXT UNIQUE, rule_id TEXT, condition_json TEXT,
  scope TEXT, source_queue_id INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, ref_id INTEGER, payload_json TEXT);
"""


def _now_iso(now: Optional[datetime] = None) -> str:
    return (now or datetime.now()).isoformat(timespec="seconds")


def case_from_dict(d: Dict[str, Any]) -> CaseInput:
    d = dict(d)
    d["attendees"] = [Attendee(**a) for a in d.get("attendees") or []]
    d["trip"] = Trip(**d["trip"]) if d.get("trip") else None
    return CaseInput(**d)


class Store:
    def __init__(self, path: str | Path, deadline_minutes: int = 7 * 24 * 60, policy: Optional[Policy] = None):
        self.path = str(path)
        self.deadline = timedelta(minutes=deadline_minutes)
        self.policy = policy or Policy()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        try:  # 2026-09-27 이전 DB — 원문 보존 열 추가
            self._conn.execute("ALTER TABLE cases ADD COLUMN docs_json TEXT")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

    # ---- 내부 -------------------------------------------------------------
    def _event(self, kind: str, ref_id: int, payload: Dict[str, Any], now: Optional[datetime] = None) -> None:
        self._conn.execute("INSERT INTO events(ts,kind,ref_id,payload_json) VALUES(?,?,?,?)",
                           (_now_iso(now), kind, ref_id, json.dumps(payload, ensure_ascii=False)))

    # ---- 케이스·판정 ---------------------------------------------------------
    def save_case(self, case: CaseInput, extracted: Dict[str, Any], source_files: List[str],
                  docs: Optional[List[Dict[str, Any]]] = None, now: Optional[datetime] = None) -> int:
        """docs = 원문 [{kind, text, file}] — 수정 화면이 같은 원문으로 대조하려고 보존한다."""
        cur = self._conn.execute(
            "INSERT INTO cases(created_at,category,basis_date,amount,case_json,extracted_json,source_files,docs_json)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (_now_iso(now), case.category, case.date, case.amount_total,
             json.dumps(asdict(case), ensure_ascii=False), json.dumps(extracted, ensure_ascii=False),
             json.dumps(source_files, ensure_ascii=False), json.dumps(docs or [], ensure_ascii=False)))
        cid = cur.lastrowid
        self._event("case.saved", cid, {"category": case.category, "date": case.date, "amount": case.amount_total}, now)
        self._conn.commit()
        return cid

    def update_case(self, cid: int, case: CaseInput, now: Optional[datetime] = None) -> None:
        self._conn.execute("UPDATE cases SET category=?, basis_date=?, amount=?, case_json=? WHERE id=?",
                           (case.category, case.date, case.amount_total, json.dumps(asdict(case), ensure_ascii=False), cid))
        self._event("case.edited", cid, {"date": case.date, "amount": case.amount_total}, now)
        self._conn.commit()

    def get_case(self, cid: int) -> Dict[str, Any]:
        r = self._conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
        if r is None:
            raise KeyError(cid)
        d = dict(r)
        d["case"] = case_from_dict(json.loads(d["case_json"]))
        d["extracted"] = json.loads(d["extracted_json"] or "{}")
        d["source_files"] = json.loads(d["source_files"] or "[]")
        d["docs"] = json.loads(d.get("docs_json") or "[]")
        return d

    def save_judgment(self, cid: int, j: Judgment, now: Optional[datetime] = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO judgments(case_id,verdict,judgment_json,notice_no,created_at) VALUES(?,?,?,?,?)",
            (cid, j.verdict, json.dumps(asdict(j), ensure_ascii=False), j.notice_no, _now_iso(now)))
        jid = cur.lastrowid
        self._event("judgment.saved", jid, {"case_id": cid, "verdict": j.verdict,
                                            "rules": [r.rule_id for r in j.reasons]}, now)
        self._conn.commit()
        return jid

    def get_judgment(self, jid: int) -> Dict[str, Any]:
        r = self._conn.execute("SELECT * FROM judgments WHERE id=?", (jid,)).fetchone()
        d = dict(r)
        d.update(json.loads(d.pop("judgment_json")))
        return d

    def latest_judgment(self, cid: int) -> Optional[Dict[str, Any]]:
        r = self._conn.execute("SELECT id FROM judgments WHERE case_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
        return self.get_judgment(r["id"]) if r else None

    def list_cases(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute("""
            SELECT c.id, c.created_at, c.category, c.basis_date, c.amount,
                   (SELECT verdict FROM judgments j WHERE j.case_id=c.id ORDER BY j.id DESC LIMIT 1) AS verdict,
                   (SELECT status FROM queue q WHERE q.case_id=c.id ORDER BY q.id DESC LIMIT 1) AS queue_status
            FROM cases c ORDER BY c.id DESC""").fetchall()
        return [dict(r) for r in rows]

    def list_case_rows(self) -> List[Dict[str, Any]]:
        """건 목록 표 한 줄 = 건 + 최신 판정(규칙·조문·고시) + 가맹점/출장지·목적·인원. 최근 순."""
        out = []
        for c in self.list_cases():
            full = self.get_case(c["id"])
            case, ex = full["case"], full["extracted"]
            j = self.latest_judgment(c["id"]) or {}
            reasons = j.get("reasons") or []
            rids = [r["rule_id"] for r in reasons if r["rule_id"] != "OK" or len(reasons) == 1]
            arts: List[str] = []
            for r in reasons:
                if r["rule_id"] != "OK" or len(reasons) == 1:
                    if r["article"] not in arts:
                        arts.append(r["article"])
            place = (case.trip.destination if case.trip and case.trip.destination else None) or ex.get("vendor_name")
            out.append(dict(c, rule_ids=rids, articles=arts, notice_no=j.get("notice_no"), judgment_id=j.get("id"),
                            place=place, what=case.purpose, n=case.attendee_count or (len(case.attendees) or None),
                            time=case.time, judged_at=j.get("created_at")))
        return out

    def cases_with_rule(self, rule_id: str, cite: Optional[str] = None) -> List[Dict[str, Any]]:
        """최신 판정이 그 규칙(과 인용 키)을 건 건 — 판정 화면의 「같은 조문을 인용한 건」."""
        hits = []
        for r in self.list_case_rows():
            j = self.get_judgment(r["judgment_id"]) if r["judgment_id"] else {}
            if any(x["rule_id"] == rule_id and (cite is None or x.get("cite") == cite) for x in j.get("reasons") or []):
                hits.append(r)
        return hits

    def case_history(self, cid: int) -> List[Dict[str, Any]]:
        """그 건의 사건 — 올림·수정·판정·심판 큐. 시간 순(같은 시각이면 기록 순)."""
        qids = {r["id"] for r in self._conn.execute("SELECT id FROM queue WHERE case_id=?", (cid,)).fetchall()}
        out = []
        for e in self.list_events(limit=100000):
            k, p = e["kind"], e["payload"]
            if (k.startswith("case.") and e["ref_id"] == cid) or (k == "judgment.saved" and p.get("case_id") == cid) \
                    or (k.startswith("queue.") and (p.get("case_id") == cid or e["ref_id"] in qids and "case_id" not in p)) \
                    or (k == "exception.registered" and e["ref_id"] in qids):
                out.append(e)
        return out

    # ---- 심판 큐 -------------------------------------------------------------
    def provisional_approve(self, cid: int, now: Optional[datetime] = None) -> int:
        now = now or datetime.now()
        cur = self._conn.execute(
            "INSERT INTO queue(case_id,kind,status,provisional_at,deadline_at) VALUES(?,?,?,?,?)",
            (cid, "임시승인", "대기", _now_iso(now), (now + self.deadline).isoformat(timespec="seconds")))
        qid = cur.lastrowid
        self._event("queue.provisional", qid, {"case_id": cid, "deadline_at": (now + self.deadline).isoformat(timespec="seconds")}, now)
        self._conn.commit()
        return qid

    def appeal(self, cid: int, statement: str, now: Optional[datetime] = None) -> int:
        now = now or datetime.now()
        cur = self._conn.execute(
            "INSERT INTO queue(case_id,kind,status,provisional_at,deadline_at,statement) VALUES(?,?,?,?,?,?)",
            (cid, "이의", "대기", _now_iso(now), (now + self.deadline).isoformat(timespec="seconds"), statement))
        qid = cur.lastrowid
        self._event("queue.appeal", qid, {"case_id": cid, "statement": statement}, now)
        self._conn.commit()
        return qid

    def get_queue_item(self, qid: int) -> Dict[str, Any]:
        r = self._conn.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
        if r is None:
            raise KeyError(qid)
        return dict(r)

    def list_queue(self, include_closed: bool = False) -> List[Dict[str, Any]]:
        order = "CASE status WHEN '기한초과' THEN 0 WHEN '대기' THEN 1 ELSE 2 END, deadline_at"
        where = "" if include_closed else "WHERE status IN ('대기','기한초과')"
        rows = self._conn.execute(f"""
            SELECT q.*, c.category, c.basis_date, c.amount,
                   (SELECT verdict FROM judgments j WHERE j.case_id=q.case_id ORDER BY j.id DESC LIMIT 1) AS verdict
            FROM queue q JOIN cases c ON c.id=q.case_id {where} ORDER BY {order}""").fetchall()
        return [dict(r) for r in rows]

    def refresh_overdue(self, now: Optional[datetime] = None) -> int:
        ts = _now_iso(now)
        rows = self._conn.execute("SELECT id FROM queue WHERE status='대기' AND deadline_at < ?", (ts,)).fetchall()
        for r in rows:
            self._conn.execute("UPDATE queue SET status='기한초과' WHERE id=?", (r["id"],))
            self._event("queue.overdue", r["id"], {}, now)
        self._conn.commit()
        return len(rows)

    def decide(self, qid: int, decision: str, note: str = "", register_exception: bool = False,
               rule_id: Optional[str] = None, exception_key: Optional[str] = None,
               decided_by: str = "행정팀", now: Optional[datetime] = None) -> None:
        assert decision in ("인정", "불인정")
        self._conn.execute("UPDATE queue SET status=?, decided_at=?, decision_note=?, decided_by=? WHERE id=?",
                           (decision, _now_iso(now), note, decided_by, qid))
        self._event("queue.decided", qid, {"decision": decision, "note": note, "by": decided_by}, now)
        if decision == "인정" and register_exception and exception_key:
            self._conn.execute(
                "INSERT OR IGNORE INTO exceptions(key,rule_id,condition_json,scope,source_queue_id,created_at) VALUES(?,?,?,?,?,?)",
                (exception_key, rule_id, json.dumps(exception_key.split("|")[1:], ensure_ascii=False), "기관", qid, _now_iso(now)))
            self._event("exception.registered", qid, {"key": exception_key, "rule_id": rule_id}, now)
        self._conn.commit()

    def list_exceptions(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._conn.execute("SELECT * FROM exceptions ORDER BY id DESC").fetchall()]

    def list_events(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM events ORDER BY id ASC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d.pop("payload_json") or "{}")
            out.append(d)
        return out

    # ---- 엔진 컨텍스트 -------------------------------------------------------
    def attendees_on_trip(self, date: Optional[str]) -> set:
        if not date:
            return set()
        names = set()
        for r in self._conn.execute("SELECT case_json FROM cases WHERE category='출장비'").fetchall():
            d = json.loads(r["case_json"])
            t = d.get("trip") or {}
            if t.get("start") and t.get("end") and t["start"] <= date <= t["end"]:
                names.update(a["name"] for a in d.get("attendees") or [])
        return names

    def context_for(self, case: CaseInput, today: Optional[str] = None) -> Context:
        exc = {r["key"]: {"source_queue_id": r["source_queue_id"], "rule_id": r["rule_id"]}
               for r in self._conn.execute("SELECT key,rule_id,source_queue_id FROM exceptions").fetchall()}
        return Context(exceptions=exc, attendees_on_trip=self.attendees_on_trip(case.date), policy=self.policy, today=today)
