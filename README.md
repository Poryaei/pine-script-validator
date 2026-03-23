# Pine Script Validator

Agent-friendly validation and debugging toolkit for TradingView Pine Script.

`Pine Script Validator` helps humans and coding agents inspect `.pine` files locally, catch syntax and semantic problems, and turn raw diagnostics into actionable debugging output. The project is built for workflows where an agent needs to read a Pine script, understand what failed, and decide what to fix next.

## What It Solves

Debugging Pine Script outside TradingView is awkward, especially for automated workflows. Agents typically need:

- a local parser they can run repeatedly
- machine-readable diagnostics
- enough source context to propose a fix
- stable output they can feed into a retry loop

This project focuses on exactly that.

## Core Capabilities

- Parse Pine Script with a pure Python lexer and parser
- Validate built-in functions and namespaces using bundled Pine v6 metadata
- Report syntax, semantic, warning, and hint diagnostics with source positions
- Emit standard JSON diagnostics for tooling integration
- Emit agent-oriented JSON reports with:
  - per-diagnostic line excerpts
  - visual pointers to the failing span
  - suggested remediation guidance
  - summary counts and next-step hints
- Validate multiple files or directories in one command
- Emit SARIF output for CI pipelines, review bots, and code scanning tools
- Audit large script corpora and generate JSON and Markdown reports

## Best Fit Use Cases

- letting agents debug Pine scripts inside local coding workflows
- validating generated Pine code before shipping it elsewhere
- regression testing parser support against real-world scripts
- scanning Pine corpora to find unsupported syntax patterns
- building higher-level Pine tooling on top of Python

## Installation

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

## Quick Start

Validate a file in human-readable mode:

```powershell
pine-validator path\to\script.pine
```

Emit plain JSON diagnostics:

```powershell
pine-validator path\to\script.pine --json
```

Emit agent-oriented debugging output:

```powershell
pine-validator path\to\script.pine --agent-json
```

Validate an entire directory of Pine files:

```powershell
pine-validator path\to\pine-scripts --agent-json
```

Emit SARIF for CI or review tooling:

```powershell
pine-validator path\to\pine-scripts --sarif
```

Validate from stdin:

```powershell
Get-Content path\to\script.pine | python -m pinescript_validator.cli - --agent-json
```

## Agent Debugging Workflow

Recommended loop for an agent:

1. Run `pine-validator script.pine --agent-json`
2. Read `summary.error` first and fix hard failures before hints
3. Use each diagnostic's `excerpt`, `pointer`, and `suggestion` fields to prepare the next code edit
4. Re-run validation after every edit until `ok` becomes `true`

The `--agent-json` mode is designed to reduce guesswork in automated debugging loops.

For larger agent workflows, you can point the CLI at a directory and let the agent process the batch report file by file.

## Example Agent Output

Input:

```pine
indicator("Example")
value = close
plot(close, invalid_param=true)
```

Command:

```powershell
pine-validator example.pine --agent-json
```

Output shape:

```json
{
  "tool": "pine-script-validator",
  "mode": "agent",
  "path": "example.pine",
  "ok": false,
  "summary": {
    "total": 2,
    "error": 1,
    "warning": 0,
    "information": 0,
    "hint": 1
  },
  "diagnostics": [
    {
      "line": 3,
      "column": 13,
      "severity": "error",
      "message": "Invalid parameter 'invalid_param' for 'plot'",
      "excerpt": "plot(close, invalid_param=true)",
      "pointer": "            ^",
      "suggestion": "Check the target function signature and remove, rename, or relocate unsupported named arguments."
    }
  ],
  "next_steps": [
    "Fix all error diagnostics first, then re-run validation to expose any follow-up semantic issues."
  ]
}
```

## CLI Modes

`pine-validator` currently supports:

- default text output for humans
- `--json` for plain machine-readable diagnostics
- `--agent-json` for richer debugging output intended for agents and automation
- directory and multi-file batch validation
- `--sarif` for CI, code scanning, and external review integrations

Exit codes:

- `0` when no error-level diagnostics are present
- `1` when at least one error-level diagnostic is reported

## Audit Mode

The audit command scans one or more script roots, compares observed Pine usage against bundled metadata and local documentation, and writes report files for broader maintenance work.

Run with default paths:

```powershell
python -m pinescript_validator.audit
```

Run with explicit roots:

```powershell
python -m pinescript_validator.audit --scripts-root ..\ExternalScripts --docs-root ..\PineTool\pinescript_docs
```

Generated outputs:

- `smart_audit_report.json`
- `smart_audit_report.md`

Audit mode is useful when you want to improve the validator itself, not just debug one script.

## Development

Run the tests:

```powershell
python -m pytest -q
```

Project layout:

```text
src/pinescript_validator/   Parser, validator, CLI, audit, and agent-report modules
tests/                      Regression and feature tests
pyproject.toml              Packaging and pytest configuration
```

## Current Scope

This project is a validator and static analysis tool, not a Pine runtime.

It currently focuses on:

- practical parser coverage for real Pine scripts
- useful diagnostics for local debugging
- machine-readable output for agents and tooling
- ongoing reduction of false positives and noisy hints

## Limitations

- It does not execute Pine Script or simulate TradingView runtime behavior
- Some undocumented or rare Pine patterns may still need parser support
- Suggested remediation text in `--agent-json` is heuristic guidance, not a guaranteed autofix
- Validation quality depends on the bundled metadata and implemented semantic rules

## Roadmap

- Improve structured diagnostics for more Pine-specific failure modes
- Expand semantic coverage for advanced script patterns
- Add more regression cases from real-world Pine scripts
- Keep improving agent-oriented debugging ergonomics

## License

MIT. See [LICENSE](LICENSE).
