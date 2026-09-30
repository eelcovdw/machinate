# Contributing

## Setup

Python 3.14 and [`uv`](https://docs.astral.sh/uv/). A Makefile wraps the usual
commands:

```bash
make setup   # uv sync
make lint    # ruff check, ruff format --check, basedpyright
make test    # pytest
```

Code conventions (layering, typing, naming, tests) are in [AGENTS.md](AGENTS.md).

## Releasing

Publishing a GitHub release runs `.github/workflows/release.yml`, which checks that the tag
matches the package version, builds, smoke-tests the wheel, and uploads to PyPI through
trusted publishing. Merges and pushes don't publish anything.

```bash
uv version --bump minor              # or patch / major; updates pyproject.toml and uv.lock
git commit -am "Release v$(uv version --short)"
git push                             # or merge it through a PR
git tag "v$(uv version --short)" && git push origin "v$(uv version --short)"
gh release create "v$(uv version --short)" --generate-notes
```
