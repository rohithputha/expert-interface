from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import get_repository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a reviewer login.")
    parser.add_argument("email")
    parser.add_argument("password")
    parser.add_argument("--name", default=None)
    parser.add_argument("--assign-all", action="store_true", help="Assign all existing calls to this reviewer.")
    args = parser.parse_args()

    repo = get_repository()
    reviewer = repo.create_reviewer(args.email, args.password, args.name)
    assigned = repo.assign_calls(reviewer["id"]) if args.assign_all else 0
    print(json.dumps({"reviewer": reviewer, "assigned": assigned}))


if __name__ == "__main__":
    main()
