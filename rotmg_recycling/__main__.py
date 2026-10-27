"""Run with: python -m rotmg_recycling path/to/inventory.json"""
import argparse
import json
import sys
from pathlib import Path

from .planner import InputError, plan_recycling


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline RotMG item-dismantling suggestion (never controls the game)."
    )
    parser.add_argument("input", type=Path, help="JSON inventory and material requirements")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = plan_recycling(payload)
    except (OSError, ValueError, InputError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["possible"] else 2


if __name__ == "__main__":
    sys.exit(main())
