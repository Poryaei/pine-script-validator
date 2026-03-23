# Contributing

Thanks for contributing to `pine-script-validator`.

If you find a bug, false positive, missing Pine Script v6 feature, or an unclear diagnostic, please open an issue in the [GitHub Issues](https://github.com/Poryaei/pine-script-validator/issues) section first when possible.

## Development Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m pytest -q
```

## What Helps Most

- regression tests for real-world Pine edge cases
- parser and validator fixes that reduce false positives
- improved diagnostics for agent-driven debugging workflows
- documentation improvements and practical examples

## Pull Request Guidelines

- keep changes focused
- add or update tests for behavioral changes
- preserve existing CLI behavior unless the change is intentional and documented
- update README when user-facing functionality changes

## Diagnostics Philosophy

- errors should point to concrete breakage
- warnings should indicate risky or consistency-sensitive behavior
- hints should stay useful and avoid becoming noise

If you are unsure whether a diagnostic should be an error, warning, or hint, open an issue or describe the tradeoff in your pull request.
