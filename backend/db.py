from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB = Path(__file__).parent / "data" / "calls.sqlite3"
HASH_ITERATIONS = 240_000


class CallRepository(ABC):
    @abstractmethod
    def sync_pages(self, rubric: list[dict[str, Any]]) -> None:
        raise NotImplementedError

    @abstractmethod
    def authenticate_reviewer(self, email: str, password: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def create_reviewer(self, email: str, password: str, display_name: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def assign_calls(self, user_id: str, call_ids: list[str] | None = None) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_calls(self, user_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_call(self, call_id: str, user_id: str | None = None) -> dict[str, Any] | None:
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
                create table if not exists reviewers (
                  id text primary key,
                  email text unique not null,
                  display_name text not null,
                  password_hash text not null,
                  active integer not null default 1,
                  created_at text not null
                );

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

                create table if not exists pages (
                  id text primary key,
                  position integer not null,
                  title text not null,
                  description text not null,
                  page_json text not null,
                  active integer not null default 1,
                  created_at text not null
                );

                create table if not exists call_assignments (
                  user_id text not null references reviewers(id),
                  call_id text not null references calls(id),
                  is_done integer not null default 0,
                  assigned_at text not null,
                  completed_at text,
                  primary key (user_id, call_id)
                );

                create table if not exists ratings (
                  id text primary key,
                  user_id text references reviewers(id),
                  call_id text not null references calls(id),
                  ratings_json text not null,
                  evidence text not null,
                  status text not null,
                  reviewer text,
                  timing_json text,
                  created_at text not null,
                  updated_at text
                );

                create unique index if not exists ratings_user_call_idx
                  on ratings(user_id, call_id);

                create table if not exists page_times (
                  user_id text not null references reviewers(id),
                  call_id text not null references calls(id),
                  page_id text not null references pages(id),
                  time_ms integer not null default 0,
                  updated_at text not null,
                  primary key (user_id, call_id, page_id)
                );
                """
            )
            _sqlite_add_column(con, "ratings", "user_id", "text references reviewers(id)")
            _sqlite_add_column(con, "ratings", "updated_at", "text")
            _sqlite_add_column(con, "ratings", "timing_json", "text")

    def sync_pages(self, rubric: list[dict[str, Any]]) -> None:
        with self.connect() as con:
            _sqlite_sync_pages(con, rubric)

    def authenticate_reviewer(self, email: str, password: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute(
                "select * from reviewers where lower(email) = lower(?) and active = 1",
                (email.strip(),),
            ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        return _reviewer(row)

    def create_reviewer(self, email: str, password: str, display_name: str | None = None) -> dict[str, Any]:
        reviewer = {
            "id": str(uuid.uuid4()),
            "email": normalize_email(email),
            "displayName": display_name or email.split("@", 1)[0],
            "passwordHash": hash_password(password),
            "createdAt": _now(),
        }
        with self.connect() as con:
            con.execute(
                """
                insert into reviewers (id, email, display_name, password_hash, active, created_at)
                values (?, ?, ?, ?, 1, ?)
                on conflict(email) do update set
                  display_name = excluded.display_name,
                  password_hash = excluded.password_hash,
                  active = 1
                """,
                (
                    reviewer["id"],
                    reviewer["email"],
                    reviewer["displayName"],
                    reviewer["passwordHash"],
                    reviewer["createdAt"],
                ),
            )
            row = con.execute("select * from reviewers where email = ?", (reviewer["email"],)).fetchone()
        return _reviewer(row)

    def assign_calls(self, user_id: str, call_ids: list[str] | None = None) -> int:
        with self.connect() as con:
            if call_ids is None:
                rows = con.execute("select id from calls order by created_at, id").fetchall()
                call_ids = [row["id"] for row in rows]
            for call_id in call_ids:
                con.execute(
                    """
                    insert into call_assignments (user_id, call_id, is_done, assigned_at)
                    values (?, ?, 0, ?)
                    on conflict(user_id, call_id) do nothing
                    """,
                    (user_id, call_id, _now()),
                )
        return len(call_ids)

    def list_calls(self, user_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        if user_id:
            query = """
                select c.*, a.is_done, a.completed_at,
                       r.updated_at as reviewed_at, rv.email as reviewed_by
                from call_assignments a
                join calls c on c.id = a.call_id
                left join ratings r on r.call_id = c.id and r.user_id = a.user_id
                left join reviewers rv on rv.id = a.user_id
                where a.user_id = ?
                order by a.is_done, c.created_at, c.id
            """
            with self.connect() as con:
                rows = [_call_summary(row) for row in con.execute(query, (user_id,)).fetchall()]
        else:
            query = """
                select c.*, null as is_done, null as completed_at,
                       null as reviewed_at, null as reviewed_by
                from calls c
                order by c.created_at, c.id
            """
            with self.connect() as con:
                rows = [_call_summary(row) for row in con.execute(query).fetchall()]
        if status:
            rows = [row for row in rows if row["reviewStatus"] == status]
        return rows

    def get_call(self, call_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        params: tuple[Any, ...]
        if user_id:
            query = """
                select c.*, a.is_done, a.completed_at,
                       r.updated_at as reviewed_at, rv.email as reviewed_by
                from calls c
                join call_assignments a on a.call_id = c.id and a.user_id = ?
                left join ratings r on r.call_id = c.id and r.user_id = a.user_id
                left join reviewers rv on rv.id = a.user_id
                where c.id = ?
            """
            params = (user_id, call_id)
        else:
            query = """
                select c.*, null as is_done, null as completed_at,
                       null as reviewed_at, null as reviewed_by
                from calls c
                where c.id = ?
            """
            params = (call_id,)
        with self.connect() as con:
            row = con.execute(query, params).fetchone()
            if not row:
                return None
            rating_rows = con.execute(
                """
                select r.*, rv.email as reviewer_email
                from ratings r
                left join reviewers rv on rv.id = r.user_id
                where r.call_id = ? and (? is null or r.user_id = ?)
                order by coalesce(r.updated_at, r.created_at) desc
                """,
                (call_id, user_id, user_id),
            ).fetchall()
            time_rows = con.execute(
                "select page_id, time_ms from page_times where call_id = ? and user_id = ?",
                (call_id, user_id),
            ).fetchall() if user_id else []
        call = _full_call(row)
        timings = _timing_from_rows(time_rows)
        call["ratingsHistory"] = [_rating(rating_row, timings) for rating_row in rating_rows]
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
                _call_values(call),
            )

    def save_rating(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_id = payload["user_id"]
        call_id = payload["call_id"]
        now = _now()
        rating_id = str(uuid.uuid4())
        reviewer = payload.get("reviewer")
        timing = payload.get("timing") or {}
        with self.connect() as con:
            reviewer_row = con.execute("select * from reviewers where id = ? and active = 1", (user_id,)).fetchone()
            if not reviewer_row:
                raise ValueError("Reviewer not found")
            assignment = con.execute(
                "select 1 from call_assignments where user_id = ? and call_id = ?",
                (user_id, call_id),
            ).fetchone()
            if not assignment:
                raise ValueError("Call is not assigned to reviewer")
            con.execute(
                """
                insert into ratings (
                  id, user_id, call_id, ratings_json, evidence, status, reviewer, timing_json, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(user_id, call_id) do update set
                  ratings_json = excluded.ratings_json,
                  evidence = excluded.evidence,
                  status = excluded.status,
                  reviewer = excluded.reviewer,
                  timing_json = excluded.timing_json,
                  updated_at = excluded.updated_at
                """,
                (
                    rating_id,
                    user_id,
                    call_id,
                    json.dumps(payload["ratings"]),
                    payload["evidence"],
                    payload.get("status", "submitted"),
                    reviewer or reviewer_row["email"],
                    json.dumps(timing),
                    now,
                    now,
                ),
            )
            _sqlite_save_page_times(con, user_id, call_id, timing, now)
            if payload.get("complete"):
                con.execute(
                    """
                    update call_assignments
                    set is_done = 1, completed_at = ?
                    where user_id = ? and call_id = ?
                    """,
                    (now, user_id, call_id),
                )
        return {
            "id": rating_id,
            "callId": call_id,
            "ratings": payload["ratings"],
            "evidence": payload["evidence"],
            "status": payload.get("status", "submitted"),
            "reviewer": reviewer,
            "timing": timing,
            "createdAt": now,
        }


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
                create table if not exists reviewers (
                  id text primary key,
                  email text unique not null,
                  display_name text not null,
                  password_hash text not null,
                  active boolean not null default true,
                  created_at timestamptz not null
                )
                """
            )
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
                create table if not exists pages (
                  id text primary key,
                  position integer not null,
                  title text not null,
                  description text not null,
                  page_json jsonb not null,
                  active boolean not null default true,
                  created_at timestamptz not null
                )
                """
            )
            con.execute(
                """
                create table if not exists call_assignments (
                  user_id text not null references reviewers(id),
                  call_id text not null references calls(id),
                  is_done boolean not null default false,
                  assigned_at timestamptz not null,
                  completed_at timestamptz,
                  primary key (user_id, call_id)
                )
                """
            )
            con.execute(
                """
                create table if not exists ratings (
                  id text primary key,
                  user_id text references reviewers(id),
                  call_id text not null references calls(id),
                  ratings_json jsonb not null,
                  evidence text not null,
                  status text not null,
                  reviewer text,
                  timing_json jsonb,
                  created_at timestamptz not null,
                  updated_at timestamptz
                )
                """
            )
            con.execute("alter table ratings add column if not exists user_id text references reviewers(id)")
            con.execute("alter table ratings add column if not exists updated_at timestamptz")
            con.execute("alter table ratings add column if not exists timing_json jsonb")
            con.execute(
                """
                create unique index if not exists ratings_user_call_idx
                  on ratings(user_id, call_id)
                """
            )
            con.execute(
                """
                create table if not exists page_times (
                  user_id text not null references reviewers(id),
                  call_id text not null references calls(id),
                  page_id text not null references pages(id),
                  time_ms bigint not null default 0,
                  updated_at timestamptz not null,
                  primary key (user_id, call_id, page_id)
                )
                """
            )

    def sync_pages(self, rubric: list[dict[str, Any]]) -> None:
        with self.connect() as con:
            for position, page in enumerate(rubric, start=1):
                con.execute(
                    """
                    insert into pages (id, position, title, description, page_json, active, created_at)
                    values (%s, %s, %s, %s, %s::jsonb, true, %s)
                    on conflict(id) do update set
                      position = excluded.position,
                      title = excluded.title,
                      description = excluded.description,
                      page_json = excluded.page_json,
                      active = true
                    """,
                    (
                        page["id"],
                        position,
                        page["title"],
                        page.get("description", ""),
                        json.dumps(page),
                        _now(),
                    ),
                )

    def authenticate_reviewer(self, email: str, password: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute(
                "select * from reviewers where lower(email) = lower(%s) and active = true",
                (email.strip(),),
            ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        return _pg_reviewer(row)

    def create_reviewer(self, email: str, password: str, display_name: str | None = None) -> dict[str, Any]:
        reviewer = {
            "id": str(uuid.uuid4()),
            "email": normalize_email(email),
            "displayName": display_name or email.split("@", 1)[0],
            "passwordHash": hash_password(password),
            "createdAt": _now(),
        }
        with self.connect() as con:
            con.execute(
                """
                insert into reviewers (id, email, display_name, password_hash, active, created_at)
                values (%s, %s, %s, %s, true, %s)
                on conflict(email) do update set
                  display_name = excluded.display_name,
                  password_hash = excluded.password_hash,
                  active = true
                """,
                (
                    reviewer["id"],
                    reviewer["email"],
                    reviewer["displayName"],
                    reviewer["passwordHash"],
                    reviewer["createdAt"],
                ),
            )
            row = con.execute("select * from reviewers where email = %s", (reviewer["email"],)).fetchone()
        return _pg_reviewer(row)

    def assign_calls(self, user_id: str, call_ids: list[str] | None = None) -> int:
        with self.connect() as con:
            if call_ids is None:
                call_ids = [row["id"] for row in con.execute("select id from calls order by created_at, id").fetchall()]
            for call_id in call_ids:
                con.execute(
                    """
                    insert into call_assignments (user_id, call_id, is_done, assigned_at)
                    values (%s, %s, false, %s)
                    on conflict(user_id, call_id) do nothing
                    """,
                    (user_id, call_id, _now()),
                )
        return len(call_ids)

    def list_calls(self, user_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        if user_id:
            query = """
                select c.*, a.is_done, a.completed_at,
                       r.updated_at as reviewed_at, rv.email as reviewed_by
                from call_assignments a
                join calls c on c.id = a.call_id
                left join ratings r on r.call_id = c.id and r.user_id = a.user_id
                left join reviewers rv on rv.id = a.user_id
                where a.user_id = %s
                order by a.is_done, c.created_at, c.id
            """
            params = (user_id,)
        else:
            query = """
                select c.*, null as is_done, null as completed_at,
                       null as reviewed_at, null as reviewed_by
                from calls c
                order by c.created_at, c.id
            """
            params = ()
        with self.connect() as con:
            rows = [_pg_call_summary(row) for row in con.execute(query, params).fetchall()]
        if status:
            rows = [row for row in rows if row["reviewStatus"] == status]
        return rows

    def get_call(self, call_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        if user_id:
            query = """
                select c.*, a.is_done, a.completed_at,
                       r.updated_at as reviewed_at, rv.email as reviewed_by
                from calls c
                join call_assignments a on a.call_id = c.id and a.user_id = %s
                left join ratings r on r.call_id = c.id and r.user_id = a.user_id
                left join reviewers rv on rv.id = a.user_id
                where c.id = %s
            """
            params = (user_id, call_id)
        else:
            query = """
                select c.*, null as is_done, null as completed_at,
                       null as reviewed_at, null as reviewed_by
                from calls c
                where c.id = %s
            """
            params = (call_id,)
        with self.connect() as con:
            row = con.execute(query, params).fetchone()
            if not row:
                return None
            rating_rows = con.execute(
                """
                select r.*, rv.email as reviewer_email
                from ratings r
                left join reviewers rv on rv.id = r.user_id
                where r.call_id = %s and (%s is null or r.user_id = %s)
                order by coalesce(r.updated_at, r.created_at) desc
                """,
                (call_id, user_id, user_id),
            ).fetchall()
            time_rows = con.execute(
                "select page_id, time_ms from page_times where call_id = %s and user_id = %s",
                (call_id, user_id),
            ).fetchall() if user_id else []
        call = _pg_full_call(row)
        timings = _timing_from_rows(time_rows)
        call["ratingsHistory"] = [_pg_rating(rating_row, timings) for rating_row in rating_rows]
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
                _call_values(call),
            )

    def save_rating(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_id = payload["user_id"]
        call_id = payload["call_id"]
        now = _now()
        rating_id = str(uuid.uuid4())
        timing = payload.get("timing") or {}
        with self.connect() as con:
            reviewer = con.execute("select * from reviewers where id = %s and active = true", (user_id,)).fetchone()
            if not reviewer:
                raise ValueError("Reviewer not found")
            assignment = con.execute(
                "select 1 from call_assignments where user_id = %s and call_id = %s",
                (user_id, call_id),
            ).fetchone()
            if not assignment:
                raise ValueError("Call is not assigned to reviewer")
            con.execute(
                """
                insert into ratings (
                  id, user_id, call_id, ratings_json, evidence, status, reviewer, timing_json, created_at, updated_at
                ) values (%s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s, %s)
                on conflict(user_id, call_id) do update set
                  ratings_json = excluded.ratings_json,
                  evidence = excluded.evidence,
                  status = excluded.status,
                  reviewer = excluded.reviewer,
                  timing_json = excluded.timing_json,
                  updated_at = excluded.updated_at
                """,
                (
                    rating_id,
                    user_id,
                    call_id,
                    json.dumps(payload["ratings"]),
                    payload["evidence"],
                    payload.get("status", "submitted"),
                    reviewer["email"],
                    json.dumps(timing),
                    now,
                    now,
                ),
            )
            _pg_save_page_times(con, user_id, call_id, timing, now)
            if payload.get("complete"):
                con.execute(
                    """
                    update call_assignments
                    set is_done = true, completed_at = %s
                    where user_id = %s and call_id = %s
                    """,
                    (now, user_id, call_id),
                )
        return {
            "id": rating_id,
            "callId": call_id,
            "ratings": payload["ratings"],
            "evidence": payload["evidence"],
            "status": payload.get("status", "submitted"),
            "reviewer": reviewer["email"],
            "timing": timing,
            "createdAt": now,
        }


def get_repository() -> CallRepository:
    database_url = os.environ.get("DATABASE_URL")
    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        return PostgresRepository(database_url)
    return SQLiteRepository(database_url)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(HASH_ITERATIONS),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_raw.encode("ascii"))
        expected = base64.b64decode(digest_raw.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations_raw))
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _sqlite_path(database_url: str | None) -> Path:
    if not database_url:
        return DEFAULT_DB
    if database_url.startswith("sqlite:///"):
        return Path(database_url.replace("sqlite:///", "", 1))
    return Path(database_url)


def _sqlite_sync_pages(con: sqlite3.Connection, rubric: list[dict[str, Any]]) -> None:
    for position, page in enumerate(rubric, start=1):
        con.execute(
            """
            insert into pages (id, position, title, description, page_json, active, created_at)
            values (?, ?, ?, ?, ?, 1, ?)
            on conflict(id) do update set
              position = excluded.position,
              title = excluded.title,
              description = excluded.description,
              page_json = excluded.page_json,
              active = 1
            """,
            (
                page["id"],
                position,
                page["title"],
                page.get("description", ""),
                json.dumps(page),
                _now(),
            ),
        )


def _sqlite_save_page_times(con: sqlite3.Connection, user_id: str, call_id: str, timing: dict[str, Any], now: str) -> None:
    for page_id, time_ms in _criterion_times(timing).items():
        con.execute(
            """
            insert into page_times (user_id, call_id, page_id, time_ms, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(user_id, call_id, page_id) do update set
              time_ms = excluded.time_ms,
              updated_at = excluded.updated_at
            """,
            (user_id, call_id, page_id, time_ms, now),
        )


def _pg_save_page_times(con: Any, user_id: str, call_id: str, timing: dict[str, Any], now: str) -> None:
    for page_id, time_ms in _criterion_times(timing).items():
        con.execute(
            """
            insert into page_times (user_id, call_id, page_id, time_ms, updated_at)
            values (%s, %s, %s, %s, %s)
            on conflict(user_id, call_id, page_id) do update set
              time_ms = excluded.time_ms,
              updated_at = excluded.updated_at
            """,
            (user_id, call_id, page_id, time_ms, now),
        )


def _criterion_times(timing: dict[str, Any]) -> dict[str, int]:
    criterion_ms = timing.get("criterionMs") if isinstance(timing, dict) else None
    if not isinstance(criterion_ms, dict):
        return {}
    times: dict[str, int] = {}
    for page_id, value in criterion_ms.items():
        try:
            time_ms = int(float(value))
        except (TypeError, ValueError):
            continue
        if time_ms >= 0:
            times[str(page_id)] = time_ms
    return times


def _timing_from_rows(rows: list[Any]) -> dict[str, Any]:
    criterion_ms = {row["page_id"]: int(row["time_ms"]) for row in rows}
    return {"criterionMs": criterion_ms, "totalMs": sum(criterion_ms.values())}


def _call_values(call: dict[str, Any]) -> tuple[Any, ...]:
    return (
        call["id"],
        call["expectedRating"],
        call["reasoning"],
        call["recordingUrl"],
        json.dumps(call["transcript"]),
        json.dumps(call["toolEvents"]),
        json.dumps(call["summary"]),
        call.get("createdAt") or _now(),
    )


def _call_summary(row: Any) -> dict[str, Any]:
    summary = _json_value(row["summary_json"])
    is_done = _row_get(row, "is_done")
    review_status = "submitted" if is_done else "unreviewed"
    return {
        "id": row["id"],
        "expectedRating": row["expected_rating"],
        "reasoning": row["reasoning"],
        "recordingUrl": _recording_url(row["id"], row["recording_url"]),
        "summary": summary,
        "reviewStatus": review_status,
        "reviewedAt": _iso(_row_get(row, "completed_at") or _row_get(row, "reviewed_at")),
        "reviewedBy": _row_get(row, "reviewed_by"),
    }


def _full_call(row: Any) -> dict[str, Any]:
    call = _call_summary(row)
    call["transcript"] = _json_value(row["transcript_json"])
    call["toolEvents"] = _json_value(row["tool_events_json"])
    call["createdAt"] = _iso(row["created_at"])
    return call


def _rating(row: Any, timing: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "callId": row["call_id"],
        "ratings": _json_value(row["ratings_json"]),
        "evidence": row["evidence"],
        "status": row["status"],
        "reviewer": _row_get(row, "reviewer_email") or row["reviewer"],
        "timing": timing or _json_value(_row_get(row, "timing_json") or "{}"),
        "createdAt": _iso(_row_get(row, "updated_at") or row["created_at"]),
    }


def _pg_call_summary(row: dict[str, Any]) -> dict[str, Any]:
    return _call_summary(row)


def _pg_full_call(row: dict[str, Any]) -> dict[str, Any]:
    return _full_call(row)


def _pg_rating(row: dict[str, Any], timing: dict[str, Any]) -> dict[str, Any]:
    return _rating(row, timing)


def _reviewer(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["display_name"],
        "displayName": row["display_name"],
    }


def _pg_reviewer(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["display_name"],
        "displayName": row["display_name"],
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _recording_url(call_id: str, stored_url: str) -> str:
    if os.environ.get("GCS_AUDIO_BUCKET"):
        return f"/api/calls/{call_id}/audio"
    return stored_url


def _row_get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[key] if key in row.keys() else None


def _sqlite_add_column(con: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in con.execute(f"pragma table_info({table})").fetchall()}
    if column not in existing:
        con.execute(f"alter table {table} add column {column} {definition}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
