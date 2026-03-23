from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

from .diagnostics import Severity
from .sarif import build_sarif_run
from .validator import PineScriptValidator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Pine Script files with the Python port of the local VS Code extension.")
    parser.add_argument("paths", nargs="+", help="Path(s), directories, glob patterns, or - to read from stdin")
    parser.add_argument("--json", action="store_true", help="Print diagnostics as JSON")
    parser.add_argument(
        "--agent-json",
        action="store_true",
        help="Print a structured report with summaries, snippets, and suggested next steps for agents and automation.",
    )
    parser.add_argument(
        "--sarif",
        action="store_true",
        help="Print SARIF output for CI, code scanning, and machine-readable review tooling.",
    )
    return parser


def _expand_paths(values: list[str]) -> list[Path]:
    expanded: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        matched = [Path(path) for path in glob.glob(value)]
        candidates = matched or [Path(value)]
        for candidate in candidates:
            if candidate.is_dir():
                files = sorted(candidate.rglob("*.pine"))
            elif candidate.is_file() and candidate.suffix.lower() == ".pine":
                files = [candidate]
            else:
                files = []
            for file_path in files:
                resolved = file_path.resolve()
                if resolved not in seen:
                    expanded.append(resolved)
                    seen.add(resolved)
    return expanded


def _validate_file_targets(validator: PineScriptValidator, paths: list[Path]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for file_path in paths:
        text = file_path.read_text(encoding="utf-8-sig")
        diagnostics = validator.validate_text(text)
        results.append(
            {
                "path": file_path,
                "text": text,
                "diagnostics": diagnostics,
            }
        )
    return results


def _summary(results: list[dict[str, object]]) -> dict[str, int]:
    diagnostics = [diagnostic for item in results for diagnostic in item["diagnostics"]]
    return {
        "files": len(results),
        "total": len(diagnostics),
        "error": sum(1 for item in diagnostics if item.severity == Severity.ERROR),
        "warning": sum(1 for item in diagnostics if item.severity == Severity.WARNING),
        "information": sum(1 for item in diagnostics if item.severity == Severity.INFORMATION),
        "hint": sum(1 for item in diagnostics if item.severity == Severity.HINT),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validator = PineScriptValidator()
    if sum(1 for flag in (args.json, args.agent_json, args.sarif) if flag) > 1:
        raise SystemExit("Choose only one of --json, --agent-json, or --sarif.")

    if "-" in args.paths:
        if len(args.paths) != 1:
            raise SystemExit("Standard input mode cannot be combined with file, directory, or glob targets.")
        text = sys.stdin.read()
        diagnostics = validator.validate_text(text)
        file_path = None
        results = [{"path": file_path, "text": text, "diagnostics": diagnostics}]
    else:
        file_paths = _expand_paths(args.paths)
        if not file_paths:
            raise SystemExit("No .pine files matched the provided targets.")
        results = _validate_file_targets(validator, file_paths)
        file_path = results[0]["path"] if len(results) == 1 else None
        text = results[0]["text"] if len(results) == 1 else ""
        diagnostics = results[0]["diagnostics"] if len(results) == 1 else []

    if args.sarif:
        print(json.dumps(build_sarif_run(results), ensure_ascii=False, indent=2))
    elif args.agent_json and len(results) > 1:
        file_reports = [
            validator.build_agent_report_for_text(item["text"], file_path=item["path"])
            for item in results
        ]
        print(
            json.dumps(
                {
                    "tool": "pine-script-validator",
                    "mode": "agent-batch",
                    "ok": all(report["ok"] for report in file_reports),
                    "summary": _summary(results),
                    "files": file_reports,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.agent_json:
        print(json.dumps(validator.build_agent_report_for_text(text, file_path=file_path), ensure_ascii=False, indent=2))
    elif args.json and len(results) > 1:
        print(
            json.dumps(
                {
                    "tool": "pine-script-validator",
                    "mode": "json-batch",
                    "summary": _summary(results),
                    "files": [
                        {
                            "path": str(item["path"]),
                            "diagnostics": [diagnostic.to_dict() for diagnostic in item["diagnostics"]],
                        }
                        for item in results
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.json:
        print(json.dumps([diagnostic.to_dict() for diagnostic in diagnostics], ensure_ascii=False, indent=2))
    else:
        any_output = False
        for item in results:
            path = item["path"]
            file_diagnostics = item["diagnostics"]
            if file_diagnostics:
                any_output = True
                for diagnostic in file_diagnostics:
                    print(diagnostic.format(path))
        if not any_output:
            print("No diagnostics.")

    return 1 if any(diagnostic.severity == Severity.ERROR for item in results for diagnostic in item["diagnostics"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
