from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import get_repository  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/import_redacted_csv.py /path/to/redacted.csv")

    csv_path = Path(sys.argv[1])
    repo = get_repository()
    imported = 0

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            call_id = clean(row.get("call_id"))
            if not call_id:
                continue

            transcript = parse_transcript(clean(row.get("readable_transcript")))
            tool_events = parse_tool_events(clean(row.get("tool_call_transcript")))
            summary = {
                "index": imported + 1,
                "turnCount": len(transcript),
                "toolCount": len(tool_events),
                "toolNames": [event["name"] for event in tool_events[:8]],
                "durationLabel": duration_label(clean(row.get("duration_seconds"))),
                "issueTags": issue_tags(clean(row.get("flagged_evals")), clean(row.get("primary_intent_category"))),
                "language": clean(row.get("language")),
                "qualityBucket": clean(row.get("quality_bucket")),
                "workflow": clean(row.get("workflow")),
            }

            repo.upsert_call(
                {
                    "id": call_id,
                    "expectedRating": clean(row.get("quality_bucket")) or "unrated",
                    "reasoning": clean(row.get("summary")),
                    "recordingUrl": clean(row.get("recording_url")),
                    "transcript": transcript,
                    "toolEvents": tool_events,
                    "summary": summary,
                }
            )
            imported += 1

    print(json.dumps({"imported": imported, "source": str(csv_path)}))


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lower() == "nan":
        return ""
    return text.strip()


def parse_transcript(text: str) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = re.match(r"^\[?([0-9]+(?:\.[0-9]+)?)\]?\s*(AGENT|USER|CALLER):\s*(.*)$", line.strip(), re.I)
        if not match:
            continue
        seconds = float(match.group(1))
        speaker = match.group(2).lower()
        if speaker == "caller":
            speaker = "user"
        turns.append(
            {
                "id": f"turn_{len(turns) + 1}",
                "speaker": speaker,
                "timestamp": f"{int(seconds // 60)}:{int(seconds % 60):02d}",
                "text": match.group(3).strip(),
            }
        )
    return turns


def parse_tool_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        call_match = re.match(r"^→\s*TOOL_CALL\s+([a-zA-Z0-9_]+)\((.*)\)\s*$", stripped)
        if call_match:
            if current:
                events.append(current)
            name = call_match.group(1)
            args = safe_json(call_match.group(2))
            current = {
                "id": f"tool_{len(events) + 1}",
                "name": name,
                "args": trim_payload(args),
                "result": None,
                "summary": summarize_tool(name, args, None),
            }
            continue

        result_match = re.match(r"^←\s*TOOL_RESULT:\s*(.*)$", stripped)
        if result_match and current:
            result = safe_json(result_match.group(1))
            current["result"] = trim_payload(result)
            current["summary"] = summarize_tool(current["name"], current["args"], result)
            events.append(current)
            current = None

    if current:
        events.append(current)
    return events


def safe_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return raw[:500]


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
            "match_count",
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


def summarize_tool(name: str, args: Any, result: Any) -> str:
    if isinstance(result, dict):
        for key in ("outcome", "status", "next_action", "rule_violated", "match_count"):
            if result.get(key) is not None:
                return f"{name}: {key} {result[key]}"
        if "count" in result:
            return f"{name}: {result['count']} result(s)"
    if isinstance(args, dict) and args.get("execution_message"):
        return f"{name}: {args['execution_message']}"
    return name


def duration_label(value: str) -> str:
    try:
        seconds = int(float(value))
    except Exception:
        return "0:00"
    return f"{seconds // 60}:{seconds % 60:02d}"


def issue_tags(flagged: str, intent: str) -> list[str]:
    text = f"{flagged} {intent}".lower()
    tags = []
    checks = {
        "verification": ["verify", "identity", "dob", "safety", "compliance"],
        "confirmation": ["confirm"],
        "transfer": ["transfer"],
        "scheduling": ["schedule", "appointment"],
        "workflow": ["workflow"],
        "language": ["language", "spanish"],
    }
    for tag, needles in checks.items():
        if any(needle in text for needle in needles):
            tags.append(tag)
    return tags[:4]


if __name__ == "__main__":
    main()
