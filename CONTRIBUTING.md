# Contributing to vii

Thanks for your interest in contributing! This document covers how to set up
a development environment, run tests/linters, and how releases are versioned
and cut.

## Development Setup

Clone the repo and install in editable mode with dev dependencies:

```bash
git clone https://github.com/aclark4life/vii
cd vii
pip install -e ".[dev]"
```

Or, if you use [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev
```

## Running the App

```bash
vii
```

Or with Textual's development console for live logging while iterating:

```bash
textual console
textual run --dev src/vii/app.py
```

## Running Tests

```bash
pytest
```

Or with uv:

```bash
uv run pytest
```

## Linting & Formatting

This project uses [ruff](https://docs.astral.sh/ruff/) for linting/formatting
and [mypy](https://mypy-lang.org/) for type checking.

```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/ --ignore-missing-imports --no-strict-optional
```

### Pre-commit hooks

Pre-commit hooks run ruff, mypy, and a few hygiene checks (trailing
whitespace, merge conflict markers, etc.) automatically before each commit:

```bash
pre-commit install
```

CI runs `pre-commit run --all-files` and the test suite on every push and
pull request (see `.github/workflows/ci.yml`).

## Changelog

User-facing changes (features, fixes, removals) should be recorded under
`## [Unreleased]` in `CHANGELOG.md`, following the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format
(`### Added`, `### Changed`, `### Fixed`, `### Removed`, etc.).

## Versioning & Releases

vii is currently pre-1.0 and follows this convention for alpha releases:

- Each release bumps the version number itself (patch or minor), and the
  alpha suffix stays at `a1` unless a fix is needed for that same version
  (e.g. `v0.2.0a1`, `v0.2.1a1`, `v0.2.2a1`, ...).
- Prefer a **minor** bump (`0.X.0a1`) when a release includes new
  user-facing features, and a **patch** bump (`0.X.Ya1`) for small
  fixes/tweaks with no new features.
- Once the project is stable enough for a non-alpha release, drop the `aN`
  suffix entirely (e.g. `0.1.0`).

To cut a release:

1. Move the relevant entries from `## [Unreleased]` in `CHANGELOG.md` into a
   new `## [X.Y.Za1] - YYYY-MM-DD` section, and update the compare links at
   the bottom of the file.
2. Bump `version` in `pyproject.toml` to match.
3. Run `uv lock` (if using uv) so `uv.lock` picks up the new version.
4. Commit as `Prepare release vX.Y.Za1`.
5. Tag the commit: `git tag vX.Y.Za1`.
6. Push both: `git push origin main && git push origin vX.Y.Za1`.

Pushing a `v*` tag triggers `.github/workflows/workflow.yml`, which builds
the package and publishes it to PyPI automatically.

## Pull Requests

- Keep changes focused and include tests for new behavior.
- Make sure `pytest`, `ruff check`, and `mypy` all pass before opening a PR.
- Update `CHANGELOG.md` and relevant docs (e.g. `README.md`) alongside
  user-facing changes.

## License

By contributing, you agree that your contributions will be licensed under
the project's MIT License.
