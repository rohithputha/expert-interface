from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import get_repository  # noqa: E402
from rubric import RUBRIC  # noqa: E402


BASE_COLUMNS = [
    "reviewer_id",
    "reviewer_email",
    "reviewer_name",
    "call_id",
    "assignment_done",
    "assigned_at",
    "completed_at",
    "has_rating",
    "rating_status",
    "rating_created_at",
    "rating_updated_at",
    "expected_rating",
    "recording_url",
    "call_index",
    "language",
    "workflow",
    "quality_bucket",
    "duration",
    "turn_count",
    "tool_count",
    "tool_names",
    "issue_tags",
    "reasoning",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export assigned call review responses with rating JSON, notes, and page timing flattened to CSV."
    )
    parser.add_argument("output", nargs="?", default="responses_export.csv", help="CSV path to write.")
    parser.add_argument(
        "--submitted-only",
        action="store_true",
        help="Only export assignments marked done in call_assignments.",
    )
    args = parser.parse_args()

    repo = get_repository()
    rows = load_rows(repo)
    if args.submitted_only:
        rows = [row for row in rows if as_bool(row_get(row, "is_done"))]

    rubric_index = build_rubric_index()
    time_by_assignment = load_page_times(repo)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    columns = build_columns(rubric_index)
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for source in rows:
            writer.writerow(flatten_row(source, rubric_index, time_by_assignment))

    print(json.dumps({"exported": len(rows), "output": str(output_path)}))


def load_rows(repo: Any) -> list[Any]:
    query = """
        select
          a.user_id,
          a.call_id,
          a.is_done,
          a.assigned_at,
          a.completed_at,
          rv.email as reviewer_email,
          rv.display_name as reviewer_name,
          c.expected_rating,
          c.reasoning,
          c.recording_url,
          c.summary_json,
          r.id as rating_id,
          r.ratings_json,
          r.evidence,
          r.status as rating_status,
          r.created_at as rating_created_at,
          r.updated_at as rating_updated_at
        from call_assignments a
        join reviewers rv on rv.id = a.user_id
        join calls c on c.id = a.call_id
        left join ratings r on r.user_id = a.user_id and r.call_id = a.call_id
        order by rv.email, a.is_done, c.created_at, a.call_id
    """
    with repo.connect() as con:
        return con.execute(query).fetchall()


def load_page_times(repo: Any) -> dict[tuple[str, str], dict[str, int]]:
    with repo.connect() as con:
        rows = con.execute("select user_id, call_id, page_id, time_ms from page_times").fetchall()
    times: dict[tuple[str, str], dict[str, int]] = {}
    for row in rows:
        key = (str(row_get(row, "user_id")), str(row_get(row, "call_id")))
        times.setdefault(key, {})[str(row_get(row, "page_id"))] = int(row_get(row, "time_ms") or 0)
    return times


def build_rubric_index() -> dict[str, Any]:
    pages = []
    subcriteria = []
    option_points: dict[tuple[str, str], Any] = {}
    for page in RUBRIC:
        page_id = page["id"]
        pages.append({"id": page_id, "title": page["title"], "column": slug(page_id)})
        for subcriterion in page.get("subcriteria", []):
            sub_id = subcriterion["id"]
            subcriteria.append(
                {
                    "page_id": page_id,
                    "page_title": page["title"],
                    "id": sub_id,
                    "title": subcriterion["title"],
                    "column": slug(sub_id),
                }
            )
            for option in subcriterion.get("options", []):
                option_points[(sub_id, option["value"])] = option.get("points")
    return {"pages": pages, "subcriteria": subcriteria, "option_points": option_points}


def build_columns(rubric_index: dict[str, Any]) -> list[str]:
    columns = list(BASE_COLUMNS)
    for item in rubric_index["subcriteria"]:
        columns.append(f"rating__{item['column']}")
        columns.append(f"points__{item['column']}")
    for page in rubric_index["pages"]:
        columns.append(f"notes__{page['column']}")
    for page in rubric_index["pages"]:
        columns.append(f"time_seconds__{page['column']}")
    columns.append("time_seconds__total")
    return columns


def flatten_row(source: Any, rubric_index: dict[str, Any], time_by_assignment: dict[tuple[str, str], dict[str, int]]) -> dict[str, Any]:
    user_id = str(row_get(source, "user_id") or "")
    call_id = str(row_get(source, "call_id") or "")
    summary = json_value(row_get(source, "summary_json"), {})
    ratings = json_value(row_get(source, "ratings_json"), {})
    evidence = json_value(row_get(source, "evidence"), {})
    page_times = time_by_assignment.get((user_id, call_id), {})

    row: dict[str, Any] = {
        "reviewer_id": user_id,
        "reviewer_email": row_get(source, "reviewer_email"),
        "reviewer_name": row_get(source, "reviewer_name"),
        "call_id": call_id,
        "assignment_done": "true" if as_bool(row_get(source, "is_done")) else "false",
        "assigned_at": iso(row_get(source, "assigned_at")),
        "completed_at": iso(row_get(source, "completed_at")),
        "has_rating": "true" if row_get(source, "rating_id") else "false",
        "rating_status": row_get(source, "rating_status"),
        "rating_created_at": iso(row_get(source, "rating_created_at")),
        "rating_updated_at": iso(row_get(source, "rating_updated_at")),
        "expected_rating": row_get(source, "expected_rating"),
        "recording_url": row_get(source, "recording_url"),
        "call_index": summary.get("index"),
        "language": summary.get("language"),
        "workflow": summary.get("workflow"),
        "quality_bucket": summary.get("qualityBucket"),
        "duration": summary.get("durationLabel"),
        "turn_count": summary.get("turnCount"),
        "tool_count": summary.get("toolCount"),
        "tool_names": join_list(summary.get("toolNames")),
        "issue_tags": join_list(summary.get("issueTags")),
        "reasoning": row_get(source, "reasoning"),
    }

    for item in rubric_index["subcriteria"]:
        value = ratings.get(item["id"]) if isinstance(ratings, dict) else None
        row[f"rating__{item['column']}"] = value
        row[f"points__{item['column']}"] = rubric_index["option_points"].get((item["id"], value), "")

    for page in rubric_index["pages"]:
        row[f"notes__{page['column']}"] = evidence.get(page["id"], "") if isinstance(evidence, dict) else ""

    total_ms = 0
    for page in rubric_index["pages"]:
        time_ms = int(page_times.get(page["id"], 0) or 0)
        total_ms += time_ms
        row[f"time_seconds__{page['column']}"] = round(time_ms / 1000, 3) if time_ms else ""
    row["time_seconds__total"] = round(total_ms / 1000, 3) if total_ms else ""
    return row


def json_value(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def row_get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (IndexError, KeyError, TypeError):
        return None


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.lower() in {"1", "true", "t", "yes", "y"}
    return False


def iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def join_list(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return "; ".join(str(item) for item in value)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


if __name__ == "__main__":
    main()
