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
            summary = {
                "index": imported + 1,
                "turnCount": len(transcript),
                "toolCount": 0,
                "toolNames": [],
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
                    "toolEvents": [],
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
