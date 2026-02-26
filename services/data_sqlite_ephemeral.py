"""
Ephemeral SQLite data layer for sessions & signups.
- Stores data on the app's local filesystem so it persists across reruns,
  but NOT across container restarts/redeploys (ideal until Microsoft API approval).
- Mirrors the in-memory function signatures used by the UI.

Tables:
  sessions(id, Title, SessionType, FacilitatorEmail, StartDateTime, EndDateTime,
           Capacity, Active, SessionCalendarEventID, TeamsJoinUrl, CreatedAt)
  signups(id, SessionId, ParticipantEmail, ParticipantName, Status, CalendarEventId, CreatedAt)
  facilitators(email, display_name)

Note:
- IDs are UUID hex strings to match string expectations in the UI.
- DateTime columns are stored as ISO 8601 strings (UTC). Keep your UI consistent.
"""

from __future__ import annotations
import os
import sqlite3
import uuid
import threading
from typing import Any, Dict, List, Sequence, Tuple

_DB_DIR = os.path.join(".", ".ephemeral")
os.makedirs(_DB_DIR, exist_ok=True)
_DB_PATH = os.path.join(_DB_DIR, "app.db")

# Single connection per process; SQLite is fine for Streamlit's usage pattern.
_conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_lock = threading.Lock()


def _exec(sql: str, params: Sequence[Any] = ()) -> None:
    with _lock:
        cur = _conn.cursor()
        cur.execute(sql, params)
        _conn.commit()


def _query(sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
    with _lock:
        cur = _conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()


def _one(sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    with _lock:
        cur = _conn.cursor()
        cur.execute(sql, params)
        return cur.fetchone()


def _ensure_schema() -> None:
    _exec(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            Title TEXT NOT NULL,
            SessionType TEXT,
            FacilitatorEmail TEXT NOT NULL,
            StartDateTime TEXT NOT NULL,
            EndDateTime TEXT NOT NULL,
            Capacity INTEGER NOT NULL CHECK (Capacity >= 0),
            Active INTEGER NOT NULL DEFAULT 1,
            SessionCalendarEventID TEXT,
            TeamsJoinUrl TEXT,
            CreatedAt TEXT DEFAULT (datetime('now'))
        );
        """
    )
    _exec(
        """
        CREATE TABLE IF NOT EXISTS signups (
            id TEXT PRIMARY KEY,
            SessionId TEXT NOT NULL,
            ParticipantEmail TEXT NOT NULL,
            ParticipantName TEXT,
            Status TEXT NOT NULL DEFAULT 'Pending',  -- Pending | Confirmed | Removed | Rejected
            CalendarEventId TEXT,
            CreatedAt TEXT DEFAULT (datetime('now')),
            UNIQUE(SessionId, ParticipantEmail)
        );
        """
    )
    _exec(
        """
        CREATE TABLE IF NOT EXISTS facilitators (
            email TEXT PRIMARY KEY,
            display_name TEXT
        );
        """
    )

_ensure_schema()


# ---------- Helpers ----------

def _row_to_session(r: sqlite3.Row) -> Dict[str, Any]:
    return {
        "ID": r["id"],
        "Title": r["Title"],
        "SessionType": r["SessionType"],
        "FacilitatorEmail": r["FacilitatorEmail"],
        "StartDateTime": r["StartDateTime"],
        "EndDateTime": r["EndDateTime"],
        "Capacity": int(r["Capacity"]),
        "Active": bool(r["Active"]),
        "SessionCalendarEventID": r["SessionCalendarEventID"] or "",
        "TeamsJoinUrl": r["TeamsJoinUrl"] or "",
    }


def _row_to_signup(r: sqlite3.Row) -> Dict[str, Any]:
    return {
        "ID": r["id"],
        "SessionId": r["SessionId"],
        "ParticipantEmail": r["ParticipantEmail"],
        "ParticipantName": r["ParticipantName"] or (r["ParticipantEmail"].split("@")[0] if r["ParticipantEmail"] else ""),
        "Status": r["Status"],
        "CalendarEventId": r["CalendarEventId"] or "",
    }


# ---------- Public API (matches your in-memory signatures) ----------

def list_sessions(active_only: bool = True) -> List[Dict[str, Any]]:
    if active_only:
        rows = _query(
            "SELECT * FROM sessions WHERE Active = 1 ORDER BY StartDateTime ASC;"
        )
    else:
        rows = _query("SELECT * FROM sessions ORDER BY StartDateTime ASC;")
    return [_row_to_session(r) for r in rows]


def get_session(session_id: str) -> Dict[str, Any]:
    r = _one("SELECT * FROM sessions WHERE id = ?;", (session_id,))
    if not r:
        raise KeyError(f"Session not found: {session_id}")
    return _row_to_session(r)


def list_signups_for_session(session_id: str, statuses: Sequence[str]) -> List[Dict[str, Any]]:
    placeholders = ",".join("?" for _ in statuses)
    sql = f"SELECT * FROM signups WHERE SessionId = ? AND Status IN ({placeholders}) ORDER BY CreatedAt ASC;"
    rows = _query(sql, (session_id, *statuses))
    return [_row_to_signup(r) for r in rows]


def list_signups_for_user(user_email: str) -> List[Dict[str, Any]]:
    rows = _query(
        "SELECT * FROM signups WHERE ParticipantEmail = ? ORDER BY CreatedAt DESC;",
        (user_email.lower(),),
    )
    return [_row_to_signup(r) for r in rows]


def count_confirmed(session_id: str) -> int:
    r = _one(
        "SELECT COUNT(*) AS c FROM signups WHERE SessionId = ? AND Status = 'Confirmed';",
        (session_id,),
    )
    return int(r["c"] if r else 0)


def create_signup(session_id: str, participant_email: str, participant_name: str) -> Dict[str, Any]:
    # Ensure session exists
    if not _one("SELECT 1 FROM sessions WHERE id = ?;", (session_id,)):
        raise KeyError(f"Session not found: {session_id}")

    signup_id = uuid.uuid4().hex
    try:
        _exec(
            """
            INSERT INTO signups (id, SessionId, ParticipantEmail, ParticipantName, Status, CalendarEventId)
            VALUES (?, ?, ?, ?, 'Pending', '');
            """,
            (signup_id, session_id, participant_email.lower(), participant_name),
        )
    except sqlite3.IntegrityError as ex:
        # Likely UNIQUE(SessionId, ParticipantEmail)
        raise ValueError("You already have a signup for this session.") from ex

    return {"ID": signup_id, "Status": "Pending"}


def update_signup_status(signup_id: str, new_status: str) -> Dict[str, Any]:
    if new_status not in ("Pending", "Confirmed", "Removed", "Rejected"):
        raise ValueError("Invalid status value.")
    _exec("UPDATE signups SET Status = ? WHERE id = ?;", (new_status, signup_id))
    return {"ID": signup_id, "Status": new_status}


# ---------- Extra helpers (for upcoming steps) ----------

def create_session(
    title: str,
    session_type: str,
    facilitator_email: str,
    start_iso: str,
    end_iso: str,
    capacity: int,
    active: bool = True,
    teams_url: str = "",
    calendar_event_id: str = "",
) -> Dict[str, Any]:
    sid = uuid.uuid4().hex
    _exec(
        """
        INSERT INTO sessions (
            id, Title, SessionType, FacilitatorEmail, StartDateTime, EndDateTime,
            Capacity, Active, SessionCalendarEventID, TeamsJoinUrl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            sid, title, session_type, facilitator_email.lower(), start_iso, end_iso,
            int(capacity), 1 if active else 0, calendar_event_id, teams_url,
        ),
    )
    return get_session(sid)


def update_session(
    session_id: str,
    **fields: Any,
) -> Dict[str, Any]:
    allowed = {
        "Title", "SessionType", "FacilitatorEmail", "StartDateTime", "EndDateTime",
        "Capacity", "Active", "SessionCalendarEventID", "TeamsJoinUrl"
    }
    sets = []
    vals: List[Any] = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f"{k} = ?")
        vals.append(v)
    if not sets:
        return get_session(session_id)
    vals.append(session_id)
    sql = f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?;"
    _exec(sql, tuple(vals))
    return get_session(session_id)


def upsert_facilitator(email: str, display_name: str | None = None) -> None:
    _exec(
        """
        INSERT INTO facilitators(email, display_name)
        VALUES(?, ?)
        ON CONFLICT(email) DO UPDATE SET display_name = excluded.display_name;
        """,
        (email.lower(), display_name),
    )


def is_facilitator(email: str) -> bool:
    r = _one("SELECT 1 AS x FROM facilitators WHERE email = ?;", (email.lower(),))
    return bool(r)
def list_facilitators() -> List[Dict[str, str]]:
    rows = _query("SELECT email, COALESCE(display_name, '') AS display_name FROM facilitators ORDER BY email;")
    return [{"email": r["email"], "display_name": r["display_name"]} for r in rows]


def remove_facilitator(email: str) -> None:
    _exec("DELETE FROM facilitators WHERE email = ?;", (email.lower(),))