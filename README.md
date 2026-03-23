# Pine Script Validator

A Python toolkit for parsing, validating, and auditing TradingView Pine Script files.

`Pine Script Validator` is designed for local analysis of `.pine` scripts. It provides syntax diagnostics, semantic validation, and repository-scale audit reporting to help catch common issues early and understand where unsupported or ambiguous Pine patterns still exist.

## Why This Project Exists

Pine Script tooling outside TradingView is limited. This project aims to make Pine scripts easier to inspect programmatically by providing:

- A Python parser for Pine Script
- Human-readable diagnostics with source locations
- Validation against bundled Pine Script v6 metadata
- Auditing tools for large collections of scripts

It is especially useful for offline validation, static analysis experiments, migration work, corpus cleanup, and building higher-level Pine tooling on top of a Python codebase.

## Features

- Pure Python lexer and parser for Pine Script
- Line and column diagnostics for parse and validation errors
- Validation of built-in functions and namespaces using bundled Pine v6 metadata
- Semantic checks for:
  - duplicate definitions
  - undefined names
  - invalid named arguments
  - unused variables
  - stateful calls inside conditional scopes
- CLI for validating individual `.pine` files
- Audit command for scanning script corpora and generating JSON and Markdown reports

## Installation

Create a virtual environment and install the project in editable mode:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

## Quick Start

Validate a single file:

```powershell
pine-validator path\to\script.pine
```

Read from standard input:

```powershell
Get-Content path\to\script.pine | python -m pinescript_validator.cli -
```

Emit diagnostics as JSON:

```powershell
pine-validator path\to\script.pine --json
```

## Example

Input:

```pine
indicator("Example")
value = close
plot(close, invalid_param=true)
```

Possible output:

```text
path\to\script.pine:3:13: error: Invalid parameter 'invalid_param' for 'plot'
path\to\script.pine:2:1: hint: Variable 'value' is declared but never used.
```

## Audit Mode

The audit command scans one or more script roots, compares observed usage against local docs and bundled metadata, and writes summary reports.

Run with default paths:

```powershell
python -m pinescript_validator.audit
```

Run with explicit script and docs roots:

```powershell
python -m pinescript_validator.audit --scripts-root ..\ExternalScripts --docs-root ..\PineTool\pinescript_docs
```

Generated outputs:

- `smart_audit_report.json`
- `smart_audit_report.md`

Audit reports are useful for:

- spotting recurring parser gaps
- identifying noisy diagnostics
- comparing local docs coverage against metadata
- finding common built-in usage patterns
- surfacing permissive instance-method hotspots

## CLI Behavior

Exit codes:

- `0` when validation completes without error-level diagnostics
- `1` when at least one error-level diagnostic is reported

## Development

Run the test suite:

```powershell
python -m pytest -q
```

Project layout:

```text
src/pinescript_validator/   Core parser, validator, CLI, and audit modules
tests/                      Regression and feature tests
pyproject.toml              Packaging and pytest configuration
```

## Current Scope

This project already covers a large set of Pine Script syntax and validation scenarios, but it is still an evolving local validator rather than a full TradingView-compatible runtime.

Current focus areas include:

- parsing modern Pine syntax patterns
- validating names and arguments using bundled metadata
- improving diagnostics quality
- reducing false positives on real-world scripts

## Limitations

- It does not execute Pine Script
- It is not a replacement for TradingView's runtime behavior
- Some edge cases and undocumented language patterns may still require additional parser or validator work
- Validation quality depends partly on the bundled metadata and the currently implemented semantic rules

## Roadmap

- Improve support for additional real-world Pine edge cases
- Expand semantic analysis coverage
- Improve documentation and examples
- Continue reducing noisy or overly permissive diagnostics

## License

MIT. See [LICENSE](LICENSE).
