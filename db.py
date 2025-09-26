import os
import sqlite3
from contextlib import contextmanager
from typing import Optional, Dict, Any
import json

from config import DB_PATH, DATA_DIR


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)


def init_db():
    ensure_dirs()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ca_mapping (
                crl_url TEXT PRIMARY KEY,
                ca_name TEXT NOT NULL,
                ca_reg_number TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ca_mapping_reg ON ca_mapping(ca_reg_number)
            """
        )
        # Детальная недельная статистика по причинам отзыва
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_details (
                week_start TEXT NOT NULL,
                ca_name TEXT,
                ca_reg_number TEXT,
                crl_name TEXT NOT NULL,
                crl_url TEXT,
                reason TEXT NOT NULL,
                count INTEGER NOT NULL,
                PRIMARY KEY (week_start, crl_name, reason)
            )
            """
        )
        # Состояния CRL
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crl_state (
                crl_name TEXT PRIMARY KEY,
                last_check TEXT,
                this_update TEXT,
                next_update TEXT,
                revoked_count INTEGER,
                crl_number TEXT,
                url TEXT,
                last_alerts TEXT,
                ca_name TEXT,
                ca_reg_number TEXT
            )
            """
        )
        # Недельная статистика
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_stats (
                category TEXT PRIMARY KEY,
                count INTEGER
            )
            """
        )
        conn.commit()


@contextmanager
def get_conn():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def upsert_ca_mapping(crl_url: str, ca_name: str, ca_reg_number: Optional[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO ca_mapping (crl_url, ca_name, ca_reg_number)
            VALUES (?, ?, ?)
            ON CONFLICT(crl_url) DO UPDATE SET
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number
            """,
            (crl_url, ca_name, ca_reg_number),
        )
        conn.commit()


def bulk_upsert_ca_mapping(mapping: Dict[str, Dict[str, str]]) -> None:
    if not mapping:
        return
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO ca_mapping (crl_url, ca_name, ca_reg_number)
            VALUES (?, ?, ?)
            ON CONFLICT(crl_url) DO UPDATE SET
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number
            """,
            [
                (
                    url,
                    info.get("name") or "Неизвестный УЦ",
                    info.get("reg_number"),
                )
                for url, info in mapping.items()
            ],
        )
        conn.commit()


def get_ca_by_crl_url(crl_url: str) -> Optional[Dict[str, str]]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT ca_name, ca_reg_number FROM ca_mapping WHERE crl_url=?",
            (crl_url,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"name": row[0], "reg_number": row[1]}


# ---- CRL state helpers ----
def crl_state_get_all() -> Dict[str, Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute("SELECT crl_name, last_check, this_update, next_update, revoked_count, crl_number, url, last_alerts, ca_name, ca_reg_number FROM crl_state")
        res: Dict[str, Dict[str, Any]] = {}
        for row in cur.fetchall():
            res[row[0]] = {
                "last_check": row[1],
                "this_update": row[2],
                "next_update": row[3],
                "revoked_count": row[4],
                "crl_number": row[5],
                "url": row[6],
                "last_alerts": {} if not row[7] else json.loads(row[7]),
                "ca_name": row[8],
                "ca_reg_number": row[9],
            }
        return res


def crl_state_upsert(crl_name: str, state: Dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO crl_state (crl_name, last_check, this_update, next_update, revoked_count, crl_number, url, last_alerts, ca_name, ca_reg_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(crl_name) DO UPDATE SET
                last_check=excluded.last_check,
                this_update=excluded.this_update,
                next_update=excluded.next_update,
                revoked_count=excluded.revoked_count,
                crl_number=excluded.crl_number,
                url=excluded.url,
                last_alerts=excluded.last_alerts,
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number
            """,
            (
                crl_name,
                state.get("last_check"),
                state.get("this_update"),
                state.get("next_update"),
                int(state.get("revoked_count") or 0),
                None if state.get("crl_number") is None else str(state.get("crl_number")),
                state.get("url"),
                json.dumps(state.get("last_alerts") or {}, ensure_ascii=False),
                state.get("ca_name"),
                state.get("ca_reg_number"),
            ),
        )
        conn.commit()


def weekly_stats_get_all() -> Dict[str, int]:
    with get_conn() as conn:
        cur = conn.execute("SELECT category, count FROM weekly_stats")
        return {row[0]: int(row[1]) for row in cur.fetchall()}


def weekly_stats_set(category: str, count: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO weekly_stats (category, count) VALUES (?, ?)
            ON CONFLICT(category) DO UPDATE SET count=excluded.count
            """,
            (category, int(count)),
        )
        conn.commit()


def weekly_details_bulk_upsert(rows: list) -> None:
    """rows: list of (week_start, ca_name, ca_reg_number, crl_name, crl_url, reason, count)"""
    if not rows:
        return
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO weekly_details (week_start, ca_name, ca_reg_number, crl_name, crl_url, reason, count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(week_start, crl_name, reason) DO UPDATE SET
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number,
                crl_url=excluded.crl_url,
                count=weekly_details.count + excluded.count
            """,
            rows,
        )
        conn.commit()


# ---- Bulk import of CRL state (migration) ----
def bulk_upsert_crl_state(state: Dict[str, Dict[str, Any]]) -> None:
    if not state:
        return
    with get_conn() as conn:
        rows = []
        for crl_name, s in state.items():
            rows.append(
                (
                    crl_name,
                    s.get("last_check"),
                    s.get("this_update"),
                    s.get("next_update"),
                    int(s.get("revoked_count") or 0),
                    None if s.get("crl_number") is None else str(s.get("crl_number")),
                    s.get("url"),
                    json.dumps(s.get("last_alerts") or {}, ensure_ascii=False),
                    s.get("ca_name"),
                    s.get("ca_reg_number"),
                )
            )
        conn.executemany(
            """
            INSERT INTO crl_state (crl_name, last_check, this_update, next_update, revoked_count, crl_number, url, last_alerts, ca_name, ca_reg_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(crl_name) DO UPDATE SET
                last_check=excluded.last_check,
                this_update=excluded.this_update,
                next_update=excluded.next_update,
                revoked_count=excluded.revoked_count,
                crl_number=excluded.crl_number,
                url=excluded.url,
                last_alerts=excluded.last_alerts,
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number
            """,
            rows,
        )
        conn.commit()



from contextlib import contextmanager
from typing import Optional, Dict, Any
import json

from config import DB_PATH, DATA_DIR


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)


def init_db():
    ensure_dirs()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ca_mapping (
                crl_url TEXT PRIMARY KEY,
                ca_name TEXT NOT NULL,
                ca_reg_number TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ca_mapping_reg ON ca_mapping(ca_reg_number)
            """
        )
        # Детальная недельная статистика по причинам отзыва
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_details (
                week_start TEXT NOT NULL,
                ca_name TEXT,
                ca_reg_number TEXT,
                crl_name TEXT NOT NULL,
                crl_url TEXT,
                reason TEXT NOT NULL,
                count INTEGER NOT NULL,
                PRIMARY KEY (week_start, crl_name, reason)
            )
            """
        )
        # Состояния CRL
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crl_state (
                crl_name TEXT PRIMARY KEY,
                last_check TEXT,
                this_update TEXT,
                next_update TEXT,
                revoked_count INTEGER,
                crl_number TEXT,
                url TEXT,
                last_alerts TEXT,
                ca_name TEXT,
                ca_reg_number TEXT
            )
            """
        )
        # Недельная статистика
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_stats (
                category TEXT PRIMARY KEY,
                count INTEGER
            )
            """
        )
        conn.commit()


@contextmanager
def get_conn():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def upsert_ca_mapping(crl_url: str, ca_name: str, ca_reg_number: Optional[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO ca_mapping (crl_url, ca_name, ca_reg_number)
            VALUES (?, ?, ?)
            ON CONFLICT(crl_url) DO UPDATE SET
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number
            """,
            (crl_url, ca_name, ca_reg_number),
        )
        conn.commit()


def bulk_upsert_ca_mapping(mapping: Dict[str, Dict[str, str]]) -> None:
    if not mapping:
        return
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO ca_mapping (crl_url, ca_name, ca_reg_number)
            VALUES (?, ?, ?)
            ON CONFLICT(crl_url) DO UPDATE SET
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number
            """,
            [
                (
                    url,
                    info.get("name") or "Неизвестный УЦ",
                    info.get("reg_number"),
                )
                for url, info in mapping.items()
            ],
        )
        conn.commit()


def get_ca_by_crl_url(crl_url: str) -> Optional[Dict[str, str]]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT ca_name, ca_reg_number FROM ca_mapping WHERE crl_url=?",
            (crl_url,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"name": row[0], "reg_number": row[1]}


# ---- CRL state helpers ----
def crl_state_get_all() -> Dict[str, Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute("SELECT crl_name, last_check, this_update, next_update, revoked_count, crl_number, url, last_alerts, ca_name, ca_reg_number FROM crl_state")
        res: Dict[str, Dict[str, Any]] = {}
        for row in cur.fetchall():
            res[row[0]] = {
                "last_check": row[1],
                "this_update": row[2],
                "next_update": row[3],
                "revoked_count": row[4],
                "crl_number": row[5],
                "url": row[6],
                "last_alerts": {} if not row[7] else json.loads(row[7]),
                "ca_name": row[8],
                "ca_reg_number": row[9],
            }
        return res


def crl_state_upsert(crl_name: str, state: Dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO crl_state (crl_name, last_check, this_update, next_update, revoked_count, crl_number, url, last_alerts, ca_name, ca_reg_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(crl_name) DO UPDATE SET
                last_check=excluded.last_check,
                this_update=excluded.this_update,
                next_update=excluded.next_update,
                revoked_count=excluded.revoked_count,
                crl_number=excluded.crl_number,
                url=excluded.url,
                last_alerts=excluded.last_alerts,
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number
            """,
            (
                crl_name,
                state.get("last_check"),
                state.get("this_update"),
                state.get("next_update"),
                int(state.get("revoked_count") or 0),
                None if state.get("crl_number") is None else str(state.get("crl_number")),
                state.get("url"),
                json.dumps(state.get("last_alerts") or {}, ensure_ascii=False),
                state.get("ca_name"),
                state.get("ca_reg_number"),
            ),
        )
        conn.commit()


def weekly_stats_get_all() -> Dict[str, int]:
    with get_conn() as conn:
        cur = conn.execute("SELECT category, count FROM weekly_stats")
        return {row[0]: int(row[1]) for row in cur.fetchall()}


def weekly_stats_set(category: str, count: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO weekly_stats (category, count) VALUES (?, ?)
            ON CONFLICT(category) DO UPDATE SET count=excluded.count
            """,
            (category, int(count)),
        )
        conn.commit()


def weekly_details_bulk_upsert(rows: list) -> None:
    """rows: list of (week_start, ca_name, ca_reg_number, crl_name, crl_url, reason, count)"""
    if not rows:
        return
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO weekly_details (week_start, ca_name, ca_reg_number, crl_name, crl_url, reason, count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(week_start, crl_name, reason) DO UPDATE SET
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number,
                crl_url=excluded.crl_url,
                count=weekly_details.count + excluded.count
            """,
            rows,
        )
        conn.commit()


# ---- Bulk import of CRL state (migration) ----
def bulk_upsert_crl_state(state: Dict[str, Dict[str, Any]]) -> None:
    if not state:
        return
    with get_conn() as conn:
        rows = []
        for crl_name, s in state.items():
            rows.append(
                (
                    crl_name,
                    s.get("last_check"),
                    s.get("this_update"),
                    s.get("next_update"),
                    int(s.get("revoked_count") or 0),
                    None if s.get("crl_number") is None else str(s.get("crl_number")),
                    s.get("url"),
                    json.dumps(s.get("last_alerts") or {}, ensure_ascii=False),
                    s.get("ca_name"),
                    s.get("ca_reg_number"),
                )
            )
        conn.executemany(
            """
            INSERT INTO crl_state (crl_name, last_check, this_update, next_update, revoked_count, crl_number, url, last_alerts, ca_name, ca_reg_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(crl_name) DO UPDATE SET
                last_check=excluded.last_check,
                this_update=excluded.this_update,
                next_update=excluded.next_update,
                revoked_count=excluded.revoked_count,
                crl_number=excluded.crl_number,
                url=excluded.url,
                last_alerts=excluded.last_alerts,
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number
            """,
            rows,
        )
        conn.commit()


