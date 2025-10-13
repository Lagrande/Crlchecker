import os
import sqlite3
from contextlib import contextmanager
from typing import Optional, Dict, Any, Tuple
import json

from config import DB_PATH, DATA_DIR


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)


def init_db():
    ensure_dirs()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        # --- миграции схемы для ca_mapping: добавляем недостающие столбцы ---
        try:
            cur = conn.execute("PRAGMA table_info(ca_mapping);")
            cols = {row[1] for row in cur.fetchall()}
            if 'crl_number' not in cols:
                conn.execute("ALTER TABLE ca_mapping ADD COLUMN crl_number TEXT;")
            if 'issuer_key_id' not in cols:
                conn.execute("ALTER TABLE ca_mapping ADD COLUMN issuer_key_id TEXT;")
        except sqlite3.OperationalError:
            # Таблицы может не быть — создадим ниже
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ca_mapping (
                crl_url TEXT PRIMARY KEY,
                ca_name TEXT NOT NULL,
                ca_reg_number TEXT,
                crl_number TEXT,
                issuer_key_id TEXT
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

        # --- Новые таблицы для версий и диффов TSL ---
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tsl_versions (
                version TEXT PRIMARY KEY,
                date TEXT,
                root_schema_location TEXT,
                xml_sha256 TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tsl_ca_snapshot (
                version TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                ca_reg_number TEXT,
                ca_id TEXT,
                snapshot_json TEXT NOT NULL,
                PRIMARY KEY (version, entity_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tsl_diffs (
                from_version TEXT,
                to_version TEXT,
                entity_type TEXT,
                entity_id TEXT,
                path TEXT,
                old_value TEXT,
                new_value TEXT,
                PRIMARY KEY (to_version, entity_type, entity_id, path)
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
            INSERT INTO ca_mapping (crl_url, ca_name, ca_reg_number, crl_number, issuer_key_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(crl_url) DO UPDATE SET
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number,
                crl_number=excluded.crl_number,
                issuer_key_id=excluded.issuer_key_id
            """,
            (crl_url, ca_name, ca_reg_number, None, None),
        )
        conn.commit()


def bulk_upsert_ca_mapping(mapping: Dict[str, Dict[str, str]]) -> None:
    if not mapping:
        return
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO ca_mapping (crl_url, ca_name, ca_reg_number, crl_number, issuer_key_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(crl_url) DO UPDATE SET
                ca_name=excluded.ca_name,
                ca_reg_number=excluded.ca_reg_number,
                crl_number=excluded.crl_number,
                issuer_key_id=excluded.issuer_key_id
            """,
            [(u, v.get("name"), v.get("reg_number"), v.get("crl_number"), v.get("issuer_key_id")) for u, v in mapping.items()],
        )
        conn.commit()


def get_ca_by_crl_url(crl_url: str) -> Optional[Dict[str, str]]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT ca_name, ca_reg_number, crl_number, issuer_key_id FROM ca_mapping WHERE crl_url=?",
            (crl_url,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"name": row[0], "reg_number": row[1], "crl_number": row[2], "issuer_key_id": row[3]}


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


# ---- TSL versioning helpers ----

def tsl_versions_get_last() -> Optional[Tuple[str, Dict[str, Any]]]:
    with get_conn() as conn:
        cur = conn.execute("SELECT version, date, root_schema_location, xml_sha256, created_at FROM tsl_versions ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return None
        return row[0], {
            'date': row[1],
            'root_schema_location': row[2],
            'xml_sha256': row[3],
            'created_at': row[4],
        }

def tsl_versions_upsert(version: str, date: Optional[str], root_schema_location: Optional[str], xml_sha256: Optional[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO tsl_versions (version, date, root_schema_location, xml_sha256, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(version) DO UPDATE SET
                date=excluded.date,
                root_schema_location=excluded.root_schema_location,
                xml_sha256=excluded.xml_sha256
            """,
            (version, date, root_schema_location, xml_sha256),
        )

def tsl_ca_snapshots_get(version: str) -> Dict[str, Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute("SELECT entity_key, snapshot_json FROM tsl_ca_snapshot WHERE version=?", (version,))
        res: Dict[str, Dict[str, Any]] = {}
        for row in cur.fetchall():
            key = row[0]
            try:
                res[key] = json.loads(row[1])
            except Exception:
                res[key] = {}
        return res

def tsl_ca_snapshots_write(version: str, snapshots: Dict[str, Dict[str, Any]]) -> None:
    if not snapshots:
        return
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO tsl_ca_snapshot (version, entity_key, ca_reg_number, ca_id, snapshot_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(version, entity_key) DO UPDATE SET
                snapshot_json=excluded.snapshot_json,
                ca_reg_number=excluded.ca_reg_number,
                ca_id=excluded.ca_id
            """,
            [(version, k, k, None, json.dumps(v, ensure_ascii=False)) for k, v in snapshots.items()],
        )

def tsl_diffs_write(from_version: Optional[str], to_version: str, diffs: list) -> None:
    if not diffs:
        return
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO tsl_diffs (from_version, to_version, entity_type, entity_id, path, old_value, new_value)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            diffs,
        )


