from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import get_repository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Assign calls to a reviewer.")
    parser.add_argument("user_id")
    parser.add_argument("call_ids", nargs="*", help="Specific call ids. Omit to assign every call.")
    args = parser.parse_args()

    repo = get_repository()
    assigned = repo.assign_calls(args.user_id, args.call_ids or None)
    print(json.dumps({"userId": args.user_id, "assigned": assigned}))


if __name__ == "__main__":
    main()
