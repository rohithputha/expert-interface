from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import get_repository  # noqa: E402


TRANSCRIPT_COL = "Scrubbed Transcript"
TOOL_COL = "Scrubbed Transcript with Tool Calls"
URL_COL = "Recording URL (Multichannel) — RAW, contains PHI"
REASON_COL = "Reasoning (why golden / bad)"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/import_calls.py /path/to/calls.xlsx")
    xlsx = Path(sys.argv[1])
    df = pd.read_excel(xlsx)
    repo = get_repository()
    calls = [build_call(row, i) for i, row in df.iterrows()]
    for call in calls:
        repo.upsert_call(call)
    print(json.dumps({"imported": len(calls), "database": "configured DATABASE_URL or backend/data/calls.sqlite3"}))


def build_call(row: Any, index: int) -> dict[str, Any]:
    transcript_text = clean(row.get(TRANSCRIPT_COL))
    tool_text = clean(row.get(TOOL_COL))
    transcript = parse_transcript(transcript_text)
    tool_events = parse_tool_events(tool_text)
    summary = {
        "index": index + 1,
        "turnCount": len(transcript),
        "toolCount": len(tool_events),
        "toolNames": [event["name"] for event in tool_events[:8]],
        "durationLabel": estimate_duration(len(transcript)),
        "issueTags": issue_tags(clean(row.get(REASON_COL)), tool_events),
    }
    return {
        "id": clean(row.get("Call ID")),
        "expectedRating": clean(row.get("Rating")),
        "reasoning": clean(row.get(REASON_COL)),
        "recordingUrl": clean(row.get(URL_COL)),
        "transcript": transcript,
        "toolEvents": tool_events,
        "summary": summary,
    }


def parse_transcript(text: str) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        match = re.match(r"^(Agent|User):\s*(.*)", line.strip())
        if match:
            if current:
                turns.append(current)
            current = {
                "id": f"turn_{len(turns) + 1}",
                "speaker": match.group(1).lower(),
                "text": match.group(2).strip(),
                "timestamp": timestamp_for_turn(len(turns)),
            }
        elif current and line.strip():
            current["text"] = f"{current['text']} {line.strip()}".strip()
    if current:
        turns.append(current)
    return turns


def parse_tool_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        call_match = re.match(r"^\[TOOL CALL\]\s*([a-zA-Z0-9_]+)\((.*)\)\s*$", lines[i].strip())
        if not call_match:
            i += 1
            continue

        name = call_match.group(1)
        args = safe_json(call_match.group(2))
        result = None
        if i + 1 < len(lines) and lines[i + 1].strip().startswith("[TOOL RESULT]"):
            raw_result = lines[i + 1].split(":", 1)[-1].strip()
            result = safe_json(raw_result)
            i += 1
        events.append(
            {
                "id": f"tool_{len(events) + 1}",
                "name": name,
                "args": trim_payload(args),
                "result": trim_payload(result),
                "summary": summarize_tool(name, args, result),
            }
        )
        i += 1
    return events


def summarize_tool(name: str, args: Any, result: Any) -> str:
    if isinstance(result, dict):
        for key in ("outcome", "status", "next_action", "rule_violated"):
            if result.get(key):
                return f"{name}: {key} {result[key]}"
        if "count" in result:
            return f"{name}: {result['count']} result(s)"
    if isinstance(args, dict) and args.get("execution_message"):
        return f"{name}: {args['execution_message']}"
    return name


def trim_payload(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        keep = {}
        for key in (
            "status",
            "outcome",
            "next_action",
            "rule_violated",
            "patient_facing",
            "count",
            "action",
            "execution_message",
            "current_visit_type",
            "new_slot_time",
            "reasonText",
            "errorMessage",
        ):
            if key in value:
                keep[key] = value[key]
        return keep or {"keys": list(value.keys())[:8]}
    return str(value)[:240]


def issue_tags(reasoning: str, tools: list[dict[str, Any]]) -> list[str]:
    text = reasoning.lower()
    tags = []
    checks = {
        "verification": ["verify", "identity", "dob", "authority"],
        "confirmation": ["confirm", "ask_confirm", "commit"],
        "transfer": ["transfer", "human", "team member"],
        "reschedule": ["reschedule", "slot", "appointment"],
        "refill": ["refill", "prescription", "pharmacy"],
        "tooling": ["tool", "ehr", "failed", "success"],
    }
    for tag, needles in checks.items():
        if any(needle in text for needle in needles):
            tags.append(tag)
    if any("transfer" in event["name"] for event in tools) and "transfer" not in tags:
        tags.append("transfer")
    return tags[:4]


def estimate_duration(turn_count: int) -> str:
    seconds = max(45, turn_count * 8)
    return f"{seconds // 60}:{seconds % 60:02d}"


def timestamp_for_turn(index: int) -> str:
    seconds = index * 8
    return f"{seconds // 60}:{seconds % 60:02d}"


def safe_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return raw[:500]


def clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


if __name__ == "__main__":
    main()
