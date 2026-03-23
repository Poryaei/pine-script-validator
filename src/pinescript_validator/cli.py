from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .diagnostics import Severity
from .validator import PineScriptValidator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Pine Script files with the Python port of the local VS Code extension.")
    parser.add_argument("path", help="Path to a .pine file, or - to read from stdin")
    parser.add_argument("--json", action="store_true", help="Print diagnostics as JSON")
    parser.add_argument(
        "--agent-json",
        action="store_true",
        help="Print a structured report with summaries, snippets, and suggested next steps for agents and automation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validator = PineScriptValidator()

    if args.path == "-":
        text = sys.stdin.read()
        diagnostics = validator.validate_text(text)
        file_path = None
    else:
        file_path = Path(args.path)
        text = file_path.read_text(encoding="utf-8")
        diagnostics = validator.validate_text(text)

    if args.agent_json:
        print(json.dumps(validator.build_agent_report_for_text(text, file_path=file_path), ensure_ascii=False, indent=2))
    elif args.json:
        print(json.dumps([diagnostic.to_dict() for diagnostic in diagnostics], ensure_ascii=False, indent=2))
    else:
        if diagnostics:
            for diagnostic in diagnostics:
                print(diagnostic.format(file_path))
        else:
            print("No diagnostics.")

    return 1 if any(diagnostic.severity == Severity.ERROR for diagnostic in diagnostics) else 0


if __name__ == "__main__":
    raise SystemExit(main())
