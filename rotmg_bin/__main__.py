"""Run offline quotes via: python -m rotmg_bin path/to/exchange.json"""
import argparse
import json
import sys
from pathlib import Path

from .exchange import QuoteInputError, quote_exchange


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline RotMG Bin trade-in quote")
    parser.add_argument("input", type=Path, help="JSON offer, price book, and bin stock")
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.input.read_text(encoding="utf-8"))
        quote = quote_exchange(request)
    except (OSError, ValueError, QuoteInputError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(quote, indent=2, sort_keys=True))
    return 0 if quote["status"] == "quoted" else 2


if __name__ == "__main__":
    sys.exit(main())
