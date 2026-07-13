from __future__ import annotations

import json
import os
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB = Path(__file__).parent / "data" / "calls.sqlite3"


class CallRepository(ABC):
    @abstractmethod
    def list_calls(self, status: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_call(self, call_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def upsert_call(self, call: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_rating(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class SQLiteRepository(CallRepository):
    def __init__(self, database_url: str | None = None) -> None:
        self.path = _sqlite_path(database_url)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        with self.connect() as con:
            con.executescript(
                """
                create table if not exists calls (
                  id text primary key,
                  expected_rating text not null,
                  reasoning text not null,
                  recording_url text not null,
                  transcript_json text not null,
                  tool_events_json text not null,
                  summary_json text not null,
                  created_at text not null
                );

                create table if not exists ratings (
                  id text primary key,
                  call_id text not null references calls(id),
                  ratings_json text not null,
                  evidence text not null,
                  status text not null,
                  reviewer text,
                  timing_json text,
                  created_at text not null
                );
                """
            )
            _sqlite_add_column(con, "ratings", "timing_json", "text")

    def list_calls(self, status: str | None = None) -> list[dict[str, Any]]:
        query = """
            select c.*, r.status as review_status, r.created_at as reviewed_at, r.reviewer as reviewed_by
            from calls c
            left join (
              select r1.call_id, r1.status, r1.created_at, r1.reviewer
              from ratings r1
              inner join (
                select call_id, max(created_at) created_at
                from ratings
                group by call_id
              ) latest on latest.call_id = r1.call_id and latest.created_at = r1.created_at
            ) r on r.call_id = c.id
            order by c.created_at, c.id
        """
        with self.connect() as con:
            rows = [_call_summary(row) for row in con.execute(query).fetchall()]
        if status:
            rows = [row for row in rows if row["reviewStatus"] == status]
        return rows

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("select * from calls where id = ?", (call_id,)).fetchone()
            if not row:
                return None
            ratings = con.execute(
                "select * from ratings where call_id = ? order by created_at desc",
                (call_id,),
            ).fetchall()
        call = _full_call(row)
        call["ratingsHistory"] = [_rating(row) for row in ratings]
        return call

    def upsert_call(self, call: dict[str, Any]) -> None:
        with self.connect() as con:
            con.execute(
                """
                insert into calls (
                  id, expected_rating, reasoning, recording_url, transcript_json,
                  tool_events_json, summary_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  expected_rating = excluded.expected_rating,
                  reasoning = excluded.reasoning,
                  recording_url = excluded.recording_url,
                  transcript_json = excluded.transcript_json,
                  tool_events_json = excluded.tool_events_json,
                  summary_json = excluded.summary_json
                """,
                (
                    call["id"],
                    call["expectedRating"],
                    call["reasoning"],
                    call["recordingUrl"],
                    json.dumps(call["transcript"]),
                    json.dumps(call["toolEvents"]),
                    json.dumps(call["summary"]),
                    call.get("createdAt") or _now(),
                ),
            )

    def save_rating(self, payload: dict[str, Any]) -> dict[str, Any]:
        rating = {
            "id": str(uuid.uuid4()),
            "callId": payload["call_id"],
            "ratings": payload["ratings"],
            "evidence": payload["evidence"],
            "status": payload.get("status", "submitted"),
            "reviewer": payload.get("reviewer"),
            "timing": payload.get("timing") or {},
            "createdAt": _now(),
        }
        with self.connect() as con:
            con.execute(
                """
                insert into ratings (id, call_id, ratings_json, evidence, status, reviewer, timing_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rating["id"],
                    rating["callId"],
                    json.dumps(rating["ratings"]),
                    rating["evidence"],
                    rating["status"],
                    rating["reviewer"],
                    json.dumps(rating["timing"]),
                    rating["createdAt"],
                ),
            )
        return rating


class PostgresRepository(CallRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        try:
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Postgres DATABASE_URL requires psycopg. Install psycopg[binary].") from exc
        self.psycopg = psycopg
        self.dict_row = dict_row
        self._init()

    def connect(self):
        return self.psycopg.connect(self.database_url, row_factory=self.dict_row)

    def _init(self) -> None:
        with self.connect() as con:
            con.execute(
                """
                create table if not exists calls (
                  id text primary key,
                  expected_rating text not null,
                  reasoning text not null,
                  recording_url text not null,
                  transcript_json jsonb not null,
                  tool_events_json jsonb not null,
                  summary_json jsonb not null,
                  created_at timestamptz not null
                )
                """
            )
            con.execute(
                """
                create table if not exists ratings (
                  id text primary key,
                  call_id text not null references calls(id),
                  ratings_json jsonb not null,
                  evidence text not null,
                  status text not null,
                  reviewer text,
                  timing_json jsonb,
                  created_at timestamptz not null
                )
                """
            )
            con.execute("alter table ratings add column if not exists timing_json jsonb")

    def list_calls(self, status: str | None = None) -> list[dict[str, Any]]:
        query = """
            select c.*, r.status as review_status, r.created_at as reviewed_at, r.reviewer as reviewed_by
            from calls c
            left join (
              select distinct on (call_id) call_id, status, created_at, reviewer
              from ratings
              order by call_id, created_at desc
            ) r on r.call_id = c.id
            order by c.created_at, c.id
        """
        with self.connect() as con:
            rows = [_pg_call_summary(row) for row in con.execute(query).fetchall()]
        if status:
            rows = [row for row in rows if row["reviewStatus"] == status]
        return rows

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("select * from calls where id = %s", (call_id,)).fetchone()
            if not row:
                return None
            ratings = con.execute(
                "select * from ratings where call_id = %s order by created_at desc",
                (call_id,),
            ).fetchall()
        call = _pg_full_call(row)
        call["ratingsHistory"] = [_pg_rating(row) for row in ratings]
        return call

    def upsert_call(self, call: dict[str, Any]) -> None:
        with self.connect() as con:
            con.execute(
                """
                insert into calls (
                  id, expected_rating, reasoning, recording_url, transcript_json,
                  tool_events_json, summary_json, created_at
                ) values (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                on conflict(id) do update set
                  expected_rating = excluded.expected_rating,
                  reasoning = excluded.reasoning,
                  recording_url = excluded.recording_url,
                  transcript_json = excluded.transcript_json,
                  tool_events_json = excluded.tool_events_json,
                  summary_json = excluded.summary_json
                """,
                (
                    call["id"],
                    call["expectedRating"],
                    call["reasoning"],
                    call["recordingUrl"],
                    json.dumps(call["transcript"]),
                    json.dumps(call["toolEvents"]),
                    json.dumps(call["summary"]),
                    call.get("createdAt") or _now(),
                ),
            )

    def save_rating(self, payload: dict[str, Any]) -> dict[str, Any]:
        rating = {
            "id": str(uuid.uuid4()),
            "callId": payload["call_id"],
            "ratings": payload["ratings"],
            "evidence": payload["evidence"],
            "status": payload.get("status", "submitted"),
            "reviewer": payload.get("reviewer"),
            "timing": payload.get("timing") or {},
            "createdAt": _now(),
        }
        with self.connect() as con:
            con.execute(
                """
                insert into ratings (id, call_id, ratings_json, evidence, status, reviewer, timing_json, created_at)
                values (%s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    rating["id"],
                    rating["callId"],
                    json.dumps(rating["ratings"]),
                    rating["evidence"],
                    rating["status"],
                    rating["reviewer"],
                    json.dumps(rating["timing"]),
                    rating["createdAt"],
                ),
            )
        return rating


def get_repository() -> CallRepository:
    database_url = os.environ.get("DATABASE_URL")
    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        return PostgresRepository(database_url)
    return SQLiteRepository(database_url)


def _sqlite_path(database_url: str | None) -> Path:
    if not database_url:
        return DEFAULT_DB
    if database_url.startswith("sqlite:///"):
        return Path(database_url.replace("sqlite:///", "", 1))
    return Path(database_url)


def _call_summary(row: sqlite3.Row) -> dict[str, Any]:
    summary = json.loads(row["summary_json"])
    return {
        "id": row["id"],
        "expectedRating": row["expected_rating"],
        "reasoning": row["reasoning"],
        "recordingUrl": row["recording_url"],
        "summary": summary,
        "reviewStatus": _row_get(row, "review_status") or "unreviewed",
        "reviewedAt": _row_get(row, "reviewed_at"),
        "reviewedBy": _row_get(row, "reviewed_by"),
    }


def _full_call(row: sqlite3.Row) -> dict[str, Any]:
    call = _call_summary(row)
    call["transcript"] = json.loads(row["transcript_json"])
    call["toolEvents"] = json.loads(row["tool_events_json"])
    call["createdAt"] = row["created_at"]
    return call


def _rating(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "callId": row["call_id"],
        "ratings": json.loads(row["ratings_json"]),
        "evidence": row["evidence"],
        "status": row["status"],
        "reviewer": row["reviewer"],
        "timing": json.loads(_row_get(row, "timing_json") or "{}"),
        "createdAt": row["created_at"],
    }


def _pg_call_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "expectedRating": row["expected_rating"],
        "reasoning": row["reasoning"],
        "recordingUrl": row["recording_url"],
        "summary": row["summary_json"],
        "reviewStatus": row["review_status"] or "unreviewed",
        "reviewedAt": _iso(row["reviewed_at"]),
        "reviewedBy": row.get("reviewed_by"),
    }


def _pg_full_call(row: dict[str, Any]) -> dict[str, Any]:
    call = _pg_call_summary({**row, "review_status": None, "reviewed_at": None, "reviewed_by": None})
    call["transcript"] = row["transcript_json"]
    call["toolEvents"] = row["tool_events_json"]
    call["createdAt"] = _iso(row["created_at"])
    return call


def _pg_rating(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "callId": row["call_id"],
        "ratings": row["ratings_json"],
        "evidence": row["evidence"],
        "status": row["status"],
        "reviewer": row["reviewer"],
        "timing": row.get("timing_json") or {},
        "createdAt": _iso(row["created_at"]),
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _row_get(row: sqlite3.Row, key: str) -> Any:
    return row[key] if key in row.keys() else None


def _sqlite_add_column(con: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in con.execute(f"pragma table_info({table})").fetchall()}
    if column not in existing:
        con.execute(f"alter table {table} add column {column} {definition}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
